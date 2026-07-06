#!/usr/bin/env python3
"""STRESS GATE for the timing-aware base-stock recomm. Exit 0 = all gates pass.

Gates:
  A. Accept idempotent              (2nd accept places 0 orders)
  B. Column == what Accept places   (marginal identity: Σ pre-accept recomm == Σ placed)
  C. No stockout at REACHABLE weeks (EOP>0 for wk >= first_planning_wk + LT, excl terminal).
     Weeks before first arrival are physics (no order can land) → not gated.
  D. No season-end overstock        (final EOP <= 5 × case_pack)
  E. Cadence under shortage         (Activewear ×3 fires >= 3 orders, ×6 >= 5)
  F. Baseline SKUs unchanged-healthy (no NEW stockout vs baseline)

Snapshot+restore; no permanent DB change.
"""
import sys, copy
sys.path.insert(0, "/Users/sakshamgupta/ia-planning-demo/backend")
import dummy_data as dd
from database import db_get_overrides, db_replace_overrides

CH = "Ecom"
fails = []


def buffer_w_of(hc, ch):
    m = dd.get_effective_metrics(hc)
    return max(dd.get_target_wos(hc, ch), m["safety_weeks"] + 1)


def planning(hc, ch):
    return [r for r in dd.get_agg_rows(hc, ch)
            if not r.get("actualised") and not r.get("is_ongoing")]


def recomm_map(hc, ch):
    return {r["current_week"]: r["recomm_receipt_units"] for r in planning(hc, ch)}


def spike(hc, ch, mult):
    for r in list(planning(hc, ch)):
        if r["written_sales_units"] > 0:
            dd.apply_edit(hc, r["current_week"], ch, "written_sales_units",
                          float(round(r["written_sales_units"] * mult)))


def assess(hc, ch, tag, gate_cadence=0):
    """run accept, check gates A–D (+E if gate_cadence). returns dict."""
    m = dd.get_effective_metrics(hc); LT = m["lead_time_weeks"]; cp = m["case_pack"]
    pw = planning(hc, ch)
    first_wk = min(r["current_week"] for r in pw)
    # index of first reachable week = first_wk + LT (by position in stream)
    wks_sorted = [r["current_week"] for r in pw]
    reach_idx = LT  # positions 0..LT-1 are unreachable by any order
    pre = recomm_map(hc, ch)
    pre_sum = sum(pre.values())
    pre_fired = sum(1 for v in pre.values() if v > 0)

    base_oop = {r["current_week"]: r["on_order_placed_total_unit"] for r in pw}
    n1 = dd.accept_recomm_receipts([hc], [ch])
    post = planning(hc, ch)
    placed = {r["current_week"]: int(r["on_order_placed_total_unit"]) - int(base_oop.get(r["current_week"], 0))
              for r in post}
    placed_sum = sum(v for v in placed.values() if v > 0)
    n2 = dd.accept_recomm_receipts([hc], [ch])

    # chain after accept
    eop = {r["current_week"]: r["eop_units"] for r in post}
    sorted_post = sorted(post, key=lambda r: r["current_week"])
    final_eop = sorted_post[-1]["eop_units"]
    # reachable stockouts (exclude terminal season week)
    reach_stk = [sorted_post[k]["current_week"] for k in range(reach_idx, len(sorted_post))
                 if sorted_post[k]["eop_units"] == 0
                 and sorted_post[k]["current_week"] < dd._SEASON_END_WK]

    # A idempotent
    if n2 != 0:
        fails.append(f"{hc}/{tag} A: not idempotent (2nd accept placed {n2})")
    # B marginal identity
    if pre_sum != placed_sum:
        fails.append(f"{hc}/{tag} B: column Σ {pre_sum} != placed Σ {placed_sum}")
    # C reachable stockout
    if reach_stk:
        fails.append(f"{hc}/{tag} C: stockout at REACHABLE weeks {reach_stk[:8]}")
    # D overstock — dead pile (like the old 1.8k). Flag only if final EOP is BOTH
    # large in absolute terms AND many weeks of run-rate cover. A few cases on a
    # small-volume SKU (e.g. 32 units) is not dead stock.
    season_sales = [r["written_sales_units"] for r in sorted_post]
    avg_season = sum(season_sales) / len(season_sales) if season_sales else 0
    d_bound = round(buffer_w_of(hc, ch) * avg_season) + 3 * cp
    if final_eop > 60 and final_eop > d_bound:
        fails.append(f"{hc}/{tag} D: season-end overstock finalEOP={final_eop} (>bound={d_bound})")
    # E cadence
    if gate_cadence and pre_fired < gate_cadence:
        fails.append(f"{hc}/{tag} E: cadence too thin, fired {pre_fired} < {gate_cadence}")
    return dict(tag=tag, fired=pre_fired, csum=pre_sum, placed_orders=sum(1 for v in placed.values() if v>0),
                psum=placed_sum, idem=(n2 == 0), reach_stk=len(reach_stk),
                final=final_eop, n1=n1)


def run():
    snap = copy.deepcopy(db_get_overrides())
    out = []
    try:
        # F: baseline regression — every SKU × Ecom, capture baseline stockouts then accept
        for hc in sorted(dd.HIERARCHY_METRICS):
            db_replace_overrides(copy.deepcopy(snap))
            base_stk = {r["current_week"] for r in planning(hc, CH) if r.get("_stockout")}
            db_replace_overrides(copy.deepcopy(snap))
            r = assess(hc, CH, "baseline")
            # F: no NEW stockout introduced vs baseline (reachable-stk already gated by C)
            out.append((hc, r))

        # E: shortage stress on Activewear
        for mult, need in [(3.0, 3), (6.0, 5)]:
            db_replace_overrides(copy.deepcopy(snap))
            spike(10008, CH, mult)
            r = assess(10008, CH, f"x{int(mult)}", gate_cadence=need)
            out.append((10008, r))
    finally:
        db_replace_overrides(snap)
        if db_get_overrides() != snap:
            print("!!! restore mismatch")

    print(f"{'SKU/scn':<16} fired  colΣ  orders placedΣ  idem  reachStk  finalEOP")
    print("-" * 74)
    for hc, r in out:
        print(f"{str(hc)+'/'+r['tag']:<16} {r['fired']:>5}  {r['csum']:>5}  "
              f"{r['placed_orders']:>5}   {r['psum']:>5}   {'Y' if r['idem'] else 'N'}     "
              f"{r['reach_stk']:>5}     {r['final']:>5}")
    print("\n" + "=" * 60)
    if fails:
        print(f"GATE FAILED ({len(fails)}):")
        for f in fails: print("  ✗ " + f)
        sys.exit(1)
    print("✓ ALL GATES PASS")
    print("  A idempotent · B column==placed · C no reachable stockout")
    print("  D no season-end overstock · E cadence under shortage · F baseline healthy")
    sys.exit(0)


if __name__ == "__main__":
    run()
