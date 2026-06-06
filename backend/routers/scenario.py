from fastapi import APIRouter
from typing import Optional
from dummy_data import SCENARIO_DATA

router = APIRouter(prefix="/scenario", tags=["scenario"])


@router.get("/")
def get_scenarios(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    scenario: Optional[int] = None,
    percent_off: Optional[float] = None,
):
    rows = SCENARIO_DATA
    if hierarchy_code:
        rows = [r for r in rows if r["hierarchy_code"] == hierarchy_code]
    if channel:
        rows = [r for r in rows if r["channel"] == channel]
    if scenario is not None:
        rows = [r for r in rows if r["scenario"] == scenario]
    if percent_off is not None:
        rows = [r for r in rows if abs(r["percent_off"] - percent_off) < 0.001]
    return rows


@router.get("/compare")
def compare_scenarios(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
):
    """Return aggregated metrics per scenario × percent_off combo."""
    rows = SCENARIO_DATA
    if hierarchy_code:
        rows = [r for r in rows if r["hierarchy_code"] == hierarchy_code]
    if channel:
        rows = [r for r in rows if r["channel"] == channel]

    buckets: dict = {}
    for r in rows:
        key = (r["scenario"], r["scenario_name"], r["percent_off"])
        if key not in buckets:
            buckets[key] = {
                "scenario": r["scenario"],
                "scenario_name": r["scenario_name"],
                "percent_off": r["percent_off"],
                "total_units": 0,
                "total_dollars": 0.0,
                "total_gm": 0.0,
            }
        buckets[key]["total_units"] += r["w_sls_u"]
        buckets[key]["total_dollars"] = round(buckets[key]["total_dollars"] + r["w_sls_dollars"], 2)
        buckets[key]["total_gm"] = round(buckets[key]["total_gm"] + r["w_gm_dollars"], 2)

    result = []
    for b in sorted(buckets.values(), key=lambda x: (x["scenario"], x["percent_off"])):
        b["avg_gm_perc"] = round(b["total_gm"] / b["total_dollars"] if b["total_dollars"] else 0, 4)
        result.append(b)
    return result


@router.get("/by-week")
def get_scenario_by_week(
    hierarchy_code: Optional[int] = None,
    channel: Optional[str] = None,
    scenario: Optional[int] = None,
    percent_off: Optional[float] = None,
):
    rows = get_scenarios(hierarchy_code, channel, scenario, percent_off)
    weeks: dict = {}
    for r in rows:
        wk = r["current_week"]
        key = (wk, r["scenario"], r["percent_off"])
        if key not in weeks:
            weeks[key] = {
                "current_week": wk,
                "scenario": r["scenario"],
                "scenario_name": r["scenario_name"],
                "percent_off": r["percent_off"],
                "total_units": 0,
                "total_dollars": 0.0,
                "total_gm": 0.0,
            }
        weeks[key]["total_units"] += r["w_sls_u"]
        weeks[key]["total_dollars"] = round(weeks[key]["total_dollars"] + r["w_sls_dollars"], 2)
        weeks[key]["total_gm"] = round(weeks[key]["total_gm"] + r["w_gm_dollars"], 2)
    return sorted(weeks.values(), key=lambda x: (x["current_week"], x["scenario"], x["percent_off"]))
