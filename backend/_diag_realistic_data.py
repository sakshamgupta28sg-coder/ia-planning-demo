#!/usr/bin/env python3
"""Inspect the new initial-buy + reorder supply model at BASELINE (no planner orders).

Shows per SKU×Ecom: opening continuity, committed-supply cliff, baseline coverage,
and what the replenishment engine now recommends. Snapshot+restore (clears overrides
for a pure baseline view, then restores)."""
import sys, copy
sys.path.insert(0, "/Users/sakshamgupta/ia-planning-demo/backend")
import dummy_data as dd
from database import db_get_overrides, db_replace_overrides

CH = "Ecom"


def run():
    snap = copy.deepcopy(db_get_overrides())
    try:
        db_replace_overrides({})   # pure baseline
        print(f"{'SKU':<22}{'profile':<14}{'wk20→21 EOP':<13}{'recomm: wks/Σ':<16}"
              f"{'excessWk':<9}{'stkoutWk':<9}{'minEOP':<7}{'finalEOP'}")
        print("-" * 104)
        for hc in sorted(dd.HIERARCHY_METRICS):
            name = next(h["l2_name"] for h in dd.HIERARCHIES if h["hierarchy_code"] == hc)
            prof = dd.SUPPLY_PROFILE[hc]
            twos = dd.get_target_wos(hc, CH)
            rows = sorted(dd.get_agg_rows(hc, CH), key=lambda r: r["current_week"])
            wk20 = next((r for r in rows if r.get("is_ongoing")), None)
            pw = [r for r in rows if not r.get("actualised") and not r.get("is_ongoing")]
            wk21 = pw[0]
            recomm_fire = [(r["current_week"] % 100, r["recomm_receipt_units"]) for r in pw if r["recomm_receipt_units"] > 0]
            excess = sum(1 for r in pw if r.get("wos") and twos > 0 and r["wos"] > twos * 1.5
                         and r["current_week"] < dd._SEASON_END_WK)
            stk = sum(1 for r in pw if r.get("_stockout"))
            body = [r["eop_units"] for r in pw if r["current_week"] < dd._SEASON_END_WK]
            min_eop = min(body) if body else None
            final = pw[-1]["eop_units"]
            prof_s = f"o{prof['open_wos']}/c{prof['commit_through']}/×{prof['commit_mult']}"
            cont = f"{wk20['eop_units'] if wk20 else '?'}→{wk21['bop_units']}"
            print(f"{name:<22}{prof_s:<14}{cont:<13}"
                  f"{str(len(recomm_fire))+'/'+str(sum(v for _,v in recomm_fire)):<16}"
                  f"{excess:<9}{stk:<9}{str(min_eop):<7}{final}")
        print("\nLegend: profile = open_wos / commit_through_wk / commit_mult")
        print("Expect: normal SKUs → recomm cadence (many wks); Sandals/Activewear → excess;")
        print("        Ankle Boots/Hoodies → stockout wks + heavy recomm (under-bought, long LT)")
    finally:
        db_replace_overrides(snap)
        if db_get_overrides() != snap:
            print("!!! restore mismatch")


if __name__ == "__main__":
    run()
