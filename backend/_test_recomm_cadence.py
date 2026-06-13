#!/usr/bin/env python3
"""Stress test: does marginal recomm produce a REORDER CADENCE when a SKU is
genuinely under-supplied, or does it structurally collapse to one order?

If it spreads orders across weeks under real shortage → policy is sound, the
demo SKUs just happen to be well-supplied. If it still fires once → the
order-up-to policy front-loads structurally (a real design problem).

Snapshot+restore; no permanent DB change.
"""
import sys, copy
sys.path.insert(0, "/Users/sakshamgupta/ia-planning-demo/backend")
import dummy_data as dd
from database import db_get_overrides, db_replace_overrides

HC, CH = 10008, "Ecom"   # Activewear Shorts (long LT)


def recomm_col():
    return [(r["current_week"], r["recomm_receipt_units"])
            for r in dd.get_agg_rows(HC, CH)
            if not r.get("actualised") and not r.get("is_ongoing")]


def eop_min():
    rows = [r for r in dd.get_agg_rows(HC, CH)
            if not r.get("actualised") and r["current_week"] < dd._SEASON_END_WK]
    return min((r["eop_units"] for r in rows), default=None)


def run():
    snap = copy.deepcopy(db_get_overrides())
    try:
        m = dd.get_effective_metrics(HC)
        print(f"Activewear LT={m['lead_time_weeks']} safety={m['safety_weeks']} "
              f"target_wos={dd.get_target_wos(HC,CH)} case_pack={m['case_pack']}\n")

        # weeks we can edit (planning)
        wks = [r["current_week"] for r in dd.get_agg_rows(HC, CH)
               if not r.get("actualised") and not r.get("is_ongoing")]

        for mult, label in [(1.0, "BASELINE"), (3.0, "3x demand"), (6.0, "6x demand")]:
            db_replace_overrides(copy.deepcopy(snap))
            if mult != 1.0:
                # spike sales across ALL planning weeks → genuine sustained shortage
                for r in dd.get_agg_rows(HC, CH):
                    if r["current_week"] in wks:
                        base = r["written_sales_units"]
                        if base > 0:
                            dd.apply_edit(HC, r["current_week"], CH,
                                          "written_sales_units", float(round(base * mult)))
            col = recomm_col()
            fired = [(w, v) for w, v in col if v > 0]
            print(f"=== {label} ===")
            print(f"  recomm fires in {len(fired)} week(s); Σ = {sum(v for _,v in fired)}")
            print(f"  weeks: {fired[:12]}{' …' if len(fired)>12 else ''}")
            # now ACCEPT and see how many orders actually get placed
            db_replace_overrides(copy.deepcopy(snap))
            if mult != 1.0:
                for r in dd.get_agg_rows(HC, CH):
                    if r["current_week"] in wks:
                        base = r["written_sales_units"]
                        if base > 0:
                            dd.apply_edit(HC, r["current_week"], CH,
                                          "written_sales_units", float(round(base * mult)))
            n = dd.accept_recomm_receipts([HC], [CH])
            placed = [(r["current_week"], int(r["on_order_placed_total_unit"]))
                      for r in dd.get_agg_rows(HC, CH)
                      if not r.get("oo_locked") and r["on_order_placed_total_unit"] > 0
                      and r["current_week"] in wks]
            print(f"  AFTER ACCEPT: {n} orders placed: {placed[:12]}{' …' if len(placed)>12 else ''}")
            print(f"  min EOP after accept: {eop_min()}")
            print()
    finally:
        db_replace_overrides(snap)
        if db_get_overrides() != snap:
            print("!!! restore mismatch")


if __name__ == "__main__":
    run()
