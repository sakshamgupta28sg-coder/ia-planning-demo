from fastapi import APIRouter
from typing import Optional
from dummy_data import TY_LY_DATA

router = APIRouter(prefix="/ty-ly", tags=["ty-ly"])


@router.get("/")
def get_ty_ly(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    week_from: Optional[int] = None,
    week_to: Optional[int] = None,
):
    rows = TY_LY_DATA
    if hierarchy_code:
        rows = [r for r in rows if r["hierarchy_code"] == hierarchy_code]
    if channel:
        rows = [r for r in rows if r["channel"] == channel]
    if week_from:
        rows = [r for r in rows if r["current_week"] >= week_from]
    if week_to:
        rows = [r for r in rows if r["current_week"] <= week_to]
    return rows


@router.get("/by-week")
def get_ty_ly_by_week(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    week_from: Optional[int] = None,
    week_to: Optional[int] = None,
):
    rows = get_ty_ly(hierarchy_code, channel, week_from, week_to)
    weeks: dict = {}
    for r in rows:
        wk = r["current_week"]
        if wk not in weeks:
            weeks[wk] = {
                "current_week": wk,
                "ty_units": 0, "ly_units": 0,
                "ty_dollars": 0.0, "ly_dollars": 0.0,
            }
        weeks[wk]["ty_units"] += r["ty_units"]
        weeks[wk]["ly_units"] += r["ly_units"]
        weeks[wk]["ty_dollars"] = round(weeks[wk]["ty_dollars"] + r["ty_dollars"], 2)
        weeks[wk]["ly_dollars"] = round(weeks[wk]["ly_dollars"] + r["ly_dollars"], 2)
    result = []
    for wk, w in sorted(weeks.items()):
        var_u = w["ty_units"] - w["ly_units"]
        var_d = round(w["ty_dollars"] - w["ly_dollars"], 2)
        result.append({
            **w,
            "units_var": var_u,
            "units_var_perc": round(var_u / w["ly_units"] if w["ly_units"] else 0, 4),
            "dollars_var": var_d,
            "dollars_var_perc": round(var_d / w["ly_dollars"] if w["ly_dollars"] else 0, 4),
        })
    return result


@router.get("/summary")
def get_ty_ly_summary(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
):
    rows = get_ty_ly(hierarchy_code, channel)
    if not rows:
        return {}
    ty_u = sum(r["ty_units"] for r in rows)
    ly_u = sum(r["ly_units"] for r in rows)
    ty_d = round(sum(r["ty_dollars"] for r in rows), 2)
    ly_d = round(sum(r["ly_dollars"] for r in rows), 2)
    return {
        "ty_units": ty_u, "ly_units": ly_u,
        "ty_dollars": ty_d, "ly_dollars": ly_d,
        "units_var": ty_u - ly_u,
        "units_var_perc": round((ty_u - ly_u) / ly_u if ly_u else 0, 4),
        "dollars_var": round(ty_d - ly_d, 2),
        "dollars_var_perc": round((ty_d - ly_d) / ly_d if ly_d else 0, 4),
    }
