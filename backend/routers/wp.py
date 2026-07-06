from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict
from dummy_data import (
    WP_DATA, HIERARCHIES, CHANNELS, FISCAL_WEEKS, CURRENT_WEEK, CATEGORIES,
    get_agg_rows, apply_edit, reset_overrides, save_snapshot, restore_snapshot, delete_snapshot,
    rename_snapshot, get_all_snapshots, apply_top_down, undo_top_down, preview_top_down,
    get_effective_metrics, update_sku_setting, reset_sku_settings, EDITABLE_SKU_FIELDS,
    get_target_wos, update_channel_target_wos, reset_channel_target_wos, _CHANNEL_TARGET_WOS,
    clear_single_override, accept_recomm_receipts, undo_recomm_receipts, shift_receipts,
    compare_snapshots, get_exceptions_panel,
    get_budget, get_audit_log, get_season_progress,
    DEFAULT_YEAR, SELECTABLE_YEARS, _year_weeks, get_active_skus,
    get_master_catalog, set_sku_tag,
    get_placeholders, add_placeholder, delete_placeholder,
)

router = APIRouter(prefix="/wp", tags=["working-plan"])

EDITABLE_FIELDS = {"written_sales_units", "written_sales_dollars", "on_order_placed_total_unit", "written_dr_perc"}


# ── Filters ───────────────────────────────────────────────────────────────────
@router.get("/filters")
def get_filters(year: int = DEFAULT_YEAR):
    weeks = _year_weeks(year)
    planning_start = next((w for w in weeks if w > CURRENT_WEEK), None)
    active = set(get_active_skus(year))
    hierarchies = [h for h in HIERARCHIES if h["hierarchy_code"] in active]
    return {
        "hierarchies": hierarchies,
        "channels": CHANNELS,
        "weeks": weeks,
        "categories": CATEGORIES,
        "current_week": CURRENT_WEEK,
        "planning_start_week": planning_start,
        "year": year,
        "selectable_years": SELECTABLE_YEARS,
    }


# ── Master SKU catalog (read-only) ────────────────────────────────────────────
@router.get("/master-sku")
def master_sku_catalog():
    return get_master_catalog()


class TagRequest(BaseModel):
    tagged_to: Optional[int] = None


@router.put("/master-sku/{hierarchy_code}/tag")
def set_master_tag(hierarchy_code: int, body: TagRequest):
    if not set_sku_tag(hierarchy_code, body.tagged_to):
        raise HTTPException(404, "SKU not found in master catalog")
    return {"hierarchy_code": hierarchy_code, "tagged_to": body.tagged_to}


# ── Placeholders (what-if clones) ─────────────────────────────────────────────
class PlaceholderRequest(BaseModel):
    name: str
    source_hc: int


@router.get("/placeholders")
def list_placeholders():
    return get_placeholders()


@router.post("/placeholders")
def create_placeholder(body: PlaceholderRequest):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    return add_placeholder(body.name.strip(), body.source_hc)


@router.delete("/placeholders/{pid}")
def remove_placeholder(pid: int):
    if not delete_placeholder(pid):
        raise HTTPException(404, "Placeholder not found")
    return {"deleted": pid}


# A placeholder is now a real (hidden) synthetic SKU, so the placeholders page reads
# and edits it through the standard WP endpoints with hierarchy_code = placeholder_hc
# (e.g. GET /by-week, PUT /row, POST /accept-recomm). No dedicated plan endpoint needed.


# ── By-week aggregation (supports portfolio + filtered view) ──────────────────
@router.get("/by-week")
def get_wp_by_week(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    week_from: Optional[int] = None,
    week_to: Optional[int] = None,
    year: int = DEFAULT_YEAR,
):
    rows = get_agg_rows(hierarchy_code, channel, year=year)
    if week_from:
        rows = [r for r in rows if r["current_week"] >= week_from]
    if week_to:
        rows = [r for r in rows if r["current_week"] <= week_to]

    # When a specific hc+ch is selected, return per-week rows directly (already one per wk)
    if hierarchy_code and channel:
        return rows

    # Otherwise group by week
    weeks: dict = {}
    for r in rows:
        wk = r["current_week"]
        if wk not in weeks:
            weeks[wk] = {
                "current_week":                wk,
                "written_sales_units":         0,
                "written_sales_dollars":       0.0,
                "written_gm_dollar":           0.0,
                "written_sales_cost":          0.0,
                "written_auc":                 r.get("written_auc", 0.0),
                "written_aur":                 0.0,
                "written_gm_perc":             0.0,
                "bop_units":                   0,
                "eop_units":                   0,
                "total_receipt_units":         0,
                "recomm_receipt_units":        0,
                "on_order_placed_total_unit":  0,
                "actual_sales_units":          0,
                "actual_sales_dollars":        0.0,
                "actual_sales_cost":           0.0,
                "markdown_units":              0,
                "markdown_dollars":            0.0,
                "wos":                         0.0,
                "sell_through_perc":           0.0,
                "otb_units":                   0,
                "otb_dollars":                 0.0,
                "variance_units":              None,
                "variance_dollars":            None,
                "variance_units_perc":         None,
                "ly_sales_units":              0,
                "ly_sales_dollars":            0.0,
                "ly_units_var":                0,
                "ly_dollars_var":              0.0,
                "ly_units_var_perc":           0.0,
                "ly_dollars_var_perc":         0.0,
                "actualised":                  r.get("actualised", False),
                "is_ongoing":                  r.get("is_ongoing", False),
                # Not meaningful when aggregated across SKUs — only set at SKU×channel level
                "fwd_coverage_wks":            None,
                "lead_time_weeks":             None,
                "_modified":                   False,
            }
        w = weeks[wk]
        w["written_sales_units"]          += r["written_sales_units"]
        w["written_sales_dollars"]         = round(w["written_sales_dollars"]  + r["written_sales_dollars"], 2)
        w["written_gm_dollar"]             = round(w["written_gm_dollar"]      + r["written_gm_dollar"], 2)
        w["written_sales_cost"]            = round(w["written_sales_cost"]     + r["written_sales_cost"], 2)
        w["bop_units"]                    += r["bop_units"]
        w["eop_units"]                    += r["eop_units"]
        w["total_receipt_units"]          += r["total_receipt_units"]
        w["recomm_receipt_units"]         += r["recomm_receipt_units"]
        w["on_order_placed_total_unit"]   += r["on_order_placed_total_unit"]
        w["actual_sales_units"]           += r.get("actual_sales_units", 0)
        w["actual_sales_dollars"]          = round(w["actual_sales_dollars"] + r.get("actual_sales_dollars", 0.0), 2)
        w["actual_sales_cost"]             = round(w["actual_sales_cost"]    + r.get("actual_sales_cost", 0.0), 2)
        w["markdown_units"]               += r.get("markdown_units", 0)
        w["markdown_dollars"]              = round(w["markdown_dollars"]    + r.get("markdown_dollars", 0.0), 2)
        w["ly_sales_units"]               += r.get("ly_sales_units", 0)
        w["ly_sales_dollars"]              = round(w["ly_sales_dollars"]   + r.get("ly_sales_dollars", 0.0), 2)
        w["otb_units"]                    += r.get("otb_units", 0)
        w["otb_dollars"]                   = round(w["otb_dollars"]        + r.get("otb_dollars", 0.0), 2)
        if r["_modified"]:
            w["_modified"] = True

    # Derive remaining fields after aggregation
    for w in weeks.values():
        if w["written_sales_units"] > 0:
            w["written_aur"] = round(w["written_sales_dollars"] / w["written_sales_units"], 2)
        if w["written_sales_dollars"] > 0:
            w["written_gm_perc"] = round(w["written_gm_dollar"] / w["written_sales_dollars"], 4)
        # Portfolio WOS: simple EOP / this-week's-plan-units.
        # Intentionally different from SKU×Channel WOS (which uses 8wk forward avg)
        # because demand curves differ per SKU. Select a specific SKU+Channel for accurate WOS.
        w["wos"] = None if w.get("actualised") else (round(w["eop_units"] / w["written_sales_units"], 2) if w["written_sales_units"] > 0 else 99.0)
        avail = w["bop_units"] + w["total_receipt_units"]
        w["sell_through_perc"] = round(w["actual_sales_units"] / avail, 4) if avail > 0 and w.get("actualised") else 0.0
        if w.get("actualised") and w["written_sales_units"] > 0:
            w["variance_units"]      = w["written_sales_units"] - w["actual_sales_units"]
            w["variance_dollars"]    = round(w["written_sales_dollars"] - w["actual_sales_dollars"], 2)
            w["variance_units_perc"] = round(w["variance_units"] / w["written_sales_units"], 4)
        ly_u = w["ly_sales_units"]; ly_d = w["ly_sales_dollars"]
        w["ly_units_var"]        = w["written_sales_units"] - ly_u
        w["ly_dollars_var"]      = round(w["written_sales_dollars"] - ly_d, 2)
        w["ly_units_var_perc"]   = round(w["ly_units_var"]   / ly_u, 4) if ly_u > 0 else 0.0
        w["ly_dollars_var_perc"] = round(w["ly_dollars_var"] / ly_d, 4) if ly_d > 0 else 0.0

    return sorted(weeks.values(), key=lambda x: x["current_week"])


# ── Summary ───────────────────────────────────────────────────────────────────
@router.get("/summary")
def get_wp_summary(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    hierarchy_codes: Optional[str] = None,
    channels: Optional[str] = None,
    baseline: bool = False,
    year: int = DEFAULT_YEAR,
):
    hc_list = [int(x) for x in hierarchy_codes.split(",") if x.strip()] if hierarchy_codes else (
        [hierarchy_code] if hierarchy_code is not None else None
    )
    ch_list = [x.strip() for x in channels.split(",") if x.strip()] if channels else (
        [channel] if channel else None
    )

    # baseline=True → the *unedited* plan: the same engine recompute with the
    # planner's cell overrides (OO Placed / sales edits) stripped (_overrides_override={}).
    # This anchors the KPI delta to "your edits", so with zero edits current==baseline
    # and the delta reads 0. (Was: raw WP_DATA seed, which differs from the recompute
    # even at zero edits → a permanent, confusing standing delta.)
    ov = {} if baseline else None
    if hc_list and ch_list:
        rows = []
        for hc in hc_list:
            for ch in ch_list:
                rows.extend(get_agg_rows(hc, ch, _overrides_override=ov, year=year))
    elif hc_list:
        rows = []
        for hc in hc_list:
            rows.extend(get_agg_rows(hc, None, _overrides_override=ov, year=year))
    elif ch_list:
        rows = [r for r in get_agg_rows(_overrides_override=ov, year=year) if r["channel"] in ch_list]
    else:
        rows = get_agg_rows(_overrides_override=ov, year=year)

    if not rows:
        return {}
    total_u = sum(r["written_sales_units"] for r in rows)
    total_d = round(sum(r["written_sales_dollars"] for r in rows), 2)
    total_g = round(sum(r["written_gm_dollar"] for r in rows), 2)
    total_disc = round(sum(r.get("written_discount_dollars", 0) for r in rows), 2)
    total_cost = round(total_d - total_g, 2)            # COGS = revenue − GM
    gross = total_d + total_disc                         # units × AIR (pre-markdown)
    # Planned Receipts = stock actually arriving in-season (ingested + OOP that lands
    # by season end). This is the real inventory inflow — distinct from OO Placed,
    # which is just the order-placement schedule (an order placed late in the season
    # arrives off-grid and is never received here).
    total_rcpt = sum(r.get("total_receipt_units", 0) for r in rows)
    return {
        "total_written_sales_units":   total_u,
        "total_written_sales_dollars": total_d,
        "total_written_gm_dollar":     total_g,
        "avg_written_gm_perc": round(total_g / total_d if total_d else 0, 4),
        "total_written_discount_dollars": total_disc,
        "total_written_cost": total_cost,
        # Dollar-weighted avg discount % = markdown $ / gross $ (not a naive mean)
        "avg_written_disc_perc": round(total_disc / gross, 4) if gross else 0,
        "total_receipt_units": int(total_rcpt),
        # Blended pricing KPIs (avoid divide-by-zero)
        "avg_aur": round(total_d / total_u, 2) if total_u else 0,
        "avg_auc": round(total_cost / total_u, 2) if total_u else 0,
    }


# ── Portfolio breakdown (per hierarchy) ───────────────────────────────────────
@router.get("/portfolio")
def get_portfolio(year: int = DEFAULT_YEAR):
    all_rows = get_agg_rows(year=year)
    per_hc: dict = {}
    for r in all_rows:
        hc = r["hierarchy_code"]
        if hc not in per_hc:
            per_hc[hc] = {
                "hierarchy_code":      hc,
                "l1_name":             r["l1_name"],
                "l2_name":             r["l2_name"],
                "written_sales_units": 0,
                "written_sales_dollars": 0.0,
                "written_gm_dollar":   0.0,
                "_modified":           False,
                # Exception tracking (populated below)
                "_planning_coverages": [],
                "_has_stockout":       False,   # genuine unmet demand any planning wk
                "_has_stockout_in_lt": False,   # unmet demand within LT (unfixable now)
            }
        per_hc[hc]["written_sales_units"]   += r["written_sales_units"]
        per_hc[hc]["written_sales_dollars"]  = round(per_hc[hc]["written_sales_dollars"] + r["written_sales_dollars"], 2)
        per_hc[hc]["written_gm_dollar"]      = round(per_hc[hc]["written_gm_dollar"]      + r["written_gm_dollar"], 2)
        if r["_modified"]:
            per_hc[hc]["_modified"] = True
        # Collect signals from planning weeks. Status keys off the GENUINE-stockout
        # chain (real unmet demand) — which already excludes intentional end-of-season
        # runout — NOT raw coverage. Coverage min/max kept only for the displayed
        # number + excess (overstock) detection. This stops thin-but-planned tail
        # runout from false-flagging critical (e.g. Sandals).
        if not r.get("actualised"):
            cov = r.get("fwd_coverage_wks") if r.get("fwd_coverage_wks") is not None else r.get("wos")
            if cov is not None:
                per_hc[hc]["_planning_coverages"].append(cov)
            if r.get("_stockout"):
                per_hc[hc]["_has_stockout"] = True
            if r.get("_stockout_in_lt"):
                per_hc[hc]["_has_stockout_in_lt"] = True

    for b in per_hc.values():
        td = b["written_sales_dollars"]
        b["avg_gm_perc"] = round(b["written_gm_dollar"] / td, 4) if td else 0

        # Status from real unmet demand, not raw coverage:
        #   critical = stockout WITHIN lead time → can't fix by ordering now (too late)
        #   low      = genuine stockout, but beyond LT → still fixable by reordering
        #   excess   = no stockout, but holding > 3× lead time of cover (overstock)
        #   ok       = survives demand, sane cover
        # Terminal end-of-season runout is already excluded from the _stockout chain,
        # so planned drain-to-zero no longer trips critical.
        covs      = b.pop("_planning_coverages")
        has_so    = b.pop("_has_stockout", False)
        has_so_lt = b.pop("_has_stockout_in_lt", False)
        if covs:
            lt = get_effective_metrics(b["hierarchy_code"])["lead_time_weeks"]
            mx = max(covs)
            if has_so_lt:
                status = "critical"
            elif has_so:
                status = "low"
            elif mx > lt * 3:
                status = "excess"
            else:
                status = "ok"
            b["exception_status"]   = status
            b["min_coverage_wks"]   = round(min(covs), 1)
        else:
            b["exception_status"]   = "ok"
            b["min_coverage_wks"]   = None

    return sorted(per_hc.values(), key=lambda x: x["hierarchy_code"])


# ── SKU Settings ──────────────────────────────────────────────────────────────
@router.get("/sku-settings")
def get_sku_settings():
    """Return effective settings (base + overrides) for all SKUs."""
    return [
        {"hierarchy_code": h["hierarchy_code"], **get_effective_metrics(h["hierarchy_code"])}
        for h in HIERARCHIES
    ]


class SKUSettingRequest(BaseModel):
    field: str
    value: int = Field(ge=0)


@router.put("/sku-settings/{hierarchy_code}")
def put_sku_setting(hierarchy_code: int, body: SKUSettingRequest):
    if body.field not in EDITABLE_SKU_FIELDS:
        raise HTTPException(400, f"'{body.field}' not editable. Allowed: {EDITABLE_SKU_FIELDS}")
    try:
        effective = update_sku_setting(hierarchy_code, body.field, body.value)
    except KeyError:
        raise HTTPException(404, f"hierarchy_code {hierarchy_code} not found")
    return {"hierarchy_code": hierarchy_code, **effective}


@router.delete("/sku-settings/{hierarchy_code}")
def reset_sku_setting(hierarchy_code: int):
    """Reset all SKU settings (+ channel target WOS + recalibration receipts) to defaults."""
    try:
        effective = reset_sku_settings(hierarchy_code)
    except KeyError:
        raise HTTPException(404, f"hierarchy_code {hierarchy_code} not found")
    return {"hierarchy_code": hierarchy_code, **effective}


# ── Target WOS per SKU×Channel ───────────────────────────────────────────────
@router.get("/target-wos")
def get_all_target_wos():
    """Return target_wos for every SKU×channel combination.
    is_overridden=True means a channel-level override exists (show ✕ reset button).
    """
    result = []
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        for ch in CHANNELS:
            result.append({
                "hierarchy_code": hc,
                "channel": ch,
                "target_wos": get_target_wos(hc, ch),
                "is_overridden": f"{hc}_{ch}" in _CHANNEL_TARGET_WOS,
            })
    return result


class TargetWOSRequest(BaseModel):
    value: int = Field(ge=1)


@router.put("/target-wos/{hierarchy_code}/{channel}")
def put_target_wos(hierarchy_code: int, channel: str, body: TargetWOSRequest):
    if channel not in CHANNELS:
        raise HTTPException(400, f"Unknown channel '{channel}'. Valid: {CHANNELS}")
    effective = update_channel_target_wos(hierarchy_code, channel, body.value)
    return {"hierarchy_code": hierarchy_code, "channel": channel, "target_wos": effective}


@router.delete("/target-wos/{hierarchy_code}/{channel}")
def delete_target_wos(hierarchy_code: int, channel: str):
    """Remove channel-level target WOS override — falls back to SKU-level default."""
    if channel not in CHANNELS:
        raise HTTPException(400, f"Unknown channel '{channel}'. Valid: {CHANNELS}")
    effective = reset_channel_target_wos(hierarchy_code, channel)
    return {"hierarchy_code": hierarchy_code, "channel": channel, "target_wos": effective}


# ── Edit row ──────────────────────────────────────────────────────────────────
class EditRequest(BaseModel):
    hierarchy_code: int
    current_week: int
    channel: str
    field: str
    value: float = Field(ge=0, description="Value must be non-negative")
    mode: Optional[str] = None  # "hold_units" or "hold_dollars" — only used for written_dr_perc edits


@router.put("/row")
def edit_row(body: EditRequest):
    if body.field not in EDITABLE_FIELDS:
        raise HTTPException(400, f"'{body.field}' is not editable. Allowed: {EDITABLE_FIELDS}")
    if body.field == "written_dr_perc" and body.value > 1:
        raise HTTPException(400, "written_dr_perc must be between 0 and 1 (e.g. 0.15 for 15%)")
    # Guard: actualized (past) rows are locked — editing history corrupts the record
    raw = next(
        (r for r in WP_DATA
         if r["hierarchy_code"] == body.hierarchy_code
         and r["channel"] == body.channel
         and r["current_week"] == body.current_week),
        None,
    )
    if raw is None:
        raise HTTPException(404, "Row not found")
    if raw.get("actualised"):
        raise HTTPException(403, f"Week {body.current_week} is actualized and cannot be edited")
    # OO Placed tail-week lock is enforced dynamically inside apply_edit (raises
    # ValueError → 403 below) so it tracks runtime lead-time changes.
    try:
        result = apply_edit(body.hierarchy_code, body.current_week, body.channel, body.field, body.value, body.mode)
    except ValueError as e:
        raise HTTPException(403, str(e))
    if not result:
        raise HTTPException(404, "Row not found")
    return result


@router.delete("/overrides")
def clear_overrides():
    reset_overrides()
    return {"reset": True}


@router.delete("/overrides/{hierarchy_code}/{current_week}/{channel}")
def clear_row_override(hierarchy_code: int, current_week: int, channel: str):
    """Undo edits to a single week×SKU×channel cell — restores to baseline."""
    row = clear_single_override(hierarchy_code, current_week, channel)
    if not row:
        raise HTTPException(404, "Row not found")
    return row


# ── Top-down distribution ─────────────────────────────────────────────────────
class WeekValueItem(BaseModel):
    hierarchy_code: int
    channel: str
    current_week: int
    value: float


class TopDownRequest(BaseModel):
    hierarchy_codes: list
    channels: list
    target: float = Field(gt=0, description="Total target to distribute across planning weeks")
    field: str = "written_sales_units"
    week_values: Optional[list] = None  # list of WeekValueItem dicts — skips LY weight calc
    year: int = DEFAULT_YEAR


@router.post("/top-down/preview")
def top_down_preview(body: TopDownRequest):
    """Dry-run: returns proposed per-week values without writing to DB."""
    allowed = {"written_sales_units", "written_sales_dollars"}
    if body.field not in allowed:
        raise HTTPException(400, f"field must be one of {allowed}")
    return preview_top_down(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        body.target,
        body.field,
        year=body.year,
    )


@router.post("/top-down")
def top_down_distribute(body: TopDownRequest):
    allowed = {"written_sales_units", "written_sales_dollars"}
    if body.field not in allowed:
        raise HTTPException(400, f"field must be one of {allowed}")
    count = apply_top_down(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        body.target,
        body.field,
        week_values=body.week_values,
        year=body.year,
    )
    return {"applied": count, "current_week": CURRENT_WEEK}


class HcChannelRequest(BaseModel):
    hierarchy_codes: list
    channels: list
    year: int = DEFAULT_YEAR


@router.post("/top-down/undo")
def top_down_undo(body: HcChannelRequest):
    """Inverse of top-down: clear written-sales split (units + dollars) on planning weeks."""
    count = undo_top_down(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        year=body.year,
    )
    return {"cleared": count}


# ── Bulk receipt shift ────────────────────────────────────────────────────────
class BulkShiftRequest(BaseModel):
    hierarchy_codes: list
    channels: list
    shift_weeks: int = Field(description="Positive = push later, negative = pull earlier")
    year: int = DEFAULT_YEAR


@router.post("/bulk-shift")
def bulk_shift(body: BulkShiftRequest):
    """Shift all OO Placed receipts for given SKUs×channels by N fiscal weeks."""
    if body.shift_weeks == 0:
        return {"shifted": 0, "dropped": 0}
    result = shift_receipts(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        body.shift_weeks,
        year=body.year,
    )
    return result


# ── Accept Recomm ─────────────────────────────────────────────────────────────
class AcceptRecommRequest(BaseModel):
    hierarchy_codes: list
    channels: list
    year: int = DEFAULT_YEAR


@router.post("/accept-recomm")
def accept_recomm(body: AcceptRecommRequest):
    """Set OO Placed = Recomm Receipt for all planning weeks of the given SKUs×channels."""
    count = accept_recomm_receipts(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        year=body.year,
    )
    return {"applied": count}


@router.post("/undo-recomm")
def undo_recomm(body: AcceptRecommRequest):
    """Inverse of accept-recomm: clear OO Placed on planning weeks → recomm reappears."""
    count = undo_recomm_receipts(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        year=body.year,
    )
    return {"cleared": count}


# ── Exception panel ───────────────────────────────────────────────────────────
@router.get("/exceptions")
def get_exceptions(year: int = DEFAULT_YEAR):
    """All planning-week rows with non-ok coverage status, for the exception panel."""
    return get_exceptions_panel(year=year)


# ── Audit log ─────────────────────────────────────────────────────────────────
@router.get("/audit")
def get_audit(limit: int = 100, hierarchy_code: Optional[int] = None, field: Optional[str] = None):
    """Most-recent cell edits, newest first. Optional SKU and field filters."""
    return get_audit_log(min(limit, 500), hierarchy_code=hierarchy_code, field=field)


# ── OTB Budget ────────────────────────────────────────────────────────────────
@router.get("/budget")
def read_budget(
    hierarchy_codes: Optional[str] = None,
    channels: Optional[str] = None,
    year: int = DEFAULT_YEAR,
):
    hc_list = [int(x) for x in hierarchy_codes.split(",") if x.strip()] if hierarchy_codes else None
    ch_list = [x.strip() for x in channels.split(",") if x.strip()] if channels else None
    return get_budget(hc_list, ch_list, year=year)


# ── Snapshots ─────────────────────────────────────────────────────────────────
class SnapshotRequest(BaseModel):
    name: str
    view: Optional[Dict] = None   # UI filter selection at save time (hcs/channels/category/year)


@router.get("/snapshots/compare")
def snapshot_compare(a: int, b: int):
    """Side-by-side week-level comparison. b=0 means current live plan."""
    result = compare_snapshots(a, b)
    if not result:
        raise HTTPException(404, "Snapshot A not found")
    return result


@router.get("/season-progress")
def season_progress(hierarchy_codes: Optional[str] = None, channels: Optional[str] = None,
                    year: int = DEFAULT_YEAR):
    """Actualized-to-date vs full-year plan — season pace KPI."""
    hc_list = [int(x) for x in hierarchy_codes.split(",") if x.strip()] if hierarchy_codes else None
    ch_list = [x.strip() for x in channels.split(",") if x.strip()] if channels else None
    return get_season_progress(hc_list, ch_list, year=year)


@router.get("/snapshots")
def list_snapshots():
    return get_all_snapshots()


@router.post("/snapshots")
def create_snapshot(body: SnapshotRequest):
    if not body.name.strip():
        raise HTTPException(400, "Snapshot name is required")
    return save_snapshot(body.name.strip(), body.view)


@router.put("/snapshots/{snap_id}/restore")
def restore(snap_id: int):
    view = restore_snapshot(snap_id)
    if view is None:
        raise HTTPException(404, "Snapshot not found")
    return {"restored": snap_id, "view": view}


@router.delete("/snapshots/{snap_id}")
def remove_snapshot(snap_id: int):
    ok = delete_snapshot(snap_id)
    if not ok:
        raise HTTPException(404, "Snapshot not found")
    return {"deleted": snap_id}


class SnapshotRenameRequest(BaseModel):
    name: str


@router.patch("/snapshots/{snap_id}")
def patch_snapshot(snap_id: int, body: SnapshotRenameRequest):
    if not body.name.strip():
        raise HTTPException(400, "Name cannot be empty")
    ok = rename_snapshot(snap_id, body.name)
    if not ok:
        raise HTTPException(404, "Snapshot not found")
    return {"id": snap_id, "name": body.name.strip()}
