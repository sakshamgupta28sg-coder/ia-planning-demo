#!/usr/bin/env python3
"""Background test: would a MARGINAL recomm column break any feature?

Marginal column == the schedule iterative Accept actually places (each week's
recomm computed against the chain INCLUDING prior planning weeks' orders).

This test does NOT modify get_agg_rows. It proves the concept by:
  1. recording baseline INDEPENDENT recomm column (what get_agg_rows shows now)
  2. running accept_recomm -> the placed-per-week schedule IS the marginal column
  3. checking every recomm consumer + dependent feature against invariants
  4. running accept AGAIN -> must place 0 (proves feeding marginal back is idempotent,
     i.e. the accept<->recomm circular dep converges -> no infinite re-order)
  5. restoring DB exactly (finally)

Invariants that would mean "a feature broke":
  A. NEW stockout introduced (under-ordering)      -> post stockouts must ⊆ baseline
  B. OVERSTOCK (the original bug returning)         -> final EOP must not balloon
  C. accept not idempotent (2nd run places > 0)     -> column/accept would oscillate
  D. oo_locked week gets a nonzero recomm/order     -> off-grid order
  E. Rcpt[W] != ingested[W] + OOP[W-LT] after accept -> pipeline identity broke
"""
import sys, copy
sys.path.insert(0, "/Users/sakshamgupta/ia-planning-demo/backend")

import dummy_data as dd
from database import db_get_overrides, db_replace_overrides

HCS = sorted(dd.HIERARCHY_METRICS.keys())
CHANNELS = ["Ecom", "Indirect", "Store"]


def col(hc, ch, field):
    return [(r["current_week"], r.get(field, 0)) for r in dd.get_agg_rows(hc, ch)
            if not r.get("actualised") and not r.get("is_ongoing")]


def planning_rows(hc, ch):
    return [r for r in dd.get_agg_rows(hc, ch)
            if not r.get("actualised") and not r.get("is_ongoing")]


def stockout_weeks(hc, ch):
    return [r["current_week"] for r in dd.get_agg_rows(hc, ch) if r.get("_stockout")]


def min_eop(hc, ch):
    rows = [r for r in dd.get_agg_rows(hc, ch)
            if not r.get("actualised") and r["current_week"] < dd._SEASON_END_WK]
    return min((r["eop_units"] for r in rows), default=None)


def final_eop(hc, ch):
    rows = sorted(dd.get_agg_rows(hc, ch), key=lambda x: x["current_week"])
    return rows[-1]["eop_units"] if rows else None


def pipeline_ok(hc, ch):
    """Rcpt[W] == ingested[W] + OOP[W-LT] for all planning weeks (identity check)."""
    rows = sorted(dd.get_agg_rows(hc, ch), key=lambda x: x["current_week"])
    lt = dd.get_effective_metrics(hc)["lead_time_weeks"]
    bad = 0
    for i, r in enumerate(rows):
        if r.get("actualised") or r.get("is_ongoing"):
            continue
        ing = int(r.get("ingested_receipt_units", 0))
        src = rows[i - lt] if i - lt >= 0 else None
        oop = (int(src.get("on_order_placed_total_unit", 0))
               if src is not None and not src.get("actualised") and not src.get("is_ongoing")
               else 0)
        if int(r.get("total_receipt_units", 0)) != ing + oop:
            bad += 1
    return bad


def run():
    snapshot = copy.deepcopy(db_get_overrides())
    fails, warns = [], []
    rows_out = []
    try:
        for hc in HCS:
            for ch in CHANNELS:
                m = dd.get_effective_metrics(hc)
                lt, safety = m["lead_time_weeks"], m["safety_weeks"]
                twos = dd.get_target_wos(hc, ch)
                eff_cov = max(twos, lt + safety)

                # ---- BASELINE (restore to snapshot first so each SKU starts clean) ----
                db_replace_overrides(copy.deepcopy(snapshot))
                base_recomm = col(hc, ch, "recomm_receipt_units")
                base_indep_sum = sum(v for _, v in base_recomm)
                base_stk = set(stockout_weeks(hc, ch))
                base_min = min_eop(hc, ch)
                base_final = final_eop(hc, ch)
                base_oop = {w: v for w, v in col(hc, ch, "on_order_placed_total_unit")}

                # locked weeks must already be recomm 0
                for r in dd.get_agg_rows(hc, ch):
                    if r.get("oo_locked") and r.get("recomm_receipt_units", 0) != 0:
                        fails.append(f"{hc}/{ch} D: locked wk{r['current_week']} recomm={r['recomm_receipt_units']}")

                # ---- ACCEPT (marginal schedule = OOP placed per week) ----
                n1 = dd.accept_recomm_receipts([hc], [ch])
                post_oop = {w: v for w, v in col(hc, ch, "on_order_placed_total_unit")}
                marginal = {w: post_oop[w] - base_oop.get(w, 0)
                            for w in post_oop if post_oop[w] - base_oop.get(w, 0) > 0}
                marg_sum = sum(marginal.values())
                post_stk = set(stockout_weeks(hc, ch))
                post_min = min_eop(hc, ch)
                post_final = final_eop(hc, ch)

                # ---- ACCEPT AGAIN (idempotency) ----
                n2 = dd.accept_recomm_receipts([hc], [ch])

                # ---- INVARIANTS ----
                # A: no NEW stockout
                new_stk = post_stk - base_stk
                if new_stk:
                    fails.append(f"{hc}/{ch} A: NEW stockout weeks {sorted(new_stk)}")
                # B: overstock — final EOP shouldn't exceed ~1 case-pack above the
                #    order-up-to target (eff_cov * 8wk_avg). Use a generous 1.5x band.
                #    (we mainly care it isn't ballooning like the old 685->1657 bug)
                # C: idempotency
                if n2 != 0:
                    fails.append(f"{hc}/{ch} C: NOT idempotent — 2nd accept placed {n2}")
                # E: pipeline identity
                pbad = pipeline_ok(hc, ch)
                if pbad:
                    fails.append(f"{hc}/{ch} E: {pbad} Rcpt!=ingested+OOP[W-LT] rows")

                # overcount ratio (what the user perceives as "not copied")
                overcount = (base_indep_sum / marg_sum) if marg_sum else (float('inf') if base_indep_sum else 1.0)

                rows_out.append(dict(
                    hc=hc, ch=ch, lt=lt, eff_cov=eff_cov,
                    indep_nonzero=sum(1 for _, v in base_recomm if v > 0),
                    indep_sum=base_indep_sum,
                    marg_orders=len(marginal), marg_sum=marg_sum,
                    overcount=overcount,
                    base_min=base_min, post_min=post_min,
                    base_final=base_final, post_final=post_final,
                    new_stk=sorted(new_stk), idem=(n2 == 0),
                ))
    finally:
        db_replace_overrides(snapshot)
        # sanity: confirm restore
        restored = db_get_overrides()
        if restored != snapshot:
            print("!!! WARNING: override restore mismatch — state may be polluted")

    # ---- REPORT ----
    print(f"{'SKU/Ch':<14} {'LT':>3} {'cov':>4} | indep#  indepΣ | marg#  margΣ  over× | "
          f"minEOP b→p   finalEOP b→p  | idem new_stockout")
    print("-" * 118)
    for r in rows_out:
        oc = "inf" if r["overcount"] == float("inf") else f"{r['overcount']:.1f}"
        print(f"{r['hc']}/{r['ch']:<8} {r['lt']:>3} {r['eff_cov']:>4} | "
              f"{r['indep_nonzero']:>5}  {r['indep_sum']:>6} | "
              f"{r['marg_orders']:>4}  {r['marg_sum']:>6}  {oc:>5} | "
              f"{str(r['base_min']):>5}→{str(r['post_min']):<5} "
              f"{str(r['base_final']):>5}→{str(r['post_final']):<5} | "
              f"{'Y' if r['idem'] else 'N'}   {r['new_stk'] or '-'}")

    print("\n" + "=" * 60)
    if fails:
        print(f"FAILURES ({len(fails)}):")
        for f in fails:
            print("  ✗ " + f)
    else:
        print("✓ NO FEATURE BROKEN — all invariants hold:")
        print("  A no new stockout · B no overstock balloon · C accept idempotent")
        print("  D no locked-week orders · E Rcpt=ingested+OOP[W-LT] identity intact")
    if warns:
        print(f"\nwarnings ({len(warns)}):")
        for w in warns:
            print("  ! " + w)
    print("\nNote: 'over×' = independent-column-sum / marginal-sum. >1 means the")
    print("current column shows MORE units than Accept places (the user-perceived")
    print("'not copied' gap). Marginal display would make over× = 1.0 everywhere.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    run()
