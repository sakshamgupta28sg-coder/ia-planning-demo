from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from dummy_data import (
    WP_DATA, HIERARCHIES, CHANNELS, FISCAL_WEEKS, CURRENT_WEEK, CATEGORIES,
    get_agg_rows, apply_edit, reset_overrides, save_snapshot, restore_snapshot, delete_snapshot,
    get_all_snapshots, apply_top_down,
)

router = APIRouter(prefix="/wp", tags=["working-plan"])

EDITABLE_FIELDS = {"written_sales_units", "written_sales_dollars", "on_order_placed_total_unit"}


# ── Filters ───────────────────────────────────────────────────────────────────
@router.get("/filters")
def get_filters():
    return {"hierarchies": HIERARCHIES, "channels": CHANNELS, "weeks": FISCAL_WEEKS, "categories": CATEGORIES}


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
                "on_order_unplaced_total_unit":0,
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
        w["on_order_unplaced_total_unit"] += r.get("on_order_unplaced_total_unit", 0)
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
        w["wos"] = round(w["eop_units"] / w["written_sales_units"], 2) if w["written_sales_units"] > 0 else 99.0
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
            }
        per_hc[hc]["written_sales_units"]   += r["written_sales_units"]
        per_hc[hc]["written_sales_dollars"]  = round(per_hc[hc]["written_sales_dollars"] + r["written_sales_dollars"], 2)
        per_hc[hc]["written_gm_dollar"]      = round(per_hc[hc]["written_gm_dollar"]      + r["written_gm_dollar"], 2)
        if r["_modified"]:
            per_hc[hc]["_modified"] = True

    for b in per_hc.values():
        td = b["written_sales_dollars"]
        b["avg_gm_perc"] = round(b["written_gm_dollar"] / td, 4) if td else 0

    return sorted(per_hc.values(), key=lambda x: x["hierarchy_code"])


# ── Edit row ──────────────────────────────────────────────────────────────────
class EditRequest(BaseModel):
    hierarchy_code: int
    current_week: int
    channel: str
    field: str
    value: float = Field(ge=0, description="Value must be non-negative")


@router.put("/row")
def edit_row(body: EditRequest):
    if body.field not in EDITABLE_FIELDS:
        raise HTTPException(400, f"'{body.field}' is not editable. Allowed: {EDITABLE_FIELDS}")
    result = apply_edit(body.hierarchy_code, body.current_week, body.channel, body.field, body.value)
    if not result:
        raise HTTPException(404, "Row not found")
    return result


@router.delete("/overrides")
def clear_overrides():
    reset_overrides()
    return {"reset": True}


# ── Top-down distribution ─────────────────────────────────────────────────────
class TopDownRequest(BaseModel):
    hierarchy_codes: list
    channels: list
    target: float = Field(gt=0, description="Total target to distribute across planning weeks")
    field: str = "written_sales_units"


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
    )
    return {"applied": count, "current_week": CURRENT_WEEK}


# ── Snapshots ─────────────────────────────────────────────────────────────────
class SnapshotRequest(BaseModel):
    name: str


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
