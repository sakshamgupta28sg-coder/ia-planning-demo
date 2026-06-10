from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from dummy_data import (
    WP_DATA, HIERARCHIES, CHANNELS, FISCAL_WEEKS, CURRENT_WEEK, CATEGORIES,
    get_agg_rows, apply_edit, reset_overrides, save_snapshot, restore_snapshot, delete_snapshot,
    rename_snapshot, get_all_snapshots, apply_top_down, preview_top_down,
    get_effective_metrics, update_sku_setting, EDITABLE_SKU_FIELDS,
    get_target_wos, update_channel_target_wos, reset_channel_target_wos, _CHANNEL_TARGET_WOS,
    clear_single_override, accept_recomm_receipts, shift_receipts,
    compare_snapshots, get_exceptions_panel,
    get_budget, set_budget, get_audit_log, get_season_progress,
)

router = APIRouter(prefix="/wp", tags=["working-plan"])

EDITABLE_FIELDS = {"written_sales_units", "written_sales_dollars", "on_order_placed_total_unit", "written_dr_perc"}


# ── Filters ───────────────────────────────────────────────────────────────────
@router.get("/filters")
def get_filters():
    planning_start = next((w for w in FISCAL_WEEKS if w > CURRENT_WEEK), None)
    return {
        "hierarchies": HIERARCHIES,
        "channels": CHANNELS,
        "weeks": FISCAL_WEEKS,
        "categories": CATEGORIES,
        "current_week": CURRENT_WEEK,
        "planning_start_week": planning_start,
    }


# ── By-week aggregation (supports portfolio + filtered view) ──────────────────
@router.get("/by-week")
def get_wp_by_week(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    week_from: Optional[int] = None,
    week_to: Optional[int] = None,
):
    rows = get_agg_rows(hierarchy_code, channel)
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
    baseline: bool = False,
):
    if baseline:
        rows = [
            {"written_sales_units": r["written_sales_units"],
             "written_sales_dollars": r["written_sales_dollars"],
             "written_gm_dollar": r["written_gm_dollar"],
             "written_gm_perc": r["written_gm_perc"]}
            for r in WP_DATA
            if (not hierarchy_code or r["hierarchy_code"] == hierarchy_code)
            and (not channel or r["channel"] == channel)
        ]
    else:
        rows = get_agg_rows(hierarchy_code, channel)

    if not rows:
        return {}
    total_u = sum(r["written_sales_units"] for r in rows)
    total_d = round(sum(r["written_sales_dollars"] for r in rows), 2)
    total_g = round(sum(r["written_gm_dollar"] for r in rows), 2)
    return {
        "total_written_sales_units":   total_u,
        "total_written_sales_dollars": total_d,
        "total_written_gm_dollar":     total_g,
        "avg_written_gm_perc": round(total_g / total_d if total_d else 0, 4),
    }


# ── Portfolio breakdown (per hierarchy) ───────────────────────────────────────
@router.get("/portfolio")
def get_portfolio():
    all_rows = get_agg_rows()
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
            }
        per_hc[hc]["written_sales_units"]   += r["written_sales_units"]
        per_hc[hc]["written_sales_dollars"]  = round(per_hc[hc]["written_sales_dollars"] + r["written_sales_dollars"], 2)
        per_hc[hc]["written_gm_dollar"]      = round(per_hc[hc]["written_gm_dollar"]      + r["written_gm_dollar"], 2)
        if r["_modified"]:
            per_hc[hc]["_modified"] = True
        # Collect coverage values from planning weeks for exception flagging
        if not r.get("actualised") and not r.get("is_ongoing"):
            cov = r.get("fwd_coverage_wks") if r.get("fwd_coverage_wks") is not None else r.get("wos")
            if cov is not None:
                per_hc[hc]["_planning_coverages"].append(cov)

    for b in per_hc.values():
        td = b["written_sales_dollars"]
        b["avg_gm_perc"] = round(b["written_gm_dollar"] / td, 4) if td else 0

        # Derive exception status from worst planning-week coverage vs lead time
        covs = b.pop("_planning_coverages")
        if covs:
            hc    = b["hierarchy_code"]
            lt    = get_effective_metrics(hc)["lead_time_weeks"]
            mn    = min(covs)
            mx    = max(covs)
            if mn < lt * 0.5:
                status = "critical"
            elif mn < lt:
                status = "low"
            elif mx > lt * 3:
                status = "excess"
            else:
                status = "ok"
            b["exception_status"]   = status
            b["min_coverage_wks"]   = round(mn, 1)
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
    value: int = Field(ge=1)


@router.put("/sku-settings/{hierarchy_code}")
def put_sku_setting(hierarchy_code: int, body: SKUSettingRequest):
    if body.field not in EDITABLE_SKU_FIELDS:
        raise HTTPException(400, f"'{body.field}' not editable. Allowed: {EDITABLE_SKU_FIELDS}")
    try:
        effective = update_sku_setting(hierarchy_code, body.field, body.value)
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
    if body.field == "on_order_placed_total_unit" and raw.get("oo_locked"):
        raise HTTPException(403, f"Week {body.current_week} OO Placed is locked — order would arrive after season end")
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
    )
    return {"applied": count, "current_week": CURRENT_WEEK}


# ── Bulk receipt shift ────────────────────────────────────────────────────────
class BulkShiftRequest(BaseModel):
    hierarchy_codes: list
    channels: list
    shift_weeks: int = Field(description="Positive = push later, negative = pull earlier")


@router.post("/bulk-shift")
def bulk_shift(body: BulkShiftRequest):
    """Shift all OO Placed receipts for given SKUs×channels by N fiscal weeks."""
    if body.shift_weeks == 0:
        return {"shifted": 0, "dropped": 0}
    result = shift_receipts(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
        body.shift_weeks,
    )
    return result


# ── Accept Recomm ─────────────────────────────────────────────────────────────
class AcceptRecommRequest(BaseModel):
    hierarchy_codes: list
    channels: list


@router.post("/accept-recomm")
def accept_recomm(body: AcceptRecommRequest):
    """Set OO Placed = Recomm Receipt for all planning weeks of the given SKUs×channels."""
    count = accept_recomm_receipts(
        [int(hc) for hc in body.hierarchy_codes],
        list(body.channels),
    )
    return {"applied": count}


# ── Exception panel ───────────────────────────────────────────────────────────
@router.get("/exceptions")
def get_exceptions():
    """All planning-week rows with non-ok coverage status, for the exception panel."""
    return get_exceptions_panel()


# ── Audit log ─────────────────────────────────────────────────────────────────
@router.get("/audit")
def get_audit(limit: int = 100, hierarchy_code: Optional[int] = None, field: Optional[str] = None):
    """Most-recent cell edits, newest first. Optional SKU and field filters."""
    return get_audit_log(min(limit, 500), hierarchy_code=hierarchy_code, field=field)


# ── OTB Budget ────────────────────────────────────────────────────────────────
class BudgetRequest(BaseModel):
    budget: float = Field(ge=0)


@router.get("/budget")
def read_budget():
    return get_budget()


@router.put("/budget")
def write_budget(body: BudgetRequest):
    return set_budget(body.budget)


# ── Snapshots ─────────────────────────────────────────────────────────────────
class SnapshotRequest(BaseModel):
    name: str


@router.get("/snapshots/compare")
def snapshot_compare(a: int, b: int):
    """Side-by-side week-level comparison. b=0 means current live plan."""
    result = compare_snapshots(a, b)
    if not result:
        raise HTTPException(404, "Snapshot A not found")
    return result


@router.get("/season-progress")
def season_progress():
    """Actualized-to-date vs full-year plan — season pace KPI."""
    return get_season_progress()


@router.get("/snapshots")
def list_snapshots():
    return get_all_snapshots()


@router.post("/snapshots")
def create_snapshot(body: SnapshotRequest):
    if not body.name.strip():
        raise HTTPException(400, "Snapshot name is required")
    return save_snapshot(body.name.strip())


@router.put("/snapshots/{snap_id}/restore")
def restore(snap_id: int):
    ok = restore_snapshot(snap_id)
    if not ok:
        raise HTTPException(404, "Snapshot not found")
    return {"restored": snap_id}


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
