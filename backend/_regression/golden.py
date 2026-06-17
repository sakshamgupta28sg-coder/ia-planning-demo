"""Regression harness — proves the engine output is unchanged across the refactor.

Usage:
    python3 _regression/golden.py capture   # write baseline.json from current code
    python3 _regression/golden.py verify    # compare current code to baseline.json

The snapshot is the full engine output (get_agg_rows) for every SKU + channel, plus
the analytic endpoints (budget, season-progress, exceptions), with current_week pinned.
Any byte difference for a pinned clock = a behavior change = gate failure.
"""
import sys, os, json, hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dummy_data as d

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")


def _canonical():
    """Deterministic dict of everything the engine produces, fresh DB / no overrides."""
    out = {}
    # Full aggregated engine output (all hc, ch, wk buckets).
    out["agg_all"] = d.get_agg_rows(None, None)
    # Per-SKU and per-SKU×channel filter paths.
    for h in d.HIERARCHIES:
        hc = h["hierarchy_code"]
        out[f"agg_{hc}"] = d.get_agg_rows(hc, None)
        for ch in d.CHANNELS:
            out[f"agg_{hc}_{ch}"] = d.get_agg_rows(hc, ch)
    # Analytics.
    out["budget_portfolio"] = d.get_budget()
    out["season_portfolio"] = d.get_season_progress()
    out["exceptions"] = d.get_exceptions_panel()
    for h in d.HIERARCHIES:
        hc = h["hierarchy_code"]
        out[f"budget_{hc}"] = d.get_budget([hc], None)
        out[f"season_{hc}"] = d.get_season_progress([hc], None)
    return out


def _dump(obj):
    return json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)


def capture():
    data = _canonical()
    with open(BASELINE, "w", encoding="utf-8") as f:
        f.write(_dump(data))
    print(f"baseline captured: {len(_dump(data))} bytes, sha={hashlib.sha256(_dump(data).encode()).hexdigest()[:12]}")


def verify(core_only: bool = False):
    if not os.path.exists(BASELINE):
        print("NO BASELINE — run capture first"); sys.exit(2)
    with open(BASELINE, encoding="utf-8") as f:
        base = json.loads(f.read())
    cur = _canonical()
    # Portfolio-level sections aggregate ALL SKUs, so they legitimately change once
    # New SKUs join. core mode checks only the original-8-SKU sections, which must
    # stay byte-identical no matter what is added.
    PORTFOLIO = {"agg_all", "budget_portfolio", "season_portfolio", "exceptions"}
    keys = [k for k in base if not (core_only and k in PORTFOLIO)]
    missing = [k for k in keys if k not in cur]
    if missing:
        print("KEY MISMATCH — missing in current:", missing[:10]); sys.exit(1)
    diffs = [k for k in keys if _dump(base[k]) != _dump(cur[k])]
    if diffs:
        print(f"FAIL — {len(diffs)} sections differ:")
        for k in diffs[:10]:
            print("  ", k)
        sys.exit(1)
    label = "original-SKU" if core_only else "all"
    print(f"PASS — {len(keys)} {label} sections byte-identical to baseline")


def verify_core():
    verify(core_only=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"capture": capture, "verify": verify, "verify_core": verify_core}.get(mode, verify)()
