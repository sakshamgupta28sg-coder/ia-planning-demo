import contextlib
import math as _math
import os
import random
import threading
from datetime import date, timedelta
from typing import Dict, List

import seed_loader

random.seed(42)

# ── CSV seed (warehouse door) ─────────────────────────────────────────────────
# If backend/seeds/catalog.csv exists, the catalog + supply + budgets are loaded
# from CSV and override the hardcoded demo literals below (see the override blocks
# before generation and before the master-SKU seed). Absent → demo literals are
# used unchanged (regression gate stays byte-identical). A malformed seed raises
# SeedError at import — fail loud, never plan on bad data.
SEEDS_DIR = os.environ.get("IA_SEEDS_DIR", os.path.join(os.path.dirname(__file__), "seeds"))
_SEED = seed_loader.load_seed(SEEDS_DIR)

HIERARCHIES = [
    {"hierarchy_code": 10001, "l1_name": "Footwear", "l2_name": "Running Shoes",      "sku_code": "FW-RUN-001"},
    {"hierarchy_code": 10002, "l1_name": "Footwear", "l2_name": "Casual Sneakers",    "sku_code": "FW-CSN-002"},
    {"hierarchy_code": 10003, "l1_name": "Footwear", "l2_name": "Ankle Boots",        "sku_code": "FW-BOT-003"},
    {"hierarchy_code": 10004, "l1_name": "Footwear", "l2_name": "Sandals",            "sku_code": "FW-SND-004"},
    {"hierarchy_code": 10005, "l1_name": "Apparel",  "l2_name": "Denim Jeans",        "sku_code": "AP-DNM-005"},
    {"hierarchy_code": 10006, "l1_name": "Apparel",  "l2_name": "Graphic Tees",       "sku_code": "AP-TEE-006"},
    {"hierarchy_code": 10007, "l1_name": "Apparel",  "l2_name": "Hoodies",            "sku_code": "AP-HOD-007"},
    {"hierarchy_code": 10008, "l1_name": "Apparel",  "l2_name": "Activewear Shorts",  "sku_code": "AP-ACT-008"},
]

# Ordered unique categories
CATEGORIES = list(dict.fromkeys(h["l1_name"] for h in HIERARCHIES))

CHANNELS = ["Ecom", "Indirect", "Store"]

# Ingested receipt budget per (hierarchy_code, channel) — season OTB target
BUDGET_DATA: Dict[tuple, float] = {
    (10001, "Ecom"):     15000,
    (10001, "Indirect"):  9000,
    (10001, "Store"):     4000,
    (10002, "Ecom"):     13000,
    (10002, "Indirect"):  7000,
    (10002, "Store"):     3500,
    (10003, "Ecom"):     25000,
    (10003, "Indirect"):  3500,
    (10003, "Store"):     1200,
    (10004, "Ecom"):      8500,
    (10004, "Indirect"):  4500,
    (10004, "Store"):     2000,
    (10005, "Ecom"):     24000,
    (10005, "Indirect"): 12000,
    (10005, "Store"):     6500,
    (10006, "Ecom"):      9000,
    (10006, "Indirect"):  5500,
    (10006, "Store"):     2500,
    (10007, "Ecom"):      6500,
    (10007, "Indirect"):  3500,
    (10007, "Store"):     1800,
    (10008, "Ecom"):      8000,
    (10008, "Indirect"):  4000,
    (10008, "Store"):     2500,
}
SUB_CHANNELS = {
    "Ecom": ["Ecom_Direct", "Ecom_Marketplace"],
    "Indirect": ["Indirect_National", "Indirect_Regional"],
    "Store": ["Store_Flagship", "Store_Outlet"],
}
WAREHOUSE_SUB_CHANNELS = {
    "Ecom": "Ecom_warehouse",
    "Indirect": "Indirect_warehouse",
    "Store": "Store_warehouse",
}

# ── The clock anchors everything: "now" → the whole year window ───────────────
# "Now" is the in-flight week = the boundary between actuals and plan. By DEFAULT,
# when a stream's history is uploaded, this is DATA-DRIVEN: now = the week after the
# latest actual in sales_history.csv. So the boundary always matches the data the SMB
# has actually loaded — upload more weeks and "now" advances; cross a year and the
# whole window (selectable years, calendar span, plan-gen years, TY/LY/LLY rollover)
# rolls forward, because all of those derive from the now-year below.
#
# Precedence:  IA_PINNED_WEEK (explicit, e.g. 202720 — demos / tests)
#            → IA_LIVE_CLOCK  (wall-clock: today's real fiscal week)
#            → DATA           (last uploaded actual + 1)   ← default for an SMB pilot
#            → 202620         (no data, no clock: the byte-stable demo fixture)
#
# Year-level resolution avoids the calendar (no chicken-and-egg with
# fiscal_week_for_date, which reads FISCAL_CALENDAR built just below).
_DEFAULT_NOW_WEEK = 202620


def _data_latest_actual_week():
    """Latest fiscal week_code present in uploaded history = the last CLOSED actual.
    None when there's no history (the demo) → clock falls back to the default/override."""
    if _SEED is None or not _SEED.sales_history:
        return None
    return max(yr * 100 + wn for (_hc, _ch, yr, wn) in _SEED.sales_history)


def _next_fiscal_week(wcode: int) -> int:
    """Week after wcode; wraps wk52 → next year wk1 (simple 52-week seed)."""
    yr, wn = wcode // 100, wcode % 100
    return (yr + 1) * 100 + 1 if wn >= 52 else wcode + 1


def _resolve_now_year() -> int:
    explicit = os.getenv("IA_PINNED_WEEK")
    if explicit:
        return int(explicit) // 100
    if os.getenv("IA_LIVE_CLOCK"):
        return date.today().year      # fiscal year ≈ calendar year in this 52-wk seed
    last = _data_latest_actual_week()
    if last is not None:
        return _next_fiscal_week(last) // 100
    return _DEFAULT_NOW_WEEK // 100


_NOW_YEAR = _resolve_now_year()

# ── Fiscal calendar (real-retail shape, simple 52-week seed) ──────────────────
# Backbone for date↔week mapping and cross-year week math. Spans now-2 … now+2:
# now+2 is the furthest selectable year (TY), now-2 is the oldest comparison year
# (LLY of the current year). Schema carries fiscal_month / fiscal_quarter and
# tolerates a 53rd week so a true 4-5-4 NRF calendar can be swapped in later
# WITHOUT a schema change. Seed: every year = 52 weeks, week 1 anchored to the
# first Monday on/after Jan 1, each week = +7 days, 4-5-4 months.
FISCAL_CALENDAR_YEARS = list(range(_NOW_YEAR - 2, _NOW_YEAR + 3))


def _build_fiscal_calendar() -> tuple:
    """Return (rows, by_code) for FISCAL_CALENDAR_YEARS — simple 52-week seed."""
    rows: List[Dict] = []
    by_code: Dict[int, Dict] = {}
    for fy in FISCAL_CALENDAR_YEARS:
        jan1 = date(fy, 1, 1)
        wk1_start = jan1 + timedelta(days=(7 - jan1.weekday()) % 7)  # first Monday on/after Jan 1
        for w in range(1, 53):  # simple seed = 52; schema tolerates 53
            start = wk1_start + timedelta(weeks=w - 1)
            end = start + timedelta(days=6)
            quarter = (w - 1) // 13 + 1            # 13 weeks per quarter
            wq = w - (quarter - 1) * 13            # 1..13 within quarter
            month_in_q = 0 if wq <= 4 else (1 if wq <= 9 else 2)   # 4-5-4
            row = {
                "week_code":      int(f"{fy}{str(w).zfill(2)}"),
                "fiscal_year":    fy,
                "fiscal_week":    w,
                "start_date":     start.isoformat(),
                "end_date":       end.isoformat(),
                "fiscal_month":   (quarter - 1) * 3 + month_in_q + 1,
                "fiscal_quarter": quarter,
            }
            rows.append(row)
            by_code[row["week_code"]] = row
    return rows, by_code


FISCAL_CALENDAR, _CAL_BY_CODE = _build_fiscal_calendar()


def fiscal_week_for_date(d: date) -> int:
    """Map a real calendar date → the fiscal week_code whose [start,end] contains it.
    Falls back to the nearest in-range week_code if the date is off the seeded grid."""
    iso = d.isoformat()
    for row in FISCAL_CALENDAR:
        if row["start_date"] <= iso <= row["end_date"]:
            return row["week_code"]
    # Off-grid: clamp to first/last seeded week.
    if iso < FISCAL_CALENDAR[0]["start_date"]:
        return FISCAL_CALENDAR[0]["week_code"]
    return FISCAL_CALENDAR[-1]["week_code"]


# Active "now" (in-flight week). Same precedence as _resolve_now_year above; this is
# the week-level resolution (the live-clock branch needs FISCAL_CALENDAR, built above).
def resolve_current_week() -> int:
    """IA_PINNED_WEEK → IA_LIVE_CLOCK (clamped to data) → DATA (last actual + 1) → 202620."""
    explicit = os.getenv("IA_PINNED_WEEK")
    if explicit:
        return int(explicit)
    last = _data_latest_actual_week()
    if os.getenv("IA_LIVE_CLOCK"):
        live = fiscal_week_for_date(date.today())
        # Clamp to last_actual+1 so a lagging upload never lets the clock outrun the
        # data — otherwise weeks in the gap flip to "actualised" with fabricated actuals.
        return min(live, _next_fiscal_week(last)) if last is not None else live
    if last is not None:
        return _next_fiscal_week(last)
    return _DEFAULT_NOW_WEEK


# Selectable planning years: the current season + the next two (view-only future),
# all derived from the clock's now-year so the window rolls forward automatically.
DEFAULT_YEAR = _NOW_YEAR
SELECTABLE_YEARS = [_NOW_YEAR, _NOW_YEAR + 1, _NOW_YEAR + 2]


def _year_weeks(year: int) -> List[int]:
    return [r["week_code"] for r in FISCAL_CALENDAR if r["fiscal_year"] == year]


# Fiscal weeks for the active planning year (2026 season). The engine reads these
# module-globals throughout; _scoped_year() temporarily repoints them at another
# year for the duration of a single read so the unchanged engine can compute it.
FISCAL_WEEKS = _year_weeks(DEFAULT_YEAR)
_SEASON_END_WK = FISCAL_WEEKS[-1]   # last week — planned runout to 0 here is intentional
_WK_POS = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}


# The season globals are process-wide, so the scoped swap MUST be serialized:
# FastAPI runs sync endpoints in a threadpool and the frontend fires several reads
# at once — concurrent swaps would corrupt FISCAL_WEEKS/_WK_POS mid-iteration (500s).
# A re-entrant lock makes scoped sections mutually exclusive (and allows nesting on
# the same thread, e.g. apply_edit → get_agg_rows). Fine for a single-user demo:
# requests just queue. The proper long-term fix is to thread `year` through instead.
_SCOPE_LOCK = threading.RLock()


@contextlib.contextmanager
def _scoped_year(year: int):
    """Temporarily repoint the season globals at `year`, restore on exit.

    Holds _SCOPE_LOCK for the whole block so concurrent requests don't race on the
    shared globals. Nesting on one thread is safe (RLock). For DEFAULT_YEAR the swap
    rebuilds identical lists → byte-identical to not scoping at all."""
    with _SCOPE_LOCK:
        global FISCAL_WEEKS, _SEASON_END_WK, _WK_POS
        saved = (FISCAL_WEEKS, _SEASON_END_WK, _WK_POS)
        wks = _year_weeks(year)
        FISCAL_WEEKS = wks
        _SEASON_END_WK = wks[-1]
        _WK_POS = {wk: i for i, wk in enumerate(wks)}
        try:
            yield
        finally:
            FISCAL_WEEKS, _SEASON_END_WK, _WK_POS = saved


def _week_offset(wk: int, delta: int):
    """Return the fiscal week `delta` positions from `wk`, or None if off-grid.

    delta = +LT  → arrival week of an order placed in `wk`
    delta = -LT  → order week that produces an arrival in `wk`
    """
    idx = _WK_POS.get(wk)
    if idx is None:
        return None
    j = idx + delta
    return FISCAL_WEEKS[j] if 0 <= j < len(FISCAL_WEEKS) else None


def _is_oo_locked(hc: int, wk: int) -> bool:
    """OO Placed locked when an order placed in `wk` would arrive after season end.

    Dynamic off the *effective* lead time (recomputed when LT changes), so it is
    never stale like a seeded flag would be.
    """
    lt = get_effective_metrics(hc)["lead_time_weeks"]
    return _week_offset(wk, lt) is None

# Base metrics per hierarchy (AIR = avg initial retail price, AUC = avg unit cost)
# OTB fields:
#   target_wos     – target weeks-of-supply to hold at EOP
#   lead_time_weeks – total inbound lead time from PO placement to receipt
#   case_pack       – minimum order quantity (round-up denominator)
#   safety_weeks    – additional buffer added to look-ahead window
HIERARCHY_METRICS = {
    10001: {"air": 119.99, "auc": 44.0,  "peak_week": 26, "peak_units":  160,  # Running Shoes  – spring marathon season (late-spring peak)
            "target_wos": 6, "lead_time_weeks": 14, "case_pack":  6, "safety_weeks": 2},
    10002: {"air":  89.99, "auc": 30.0,  "peak_week": 25, "peak_units":  210,  # Casual Sneakers – summer
            "target_wos": 6, "lead_time_weeks": 12, "case_pack":  6, "safety_weeks": 2},
    10003: {"air": 154.99, "auc": 55.0,  "peak_week": 41, "peak_units":  140,  # Ankle Boots    – fall
            "target_wos": 8, "lead_time_weeks": 16, "case_pack":  4, "safety_weeks": 3},
    10004: {"air":  64.99, "auc": 21.0,  "peak_week": 22, "peak_units":  230,  # Sandals        – summer
            "target_wos": 5, "lead_time_weeks": 10, "case_pack": 12, "safety_weeks": 1},
    10005: {"air":  79.99, "auc": 27.0,  "peak_week": 38, "peak_units":  280,  # Denim Jeans    – back-to-school
            "target_wos": 8, "lead_time_weeks": 14, "case_pack": 12, "safety_weeks": 2},
    10006: {"air":  34.99, "auc": 11.0,  "peak_week": 26, "peak_units":  430,  # Graphic Tees   – summer
            "target_wos": 6, "lead_time_weeks": 10, "case_pack": 24, "safety_weeks": 2},
    10007: {"air":  69.99, "auc": 23.0,  "peak_week": 42, "peak_units":  250,  # Hoodies        – fall
            "target_wos": 8, "lead_time_weeks": 12, "case_pack": 12, "safety_weeks": 3},
    10008: {"air":  44.99, "auc": 14.0,  "peak_week": 24, "peak_units":  340,  # Activewear Shorts – summer
            "target_wos": 5, "lead_time_weeks": 10, "case_pack": 24, "safety_weeks": 1},
}

# ── Pre-seeded New SKUs ───────────────────────────────────────────────────────────
# Real products onboarded mid-life. Appended to the catalog AFTER the originals so
# the original-8 generation + RNG stay byte-identical. Each has its OWN price/curve;
# it only BORROWS Disc% from a tagged Old SKU during its New year (first 52 weeks from
# activation), because it has no LY/LLY history yet. Activations land in 2026 so they
# read as New in the 2026 view and flip to Old by the 2028 view.
NEW_SKU_HCS = {30001, 30002}
NEW_SKU_HIERARCHIES = [
    {"hierarchy_code": 30001, "l1_name": "Footwear", "l2_name": "Trail Runners", "sku_code": "FW-TRL-301"},
    {"hierarchy_code": 30002, "l1_name": "Apparel",  "l2_name": "Puffer Jacket", "sku_code": "AP-PUF-302"},
]
NEW_SKU_METRICS = {
    30001: {"air": 134.99, "auc": 48.0, "peak_week": 28, "peak_units": 150,
            "target_wos": 6, "lead_time_weeks": 12, "case_pack": 6, "safety_weeks": 2},
    30002: {"air":  99.99, "auc": 34.0, "peak_week": 44, "peak_units": 180,
            "target_wos": 8, "lead_time_weeks": 12, "case_pack": 8, "safety_weeks": 2},
}
# Lifecycle + descriptive attrs per New SKU (Old SKUs default to long-lived in the seed).
NEW_SKU_LIFECYCLE = {
    30001: {"activation_week": 202614, "deactivation_week": 202852, "tagged_to": 10001, "color": "Green", "size": "US 9"},
    30002: {"activation_week": 202624, "deactivation_week": 202852, "tagged_to": 10007, "color": "Olive", "size": "M"},
}
NEW_SKU_SUPPLY = {
    30001: {"open_wos": 5, "commit_through": 33, "commit_mult": 1.0},
    30002: {"open_wos": 4, "commit_through": 40, "commit_mult": 0.8},
}
# Metrics for New SKUs merge now (harmless dict); the New SKUs are NOT added to the
# HIERARCHIES list until AFTER the original-8 generation (see the generation block),
# so the originals' RNG stream — and thus TY/LY — stays byte-identical.
HIERARCHY_METRICS = {**HIERARCHY_METRICS, **NEW_SKU_METRICS}

# Committed-supply (buy) posture per SKU — models a REAL pre-season buy instead of
# auto-stocking every week to target. A buyer commits an initial inventory + a schedule
# of receipts that covers the early/peak weeks; after `commit_through` the committed buy
# is exhausted and the planner must REORDER (place OO) to cover the rest of the season —
# which is the whole job of the replenishment engine.
#
#   open_wos       opening inventory entering the planning horizon, in weeks of fwd demand
#   commit_through last week-number (wk%100) with committed ingested receipts; 0 after
#   commit_mult    how generous the committed buy is vs target coverage
#                    1.0 = buy to hold target;  >1 = over-bought (excess/markdown);
#                    <1 = under-bought (lean → genuine stockout risk, esp. long LT)
#
# Mix is deliberate: most SKUs need a steady reorder cadence; Sandals/Activewear are
# over-bought early-peak (excess flags); Ankle Boots/Hoodies are under-bought late-peak
# with long lead times (must reorder early or stock out).
SUPPLY_PROFILE = {
    10001: {"open_wos": 5, "commit_through": 33, "commit_mult": 1.0},  # Running Shoes  – normal, reorder back half
    10002: {"open_wos": 5, "commit_through": 32, "commit_mult": 1.0},  # Casual Sneakers – normal
    10003: {"open_wos": 3, "commit_through": 30, "commit_mult": 0.6},  # Ankle Boots    – under-bought, LT16, late peak
    10004: {"open_wos": 9, "commit_through": 46, "commit_mult": 1.7},  # Sandals        – over-bought early-peak → excess
    10005: {"open_wos": 4, "commit_through": 34, "commit_mult": 0.9},  # Denim Jeans    – tight, reorder for late peak
    10006: {"open_wos": 5, "commit_through": 33, "commit_mult": 1.0},  # Graphic Tees   – normal
    10007: {"open_wos": 4, "commit_through": 32, "commit_mult": 0.7},  # Hoodies        – under-bought, late peak
    10008: {"open_wos": 7, "commit_through": 40, "commit_mult": 1.4},  # Activewear     – mild over-bought early-peak
}
SUPPLY_PROFILE = {**SUPPLY_PROFILE, **NEW_SKU_SUPPLY}  # include pre-seeded New SKUs

CHANNEL_SPLIT = {"Ecom": 0.55, "Indirect": 0.30, "Store": 0.15}

# The fiscal week that is currently in-flight (not yet actualised, but not open for editing).
# Resolved via the calendar clock (pinned 202620 unless IA_LIVE_CLOCK is set).
CURRENT_WEEK = resolve_current_week()


def _seasonal_curve(week_num: int, peak_week: int) -> float:
    dist = abs(week_num - peak_week)
    if dist == 0:
        return 1.0
    if dist <= 3:
        return 0.7 - dist * 0.1
    if dist <= 8:
        return max(0.05, 0.4 - dist * 0.04)
    return max(0.02, 0.1 - dist * 0.005)


def _dr_perc(week_num: int, peak_week: int) -> float:
    """Discount rate peaks after peak selling period."""
    post = week_num - peak_week
    if post < 0:
        return round(random.uniform(0.0, 0.05), 4)
    if post < 3:
        return round(random.uniform(0.05, 0.15), 4)
    if post < 8:
        return round(random.uniform(0.15, 0.30), 4)
    return round(random.uniform(0.25, 0.40), 4)


# ACTUAL discount that ran last year (LY) and two years ago (LLY), keyed at
# (category, hierarchy_code, channel, week_num) — i.e. week × category × SKU × channel.
# Independent draws (peak-relative shape × noise) so they differ from the TY plan curve.
# These are the *history* a planner looks back on; populated by _build_history_discounts()
# during generate_wp_data() and consumed by both WP planning weeks and generate_ty_ly_data().
_LY_DISC: Dict[tuple, float] = {}
_LLY_DISC: Dict[tuple, float] = {}


# ── Sales-history reforecast helpers (Phase 2) ────────────────────────────────
# When sales_history.csv covers a stream, forward weeks are reforecast from its
# own history shape instead of the parametric peak curve. Precedence: LY → LLY →
# TY actuals (run-rate). Streams with NO history fall through to the parametric
# curve + RNG (the original behavior), so a corpus without sales_history.csv is
# byte-identical to before. Shapes are pure functions of the seed (no RNG), so
# results are deterministic across restarts.
_REFORECAST_CACHE: Dict[tuple, object] = {}


def _stream_has_history(hc: int, ch: str) -> bool:
    return _SEED is not None and _SEED.has_history(hc, ch)


def _scoped_fiscal_year() -> int:
    """Absolute calendar year the season globals (FISCAL_WEEKS) currently point at."""
    return int(str(FISCAL_WEEKS[0])[:4])


def _reforecast_shape(hc: int, ch: str):
    """(weights_by_week_num, total_units, source_year) for forward reforecast, or None.

    Year-relative to the scoped plan year `py`: shape the forward weeks off the prior
    year's actual seasonal curve (py-1 → py-2 → py fallback). weights sum to 1.0 over
    the weeks present in the chosen history year; total is that year's unit total.
    None → use parametric curve. (For py=2026 this is 2025→2024→2026, i.e. the old
    LY→LLY→TY precedence — behavior preserved.)
    """
    if _SEED is None:
        return None
    py = _scoped_fiscal_year()
    ckey = (hc, ch, py)
    if ckey in _REFORECAST_CACHE:
        return _REFORECAST_CACHE[ckey]

    def _series(yr):
        s = {wn: _SEED.history_units(hc, ch, yr, wn)
             for wn in range(1, 54)
             if _SEED.history_units(hc, ch, yr, wn) is not None}
        return s, sum(s.values())

    # Shape forward weeks off the most recent prior year with a (near-)FULL curve —
    # a partial actuals-to-date year (e.g. the current year, wks 1-19 only) can't
    # forecast wks 20-52, so skip it. Walk py-1, py-2, py-3, then accept any year
    # with data as a last resort. (For py=2026 this is 2025, the full prior year —
    # behavior preserved.)
    candidates = (py - 1, py - 2, py - 3, py)
    shape = None
    for yr in candidates:
        series, total = _series(yr)
        if total > 0 and len(series) >= 50:
            shape = ({wn: u / total for wn, u in series.items()}, total, yr)
            break
    if shape is None:                       # no full year — take whatever exists
        for yr in candidates:
            series, total = _series(yr)
            if series and total > 0:
                shape = ({wn: u / total for wn, u in series.items()}, total, yr)
                break
    _REFORECAST_CACHE[ckey] = shape
    return shape


def _history_cell_units(hc: int, ch: str, week_num: int, is_actual: bool, shape) -> int:
    """Deterministic units for a history stream's week.

    Actualised/ongoing week with an actual for the scoped year → that actual (real
    sales). Otherwise (forward weeks, or actual weeks with no row) → reforecast
    share × target.
    """
    if is_actual:
        a = _SEED.history_units(hc, ch, _scoped_fiscal_year(), week_num)
        if a is not None:
            return int(a)
    weights, total, _yr = shape
    return round(weights.get(week_num, 0.0) * total)


def _forecast_override(hc: int, ch: str, wk: int):
    """Explicit forecast (forecast.csv) for an unactualised cell → (units|None, oo_placed).

    units None → keep the engine forecast; oo_placed defaults 0. (None, 0) when there's
    no file / no row, so a corpus without forecast.csv is byte-identical.
    """
    if _SEED is None:
        return None, 0
    fc = _SEED.forecast_cell(hc, ch, wk // 100, wk % 100)
    if not fc:
        return None, 0
    u = fc.get("units")
    return (int(u) if u is not None else None), int(fc.get("oo_placed") or 0)


def _build_history_discounts() -> tuple:
    """Seed LY + LLY actual discount per (l1_category, hc, channel, week_num)."""
    ly: Dict[tuple, float] = {}
    lly: Dict[tuple, float] = {}
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        l1 = h["l1_name"]
        m = HIERARCHY_METRICS[hc]
        for ch in CHANNELS:
            for wk in FISCAL_WEEKS:
                wn = wk % 100
                base = _dr_perc(wn, m["peak_week"])
                ly[(l1, hc, ch, wn)]  = round(min(0.6, max(0.0, base * random.uniform(0.8, 1.2))), 4)
                lly[(l1, hc, ch, wn)] = round(min(0.6, max(0.0, base * random.uniform(0.8, 1.2))), 4)
    return ly, lly


# Per-SKU setting overrides loaded from DB at startup (field → value).
# Empty until _load_sku_settings() runs after DB init.
_SKU_SETTINGS_OVERRIDES: Dict[int, Dict] = {}


def get_effective_metrics(hc: int) -> Dict:
    """Base HIERARCHY_METRICS merged with any user-persisted SKU setting overrides."""
    base = dict(HIERARCHY_METRICS[hc])
    base.update(_SKU_SETTINGS_OVERRIDES.get(hc, {}))
    return base


# Fixed forward window used for WOS denominator (independent of lead-time).
WOS_WINDOW = 8

# Populated by generate_wp_data(); keyed (hc, ch, wk) → sum of planned units
# over the look-ahead window [wk+1 … wk+lead_time_weeks+safety_weeks].
_FORWARD_DEMAND_INDEX: Dict[tuple, int] = {}

# 8-week forward demand index used exclusively for WOS denominator.
_WOS_DEMAND_INDEX: Dict[tuple, int] = {}

# Sum of already-planned OO Placed receipts over the next lead_time weeks.
# Used by recomm to net off inventory already in the inbound pipeline so we
# don't double-count receipts that are already scheduled to arrive.
_PIPELINE_INDEX: Dict[tuple, int] = {}


# Per SKU×channel target WOS overrides (loaded from DB at startup).
# Key = "{hc}_{channel}"
_CHANNEL_TARGET_WOS: Dict[str, int] = {}


def get_target_wos(hc: int, channel: str) -> int:
    """Channel-level target WOS override → SKU-level override → base metric."""
    ch_key = f"{hc}_{channel}"
    if ch_key in _CHANNEL_TARGET_WOS:
        return _CHANNEL_TARGET_WOS[ch_key]
    return get_effective_metrics(hc)["target_wos"]


def _weeks_of_cover(stock, idx: int, sales: list, fallback_rate: float) -> float:
    """Forward weeks of demand `stock` covers, walking the REAL demand curve from
    idx+1 (not a flat average). Seasonality-aware:

      - Flat-demand region → reduces to stock / rate, i.e. identical to the old
        8wk-avg result. So calm/tail rows do not move.
      - Demand ramp (e.g. pre-peak) → the rising weeks consume `stock` faster, so
        coverage does NOT inflate. This is what stops FC exploding to 100+ when a
        peak-sized pipeline is measured against trough current demand.

    Leftover stock that outlasts the remaining season is extrapolated at
    `fallback_rate` (the 8wk forward avg at idx) so the end-of-season overstock
    signal keeps its prior magnitude. Caller gates on fallback_rate>0, mirroring
    the old `if wos_avg_s > 0 else None` so None-rows stay None.
    """
    if stock <= 0:
        return 0.0
    remaining = float(stock)
    weeks = 0.0
    n = len(sales)
    for j in range(idx + 1, n):
        d = sales[j]
        if d <= 0:
            weeks += 1.0                       # zero-demand week covered trivially
            continue
        if remaining >= d:
            remaining -= d
            weeks += 1.0
        else:
            return round(weeks + remaining / d, 2)
    if remaining > 0 and fallback_rate > 0:    # outlasts season → extrapolate
        weeks += remaining / fallback_rate
    return round(weeks, 2)


def _level_order_schedule(stream, lead_time, cp):
    """Deadline-feasible, MINIMUM-PEAK order schedule for one SKU×channel stream.

    Replaces "fill the whole forward buffer at the first reorder week" — which dumped a
    season's buy into ONE order when lead time is long and demand ramps (Ankle Boots LT16:
    324 units in wk21) — with a leveled plan that spreads orders across the unlocked weeks
    while still covering every week, INCLUDING the locked tail, at the lowest possible peak
    per-week order.

    Returns `order[i]` = units to have ON ORDER at planning week i (case-pack multiples).
    The caller turns it into the marginal recomm = max(0, order[i] − current OOP[i]).

    Method: an order placed at week j arrives at j+LT, so to avoid unmet demand the orders
    ARRIVED by any week w must cover `need(w)` = demand due by w net of starting position +
    ingested supply. With consecutive orderable weeks the arrival weeks are consecutive, so
    enforcing cumulative-orders[j] ≥ need(j+LT) (and the last orderable week ≥ the whole
    tail) covers every week. Min peak M = max_j ⌈need(j+LT)/(#orderable ≤ j)⌉; a backward
    pass gives the min-peak cumulative targets; rounding the CUMULATIVE target up to case
    pack (not each order) keeps the total exact and only pulls supply EARLIER, so rounding
    can never create a stockout. Verified: 0 unmet-demand stockout across all streams.
    """
    n = len(stream)
    order = [0] * n
    if cp <= 0 or lead_time < 0:
        return order
    # Ongoing week is a planning week → orderable. Only actualized weeks are excluded.
    isP   = [not s.get("actualised") for s in stream]
    sales = [s.get("written_sales_units", 0) for s in stream]
    ing   = [int(s.get("ingested_receipt_units", 0)) for s in stream]
    # starting position entering the planning horizon = EOP of the last actualized week.
    # A future season has no actualized week → fall back to the opening BOP of the first
    # planning week (the calibrated opening inventory), not 0.
    initpos = 0
    _anchored = False
    for k in range(n):
        if not isP[k]:
            initpos = stream[k]["eop_units"]
            _anchored = True
    if not _anchored and n > 0:
        initpos = stream[0].get("bop_units", 0)
    orderable = [i for i in range(n) if isP[i] and (i + lead_time) < n]
    if not orderable:
        return order
    cum_d = [0] * n; cum_i = [0] * n; sd = 0; si = 0
    for w in range(n):
        if isP[w]:
            sd += sales[w]; si += ing[w]
        cum_d[w] = sd; cum_i[w] = si
    def need(w):
        return max(0, cum_d[w] - initpos - cum_i[w])
    R = {j: need(min(j + lead_time, n - 1)) for j in orderable}
    R[orderable[-1]] = need(n - 1)              # last orderable week must cover the tail
    M = float(cp); cnt = 0
    for j in orderable:
        cnt += 1
        M = max(M, R[j] / cnt)
    M = int(_math.ceil(M / cp) * cp)            # minimum feasible peak per-week order
    cumO = {}; nxt = 0
    for j in reversed(orderable):               # backward → min-peak cumulative targets
        cumO[j] = max(R[j], nxt - M); nxt = cumO[j]
    prev_r = 0
    for j in orderable:                          # round CUMULATIVE up to case pack, then diff
        r = max(prev_r, int(_math.ceil(cumO[j] / cp) * cp))
        order[j] = r - prev_r
        prev_r = r
    return order


def _compute_recomm_receipt(hc: int, ch: str, wk: int, eop_units: int) -> int:
    """Rolling OTB Forward Coverage model.

    Uses EOP (end-of-period units after this week's sales + receipts) as the
    starting inventory — more accurate than BOP because this week's sales
    deplete stock before the ordered receipt can arrive.

    receipt_needed = forward_demand          # planned sales over look-ahead window
                   + target_eop              # avg_weekly_demand × target_wos (buffer)
                   - eop_units               # stock on hand at end of this week
                   - pipeline                # OO already placed for next lead_time weeks
                                             # (avoids double-ordering receipts in-flight)

    Rounded *up* to nearest case-pack; floored at 0.
    """
    m = get_effective_metrics(hc)
    look_ahead = m["lead_time_weeks"] + m["safety_weeks"]
    if look_ahead <= 0:
        return 0
    fwd_demand = _FORWARD_DEMAND_INDEX.get((hc, ch, wk), 0)
    if fwd_demand <= 0:
        return 0
    # Use 8-week forward avg (same denominator as Pass 1b and WOS) so target_eop is consistent.
    wos_fwd   = _WOS_DEMAND_INDEX.get((hc, ch, wk), 0)
    weekly_avg = wos_fwd / WOS_WINDOW if WOS_WINDOW > 0 else 0
    target_eop = round(weekly_avg * get_target_wos(hc, ch))
    pipeline = _PIPELINE_INDEX.get((hc, ch, wk), 0)
    raw = max(0, fwd_demand + target_eop - eop_units - pipeline)
    cp = m["case_pack"]
    return int(_math.ceil(raw / cp) * cp) if (raw > 0 and cp > 0) else 0


def generate_wp_data(hierarchies=None) -> List[Dict]:
    global _FORWARD_DEMAND_INDEX, _WOS_DEMAND_INDEX
    hierarchies = hierarchies if hierarchies is not None else HIERARCHIES
    rows: List[Dict] = []
    demand_index: Dict[tuple, int] = {}  # (hc, ch, wk) → planned sales units

    # ── Pass 1: generate rows + collect demand per cell ───────────────────────
    for h in hierarchies:
        hc = h["hierarchy_code"]
        m = HIERARCHY_METRICS[hc]
        # Calibrate opening BOP so week 21 WOS ≈ (target_wos + 2) using 8-week window.
        bop = {}
        for _ch in CHANNELS:
            _shape = _reforecast_shape(hc, _ch)
            if _shape is not None:
                # History stream: opening stock off the reforecast forward demand.
                _fwd = sum(_history_cell_units(hc, _ch, wn, False, _shape)
                           for wn in range(22, 22 + WOS_WINDOW))
            else:
                _fwd = sum(
                    round(m["peak_units"] * CHANNEL_SPLIT[_ch] * _seasonal_curve(wn, m["peak_week"]))
                    for wn in range(22, 22 + WOS_WINDOW)
                )
            _fwd_avg = _fwd / WOS_WINDOW
            bop[_ch] = round(_fwd_avg * SUPPLY_PROFILE[hc]["open_wos"])

        for ch in CHANNELS:
            wh = WAREHOUSE_SUB_CHANNELS[ch]
            # When this stream has history, forward weeks reforecast from it and
            # actuals come straight from the seed — fully deterministic, no RNG. A
            # stream without history takes the parametric+RNG path below unchanged,
            # so a corpus with no sales_history.csv is byte-identical to before.
            shape = _reforecast_shape(hc, ch)
            for wk in FISCAL_WEEKS:
                week_num = wk % 100
                is_past     = wk < CURRENT_WEEK     # clock-derived (== week_num<20 at 202620)
                is_ongoing  = (wk == CURRENT_WEEK)
                is_planning = not is_past and not is_ongoing

                if shape is not None:
                    is_actual = is_past or is_ongoing
                    units = _history_cell_units(hc, ch, week_num, is_actual, shape)
                    _yr_dr = _scoped_fiscal_year() if is_actual else shape[2]
                    hist_dr = _SEED.history_discount(hc, ch, _yr_dr, week_num)
                    dr = hist_dr if hist_dr is not None else _dr_perc(week_num, m["peak_week"])
                else:
                    curve = _seasonal_curve(week_num, m["peak_week"])
                    dr    = _dr_perc(week_num, m["peak_week"])
                    units = round(m["peak_units"] * CHANNEL_SPLIT[ch] * curve * random.uniform(0.9, 1.1))

                # Optional explicit forecast (forecast.csv) for UNACTUALISED weeks:
                # planner-supplied expected_sales_units replaces the reforecast/curve
                # guess; oo_placed pre-loads the order plan (lands as receipts at W+LT
                # via the normal OOP chain). Absent cell / no file → engine forecast
                # unchanged (so a corpus without forecast.csv is byte-identical).
                seed_oop = 0
                if not is_past:
                    _fc_units, seed_oop = _forecast_override(hc, ch, wk)
                    if _fc_units is not None:
                        units = _fc_units
                aur   = round(m["air"] * (1 - dr), 2)
                sales_dollars = round(aur * units, 2)
                sales_cost    = round(m["auc"] * units, 2)
                gm_dollar     = round(sales_dollars - sales_cost, 2)
                gm_perc       = round((gm_dollar / sales_dollars) if sales_dollars else 0, 4)

                current_bop = round(bop[ch])
                # Past / ongoing: historical receipts. Demo = random noise; history
                # stream = deterministic ~sell-through buffer (no receipt history yet).
                # Planning: placeholder 0 — Pass 1b sets correct target-WOS receipts.
                if is_past or is_ongoing:
                    receipt_units = (round(units * 1.1) if shape is not None
                                     else round(units * 1.1 * random.uniform(0.8, 1.2)))
                else:
                    receipt_units = 0
                eop = max(0, current_bop - units + receipt_units)
                bop[ch] = eop

                if shape is not None:
                    actual_units = units if is_past else 0   # history units ARE the actuals
                else:
                    actual_units = round(units * random.uniform(0.78, 1.08)) if is_past else 0
                actual_dollars = round(actual_units * aur, 2)
                actual_cost    = round(actual_units * m["auc"], 2)
                md_units   = round(units * dr)
                md_dollars = round(md_units * m["air"] * dr, 2)

                demand_index[(hc, ch, wk)] = units
                rows.append({
                    "hierarchy_code": hc,
                    "l1_name": h["l1_name"],
                    "l2_name": h["l2_name"],
                    "channel": ch,
                    "sub_channel": wh,
                    "current_week": wk,
                    "written_sales_units":    units,
                    "written_sales_dollars":  sales_dollars,
                    "written_sales_cost":     sales_cost,
                    "written_aur":            aur,
                    "written_auc":            m["auc"],
                    "written_air":            m["air"],
                    "written_dr_perc":        dr,
                    "written_discount_dollars": round(units * m["air"] * dr, 2),
                    "written_gm_dollar":      gm_dollar,
                    "written_gm_perc":        gm_perc,
                    "bop_units":              current_bop,
                    "eop_units":              eop,
                    "bop_cost":               round(current_bop * m["auc"], 2),
                    "eop_cost":               round(eop * m["auc"], 2),
                    "on_order_placed_total_unit": seed_oop,        # 0 at baseline, or forecast.csv oo_placed (unactualised)
                    "total_receipt_units":    receipt_units,       # derived in chain (ingested + OOP[W-LT])
                    "ingested_receipt_units": receipt_units,       # INDEPENDENT supply baseline (immutable)
                    "oo_locked":              False,  # set in remap pass (tail weeks)
                    "recomm_receipt_units":   0,   # filled in Pass 3
                    "lead_time_weeks":        m["lead_time_weeks"],
                    "fwd_coverage_wks":       None,  # filled in get_agg_rows
                    "actualised":   is_past,
                    "is_ongoing":   is_ongoing,
                    "actual_sales_units":   actual_units,
                    "actual_sales_dollars": actual_dollars,
                    "actual_sales_cost":    actual_cost,
                    "markdown_units":       md_units,
                    "markdown_dollars":     md_dollars,
                })

    # ── Pass 1a: planning-week discounts from history ────────────────────────
    # Unactualised weeks have no real markdown yet. Seed each from last year's ACTUAL
    # discount for the same week (LY); fall back to LLY; then to this SKU's average
    # actual discount across TY actualised weeks. Built here (after actual-week draws)
    # so historical/actualised numbers stay unchanged. Only dollar/disc fields move —
    # units, receipts and the EOP chain are independent of the discount rate.
    global _LY_DISC, _LLY_DISC
    _LY_DISC, _LLY_DISC = _build_history_discounts()
    for h in hierarchies:
        hc = h["hierarchy_code"]
        m  = HIERARCHY_METRICS[hc]
        air, auc = m["air"], m["auc"]
        for ch in CHANNELS:
            # History streams set forward-week discounts in the main loop (from the
            # seed's LY/LLY discount), so skip them here — leave those values intact.
            if _stream_has_history(hc, ch):
                continue
            stream = [r for r in rows if r["hierarchy_code"] == hc and r["channel"] == ch]
            actual_drs = [r["written_dr_perc"] for r in stream if r["actualised"]]
            avg_ty = round(sum(actual_drs) / len(actual_drs), 4) if actual_drs else 0.0
            for r in stream:
                if r["actualised"] or r.get("is_ongoing"):
                    continue
                wn = r["current_week"] % 100
                l1 = r["l1_name"]
                dr = _LY_DISC.get((l1, hc, ch, wn))
                if dr is None:
                    dr = _LLY_DISC.get((l1, hc, ch, wn))
                if dr is None:
                    dr = avg_ty
                units = r["written_sales_units"]
                aur   = round(air * (1 - dr), 2)
                r["written_dr_perc"]           = dr
                r["written_aur"]               = aur
                r["written_sales_dollars"]     = round(aur * units, 2)
                r["written_discount_dollars"]  = round(units * air * dr, 2)
                r["written_gm_dollar"]         = round(r["written_sales_dollars"] - r["written_sales_cost"], 2)
                r["written_gm_perc"]           = round(r["written_gm_dollar"] / r["written_sales_dollars"]
                                                       if r["written_sales_dollars"] else 0, 4)
                r["markdown_units"]            = round(units * dr)
                r["markdown_dollars"]          = round(r["markdown_units"] * air * dr, 2)

    # ── Build demand indexes ──────────────────────────────────────────────────
    wk_pos = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}
    _FORWARD_DEMAND_INDEX = {}
    _WOS_DEMAND_INDEX = {}
    for (hc, ch, wk) in demand_index:
        m   = HIERARCHY_METRICS[hc]
        la  = m["lead_time_weeks"] + m["safety_weeks"]
        idx = wk_pos[wk]
        _FORWARD_DEMAND_INDEX[(hc, ch, wk)] = sum(
            demand_index.get((hc, ch, fw), 0)
            for fw in FISCAL_WEEKS[idx + 1: idx + 1 + la]
        )
        _WOS_DEMAND_INDEX[(hc, ch, wk)] = sum(
            demand_index.get((hc, ch, fw), 0)
            for fw in FISCAL_WEEKS[idx + 1: idx + 1 + WOS_WINDOW]
        )

    # ── Pass 1b: set planning-week receipts so WOS ≈ target_wos ──────────────
    # Walk each SKU×channel stream forward from CURRENT_WEEK's EOP; set receipt
    # = units needed to bring EOP up to (target_wos × fwd_avg_8wk) each week.
    row_lkp: Dict[tuple, Dict] = {
        (r["hierarchy_code"], r["channel"], r["current_week"]): r for r in rows
    }
    for h in hierarchies:
        hc = h["hierarchy_code"]
        m  = HIERARCHY_METRICS[hc]
        cp = m["case_pack"]
        for ch in CHANNELS:
            ongoing = row_lkp.get((hc, ch, CURRENT_WEEK))
            if ongoing:
                prev_eop = ongoing["eop_units"]
            else:
                # Future season (no in-flight week in this year): open from the
                # calibrated opening BOP set in Pass 1, NOT zero — otherwise the whole
                # year would start dry. (2026 always has an ongoing week → unchanged.)
                _first = row_lkp.get((hc, ch, FISCAL_WEEKS[0]))
                prev_eop = _first["bop_units"] if _first else 0
            for wk in FISCAL_WEEKS:
                r = row_lkp.get((hc, ch, wk))
                if not r or r.get("actualised") or r.get("is_ongoing"):
                    continue
                # BOP = previous week's EOP
                r["bop_units"] = prev_eop
                r["bop_cost"]  = round(prev_eop * m["auc"], 2)
                sales = r["written_sales_units"]
                eop_no_rcpt = max(0, prev_eop - sales)
                # Committed (ingested) supply = the pre-season BUY, not an auto-top-up.
                # Through `commit_through` the buyer holds (target_wos × commit_mult) weeks
                # of cover; after that the committed buy is exhausted → receipt = 0 and the
                # planner must reorder (place OO) to avoid running out. This is what gives
                # the replenishment engine real work instead of a pre-balanced season.
                wos_dem  = _WOS_DEMAND_INDEX.get((hc, ch, wk), 0)
                fwd_avg8 = wos_dem / WOS_WINDOW if WOS_WINDOW > 0 else 0
                prof = SUPPLY_PROFILE[hc]
                if (wk % 100) <= prof["commit_through"]:
                    target_eop = round(m["target_wos"] * prof["commit_mult"] * fwd_avg8)
                    if target_eop <= eop_no_rcpt:
                        receipt = 0
                    else:
                        raw     = target_eop - eop_no_rcpt
                        receipt = int(_math.ceil(raw / cp) * cp) if cp > 0 else int(raw)
                else:
                    receipt = 0   # committed buy exhausted — planner reorders from here
                eop = eop_no_rcpt + receipt
                # This committed-buy receipt schedule IS the ingested supply baseline.
                r["total_receipt_units"]         = receipt
                r["ingested_receipt_units"]      = receipt   # independent supply (immutable)
                r["on_order_placed_total_unit"]  = _forecast_override(hc, ch, wk)[1]   # forecast.csv plan (else 0); planner orders ON TOP
                r["eop_units"] = eop
                r["eop_cost"]  = round(eop * m["auc"], 2)
                prev_eop = eop

    # ── Historical OO Placed (display) is NOT stored here ────────────────────────
    # Actualised/ongoing weeks keep OOP = 0 in WP_DATA so the recomm-pipeline math
    # reads clean planner-order data (no historical pollution). The display value
    # OOP[W] = ingested[W+LT] is recomputed off EFFECTIVE LT on every read in
    # get_agg_rows() — that way it tracks runtime lead-time changes and never goes
    # stale against the receipt offset. (Earlier this was a base-LT Pass 1c backfill
    # written into WP_DATA, which both went stale on LT change and leaked into the
    # pipeline index for early planning weeks.)

    # ── OO Placed locks (tail weeks) ─────────────────────────────────────────────
    # OOP[W] = NEW orders the planner places; they arrive at W+LT and ADD to Rcpt
    # (Rcpt[W] = ingested[W] + OOP[W−LT]). Baseline OOP = 0 (set above). A week is
    # locked when W+LT lands past season end — that order could never be received.
    for h in hierarchies:
        hc = h["hierarchy_code"]
        lt = HIERARCHY_METRICS[hc]["lead_time_weeks"]
        for ch in CHANNELS:
            for wk in FISCAL_WEEKS:
                r = row_lkp.get((hc, ch, wk))
                if not r or r.get("actualised") or r.get("is_ongoing"):
                    continue
                r["oo_locked"] = (_week_offset(wk, lt) is None)

    # ── Recomm pipeline index (avoid double-ordering stock already coming) ──────
    # = total receipts ARRIVING over the next LT weeks = ingested supply + any
    # planner orders landing there. At baseline OOP=0 → just ingested supply.
    _PIPELINE_INDEX.clear()
    for (hc, ch, wk) in demand_index:
        m   = HIERARCHY_METRICS[hc]
        lt  = m["lead_time_weeks"]
        idx = wk_pos[wk]
        _PIPELINE_INDEX[(hc, ch, wk)] = sum(
            row_lkp.get((hc, ch, fw), {}).get("ingested_receipt_units", 0)
            for fw in FISCAL_WEEKS[idx + 1: idx + 1 + lt]
        )

    # ── Pass 3: backfill recomm_receipt_units (Rolling OTB Forward Coverage) ──
    for r in rows:
        if r["actualised"] or r.get("is_ongoing"):
            r["recomm_receipt_units"] = 0
        else:
            r["recomm_receipt_units"] = _compute_recomm_receipt(
                r["hierarchy_code"], r["channel"], r["current_week"],
                r["eop_units"],
            )

    return rows


def generate_ty_ly_data() -> List[Dict]:
    rows = []
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m = HIERARCHY_METRICS[hc]
        for ch in CHANNELS:
            for wk in FISCAL_WEEKS:
                week_num = wk % 100
                curve = _seasonal_curve(week_num, m["peak_week"])
                ty_units = round(m["peak_units"] * CHANNEL_SPLIT[ch] * curve * random.uniform(0.9, 1.1))
                ly_units = round(ty_units * random.uniform(0.85, 1.15))
                lly_units = round(ly_units * random.uniform(0.82, 1.12))
                ty_dr  = _dr_perc(week_num, m["peak_week"])
                ly_dr  = _LY_DISC.get((h["l1_name"], hc, ch, week_num), ty_dr)
                lly_dr = _LLY_DISC.get((h["l1_name"], hc, ch, week_num), ty_dr)
                # History stream: override the RNG draws above with the seed's real
                # actuals by ABSOLUTE year (TY=this year, LY=-1, LLY=-2). NOTE: this
                # TY_LY_DATA table is now only the demo/no-history fallback + the
                # orphaned /ty-ly endpoint — history streams take the year-relative
                # path in get_agg_rows. (RNG still drew, so no-history is unchanged.)
                _ty_year  = wk // 100
                if _stream_has_history(hc, ch):
                    _hu = _SEED.history_units(hc, ch, _ty_year, week_num)
                    if _hu is not None:
                        ty_units = int(_hu)
                        _hd = _SEED.history_discount(hc, ch, _ty_year, week_num)
                        if _hd is not None:
                            ty_dr = _hd
                    _hu = _SEED.history_units(hc, ch, _ty_year - 1, week_num)
                    if _hu is not None:
                        ly_units = int(_hu)
                        _hd = _SEED.history_discount(hc, ch, _ty_year - 1, week_num)
                        if _hd is not None:
                            ly_dr = _hd
                    _hu = _SEED.history_units(hc, ch, _ty_year - 2, week_num)
                    if _hu is not None:
                        lly_units = int(_hu)
                        _hd = _SEED.history_discount(hc, ch, _ty_year - 2, week_num)
                        if _hd is not None:
                            lly_dr = _hd
                ty_dollars = round(ty_units * m["air"] * (1 - ty_dr), 2)
                ly_dollars = round(ly_units * m["air"] * (1 - ly_dr), 2)
                lly_dollars = round(lly_units * m["air"] * (1 - lly_dr), 2)
                # Retail (ticket = units × AIR) + discount $ per year — feeds the
                # TY/LY/LLY tab's AUR / Disc% / Disc$ columns. AIR is per-SKU constant
                # (no per-year AIR input), so only AUR/Disc%/Disc$ vary across years.
                ty_retail  = round(ty_units  * m["air"], 2)
                ly_retail  = round(ly_units  * m["air"], 2)
                lly_retail = round(lly_units * m["air"], 2)
                rows.append({
                    "hierarchy_code": hc,
                    "l1_name": h["l1_name"],
                    "l2_name": h["l2_name"],
                    "channel": ch,
                    "current_week": wk,
                    "compared_week":     wk - 100,   # same week, prior year
                    "compared_week_lly": wk - 200,   # same week, two years prior
                    "ty_units": ty_units,
                    "ly_units": ly_units,
                    "lly_units": lly_units,
                    "ty_dollars": ty_dollars,
                    "ly_dollars": ly_dollars,
                    "lly_dollars": lly_dollars,
                    "ty_dr_perc": ty_dr,
                    "ly_dr_perc": ly_dr,
                    "lly_dr_perc": lly_dr,
                    "ly_retail_dollars":   ly_retail,
                    "lly_retail_dollars":  lly_retail,
                    "ly_disc_dollars":     round(ly_retail  - ly_dollars,  2),
                    "lly_disc_dollars":    round(lly_retail - lly_dollars, 2),
                    "units_var": ty_units - ly_units,
                    "units_var_perc": round((ty_units - ly_units) / ly_units if ly_units else 0, 4),
                    "dollars_var": round(ty_dollars - ly_dollars, 2),
                    "dollars_var_perc": round((ty_dollars - ly_dollars) / ly_dollars if ly_dollars else 0, 4),
                })
    return rows


def generate_scenario_data() -> List[Dict]:
    rows = []
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m = HIERARCHY_METRICS[hc]
        for scenario in [0, 1, 2]:  # 0=base, 1=optimistic, 2=pessimistic
            for pct_off in [0.0, 0.10, 0.20, 0.30]:
                for ch in CHANNELS:
                    for wk in FISCAL_WEEKS[-16:]:  # last 16 weeks (planning horizon)
                        week_num = wk % 100
                        curve = _seasonal_curve(week_num, m["peak_week"])
                        # elasticity: discount drives more units
                        unit_lift = 1 + pct_off * 1.5 * (0.8 + scenario * 0.2)
                        units = round(m["peak_units"] * CHANNEL_SPLIT[ch] * curve * unit_lift)
                        aur = round(m["air"] * (1 - pct_off), 2)
                        sales_dollars = round(aur * units, 2)
                        gm = round((sales_dollars - m["auc"] * units), 2)
                        rows.append({
                            "hierarchy_code": hc,
                            "l1_name": h["l1_name"],
                            "l2_name": h["l2_name"],
                            "channel": ch,
                            "current_week": wk,
                            "scenario": scenario,
                            "scenario_name": ["Base", "Optimistic", "Pessimistic"][scenario],
                            "percent_off": pct_off,
                            "w_sls_u": units,
                            "w_sls_dollars": sales_dollars,
                            "w_aur": aur,
                            "w_gm_dollars": gm,
                            "w_gm_percent": round(gm / sales_dollars if sales_dollars else 0, 4),
                        })
    return rows


def _next_new_sku_hc() -> int:
    """Derive next hierarchy_code from DB max (floor at 20001)."""
    return max(db_get_max_new_sku_hc() + 1, 20001)


def get_new_skus() -> List[Dict]:
    """Return all user-created SKUs from persistent storage."""
    return db_get_all_new_skus()


def add_new_sku(sku: Dict) -> Dict:
    """Assign hierarchy_code, persist to DB, return the full record."""
    hc = _next_new_sku_hc()
    sku["hierarchy_code"] = hc
    sku["feed_type"] = "new"
    db_insert_new_sku(hc, sku)
    return sku


def delete_sku(hierarchy_code: int) -> bool:
    """Delete a user-created SKU from DB. Returns True if deleted."""
    return db_delete_new_sku(hierarchy_code)


# ── CSV seed override (generation-feeding globals) ────────────────────────────
# Replace the demo literals with the CSV catalog BEFORE generation runs, so every
# downstream structure (RNG sales curve, supply, demand indexes, budgets) is built
# from the seed. Order of HIERARCHIES + NEW_SKU_HIERARCHIES is preserved from the
# CSV so the RNG draw sequence — and thus byte-identical demo output — is kept when
# the seed equals the demo. Descriptors + lifecycle anchors are overridden later,
# just before the master-SKU seed (they aren't needed for generation).
if _SEED is not None:
    HIERARCHIES = list(_SEED.hierarchies)
    NEW_SKU_HIERARCHIES = list(_SEED.new_hierarchies)
    NEW_SKU_HCS = set(_SEED.new_hcs)
    HIERARCHY_METRICS = dict(_SEED.metrics)
    SUPPLY_PROFILE = dict(_SEED.supply)
    NEW_SKU_LIFECYCLE = dict(_SEED.new_lifecycle)
    BUDGET_DATA = dict(_SEED.budgets)
    CATEGORIES = list(dict.fromkeys(h["l1_name"] for h in HIERARCHIES))


# ── Pre-generate on import (multi-year, RNG-order-preserving) ─────────────────────
# Order matters: generate 2026 FIRST, then TY/LY + scenario, so their RNG draws sit
# at the exact same offset as before multi-year → byte-identical. The view-only
# future seasons (2027/28) are generated LAST; their RNG is new but only shapes
# future-year data. Demand indexes are the union across years (week_code keys carry
# the year, so no collision); 2026 values are preserved from the first pass.
WP_DATA = generate_wp_data()                       # 2026 season (identical RNG block)
_fwd_acc = dict(_FORWARD_DEMAND_INDEX)
_wos_acc = dict(_WOS_DEMAND_INDEX)
TY_LY_DATA = generate_ty_ly_data()                 # same RNG offset as pre-multi-year
SCENARIO_DATA = generate_scenario_data()           # same RNG offset as pre-multi-year
for _yr in SELECTABLE_YEARS:
    if _yr == DEFAULT_YEAR:
        continue
    with _scoped_year(_yr):
        WP_DATA = WP_DATA + generate_wp_data()      # append future season
        _fwd_acc.update(_FORWARD_DEMAND_INDEX)
        _wos_acc.update(_WOS_DEMAND_INDEX)

# Pre-seeded New SKUs generated LAST (own streams), so the originals' RNG is untouched.
# Each New SKU is a full season per year; rows BEFORE its activation week are dropped
# (no metrics pre-launch). Disc% borrow from the tagged Old SKU is applied at read time.
for _yr in SELECTABLE_YEARS:
    with _scoped_year(_yr):
        WP_DATA = WP_DATA + generate_wp_data(hierarchies=NEW_SKU_HIERARCHIES)
        _fwd_acc.update(_FORWARD_DEMAND_INDEX)
        _wos_acc.update(_WOS_DEMAND_INDEX)
WP_DATA = [
    r for r in WP_DATA
    if not (r["hierarchy_code"] in NEW_SKU_HCS
            and r["current_week"] < NEW_SKU_LIFECYCLE[r["hierarchy_code"]]["activation_week"])
]
# Now the New SKUs are real catalog members (for filters, active-set, master page).
HIERARCHIES = HIERARCHIES + NEW_SKU_HIERARCHIES
CATEGORIES = list(dict.fromkeys(h["l1_name"] for h in HIERARCHIES))
_FORWARD_DEMAND_INDEX = _fwd_acc
_WOS_DEMAND_INDEX = _wos_acc

# ── Override / Snapshot layer ──────────────────────────────────────────────────
from datetime import datetime
from database import (
    init_db,
    db_get_overrides, db_upsert_override, db_clear_overrides, db_replace_overrides,
    db_batch_upsert_overrides, db_batch_edit,
    db_list_snapshots, db_get_snapshot, db_insert_snapshot, db_delete_snapshot, db_rename_snapshot,
    db_get_all_sku_settings, db_upsert_sku_setting, db_replace_sku_settings,
    db_get_all_channel_settings, db_upsert_channel_setting, db_replace_channel_settings,
    db_get_all_new_skus, db_get_max_new_sku_hc, db_insert_new_sku, db_delete_new_sku,
    db_delete_override,
    db_log_audit, db_get_audit_log,
    db_get_setting, db_set_setting, mutation_version,
    db_replace_wp_facts, db_load_wp_facts, db_replace_fiscal_calendar,
    db_replace_master_sku, db_load_master_sku, db_set_master_tag,
    db_init_placeholders, db_list_placeholders, db_insert_placeholder, db_delete_placeholder,
)

init_db()  # create tables on first import; no-op if already exist
db_init_placeholders()

# ── Materialize seed into the SQLite "warehouse", then run the engine off it ──────
# The generated rows + fiscal calendar are written to DB tables (source of truth,
# real joins), then WP_DATA is RELOADED from wp_facts so the engine operates on the
# warehouse copy. Round-trip is lossless (JSON payload) → byte-identical to the
# in-memory generation. Rebuilt from seed on every startup; overrides persist apart.
db_replace_fiscal_calendar(FISCAL_CALENDAR)
db_replace_wp_facts(WP_DATA)
WP_DATA = db_load_wp_facts()

# Baseline (seed) discount per (hc, week_code, channel) — the source a New SKU borrows
# from its tagged Old SKU. O(1) lookup built once; Old-SKU seed dr is immutable.
_BASELINE_DR = {(r["hierarchy_code"], r["current_week"], r["channel"]): r["written_dr_perc"]
                for r in WP_DATA}

# ── Master SKU catalog ───────────────────────────────────────────────────────────
# Descriptive (display-only) attributes for the existing 8 SKUs.
_SKU_DESCRIPTORS = {
    10001: ("Blue",   "US 9"),
    10002: ("White",  "US 10"),
    10003: ("Black",  "US 8"),
    10004: ("Tan",    "US 7"),
    10005: ("Indigo", "32x32"),
    10006: ("Black",  "M"),
    10007: ("Grey",   "L"),
    10008: ("Navy",   "M"),
}

# Lifecycle anchors. The 8 originals are long-lived "Old" SKUs: activated in FY2024,
# deactivating far in the future → active in every viewable year (2026/27/28).
_OLD_ACTIVATION_WK   = 202401
_OLD_DEACTIVATION_WK = 202852

# ── CSV seed override (master-catalog globals) ────────────────────────────────
# Descriptors (color/size) + the Old-SKU lifecycle anchors feed _build_master_sku_seed
# only; override them from the seed here, after their literal definitions and before
# the seed is built. New-SKU color/size/lifecycle already came from NEW_SKU_LIFECYCLE.
if _SEED is not None:
    _SKU_DESCRIPTORS = dict(_SEED.descriptors)
    if _SEED.old_activation is not None:
        _OLD_ACTIVATION_WK = _SEED.old_activation
    if _SEED.old_deactivation is not None:
        _OLD_DEACTIVATION_WK = _SEED.old_deactivation


def _build_master_sku_seed() -> List[Dict]:
    """Seed master_sku: 8 long-lived Old products + the pre-seeded New SKUs."""
    rows: List[Dict] = []
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m = HIERARCHY_METRICS[hc]
        if hc in NEW_SKU_HCS:
            lc = NEW_SKU_LIFECYCLE[hc]
            rows.append({
                "hierarchy_code": hc, "l1_name": h["l1_name"], "l2_name": h["l2_name"],
                "sku_code": h.get("sku_code"), "color": lc["color"], "size": lc["size"],
                "air": m["air"], "auc": m["auc"],
                "activation_week": lc["activation_week"], "deactivation_week": lc["deactivation_week"],
                "status_seed": "New", "tagged_to": lc["tagged_to"],
            })
        else:
            color, size = _SKU_DESCRIPTORS.get(hc, (None, None))
            rows.append({
                "hierarchy_code": hc, "l1_name": h["l1_name"], "l2_name": h["l2_name"],
                "sku_code": h.get("sku_code"), "color": color, "size": size,
                "air": m["air"], "auc": m["auc"],
                "activation_week": _OLD_ACTIVATION_WK, "deactivation_week": _OLD_DEACTIVATION_WK,
                "status_seed": "Old", "tagged_to": None,
            })
    return rows


db_replace_master_sku(_build_master_sku_seed())
MASTER_SKU = db_load_master_sku()
_MASTER_BY_HC = {r["hierarchy_code"]: r for r in MASTER_SKU}


_CAL_ORDER = {r["week_code"]: i for i, r in enumerate(FISCAL_CALENDAR)}


def get_sku_status(hierarchy_code: int, as_of_week: int) -> str:
    """Derived Old/New: New within 52 weeks of activation (by viewed time), else Old."""
    rec = _MASTER_BY_HC.get(hierarchy_code)
    if not rec:
        return "Old"
    act = _CAL_ORDER.get(rec["activation_week"])
    now = _CAL_ORDER.get(as_of_week)
    if act is None or now is None:
        return rec["status_seed"]
    # New until 52 weeks past activation (incl. pre-launch upcoming SKUs); then Old.
    return "New" if (now - act) < 52 else "Old"


def get_master_catalog(as_of_week: int = None) -> List[Dict]:
    """Master SKU catalog with status (Old/New) derived for the given as-of week."""
    aw = as_of_week or CURRENT_WEEK
    out = []
    for r in MASTER_SKU:
        d = dict(r)
        d["status"] = get_sku_status(r["hierarchy_code"], aw)
        out.append(d)
    return out


def set_sku_tag(hierarchy_code: int, tagged_to) -> bool:
    """Set/clear the New→Old Disc% borrow tag and refresh the in-memory catalog."""
    global MASTER_SKU, _MASTER_BY_HC
    ok = db_set_master_tag(hierarchy_code, tagged_to)
    MASTER_SKU = db_load_master_sku()
    _MASTER_BY_HC = {r["hierarchy_code"]: r for r in MASTER_SKU}
    return ok


# ── Placeholders (full editable what-if SKUs cloned from an Old SKU) ──────────────
# A placeholder is MATERIALIZED as a hidden synthetic SKU: on create we deep-clone the
# source Old SKU's base rows across ALL years into a new hierarchy_code (PLACEHOLDER_HC_BASE
# + registry id) and mirror its index entries, so the placeholder behaves identically to
# the source until edited. From then on every WP action (row edits, Accept Recomm,
# top-down, shift, SKU settings, target WOS, snapshots) works on it for free — edits are
# keyed by the placeholder's hc, fully independent of the source. The placeholder hcs are
# tracked in PLACEHOLDER_HCS and EXCLUDED from every main-app view (portfolio, exceptions,
# filters, master catalog); they surface only on the dedicated placeholders page.
PLACEHOLDER_HC_BASE = 90000
PLACEHOLDER_HCS: set = set()

# Index dicts mirrored when a placeholder is materialized (keyed (hc, channel, week)).
_PLACEHOLDER_INDEXES = (_FORWARD_DEMAND_INDEX, _WOS_DEMAND_INDEX, _PIPELINE_INDEX)


def _placeholder_hc(pid: int) -> int:
    return PLACEHOLDER_HC_BASE + int(pid)


def _materialize_placeholder(ph: Dict) -> int:
    """Clone the source Old SKU into a synthetic placeholder SKU. Idempotent."""
    import copy
    phc = _placeholder_hc(ph["id"])
    src = int(ph["source_hc"])
    if phc in HIERARCHY_METRICS:          # already materialized this session
        PLACEHOLDER_HCS.add(phc)
        return phc
    if src not in HIERARCHY_METRICS:      # source vanished — skip gracefully
        return phc

    # 1. Clone every base row of the source SKU (all years, all channels).
    cloned = []
    for r in WP_DATA:
        if r["hierarchy_code"] != src:
            continue
        c = copy.deepcopy(r)
        c["hierarchy_code"] = phc
        if "l2_name" in c:
            c["l2_name"] = ph["name"]
        cloned.append(c)
    WP_DATA.extend(cloned)

    # 2. Mirror the source's index entries (no re-derivation → identical behavior).
    for idx in _PLACEHOLDER_INDEXES:
        for k, v in list(idx.items()):
            if k[0] == src:
                idx[(phc,) + k[1:]] = v
    for k, v in list(_BASELINE_DR.items()):
        if k[0] == src:
            _BASELINE_DR[(phc,) + k[1:]] = v

    # 3. Register catalog identity + metrics (copied from source).
    src_h = next((h for h in HIERARCHIES if h["hierarchy_code"] == src), {})
    HIERARCHIES.append({
        "hierarchy_code": phc,
        "l1_name": src_h.get("l1_name", "Placeholder"),
        "l2_name": ph["name"],
        "sku_code": f"PH-{ph['id']}",
    })
    HIERARCHY_METRICS[phc] = dict(HIERARCHY_METRICS[src])
    PLACEHOLDER_HCS.add(phc)
    _bump_mem_version()   # WP_DATA changed in memory → invalidate agg cache
    return phc


def _dematerialize_placeholder(phc: int) -> None:
    """Tear a placeholder SKU out of every engine structure + drop its overrides."""
    global WP_DATA
    from database import db_delete_sku_setting
    if phc not in PLACEHOLDER_HCS and phc not in HIERARCHY_METRICS:
        return
    WP_DATA = [r for r in WP_DATA if r["hierarchy_code"] != phc]
    for idx in _PLACEHOLDER_INDEXES:
        for k in [k for k in idx if k[0] == phc]:
            idx.pop(k, None)
    for k in [k for k in _BASELINE_DR if k[0] == phc]:
        _BASELINE_DR.pop(k, None)
    HIERARCHIES[:] = [h for h in HIERARCHIES if h["hierarchy_code"] != phc]
    HIERARCHY_METRICS.pop(phc, None)
    _SKU_SETTINGS_OVERRIDES.pop(phc, None)
    PLACEHOLDER_HCS.discard(phc)
    # Drop this placeholder's cell + setting overrides so a re-created id starts clean.
    for key in [k for k in db_get_overrides() if k.startswith(f"{phc}_")]:
        db_delete_override(key)
    db_delete_sku_setting(phc)
    _bump_mem_version()   # WP_DATA changed in memory → invalidate agg cache


def _materialize_all_placeholders() -> None:
    """Re-materialize every registered placeholder — run once at startup."""
    for ph in db_list_placeholders():
        _materialize_placeholder(ph)


def get_placeholders() -> List[Dict]:
    """Registry rows annotated with their synthetic hierarchy_code."""
    return [{**p, "placeholder_hc": _placeholder_hc(p["id"])} for p in db_list_placeholders()]


def add_placeholder(name: str, source_hc: int) -> Dict:
    from datetime import datetime
    rec = db_insert_placeholder(name, source_hc, datetime.utcnow().isoformat())
    phc = _materialize_placeholder(rec)
    return {**rec, "placeholder_hc": phc}


def delete_placeholder(pid: int) -> bool:
    _dematerialize_placeholder(_placeholder_hc(pid))
    return db_delete_placeholder(pid)


def get_active_skus(fiscal_year: int, as_of_week: int = None) -> List[int]:
    """SKUs whose lifecycle overlaps the given fiscal year (master ⋈ calendar)."""
    yr_first = int(f"{fiscal_year}01")
    yr_last = int(f"{fiscal_year}52")
    def pos(wk):
        return _CAL_ORDER.get(wk, -1)
    return [
        r["hierarchy_code"] for r in MASTER_SKU
        if pos(r["activation_week"]) <= pos(yr_last) and pos(r["deactivation_week"]) >= pos(yr_first)
    ]

# ── Per-SKU editable settings ──────────────────────────────────────────────────
EDITABLE_SKU_FIELDS = {"case_pack", "lead_time_weeks", "safety_weeks", "target_wos"}


def recompute_recomm_for_sku(hc: int):
    """Rebuild forward demand index + WOS index + recomm_receipt for one SKU after settings change."""
    m = get_effective_metrics(hc)
    look_ahead = m["lead_time_weeks"] + m["safety_weeks"]
    wk_pos = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}

    # Rebuild demand map for this SKU from WP_DATA
    demand_map: Dict[tuple, int] = {
        (hc, r["channel"], r["current_week"]): r["written_sales_units"]
        for r in WP_DATA if r["hierarchy_code"] == hc
    }
    oo_map: Dict[tuple, int] = {
        (hc, r["channel"], r["current_week"]): r["on_order_placed_total_unit"]
        for r in WP_DATA if r["hierarchy_code"] == hc
    }
    ing_map: Dict[tuple, int] = {
        (hc, r["channel"], r["current_week"]): r.get("ingested_receipt_units", 0)
        for r in WP_DATA if r["hierarchy_code"] == hc
    }

    # Rewrite demand + pipeline indexes for this SKU
    lt = m["lead_time_weeks"]
    for ch in CHANNELS:
        for wk in FISCAL_WEEKS:
            idx = wk_pos[wk]
            _FORWARD_DEMAND_INDEX[(hc, ch, wk)] = sum(
                demand_map.get((hc, ch, fw), 0)
                for fw in FISCAL_WEEKS[idx + 1: idx + 1 + look_ahead]
            )
            _WOS_DEMAND_INDEX[(hc, ch, wk)] = sum(
                demand_map.get((hc, ch, fw), 0)
                for fw in FISCAL_WEEKS[idx + 1: idx + 1 + WOS_WINDOW]
            )
            # Pipeline = receipts ARRIVING next LT weeks = ingested + planner OOP
            # landing there (Rcpt[fw] = ingested[fw] + OOP[fw−LT]). Must match the
            # other rebuild paths so recomm is consistent on fresh load too.
            _PIPELINE_INDEX[(hc, ch, wk)] = sum(
                ing_map.get((hc, ch, fw), 0)
                + oo_map.get((hc, ch, _week_offset(fw, -lt)), 0)
                for fw in FISCAL_WEEKS[idx + 1: idx + 1 + lt]
            )

    # Recompute recomm_receipt_units for all rows of this SKU
    for r in WP_DATA:
        if r["hierarchy_code"] != hc:
            continue
        if r["actualised"] or r.get("is_ongoing"):
            r["recomm_receipt_units"] = 0
        else:
            r["recomm_receipt_units"] = _compute_recomm_receipt(
                hc, r["channel"], r["current_week"],
                r["eop_units"],
            )


def _recalibrate_pass1b(hc: int, channels: List[str] = None):
    """Refresh recomm + pipeline for one SKU after a setting change.

    Under the OOP/ingested model the supply baseline (ingested_receipt_units) is
    FIXED backend data and the planner owns OO Placed — so a target_wos / lead_time
    change must NOT rewrite orders. It only changes the recommendation (target_EOP,
    look-ahead, rounding) and which tail weeks are locked. So this just rebuilds the
    pipeline index + recomm; OOP and ingested supply are left untouched.
    """
    _channels = channels if channels is not None else CHANNELS
    _rebuild_pipeline_and_recomm([hc], _channels)


def update_sku_setting(hc: int, field: str, value) -> Dict:
    """Update one editable SKU field, persist to DB, recompute recomm. Returns effective metrics."""
    global _SKU_SETTINGS_OVERRIDES
    if field not in EDITABLE_SKU_FIELDS:
        raise ValueError(f"'{field}' not editable. Allowed: {EDITABLE_SKU_FIELDS}")
    current = dict(_SKU_SETTINGS_OVERRIDES.get(hc, {}))
    current[field] = int(value)
    db_upsert_sku_setting(hc, current)
    _SKU_SETTINGS_OVERRIDES[hc] = current
    recompute_recomm_for_sku(hc)
    # Any setting that changes the receipt plan → re-calibrate Pass 1b receipts for
    # all channels so OOP/Rcpt/locks reflect the new value without a restart:
    #   target_wos     → target_EOP changes
    #   lead_time_weeks→ order↔arrival shift AND which tail weeks are locked
    #   case_pack      → receipt rounding
    #   safety_weeks   → look-ahead window
    if field in ("target_wos", "lead_time_weeks", "case_pack", "safety_weeks"):
        _recalibrate_pass1b(hc)
    return get_effective_metrics(hc)


def _load_sku_settings():
    """Load persisted SKU setting overrides from DB and recompute affected SKUs."""
    global _SKU_SETTINGS_OVERRIDES
    _SKU_SETTINGS_OVERRIDES = {int(k): v for k, v in db_get_all_sku_settings().items()}
    for hc in _SKU_SETTINGS_OVERRIDES:
        if hc in HIERARCHY_METRICS:
            recompute_recomm_for_sku(hc)


_load_sku_settings()


def reset_sku_settings(hc: int) -> Dict:
    """Reset all SKU settings (lead_time, case_pack, safety_weeks, target_wos) to
    base HIERARCHY_METRICS defaults. Also clears channel-level target WOS overrides
    and recalibration leftover OO Placed overrides so the row plan returns clean.

    Sales edits are preserved (only the OO field is stripped from mixed overrides).
    Returns effective metrics after reset.
    """
    global _SKU_SETTINGS_OVERRIDES, _CHANNEL_TARGET_WOS
    from database import db_delete_sku_setting, db_delete_channel_setting, db_delete_override

    # 1. SKU-level setting overrides → base metrics
    _SKU_SETTINGS_OVERRIDES.pop(hc, None)
    db_delete_sku_setting(hc)

    # 2. Channel-level target WOS overrides for every channel of this SKU
    for ch in CHANNELS:
        ck = f"{hc}_{ch}"
        if ck in _CHANNEL_TARGET_WOS:
            _CHANNEL_TARGET_WOS.pop(ck, None)
            db_delete_channel_setting(ck)

    # 3. Strip recalibration-written OO Placed overrides (preserve sales edits)
    overrides = db_get_overrides()
    planning_wks = [w for w in FISCAL_WEEKS if w > CURRENT_WEEK]
    updates: Dict[str, Dict] = {}
    for ch in CHANNELS:
        for wk in planning_wks:
            k = _ovr_key(hc, wk, ch)
            if k not in overrides:
                continue
            entry = dict(overrides[k])
            if entry.get("_last_edited") == "on_order_placed_total_unit":
                db_delete_override(k)
            elif "on_order_placed_total_unit" in entry:
                entry.pop("on_order_placed_total_unit", None)
                updates[k] = entry
    if updates:
        db_batch_upsert_overrides(updates)

    # 4. Rebuild pipeline + recomm for this SKU (back to base-metric baseline)
    _rebuild_pipeline_and_recomm([hc])
    recompute_recomm_for_sku(hc)
    return get_effective_metrics(hc)


def reset_channel_target_wos(hc: int, channel: str) -> int:
    """Remove channel-level target WOS override → falls back to SKU-level default.

    Clears all on_order_placed_total_unit overrides for this SKU×channel so rows
    return to clean (unmodified) state — no amber highlight left by recalibration.
    Returns the effective target_wos after reset.
    """
    global _CHANNEL_TARGET_WOS
    from database import db_delete_channel_setting
    ch_key = f"{hc}_{channel}"
    _CHANNEL_TARGET_WOS.pop(ch_key, None)
    db_delete_channel_setting(ch_key)

    # Clear OO Placed overrides for all planning weeks of this SKU×channel.
    # These were written by the previous _recalibrate_pass1b call; removing them
    # returns rows to the WP_DATA baseline (original Pass 1b values = SKU default).
    overrides = db_get_overrides()
    planning_wks = [w for w in FISCAL_WEEKS if w > CURRENT_WEEK]
    updates = {}
    for wk in planning_wks:
        ovr_key = _ovr_key(hc, wk, channel)
        if ovr_key in overrides:
            entry = dict(overrides[ovr_key])
            # Only remove the OO field — preserve any sales edits the planner made
            if entry.get("_last_edited") == "on_order_placed_total_unit":
                # Entire override was a receipt calibration — delete it
                from database import db_delete_override
                db_delete_override(ovr_key)
            elif "on_order_placed_total_unit" in entry:
                # Mixed override (sales + OO) — strip only the OO field
                entry.pop("on_order_placed_total_unit", None)
                updates[ovr_key] = entry

    if updates:
        db_batch_upsert_overrides(updates)

    _rebuild_pipeline_and_recomm([hc], [channel])
    recompute_recomm_for_sku(hc)
    return get_target_wos(hc, channel)


def update_channel_target_wos(hc: int, channel: str, value: int) -> int:
    """Persist target WOS for one SKU×channel, re-calibrate Pass 1b receipts, recompute recomm."""
    global _CHANNEL_TARGET_WOS
    key = f"{hc}_{channel}"
    _CHANNEL_TARGET_WOS[key] = int(value)
    db_upsert_channel_setting(key, {"target_wos": int(value)})
    # Re-run Pass 1b for this channel only — planning receipts now target the new WOS.
    _recalibrate_pass1b(hc, [channel])
    # _recalibrate_pass1b already rebuilds pipeline + recomm via _rebuild_pipeline_and_recomm;
    # also rebuild demand indexes (lead/safety unchanged but WOS denominator affects target_eop).
    recompute_recomm_for_sku(hc)
    return int(value)


def _load_channel_settings():
    global _CHANNEL_TARGET_WOS
    for key, data in db_get_all_channel_settings().items():
        if "target_wos" in data:
            _CHANNEL_TARGET_WOS[key] = int(data["target_wos"])
    # Recompute affected SKUs
    affected = {int(key.split("_")[0]) for key in _CHANNEL_TARGET_WOS}
    for hc in affected:
        if hc in HIERARCHY_METRICS:
            recompute_recomm_for_sku(hc)


_load_channel_settings()


def _ovr_key(hc: int, wk: int, ch: str) -> str:
    return f"{hc}_{wk}_{ch}"


def _recalc(row: Dict, ovr: Dict) -> Dict:
    """Apply override values and cascade all dependent fields.

    Four editing scenarios (AIR always fixed as Unit List Price):
      1. Units edited    → keep disc%, AIR; recalc AUR, Sales $, Disc $
      2. Sales $ edited  → keep disc%, AIR; back-calc Units; recalc AUR, Disc $
      3. Disc% edited (hold_units) → keep Units, AIR; recalc AUR, Sales $, Disc $
      4. Disc% edited (hold_dollars) → keep Sales $, AIR; back-calc Units; recalc AUR, Disc $
    """
    row = dict(row)
    for field, val in ovr.items():
        row[field] = val

    air     = row["written_air"]   # Unit List Price — always from input files, never overridden
    auc     = row["written_auc"]   # Cost — always from input files
    trigger = ovr.get("_last_edited")
    mode    = ovr.get("_edit_mode", "hold_units")  # disc% edit anchor

    # ── Scenario 1: Units edited ────────────────────────────────────────────────
    if trigger == "written_sales_units":
        units = row["written_sales_units"]
        dr    = row["written_dr_perc"]
        aur   = round(air * (1 - dr), 2)
        row["written_aur"]               = aur
        row["written_sales_dollars"]     = round(aur * units, 2)
        row["written_discount_dollars"]  = round(units * air * dr, 2)

    # ── Scenario 2: Sales $ edited ──────────────────────────────────────────────
    elif trigger == "written_sales_dollars":
        dr  = row["written_dr_perc"]
        aur = round(air * (1 - dr), 2)
        row["written_aur"] = aur
        units = round(row["written_sales_dollars"] / aur) if aur > 0 else 0
        row["written_sales_units"]       = units
        row["written_discount_dollars"]  = round(units * air * dr, 2)

    # ── Scenarios 3 & 4: Disc% edited ──────────────────────────────────────────
    elif trigger == "written_dr_perc":
        dr  = row["written_dr_perc"]
        aur = round(air * (1 - dr), 2)
        row["written_aur"] = aur
        if mode == "hold_units":
            # Scenario 3: units fixed, sales $ adjusts
            units = row["written_sales_units"]
            row["written_sales_dollars"]    = round(aur * units, 2)
            row["written_discount_dollars"] = round(units * air * dr, 2)
        else:
            # Scenario 4: sales $ fixed, units back-calc
            dollars = row["written_sales_dollars"]
            units   = round(dollars / aur) if aur > 0 else 0
            row["written_sales_units"]      = units
            row["written_discount_dollars"] = round(units * air * dr, 2)

    # ── OO placed: order this week, arrives LT weeks later ──────────────────────
    # Does NOT change this week's receipts/EOP — Rcpt[W] = OOP[W−LT], so editing
    # OOP[W] moves the arrival at W+LT. The chain in get_agg_rows re-derives all
    # receipts/EOP from shifted OOP; here we leave same-week receipts untouched.
    elif trigger == "on_order_placed_total_unit":
        pass

    # Sync units from row (may have been back-calculated above)
    units = row["written_sales_units"]
    auc   = row["written_auc"]

    # ── Derived cost / GM ──────────────────────────────────────────────────────
    row["written_sales_cost"] = round(units * auc, 2)
    row["written_gm_dollar"]  = round(row["written_sales_dollars"] - row["written_sales_cost"], 2)
    if row["written_sales_dollars"] > 0:
        row["written_gm_perc"] = round(row["written_gm_dollar"] / row["written_sales_dollars"], 4)

    # ── Inventory ──────────────────────────────────────────────────────────────
    row["eop_units"] = max(0, row["bop_units"] - units + row["total_receipt_units"])

    # ── Recomm receipt (planning weeks only) ───────────────────────────────────
    if not row.get("actualised") and not row.get("is_ongoing"):
        row["recomm_receipt_units"] = _compute_recomm_receipt(
            row["hierarchy_code"], row["channel"], row["current_week"],
            row["eop_units"],
        )
    else:
        row["recomm_receipt_units"] = 0

    # ── WOS — 8-week forward avg for planning; null for actualized ────────────
    _eff_m = get_effective_metrics(row["hierarchy_code"])
    row["lead_time_weeks"] = _eff_m["lead_time_weeks"]
    if row.get("actualised"):
        row["wos"] = None
        row["fwd_coverage_wks"] = None
        row.setdefault("first_stockout_week", None)
    elif row.get("is_ongoing"):
        row["wos"] = round(row["eop_units"] / units, 2) if units > 0 else None
        row["fwd_coverage_wks"] = None
        row.setdefault("first_stockout_week", None)
    else:
        _wos_fwd = _WOS_DEMAND_INDEX.get((row["hierarchy_code"], row["channel"], row["current_week"]), 0)
        _wos_avg = _wos_fwd / WOS_WINDOW if WOS_WINDOW > 0 else 0
        row["wos"] = round(row["eop_units"] / _wos_avg, 2) if _wos_avg > 0 else None
        # fwd_coverage + first_stockout not computable in single-row context — stream walk handles it
        row.setdefault("fwd_coverage_wks", None)
        row.setdefault("first_stockout_week", None)
    avail = row["bop_units"] + row["total_receipt_units"]
    row["sell_through_perc"] = round(row["actual_sales_units"] / avail, 4) if avail > 0 and row.get("actualised") else 0.0
    row["otb_units"]   = 0
    row["otb_dollars"] = 0.0
    if row.get("actualised"):
        row["variance_units"]      = row["written_sales_units"] - row["actual_sales_units"]
        row["variance_dollars"]    = round(row["written_sales_dollars"] - row["actual_sales_dollars"], 2)
        row["variance_units_perc"] = round(row["variance_units"] / row["written_sales_units"], 4) if row["written_sales_units"] > 0 else 0.0
    row["_modified"] = True
    return row


# ── get_agg_rows read-through cache ───────────────────────────────────────────
# _agg_rows_impl recomputes the full aggregate + BOP/EOP chain + recomm on every
# call (no memoization), which is fine at 8 SKUs (~65ms) but grows linearly (~5ms
# /SKU). Most requests are reads with no state change, so we cache per
# (year, hc_filter, ch_filter) and invalidate the WHOLE cache whenever the
# mutation token changes. The token = (DB mutation_version, in-memory WP_DATA
# version); any committed write or placeholder (de)materialization bumps it, so a
# stale read is impossible. Scenario evaluation (_overrides_override) bypasses the
# cache entirely. Returned rows are fresh shallow copies (buckets are flat scalar
# dicts), so callers can mutate freely without corrupting the cached copy.
_AGG_CACHE: Dict[tuple, List[Dict]] = {}
_AGG_CACHE_TOKEN = None
# Strictly-past years (< DEFAULT_YEAR) are read-only history — no edit to the current
# or a future year can change them. So their builds (the LY/LLY comparison columns,
# ~36% of a portfolio load) survive mutation-version bumps and are cached on the seed
# version alone, instead of being thrown away with _AGG_CACHE after every edit.
_PAST_CACHE: Dict[tuple, List[Dict]] = {}
_PAST_CACHE_MEM = None
# Bumped on in-memory WP_DATA mutations that don't themselves commit a DB write
# the cache would otherwise see (placeholder materialize/dematerialize). DB writes
# are already covered by mutation_version().
_MEM_VERSION = 0


def _bump_mem_version() -> None:
    global _MEM_VERSION
    _MEM_VERSION += 1


def get_agg_rows(hc_filter: int = None, ch_filter: str = None,
                 _overrides_override: Dict = None, year: int = DEFAULT_YEAR,
                 _with_compare: bool = True) -> List[Dict]:
    """Aggregate one year's WP_DATA by (hc, wk, ch), sum sub_channels, apply overrides.

    Runs the engine under _scoped_year(year) so the chain/recomm passes walk that
    year's weeks. Defaults to DEFAULT_YEAR (2026) → byte-identical to pre-multi-year.
    Read-through cached (see _AGG_CACHE); scenario eval bypasses the cache.

    _with_compare: build the year-relative LY/LLY comparison columns. Set False when
    this call is itself sourcing a comparison year's forecast (prevents recursion).
    """
    # Scenario evaluation supplies its own override set and must never read or
    # write the shared cache.
    if _overrides_override is not None:
        with _scoped_year(year):
            return _agg_rows_impl(hc_filter, ch_filter, _overrides_override, year, _with_compare)

    # Strictly-past years are immutable w.r.t. current/future-year edits, so their
    # builds outlive mutation-version bumps — cache on seed version only. This is the
    # comparison-map (_with_compare=False) sub-build path; keeping it warm across edits
    # is what removes the ~36% LY/LLY rebuild from every post-edit portfolio load.
    if not _with_compare and year < DEFAULT_YEAR:
        global _PAST_CACHE_MEM
        if _PAST_CACHE_MEM != _MEM_VERSION:
            _PAST_CACHE.clear(); _PAST_CACHE_MEM = _MEM_VERSION
        pkey = (year, hc_filter, ch_filter)
        past = _PAST_CACHE.get(pkey)
        if past is None:
            with _scoped_year(year):
                past = _agg_rows_impl(hc_filter, ch_filter, None, year, False)
            _PAST_CACHE[pkey] = past
        return [dict(r) for r in past]

    global _AGG_CACHE_TOKEN
    token = (mutation_version(), _MEM_VERSION)
    if token != _AGG_CACHE_TOKEN:
        _AGG_CACHE.clear()
        _AGG_CACHE_TOKEN = token

    ckey = (year, hc_filter, ch_filter, _with_compare)
    cached = _AGG_CACHE.get(ckey)
    if cached is None:
        with _scoped_year(year):
            cached = _agg_rows_impl(hc_filter, ch_filter, None, year, _with_compare)
        _AGG_CACHE[ckey] = cached
    # Hand out fresh copies so callers never mutate the cached rows.
    return [dict(r) for r in cached]


# Comparison value used when a stream/year/week has neither history actuals nor a
# forecast (e.g. a fully-past year not covered by the file). All zeros.
_ZERO_COMP = {"units": 0, "dollars": 0.0, "aur": 0.0, "dr": 0.0, "discd": 0.0}


def _emit_comparison(b: Dict, prefix: str, cv: Dict) -> None:
    """Write a comparison year's columns (units/$/AUR/Disc%/Disc$ + variances) onto b."""
    units, dollars = cv["units"], cv["dollars"]
    b[f"{prefix}_sales_units"]      = units
    b[f"{prefix}_sales_dollars"]    = dollars
    b[f"{prefix}_aur"]              = cv["aur"]
    b[f"{prefix}_dr_perc"]          = cv["dr"]
    b[f"{prefix}_discount_dollars"] = cv["discd"]
    uv = b["written_sales_units"] - units
    dv = round(b["written_sales_dollars"] - dollars, 2)
    b[f"{prefix}_units_var"]        = uv
    b[f"{prefix}_dollars_var"]      = dv
    b[f"{prefix}_units_var_perc"]   = round(uv / units, 4) if units > 0 else 0.0
    b[f"{prefix}_dollars_var_perc"] = round(dv / dollars, 4) if dollars > 0 else 0.0


def _comparison_map(comp_year: int, hc_filter, ch_filter) -> Dict[tuple, Dict]:
    """Per (hc, ch, week_num) comparison values for an absolute calendar year.

    Each actualised week present in the history file → real actuals; every other
    week → that year's WP forecast (written_sales). Keyed for direct bucket lookup.
    Only history streams use this (non-history streams keep the TY_LY_DATA path).
    """
    out: Dict[tuple, Dict] = {}
    # That year's WP forecast (no nested comparison → no recursion). Empty for fully
    # past years with no WP_DATA — those are covered entirely by file actuals.
    fc = get_agg_rows(hc_filter, ch_filter, year=comp_year, _with_compare=False)
    fc_by = {(r["hierarchy_code"], r["channel"], r["current_week"] % 100): r for r in fc}

    streams = {(hc, ch) for (hc, ch, _wn) in fc_by}
    if _SEED is not None:
        streams |= {(hc, ch) for (hc, ch, yr, _wn) in _SEED.sales_history if yr == comp_year}

    for (hc, ch) in streams:
        if hc_filter and hc != hc_filter:
            continue
        if ch_filter and ch != ch_filter:
            continue
        if hc not in HIERARCHY_METRICS or not _stream_has_history(hc, ch):
            continue
        air = get_effective_metrics(hc)["air"]
        for wn in range(1, 54):
            fiscal_wk = comp_year * 100 + wn
            actualised = fiscal_wk < CURRENT_WEEK
            units = dollars = disc = None
            if actualised:
                u = _SEED.history_units(hc, ch, comp_year, wn)
                if u is not None:
                    disc = _SEED.history_discount(hc, ch, comp_year, wn) or 0.0
                    units = int(u)
                    dollars = round(units * air * (1 - disc), 2)
            if units is None:
                r = fc_by.get((hc, ch, wn))
                if r is None:
                    continue
                units = r["written_sales_units"]
                dollars = r["written_sales_dollars"]
            retail = round(units * air, 2)
            discd = round(retail - dollars, 2)
            out[(hc, ch, wn)] = {
                "units": units,
                "dollars": dollars,
                "aur": round(dollars / units, 2) if units > 0 else 0.0,
                "dr": round(discd / retail, 4) if retail > 0 else 0.0,
                "discd": discd,
            }
    return out


def _agg_rows_impl(hc_filter: int = None, ch_filter: str = None,
                   _overrides_override: Dict = None, year: int = DEFAULT_YEAR,
                   _with_compare: bool = True) -> List[Dict]:
    """Aggregate WP_DATA by (hc, wk, ch), sum sub_channels, apply overrides.

    _overrides_override: if provided, use this dict instead of reading from DB.
    Used by compare_snapshots() to evaluate two scenarios without touching global state.
    """
    buckets: Dict[str, Dict] = {}

    for r in WP_DATA:
        if int(str(r["current_week"])[:4]) != year:   # scope to the viewed fiscal year
            continue
        if hc_filter and r["hierarchy_code"] != hc_filter:
            continue
        # Placeholders are hidden synthetic SKUs: include them only when explicitly
        # requested by hc (the placeholders page). An unfiltered portfolio sweep must
        # never see them, or they would pollute aggregation / budget / exceptions.
        if not hc_filter and r["hierarchy_code"] in PLACEHOLDER_HCS:
            continue
        if ch_filter and r["channel"] != ch_filter:
            continue
        key = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        if key not in buckets:
            buckets[key] = {
                "hierarchy_code": r["hierarchy_code"],
                "current_week":   r["current_week"],
                "channel":        r["channel"],
                "l1_name":        r["l1_name"],
                "l2_name":        r["l2_name"],
                "written_sales_units":       0,
                "written_sales_dollars":     0.0,
                "written_sales_cost":        0.0,
                "written_gm_dollar":         0.0,
                "written_aur":               0.0,
                "written_auc":               r["written_auc"],
                "written_air":               r["written_air"],
                "written_dr_perc":           r.get("written_dr_perc", 0),
                "written_discount_dollars":  0.0,
                "written_gm_perc":           0.0,
                "bop_units":                 0,
                "eop_units":                 0,
                "bop_cost":                  0.0,
                "eop_cost":                  0.0,
                "total_receipt_units":       0,
                "ingested_receipt_units":    0,
                "recomm_receipt_units":      0,
                "on_order_placed_total_unit":   0,
                "oo_locked":                 False,
                "actualised":  r["actualised"],
                "is_ongoing":  r.get("is_ongoing", False),
                "actual_sales_units":   0,
                "actual_sales_dollars": 0.0,
                "actual_sales_cost":    0.0,
                "markdown_units":       0,
                "markdown_dollars":     0.0,
                "_modified":   False,
            }
        b = buckets[key]
        b["written_sales_units"]         += r["written_sales_units"]
        b["written_sales_dollars"]        = round(b["written_sales_dollars"]    + r["written_sales_dollars"], 2)
        b["written_sales_cost"]           = round(b["written_sales_cost"]        + r["written_sales_cost"], 2)
        b["written_gm_dollar"]            = round(b["written_gm_dollar"]         + r["written_gm_dollar"], 2)
        b["bop_units"]                   += r["bop_units"]
        b["eop_units"]                   += r["eop_units"]
        b["bop_cost"]                     = round(b["bop_cost"]  + r["bop_cost"], 2)
        b["eop_cost"]                     = round(b["eop_cost"]  + r["eop_cost"], 2)
        b["total_receipt_units"]         += r["total_receipt_units"]
        b["ingested_receipt_units"]      += r.get("ingested_receipt_units", 0)
        b["recomm_receipt_units"]        += r["recomm_receipt_units"]
        b["on_order_placed_total_unit"]  += r["on_order_placed_total_unit"]
        b["oo_locked"]                    = b["oo_locked"] or r.get("oo_locked", False)
        b["actual_sales_units"]          += r["actual_sales_units"]
        b["actual_sales_dollars"]         = round(b["actual_sales_dollars"] + r["actual_sales_dollars"], 2)
        b["actual_sales_cost"]            = round(b["actual_sales_cost"]    + r["actual_sales_cost"], 2)
        b["markdown_units"]              += r["markdown_units"]
        b["markdown_dollars"]             = round(b["markdown_dollars"]     + r["markdown_dollars"], 2)
        b["written_discount_dollars"]     = round(b["written_discount_dollars"] + r.get("written_discount_dollars", 0.0), 2)

    # ── LY / LLY lookups (keyed same way as buckets) ─────────────────────────────
    _ly: Dict[str, Dict] = {}
    _lly: Dict[str, Dict] = {}
    for r in TY_LY_DATA:
        if hc_filter and r["hierarchy_code"] != hc_filter:
            continue
        if ch_filter and r["channel"] != ch_filter:
            continue
        k = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        if k not in _ly:
            _ly[k]  = {"ly_units": 0,  "ly_dollars":  0.0, "ly_retail": 0.0,  "ly_disc": 0.0}
            _lly[k] = {"lly_units": 0, "lly_dollars": 0.0, "lly_retail": 0.0, "lly_disc": 0.0}
        _ly[k]["ly_units"]    += r["ly_units"]
        _ly[k]["ly_dollars"]   = round(_ly[k]["ly_dollars"]  + r["ly_dollars"],  2)
        _ly[k]["ly_retail"]    = round(_ly[k]["ly_retail"]   + r.get("ly_retail_dollars", 0.0), 2)
        _ly[k]["ly_disc"]      = round(_ly[k]["ly_disc"]     + r.get("ly_disc_dollars",   0.0), 2)
        _lly[k]["lly_units"]  += r.get("lly_units", 0)
        _lly[k]["lly_dollars"] = round(_lly[k]["lly_dollars"] + r.get("lly_dollars", 0.0), 2)
        _lly[k]["lly_retail"]  = round(_lly[k]["lly_retail"]  + r.get("lly_retail_dollars", 0.0), 2)
        _lly[k]["lly_disc"]    = round(_lly[k]["lly_disc"]    + r.get("lly_disc_dollars",   0.0), 2)

    # ── Year-relative comparison (history streams only) ──────────────────────────
    # For history streams, LY = year-1 and LLY = year-2, pulled from the file where
    # the week is actualised and forecast otherwise (see _comparison_map). Non-history
    # streams keep the TY_LY_DATA path above (demo stays byte-identical). Skipped when
    # this read is itself sourcing a comparison year's forecast (_with_compare=False).
    _comp_ly: Dict[tuple, Dict] = {}
    _comp_lly: Dict[tuple, Dict] = {}
    if _with_compare and _SEED is not None and _SEED.sales_history:
        _comp_ly  = _comparison_map(year - 1, hc_filter, ch_filter)
        _comp_lly = _comparison_map(year - 2, hc_filter, ch_filter)

    for key, b in buckets.items():
        # AUR / GM% / implied Disc%
        if b["written_sales_units"] > 0:
            b["written_aur"] = round(b["written_sales_dollars"] / b["written_sales_units"], 2)
        if b["written_sales_dollars"] > 0:
            b["written_gm_perc"] = round(b["written_gm_dollar"] / b["written_sales_dollars"], 4)
        # Derive disc% from AUR/AIR (consistent after any overrides)
        if b["written_air"] > 0:
            b["written_dr_perc"] = round(max(0.0, 1 - b["written_aur"] / b["written_air"]), 4)

        # WOS (Weeks of Supply)
        b["wos"] = round(b["eop_units"] / b["written_sales_units"], 2) if b["written_sales_units"] > 0 else None

        # Sell-Through % (only meaningful for actualised weeks)
        avail = b["bop_units"] + b["total_receipt_units"]
        b["sell_through_perc"] = round(b["actual_sales_units"] / avail, 4) if avail > 0 and b["actualised"] else 0.0

        b["otb_units"]   = 0
        b["otb_dollars"] = 0.0

        # Plan vs Actual variance
        if b["actualised"]:
            b["variance_units"]      = b["written_sales_units"] - b["actual_sales_units"]
            b["variance_dollars"]    = round(b["written_sales_dollars"] - b["actual_sales_dollars"], 2)
            b["variance_units_perc"] = round(b["variance_units"] / b["written_sales_units"], 4) if b["written_sales_units"] > 0 else 0.0
        else:
            b["variance_units"]      = None
            b["variance_dollars"]    = None
            b["variance_units_perc"] = None

        # LY / LLY — history streams use the year-relative comparison maps; non-history
        # streams (the demo) keep the TY_LY_DATA path → byte-identical to before.
        if _stream_has_history(b["hierarchy_code"], b["channel"]):
            _wn = b["current_week"] % 100
            _hc, _ch = b["hierarchy_code"], b["channel"]
            _emit_comparison(b, "ly",  _comp_ly.get((_hc, _ch, _wn),  _ZERO_COMP))
            _emit_comparison(b, "lly", _comp_lly.get((_hc, _ch, _wn), _ZERO_COMP))
        else:
            # LY
            ly = _ly.get(key, {"ly_units": 0, "ly_dollars": 0.0, "ly_retail": 0.0, "ly_disc": 0.0})
            b["ly_sales_units"]      = ly["ly_units"]
            b["ly_sales_dollars"]    = ly["ly_dollars"]
            b["ly_aur"]              = round(ly["ly_dollars"] / ly["ly_units"], 2) if ly["ly_units"] > 0 else 0.0
            b["ly_discount_dollars"] = ly["ly_disc"]
            b["ly_dr_perc"]          = round(ly["ly_disc"] / ly["ly_retail"], 4) if ly["ly_retail"] > 0 else 0.0
            b["ly_units_var"]        = b["written_sales_units"] - ly["ly_units"]
            b["ly_dollars_var"]      = round(b["written_sales_dollars"] - ly["ly_dollars"], 2)
            b["ly_units_var_perc"]   = round(b["ly_units_var"]   / ly["ly_units"],   4) if ly["ly_units"]   > 0 else 0.0
            b["ly_dollars_var_perc"] = round(b["ly_dollars_var"] / ly["ly_dollars"], 4) if ly["ly_dollars"] > 0 else 0.0

            # LLY (last-to-last year)
            lly = _lly.get(key, {"lly_units": 0, "lly_dollars": 0.0, "lly_retail": 0.0, "lly_disc": 0.0})
            b["lly_sales_units"]      = lly["lly_units"]
            b["lly_sales_dollars"]    = lly["lly_dollars"]
            b["lly_aur"]              = round(lly["lly_dollars"] / lly["lly_units"], 2) if lly["lly_units"] > 0 else 0.0
            b["lly_discount_dollars"] = lly["lly_disc"]
            b["lly_dr_perc"]          = round(lly["lly_disc"] / lly["lly_retail"], 4) if lly["lly_retail"] > 0 else 0.0
            b["lly_units_var"]        = b["written_sales_units"] - lly["lly_units"]
            b["lly_dollars_var"]      = round(b["written_sales_dollars"] - lly["lly_dollars"], 2)
            b["lly_units_var_perc"]   = round(b["lly_units_var"]   / lly["lly_units"],   4) if lly["lly_units"]   > 0 else 0.0
            b["lly_dollars_var_perc"] = round(b["lly_dollars_var"] / lly["lly_dollars"], 4) if lly["lly_dollars"] > 0 else 0.0

    _active_ovrs = _overrides_override if _overrides_override is not None else db_get_overrides()
    for key, ovr in _active_ovrs.items():
        if key in buckets:
            buckets[key] = _recalc(buckets[key], ovr)
            # An edit changes written_sales_* but the LY/LLY comparison columns were
            # computed above against the pre-edit value — refresh their variances so
            # TY/LY % and TY/LLY % reflect the new TY (LY/LLY bases are historical).
            b = buckets[key]
            for prefix in ("ly", "lly"):
                bu, bd = b[f"{prefix}_sales_units"], b[f"{prefix}_sales_dollars"]
                uv = b["written_sales_units"] - bu
                dv = round(b["written_sales_dollars"] - bd, 2)
                b[f"{prefix}_units_var"]        = uv
                b[f"{prefix}_dollars_var"]      = dv
                b[f"{prefix}_units_var_perc"]   = round(uv / bu, 4) if bu > 0 else 0.0
                b[f"{prefix}_dollars_var_perc"] = round(dv / bd, 4) if bd > 0 else 0.0

    # ── BOP chain propagation + WOS ───────────────────────────────────────────
    # Enforce bop[N+1] = eop[N] and compute WOS with correct denominator:
    #   Actualised / ongoing → trailing 4-week actual sales avg
    #   Planning             → forward N-week planned sales avg
    _streams: Dict[tuple, list] = {}
    for b in buckets.values():
        _streams.setdefault((b["hierarchy_code"], b["channel"]), []).append(b)

    for (hc_s, ch_s), stream in _streams.items():
        stream.sort(key=lambda x: x["current_week"])
        prev_eop = None
        actual_window: List[int] = []   # rolling 4-week actual sales for trailing WOS
        m_s = get_effective_metrics(hc_s)
        lead_time_s   = m_s["lead_time_weeks"]
        look_ahead_s  = lead_time_s + m_s["safety_weeks"]
        target_wos_s  = get_target_wos(hc_s, ch_s)
        # Forward demand curve for this stream — used by the coverage walk (WOS/FC)
        # so coverage tracks real seasonality, not a flat 8wk average.
        sales_s       = [x.get("written_sales_units", 0) for x in stream]

        for i, b in enumerate(stream):
            b["lead_time_weeks"] = lead_time_s   # expose on every row for frontend coloring
            b["target_wos"]      = target_wos_s  # for target-aware excess coloring
            # Dynamic lock: order placed here would arrive (W+LT) past season end.
            # Recomputed off effective LT every read → never stale after an LT change.
            b["oo_locked"] = (
                not b.get("actualised")
                and _week_offset(b["current_week"], lead_time_s) is None
            )

            # Historical OO Placed display for ACTUALIZED weeks = the ingested supply
            # that arrived LT weeks LATER (the order that week produced):
            # OOP[W] = ingested[W+LT].  Recomputed off EFFECTIVE LT every read so it
            # stays consistent with the receipt offset after an LT change.
            # Display-only — receipt formula skips actualized source OOP. The ONGOING
            # week is NOT display-only: it's a planning week (orders placed there are
            # the planner's and land as receipts at W+LT), so it keeps its real OOP.
            if b.get("actualised"):
                fwd = stream[i + lead_time_s] if i + lead_time_s < len(stream) else None
                b["on_order_placed_total_unit"] = (
                    int(fwd.get("ingested_receipt_units", 0)) if fwd else 0
                )

            if b.get("actualised"):
                actual_window.append(b.get("actual_sales_units", 0))
                if len(actual_window) > 4:
                    actual_window.pop(0)
                b["wos"]                = None
                b["fwd_coverage_wks"]   = None
                b["first_stockout_week"] = None
                prev_eop = b["eop_units"]
                continue

            # Receipts this week = INGESTED supply baseline + planner orders landing now.
            #   Rcpt[W] = ingested[W] + OOP[W − LT]
            # Ingested is independent backend data; OOP is the planner's orders placed
            # LT weeks earlier (now arriving). Ongoing week is treated as planning.
            units_s = b["written_sales_units"]
            ingested = int(b.get("ingested_receipt_units", 0))
            src = stream[i - lead_time_s] if i - lead_time_s >= 0 else None
            # Only use OOP from non-actualized source weeks — actualized OOP is
            # display-only (ingested already carries those historical arrivals).
            # The ongoing week's OOP DOES land (it's a planning order).
            oo_landing = (
                int(src.get("on_order_placed_total_unit", 0))
                if src is not None and not src.get("actualised")
                else 0
            )
            b["total_receipt_units"] = ingested + oo_landing

            # Propagate BOP
            if prev_eop is not None:
                b["bop_units"] = prev_eop
            b["eop_units"] = max(0, b["bop_units"] - units_s + b["total_receipt_units"])
            prev_eop = b["eop_units"]

            # Real stockout = couldn't fully serve demand this week (unmet demand).
            #   available = BOP + receipts(stock actually arriving this week)
            #   if available < demand → genuine stockout, EOP clamps to 0
            # Terminal season week excluded: planned runout to zero is intentional.
            _avail = b["bop_units"] + b["total_receipt_units"]
            b["_stockout"] = (
                units_s > 0
                and _avail < units_s
                and b["current_week"] < _SEASON_END_WK
            )

            wos_s     = _WOS_DEMAND_INDEX.get((hc_s, ch_s, b["current_week"]), 0)
            wos_avg_s = wos_s / WOS_WINDOW if WOS_WINDOW > 0 else 0

            # Ongoing + planning weeks both use forward WOS = weeks of cover for
            # current stock (EOP only), walked down the real demand curve. Gated on
            # wos_avg_s>0 so terminal weeks with no forward demand stay None.
            b["wos"] = _weeks_of_cover(b["eop_units"], i, sales_s, wos_avg_s) if wos_avg_s > 0 else None
            # FC + first_stockout_week computed in second pass below
            # (needs full BOP chain propagated first so future eop_units are accurate)
            b["fwd_coverage_wks"]   = None
            b["first_stockout_week"] = None

        # ── Second pass: FC (display) + stockout signals (classification) ────
        # Runs after full BOP chain so future eop_units / _stockout flags are real.
        #
        # Two SEPARATE concerns, deliberately not merged into one number:
        #
        #   FC (display)  = weeks of cover for (EOP + pipeline), WALKED down the real
        #     forward demand curve (see _weeks_of_cover), not divided by a flat 8wk
        #     average. The flat-avg form exploded to 100+ in pre-peak weeks because a
        #     peak-sized pipeline was measured against trough current demand; walking
        #     the curve consumes that pipeline at its true (rising) rate instead.
        #     pipeline = the planner's ORDERS in transit (OOP placed but not yet
        #     received = OOP over the last LT weeks). Ingested supply is NOT added
        #     here — it already flows into EOP as it lands, so adding it would
        #     double-count. At baseline (no orders) FC == WOS (same walk, same stock).
        #
        #   Stockout flags (classification) = walk the real EOP chain
        #     A back-loaded receipt (lands wk+14) leaves you dry wks 1-13 even though
        #     FC looks healthy. So exceptions classify off the chain, not off FC.
        for i, b in enumerate(stream):
            if b.get("actualised"):
                continue
            wos_s     = _WOS_DEMAND_INDEX.get((hc_s, ch_s, b["current_week"]), 0)
            wos_avg_s = wos_s / WOS_WINDOW if WOS_WINDOW > 0 else 0

            # pipeline = PLANNER orders in transit = OOP placed in the last LT weeks
            # (weeks i-LT+1 .. i), which arrive over the next LT weeks. Not received yet.
            # Exclude only actualized rows — their OOP is display-only (historical
            # orders already in ingested supply). Ongoing + planning OOP both count.
            lo = max(0, i - lead_time_s + 1)
            pipeline = sum(
                px.get("on_order_placed_total_unit", 0)
                for px in stream[lo : i + 1]
                if not px.get("actualised")
            )
            # FC = forward weeks of cover for stock + in-transit pipeline, walked down
            # the real demand curve (same method as WOS). Walking the curve is what
            # keeps a peak-sized pipeline from reading as 100+ weeks against trough
            # current demand: the ramp/peak consumes the pipeline at its true rate.
            # Where pipeline==0 this is identical to WOS by construction (consistent).
            b["fwd_coverage_wks"] = (
                _weeks_of_cover(b["eop_units"] + pipeline, i, sales_s, wos_avg_s)
                if wos_avg_s > 0 else None
            )

            # Stockout WITHIN lead time = can't be fixed by reordering now (order
            # placed today lands in LT weeks, too late). Window [i .. i+LT] inclusive.
            b["_stockout_in_lt"] = any(
                px.get("_stockout")
                for px in stream[i : i + 1 + lead_time_s]
                if not px.get("actualised")
            )
            # Earliest future week with genuine unmet demand (real stockout signal).
            b["first_stockout_week"] = next(
                (px["current_week"] for px in stream[i:]
                 if not px.get("actualised") and px.get("_stockout")),
                None
            )

        # ── Third pass: recomm = periodic TIMING-AWARE base-stock replenishment ─
        # Each week's recomm = the order a planner should place THAT week to keep
        # inventory healthy — a real reorder schedule, not one front-loaded lump.
        #
        # Per week i, an order placed now ARRIVES at t = i + LT. Size it to bring the
        # projected EOP AT ITS ARRIVAL WEEK t up to a forward-cover buffer:
        #   buffer_w = max(target_wos, safety + 1)         weeks of cover to hold
        #   target   = Σ demand over weeks [t+1 .. t+buffer_w]   (cover from arrival)
        #   recomm   = max(0, target − projected_EOP[t])   ⌈round up to case pack⌉
        #
        # Walked chronologically on a SIMULATED chain: placing week i's order lifts
        # sim receipts at t and re-chains EOP downstream, so week i+1 sees it and only
        # tops up the NEW marginal gap. Steady state → each week reorders ≈ one week's
        # demand → orders fire weekly and deliveries stream in LT-shifted, MATCHING
        # demand instead of dumping the whole season at once.
        #
        # Why target the ARRIVAL week (not the current week): coverage is timing-aware.
        # A single lump landing at t+LT can fool a window-SUM ("enough is coming") yet
        # leave you dry until it lands. Targeting projected EOP at each order's own
        # arrival week walks the real chain, so it neither starves the gap nor piles a
        # season's worth into one delivery. (This replaced an order-up-to-eff_cov
        # policy capped at Σ-all-remaining-demand, which collapsed to one giant order:
        # 8-week stockout then ~1.8k units of dead end-of-season overstock under load.)
        #
        # The column == what Accept places (Accept walks the same weeks). FC / stockout
        # signals (second pass) stay on the REAL chain (current OOP), not this sim.
        cp_s  = m_s["case_pack"]
        # Recomm = a leveled, deadline-feasible order schedule (minimum peak per-week order),
        # netted against what's already on order. Replaces the old "fill the whole forward
        # buffer at the first reorder week" sizing, which dumped a season's buy into one
        # order for long-LT ramping SKUs (Ankle Boots LT16: 324 in wk21) and — when a flat
        # per-week cap was tried to spread it — under-ordered into a tail stockout. The
        # leveled schedule spreads the buy across unlocked weeks AND covers every week incl.
        # the locked tail (0 unmet-demand stockout across all SKU×channel streams).
        sched = _level_order_schedule(stream, lead_time_s, cp_s)   # STABLE target (need ignores OOP)
        # recomm = cumulative top-up to reach the stable target, crediting OOP placed in ANY
        # week (forecast.csv seed or hand edits) — not just the same week the schedule picked.
        # Walk chronologically: keep a running total of (placed OOP + recomm so far); at each
        # planning week recommend only the shortfall vs the schedule's cumulative target.
        #   • OOP already covers the target  → recomm 0 (no double-order, even if placed in a
        #     week the schedule didn't choose — the LT-mismatch / over-supply-on-accept bug).
        #   • accept adds recomm once → running total hits the target → re-read recomm 0
        #     (idempotent), and because the target is stable it converges in one pass for any LT.
        run = 0          # cumulative (placed OOP + recommended) across planning weeks
        cum_target = 0   # cumulative schedule target across planning weeks
        for i, b in enumerate(stream):
            if b.get("actualised"):
                b["recomm_receipt_units"] = 0     # display-only OOP; not a future order
                continue
            cum_target += int(sched[i])           # 0 except at orderable weeks
            run += int(b.get("on_order_placed_total_unit", 0))
            if b.get("oo_locked"):
                b["recomm_receipt_units"] = 0     # can't order here, but its (0) OOP still counted
                continue
            rec = max(0, cum_target - run)
            b["recomm_receipt_units"] = rec
            run += rec

    _apply_newsku_disc_borrow(buckets.values(), _active_ovrs)
    return sorted(buckets.values(), key=lambda x: (x["current_week"], x["hierarchy_code"], x["channel"]))


def _apply_newsku_disc_borrow(rows, overrides: Dict = None) -> None:
    """For each New-SKU row inside its New window, override Disc% with the tagged Old
    SKU's discount for the same week × channel and recompute the dollar/GM fields.

    A New SKU has no LY/LLY history, so its planning-week Disc% would seed to ~0. While
    it is New (within 52 weeks of activation, by the row's own week), it instead inherits
    the tagged Old SKU's markdown shape; once it becomes Old it keeps its own (no borrow).
    Disc% doesn't touch units/receipts/EOP, so the inventory chain is unaffected.

    A planner's OWN Disc% edit wins over the borrow: if the cell has a written_dr_perc
    override, the borrow is skipped so the edit sticks."""
    overrides = overrides or {}
    for b in rows:
        hc = b["hierarchy_code"]
        if hc not in NEW_SKU_HCS:
            continue
        # Planner edited this cell's Disc% → respect it, don't borrow over it.
        ovr = overrides.get(_ovr_key(hc, b["current_week"], b["channel"]))
        if ovr and "written_dr_perc" in ovr:
            continue
        tag = (_MASTER_BY_HC.get(hc) or {}).get("tagged_to")
        if not tag:
            continue
        act = _CAL_ORDER.get(NEW_SKU_LIFECYCLE[hc]["activation_week"])
        now = _CAL_ORDER.get(b["current_week"])
        if act is None or now is None or not (0 <= now - act < 52):
            continue   # outside the New window → keep own (no borrow)
        dr = _BASELINE_DR.get((tag, b["current_week"], b["channel"]))
        if dr is None:
            continue
        air = b["written_air"]
        units = b["written_sales_units"]
        aur = round(air * (1 - dr), 2)
        b["written_dr_perc"]          = dr
        b["written_aur"]              = aur
        b["written_sales_dollars"]    = round(aur * units, 2)
        b["written_discount_dollars"] = round(units * air * dr, 2)
        b["written_gm_dollar"]        = round(b["written_sales_dollars"] - b["written_sales_cost"], 2)
        b["written_gm_perc"]          = round(b["written_gm_dollar"] / b["written_sales_dollars"]
                                              if b["written_sales_dollars"] else 0, 4)


def apply_edit(hc: int, wk: int, ch: str, field: str, value: float, mode: str = None) -> Dict:
    # The fiscal year is encoded in the week code (202730 → 2027). Scope the whole
    # edit — lock check, recomm rebuild (walks FISCAL_WEEKS), and the re-read — to that
    # year so edits work in any viewed year. For 2026 this is the same as not scoping.
    with _scoped_year(wk // 100):
        return _apply_edit_impl(hc, wk, ch, field, value, mode)


def _apply_edit_impl(hc: int, wk: int, ch: str, field: str, value: float, mode: str = None) -> Dict:
    year = wk // 100
    key = _ovr_key(hc, wk, ch)

    # Reject OO Placed edits on locked tail weeks — an order placed here would
    # arrive after season end (W+LT off-grid) so it can never be received.
    # Dynamic off effective LT, so it tracks runtime lead-time changes.
    if field == "on_order_placed_total_unit" and _is_oo_locked(hc, wk):
        raise ValueError(
            f"OO Placed locked for week {wk}: arrival (W+lead_time) lands after season end."
        )

    overrides = db_get_overrides()
    entry = overrides.get(key, {})

    # Capture old value for audit log (existing override → base WP_DATA → None)
    old_value = entry.get(field)
    if old_value is None:
        _base_row = next(
            (r for r in WP_DATA
             if r["hierarchy_code"] == hc and r["channel"] == ch and r["current_week"] == wk),
            None,
        )
        if _base_row:
            old_value = _base_row.get(field)

    # Round appropriately per field type
    if field in ("written_sales_units", "on_order_placed_total_unit"):
        value = float(round(value))
    elif field == "written_dr_perc":
        value = round(min(max(value, 0.0), 1.0), 4)  # clamp 0–100%, 4 dp
    else:
        value = round(value, 2)
    entry[field] = value
    entry["_last_edited"] = field
    if field == "written_dr_perc" and mode in ("hold_units", "hold_dollars"):
        entry["_edit_mode"] = mode
    db_upsert_override(key, entry)
    db_log_audit(hc, ch, wk, field, old_value, value)

    # Demand changed → rebuild demand indexes + pipeline + recomm
    if field in ("written_sales_units", "written_sales_dollars"):
        _rebuild_fwd_demand_and_recomm([hc], [ch])
    # OO Placed changed → pipeline is stale → recomm for earlier weeks must be updated
    elif field == "on_order_placed_total_unit":
        _rebuild_pipeline_and_recomm([hc], [ch])

    rows = get_agg_rows(hc, ch, year=year)
    return next((r for r in rows if r["current_week"] == wk), None)


def reset_overrides():
    db_clear_overrides()
    _reset_fwd_demand_and_recomm()   # restore index + WP_DATA recomm to baseline


def restore_snapshot(snap_id: int):
    """Restore a snapshot's plan state. Returns the saved UI view dict (which SKUs/
    channels/category/year were on screen at save time) so the frontend can re-apply
    it, or None if the snapshot doesn't exist. Old snapshots return {} (no view)."""
    global _SKU_SETTINGS_OVERRIDES, _CHANNEL_TARGET_WOS
    snap = db_get_snapshot(snap_id)
    if not snap:
        return None
    db_replace_overrides(snap["overrides"])

    # Restore the captured plan settings too (lead_time/case_pack/safety_weeks/
    # target_wos + channel target WOS). Old snapshots have no settings payload → {}
    # which correctly restores to base-metric defaults (no overrides).
    settings = snap.get("settings") or {}
    sku_settings = {int(hc): dict(v) for hc, v in settings.get("sku", {}).items()}
    chan_settings = {k: int(v) for k, v in settings.get("channel", {}).items()}
    # Mutate in place (clear + update), do NOT rebind — routers import these dicts by
    # reference (from dummy_data import _CHANNEL_TARGET_WOS), so rebinding would leave
    # them pointing at the stale pre-restore object.
    _SKU_SETTINGS_OVERRIDES.clear(); _SKU_SETTINGS_OVERRIDES.update(sku_settings)
    _CHANNEL_TARGET_WOS.clear();     _CHANNEL_TARGET_WOS.update(chan_settings)
    db_replace_sku_settings(sku_settings)
    # channel_settings DB form is {"target_wos": N}; in-memory form is the bare int.
    db_replace_channel_settings({k: {"target_wos": v} for k, v in chan_settings.items()})

    # Rebuild demand + pipeline indexes so recomm reflects snapshot's sales/OO state,
    # and re-derive each SKU's plan from the restored settings (lead_time/case_pack
    # change look-ahead, locks and rounding). Without this they stay stale until restart.
    #
    # _rebuild_fwd_demand_and_recomm rebuilds ALL three indexes (fwd/wos/pipeline) +
    # recomm override-aware for every SKU it processes, so the old per-SKU
    # recompute_recomm_for_sku loop over all SKUs was redundant (~2.3s on 60 SKUs) —
    # phase 2 overwrote every key it wrote. The one exception: _rebuild skips SKUs with
    # look_ahead<=0, so those still need the per-SKU recompute. Guard for exactly those.
    all_hcs = [h["hierarchy_code"] for h in HIERARCHIES]
    for hc in all_hcs:
        m = get_effective_metrics(hc)
        if m["lead_time_weeks"] + m["safety_weeks"] <= 0:
            recompute_recomm_for_sku(hc)   # _rebuild would skip it below
    _rebuild_fwd_demand_and_recomm(all_hcs)
    return settings.get("view") or {}


def delete_snapshot(snap_id: int) -> bool:
    return db_delete_snapshot(snap_id)


def rename_snapshot(snap_id: int, new_name: str) -> bool:
    return db_rename_snapshot(snap_id, new_name.strip())


def save_snapshot(name: str, view: Dict = None) -> Dict:
    all_rows = get_agg_rows()
    overrides = db_get_overrides()
    td = round(sum(r["written_sales_dollars"] for r in all_rows), 2)
    tg = round(sum(r["written_gm_dollar"] for r in all_rows), 2)
    summary = {
        "total_sales_units":   sum(r["written_sales_units"] for r in all_rows),
        "total_sales_dollars": td,
        "total_gm_dollar":     tg,
        # Dollar-weighted GM% — not simple average (P-03)
        "avg_gm_perc":         round(tg / td, 4) if td > 0 else 0,
    }
    # Capture the full plan state, not just cell overrides: SKU-level settings
    # (lead_time/case_pack/safety_weeks/target_wos) and channel-level target WOS
    # overrides live at save time, so restore returns the exact plan the planner saw.
    settings = {
        "sku":     {str(hc): dict(v) for hc, v in _SKU_SETTINGS_OVERRIDES.items()},
        "channel": {k: int(v) for k, v in _CHANNEL_TARGET_WOS.items()},
        # The UI filter selection live at save time (which SKUs/channels/category/year
        # were on screen). Inert on the backend — restore returns it so the frontend can
        # re-apply the same view and auto-show those features. Old snapshots have no view.
        "view":    view or {},
    }
    return db_insert_snapshot(
        name=name,
        created_at=datetime.now().isoformat(),
        overrides_count=len(overrides),
        overrides={k: dict(v) for k, v in overrides.items()},
        summary=summary,
        settings=settings,
    )


def get_all_snapshots() -> List[Dict]:
    return db_list_snapshots()


def _rebuild_fwd_demand_and_recomm(hcs: List[int], channels: List[str] = None):
    """Rebuild _FORWARD_DEMAND_INDEX + _WOS_DEMAND_INDEX from WP_DATA + current overrides
    for given SKUs, then recompute recomm_receipt_units in WP_DATA for those SKUs.

    Called whenever written_sales_units change (top-down or single-cell edit) so
    recomm and WOS for ALL weeks stay consistent with the updated demand.
    """
    _channels = channels if channels is not None else CHANNELS
    overrides = db_get_overrides()
    wk_pos = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}

    for hc in hcs:
        m = get_effective_metrics(hc)
        look_ahead = m["lead_time_weeks"] + m["safety_weeks"]
        if look_ahead <= 0:
            continue

        for ch in _channels:
            # Effective units per week — mirrors _recalc logic for each trigger type
            eff_units: Dict[int, int] = {}
            for r in WP_DATA:
                if r["hierarchy_code"] != hc or r["channel"] != ch:
                    continue
                key = _ovr_key(hc, r["current_week"], ch)
                ovr = overrides.get(key, {})
                trigger = ovr.get("_last_edited")

                if trigger == "written_sales_units" and "written_sales_units" in ovr:
                    # Scenario 1: units edited directly
                    eff_units[r["current_week"]] = int(ovr["written_sales_units"])
                elif trigger == "written_sales_dollars" and "written_sales_dollars" in ovr:
                    # Scenario 2: dollars edited → back-calc units (same as _recalc)
                    air = r["written_air"]
                    dr  = float(ovr.get("written_dr_perc", r["written_dr_perc"]))
                    aur = round(air * (1 - dr), 2)
                    eff_units[r["current_week"]] = int(round(ovr["written_sales_dollars"] / aur)) if aur > 0 else 0
                elif trigger == "written_dr_perc" and "written_dr_perc" in ovr:
                    # Scenarios 3/4: disc% edited — units may have changed
                    mode = ovr.get("_edit_mode", "hold_units")
                    air  = r["written_air"]
                    dr   = float(ovr["written_dr_perc"])
                    aur  = round(air * (1 - dr), 2)
                    if mode == "hold_units":
                        eff_units[r["current_week"]] = r["written_sales_units"]
                    else:  # hold_dollars
                        dollars = float(ovr.get("written_sales_dollars", r["written_sales_dollars"]))
                        eff_units[r["current_week"]] = int(round(dollars / aur)) if aur > 0 else 0
                else:
                    eff_units[r["current_week"]] = r["written_sales_units"]

            # Rebuild demand + pipeline indexes for all weeks of this SKU×channel
            lt = m["lead_time_weeks"]
            # Build oo_ovr + ing_map once (not inside the 52-week loop).
            oo_ovr = {
                r["current_week"]: overrides.get(
                    _ovr_key(hc, r["current_week"], ch), {}
                ).get("on_order_placed_total_unit", r["on_order_placed_total_unit"])
                for r in WP_DATA
                if r["hierarchy_code"] == hc and r["channel"] == ch
            }
            ing_map = {
                r["current_week"]: r.get("ingested_receipt_units", 0)
                for r in WP_DATA
                if r["hierarchy_code"] == hc and r["channel"] == ch
            }
            for wk in FISCAL_WEEKS:
                idx = wk_pos[wk]
                _FORWARD_DEMAND_INDEX[(hc, ch, wk)] = sum(
                    eff_units.get(fw, 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + look_ahead]
                )
                _WOS_DEMAND_INDEX[(hc, ch, wk)] = sum(
                    eff_units.get(fw, 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + WOS_WINDOW]
                )
                # Pipeline = total receipts ARRIVING next LT weeks = ingested supply
                # + planner OOP landing there (Rcpt[fw] = ingested[fw] + OOP[fw−LT]).
                # Must match _rebuild_pipeline_and_recomm so recomm stays consistent
                # whether the last edit was sales or OO Placed.
                _PIPELINE_INDEX[(hc, ch, wk)] = sum(
                    ing_map.get(fw, 0) + oo_ovr.get(_week_offset(fw, -lt), 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + lt]
                )

        # Rewrite recomm in WP_DATA for this SKU (non-overridden rows serve their value directly)
        for r in WP_DATA:
            if r["hierarchy_code"] != hc:
                continue
            if r["actualised"] or r.get("is_ongoing"):
                r["recomm_receipt_units"] = 0
            else:
                r["recomm_receipt_units"] = _compute_recomm_receipt(
                    hc, r["channel"], r["current_week"],
                    r["eop_units"],
                )


def _rebuild_pipeline_and_recomm(hcs: List[int], channels: List[str] = None):
    """Rebuild _PIPELINE_INDEX and recompute recomm for given SKUs after OO Placed edit.
    Lighter than _rebuild_fwd_demand_and_recomm — demand indexes are unchanged."""
    _channels = channels if channels is not None else CHANNELS
    overrides  = db_get_overrides()
    wk_pos     = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}

    for hc in hcs:
        m  = get_effective_metrics(hc)
        lt = m["lead_time_weeks"]
        for ch in _channels:
            oo_map = {
                r["current_week"]: overrides.get(
                    _ovr_key(hc, r["current_week"], ch), {}
                ).get("on_order_placed_total_unit", r["on_order_placed_total_unit"])
                for r in WP_DATA
                if r["hierarchy_code"] == hc and r["channel"] == ch
            }
            ing_map = {
                r["current_week"]: r.get("ingested_receipt_units", 0)
                for r in WP_DATA
                if r["hierarchy_code"] == hc and r["channel"] == ch
            }
            # Recomm pipeline = total receipts ARRIVING next LT weeks (avoid double-order):
            #   Rcpt[fw] = ingested[fw] + OOP[fw−LT]
            for wk in FISCAL_WEEKS:
                idx = wk_pos[wk]
                _PIPELINE_INDEX[(hc, ch, wk)] = sum(
                    ing_map.get(fw, 0) + oo_map.get(_week_offset(fw, -lt), 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + lt]
                )
        for r in WP_DATA:
            if r["hierarchy_code"] != hc:
                continue
            if r["actualised"] or r.get("is_ongoing"):
                r["recomm_receipt_units"] = 0
            else:
                r["recomm_receipt_units"] = _compute_recomm_receipt(
                    hc, r["channel"], r["current_week"], r["eop_units"],
                )


def _reset_fwd_demand_and_recomm():
    """Rebuild _FORWARD_DEMAND_INDEX from original WP_DATA units (no planning overrides)
    and recompute WP_DATA recomm_receipt_units.  Called after reset_overrides() so recomm
    snaps back to baseline.  Respects persisted SKU settings (case pack, lead time etc.)."""
    wk_pos = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}

    # WP_DATA written_sales_units are always original — overrides only live in DB / _recalc,
    # never mutated in-place on WP_DATA rows.
    demand_map: Dict[tuple, int] = {
        (r["hierarchy_code"], r["channel"], r["current_week"]): r["written_sales_units"]
        for r in WP_DATA
    }
    # Baseline OO Placed (before any overrides) + ingested supply baseline
    oo_base_map: Dict[tuple, int] = {
        (r["hierarchy_code"], r["channel"], r["current_week"]): r["on_order_placed_total_unit"]
        for r in WP_DATA
    }
    ing_base_map: Dict[tuple, int] = {
        (r["hierarchy_code"], r["channel"], r["current_week"]): r.get("ingested_receipt_units", 0)
        for r in WP_DATA
    }

    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m  = get_effective_metrics(hc)   # honours persisted SKU settings
        look_ahead = m["lead_time_weeks"] + m["safety_weeks"]
        if look_ahead <= 0:
            continue
        lt = m["lead_time_weeks"]
        for ch in CHANNELS:
            for wk in FISCAL_WEEKS:
                idx = wk_pos[wk]
                _FORWARD_DEMAND_INDEX[(hc, ch, wk)] = sum(
                    demand_map.get((hc, ch, fw), 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + look_ahead]
                )
                _WOS_DEMAND_INDEX[(hc, ch, wk)] = sum(
                    demand_map.get((hc, ch, fw), 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + WOS_WINDOW]
                )
                # Pipeline = total receipts arriving next LT weeks: ingested[fw] + OOP[fw−LT].
                _PIPELINE_INDEX[(hc, ch, wk)] = sum(
                    ing_base_map.get((hc, ch, fw), 0)
                    + oo_base_map.get((hc, ch, _week_offset(fw, -lt)), 0)
                    for fw in FISCAL_WEEKS[idx + 1: idx + 1 + lt]
                )

    for r in WP_DATA:
        if r["actualised"] or r.get("is_ongoing"):
            r["recomm_receipt_units"] = 0
        else:
            r["recomm_receipt_units"] = _compute_recomm_receipt(
                r["hierarchy_code"], r["channel"], r["current_week"],
                r["eop_units"],
            )


def clear_single_override(hc: int, wk: int, ch: str) -> Dict:
    """Remove override for one cell. Rebuilds indexes if demand/OO changed. Returns fresh row.

    The fiscal year is encoded in the week code (202730 → 2027). Scope the index
    rebuild (walks FISCAL_WEEKS) and the re-read to that year so reset works in any
    viewed year — without it the rebuild touched 2026 and the re-read missed the row
    (404). For 2026 this is identical to not scoping.
    """
    year = wk // 100
    with _scoped_year(year):
        key = _ovr_key(hc, wk, ch)
        overrides = db_get_overrides()
        if key in overrides:
            last_edited = overrides[key].get("_last_edited")
            db_delete_override(key)
            if last_edited in ("written_sales_units", "written_sales_dollars", "written_dr_perc"):
                _rebuild_fwd_demand_and_recomm([hc], [ch])
            elif last_edited == "on_order_placed_total_unit":
                _rebuild_pipeline_and_recomm([hc], [ch])
        rows = get_agg_rows(hc, ch, year=year)
        return next((r for r in rows if r["current_week"] == wk), {})


def shift_receipts(hcs: List[int], channels: List[str], shift_weeks: int, year: int = DEFAULT_YEAR) -> Dict:
    """Shift OO Placed by N fiscal weeks, scoped to the viewed fiscal year."""
    with _scoped_year(year):
        return _shift_receipts_impl(hcs, channels, shift_weeks, year)


def _shift_receipts_impl(hcs: List[int], channels: List[str], shift_weeks: int, year: int = DEFAULT_YEAR) -> Dict:
    """Shift all OO Placed values for given SKUs×channels by N fiscal weeks.

    Positive shift_weeks = push later (supplier delay).
    Negative shift_weeks = pull earlier (accelerate delivery).
    OOs that would land outside the planning window are dropped.

    Returns: {"shifted": count, "dropped": count}
    """
    if shift_weeks == 0:
        return {"shifted": 0, "dropped": 0}

    # In a future year (every week > CURRENT_WEEK) all weeks are planning.
    planning_wks = {w for w in FISCAL_WEEKS if w > CURRENT_WEEK} or set(FISCAL_WEEKS)
    overrides = db_get_overrides()
    updates: Dict[str, Dict] = {}

    shifted = 0
    dropped = 0

    for hc in hcs:
        for ch in channels:
            # Collect current OO for planning weeks (from live agg rows so overrides are reflected)
            oo_by_week: Dict[int, float] = {}
            for r in get_agg_rows(hc, ch, year=year):
                if r["current_week"] in planning_wks:
                    oo = float(r.get("on_order_placed_total_unit", 0))
                    if oo > 0:
                        oo_by_week[r["current_week"]] = oo

            if not oo_by_week:
                continue

            # Build destination mapping
            new_oo: Dict[int, float] = {}
            for src_wk, oo in oo_by_week.items():
                try:
                    src_idx = FISCAL_WEEKS.index(src_wk)
                except ValueError:
                    dropped += 1
                    continue
                dst_idx = src_idx + shift_weeks
                if 0 <= dst_idx < len(FISCAL_WEEKS):
                    dst_wk = FISCAL_WEEKS[dst_idx]
                    if dst_wk in planning_wks:
                        new_oo[dst_wk] = new_oo.get(dst_wk, 0.0) + oo
                        shifted += 1
                    else:
                        dropped += 1
                else:
                    dropped += 1

            # Write zero to all source weeks, then new values to destination weeks
            all_affected = planning_wks & (set(oo_by_week) | set(new_oo))
            for wk in all_affected:
                key = _ovr_key(hc, wk, ch)
                entry = dict(overrides.get(key, {}))
                entry["on_order_placed_total_unit"] = float(round(new_oo.get(wk, 0.0)))
                entry["_last_edited"] = "on_order_placed_total_unit"
                updates[key] = entry

    if updates:
        db_batch_upsert_overrides(updates)
        _rebuild_pipeline_and_recomm(hcs, channels)

    return {"shifted": shifted, "dropped": dropped}


def accept_recomm_receipts(hcs: List[int], channels: List[str], year: int = DEFAULT_YEAR) -> int:
    """Add the recommended residual to OO Placed for all planning weeks of given SKUs×channels.

    One-click replacement for manually editing OO Placed week-by-week. Returns count of
    rows updated. Operates on the viewed fiscal year.

    SINGLE BATCH: read the recomm column ONCE, then set each planning week's
    OOP = current_OOP + recomm. Recomm already credits already-placed OOP as supply
    (see `_level_order_schedule.need`), so the column IS the coherent residual plan that
    covers every week — placing it all at once gives full coverage with no over-supply.
    (The old chronological re-read loop is wrong now that the target depends on placed OOP:
    each placement shrank the remaining target → long-LT SKUs under-converged.)
    A re-read after this returns recomm 0 everywhere (idempotent). Locked weeks never order.
    """
    # BATCHED: exactly the per-week apply_edit(on_order_placed_total_unit) path, but the
    # costs that made it O(n^2)/180-builds are hoisted out:
    #   • recomm read: ONE get_agg_rows(None,None) portfolio build instead of one per
    #     (hc,ch). Placeholders are excluded from the portfolio sweep, so a placeholder hc
    #     still reads per-stream (always a single hidden SKU anyway).
    #   • write: every row in ONE transaction / ONE commit (was: commit per week).
    #   • recomm rebuild: ONCE for all touched streams (was: rebuild per week).
    # A stream's recomm is computed independently of other streams, so reading it from the
    # portfolio build is identical to reading it per-(hc,ch). Verified byte-identical to the
    # old loop (overrides + full get_agg_rows + audit + idempotency) on F-CSV6/LONGLT/
    # EARLYPEAK/DUPNAME/CSV60. Recomm/chain math itself is untouched.
    overrides = db_get_overrides()                      # read ONCE (was: per apply_edit)
    # First base row per (hc, ch, wk) for the audit old_value — matches apply_edit's
    # next(...) "first match" semantics.
    wp_by: Dict[tuple, Dict] = {}
    for _r in WP_DATA:
        wp_by.setdefault((_r["hierarchy_code"], _r["channel"], _r["current_week"]), _r)

    req_hcs, req_chs = set(hcs), set(channels)
    ph_hcs = [hc for hc in hcs if hc in PLACEHOLDER_HCS]
    rows = [
        r for r in get_agg_rows(None, None, year=year)
        if r["hierarchy_code"] in req_hcs and r["channel"] in req_chs
    ] if any(hc not in PLACEHOLDER_HCS for hc in hcs) else []
    for hc in ph_hcs:
        for ch in channels:
            rows += get_agg_rows(hc, ch, year=year)

    upserts: List[tuple] = []       # (key, entry)
    audit_rows: List[tuple] = []    # (hc, ch, wk, field, old_value, new_value)
    touched_hcs, touched_chs = set(), set()
    count = 0
    # SINGLE batch per stream: recomm already credits placed OOP as supply, so the column
    # IS the coherent residual plan — add it to OOP once, no chronological re-loop.
    for r in rows:
        if r.get("actualised") or r.get("is_ongoing") or r.get("oo_locked"):
            continue
        rec = int(r.get("recomm_receipt_units", 0))
        if rec <= 0:
            continue
        hc, ch, wk = r["hierarchy_code"], r["channel"], r["current_week"]
        new_oop = int(r.get("on_order_placed_total_unit", 0)) + rec
        key = _ovr_key(hc, wk, ch)
        entry = overrides.get(key, {})
        old_value = entry.get("on_order_placed_total_unit")
        if old_value is None:
            _b = wp_by.get((hc, ch, wk))
            if _b:
                old_value = _b.get("on_order_placed_total_unit")
        value = float(round(new_oop))                   # same rounding as apply_edit
        entry["on_order_placed_total_unit"] = value
        entry["_last_edited"] = "on_order_placed_total_unit"
        overrides[key] = entry
        upserts.append((key, entry))
        audit_rows.append((hc, ch, wk, "on_order_placed_total_unit", old_value, value))
        touched_hcs.add(hc); touched_chs.add(ch)
        count += 1

    if upserts:
        db_batch_edit(upserts, audit_rows)              # ONE transaction / ONE commit
        with _scoped_year(year):                        # rebuild recomm ONCE for all streams
            _rebuild_pipeline_and_recomm(sorted(touched_hcs), sorted(touched_chs))
    return count


def undo_recomm_receipts(hcs: List[int], channels: List[str], year: int = DEFAULT_YEAR) -> int:
    """Inverse of accept_recomm_receipts: clear OO Placed on planning weeks.

    Removes the `on_order_placed_total_unit` override from every unlocked,
    non-actualised planning week of the given SKUs×channels, returning OO Placed
    to baseline (ingested-only) so the recomm reappears. Other overrides on the
    same week (e.g. written sales) are preserved — only the OO field is dropped.
    Returns count of weeks cleared.
    """
    # BATCHED (mirrors accept): one portfolio get_agg_rows for normal SKUs (+ per-stream for
    # placeholders), edit the overrides dict in memory, then persist in ONE atomic
    # db_replace_overrides — instead of a per-(hc,ch) build and a commit per week. End state
    # (overrides + recomm) is byte-identical to the old loop (verified vs golden).
    overrides = db_get_overrides()
    req_hcs, req_chs = set(hcs), set(channels)
    ph_hcs = [hc for hc in hcs if hc in PLACEHOLDER_HCS]
    rows = [
        r for r in get_agg_rows(None, None, year=year)
        if r["hierarchy_code"] in req_hcs and r["channel"] in req_chs
    ] if any(hc not in PLACEHOLDER_HCS for hc in hcs) else []
    for hc in ph_hcs:
        for ch in channels:
            rows += get_agg_rows(hc, ch, year=year)

    changed = False
    count = 0
    for r in rows:
        # Planning weeks where the planner could have placed an order.
        if r.get("actualised") or r.get("is_ongoing") or r.get("oo_locked"):
            continue
        key = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        entry = overrides.get(key)
        if not entry or "on_order_placed_total_unit" not in entry:
            continue
        rest = {
            k: v for k, v in entry.items()
            if k not in ("on_order_placed_total_unit", "_last_edited")
        }
        if rest:
            rest["_last_edited"] = "on_order_placed_total_unit"
            overrides[key] = rest
        else:
            del overrides[key]
        count += 1
        changed = True

    if changed:
        db_replace_overrides(overrides)                 # ONE atomic write (was: per week)
        with _scoped_year(year):
            _rebuild_pipeline_and_recomm(hcs, channels)
    return count


def undo_top_down(hcs: List[int], channels: List[str], year: int = DEFAULT_YEAR) -> int:
    """Inverse of apply_top_down: clear the written-sales split on planning weeks.

    Removes BOTH `written_sales_units` and `written_sales_dollars` overrides from
    every non-actualised, non-ongoing planning week of the given SKUs×channels,
    returning sales to baseline. Both fields are cleared (not just the one the
    split wrote) because they're price-linked — leaving one would desync the cell.
    OO Placed and disc% overrides on the same week are preserved.
    Returns count of weeks cleared.
    """
    sales_fields = ("written_sales_units", "written_sales_dollars")
    overrides = db_get_overrides()
    touched = False
    count = 0
    for hc in hcs:
        for ch in channels:
            planning_wks = {
                r["current_week"]
                for r in get_agg_rows(hc, ch, year=year)
                if not r.get("actualised") and not r.get("is_ongoing")
            }
            for wk in planning_wks:
                key = _ovr_key(hc, wk, ch)
                entry = overrides.get(key)
                if not entry or not any(f in entry for f in sales_fields):
                    continue
                rest = {
                    k: v for k, v in entry.items()
                    if k not in sales_fields and k not in ("_last_edited", "_edit_mode")
                }
                if rest:
                    # Re-anchor _last_edited to a surviving editable field so _recalc
                    # cascades off the right trigger.
                    if "on_order_placed_total_unit" in rest:
                        rest["_last_edited"] = "on_order_placed_total_unit"
                    elif "written_dr_perc" in rest:
                        rest["_last_edited"] = "written_dr_perc"
                    db_upsert_override(key, rest)
                else:
                    db_delete_override(key)
                count += 1
                touched = True
    if touched:
        with _scoped_year(year):
            _rebuild_fwd_demand_and_recomm(hcs, channels)
    return count


def preview_top_down(hcs: List[int], channels: List[str], target: float, field: str,
                     year: int = DEFAULT_YEAR) -> Dict:
    """Dry-run of apply_top_down — same weight logic, no DB writes.

    Returns per-week proposed values and an aggregated summary so the
    frontend can show a confirmation step before committing.
    """
    ly_field  = "ly_units"  if field == "written_sales_units" else "ly_dollars"
    lly_field = "lly_units" if field == "written_sales_units" else "lly_dollars"

    ly_map:  Dict[str, float] = {}
    lly_map: Dict[str, float] = {}
    for r in TY_LY_DATA:
        if r["hierarchy_code"] not in hcs or r["channel"] not in channels:
            continue
        k = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        ly_map[k]  = float(r.get(ly_field,  0) or 0)
        lly_map[k] = float(r.get(lly_field, 0) or 0)

    planning_rows: List[Dict] = []
    for hc in hcs:
        for ch in channels:
            for r in get_agg_rows(hc, ch, year=year):
                if not r["actualised"] and not r.get("is_ongoing", False):
                    planning_rows.append(r)

    if not planning_rows:
        return {"rows": [], "current_total": 0, "proposed_total": 0, "weeks": 0}

    weights: List[float] = []
    for r in planning_rows:
        k = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        w = ly_map.get(k, 0.0)
        if w <= 0: w = lly_map.get(k, 0.0)
        if w <= 0: w = float(r.get(field, 0) or 0)
        weights.append(w)

    total_w = sum(weights)
    rows_out = []
    for r, w in zip(planning_rows, weights):
        share   = (w / total_w) if total_w > 0 else (1 / len(planning_rows))
        proposed = round(target * share) if field == "written_sales_units" else round(target * share, 2)
        rows_out.append({
            "hierarchy_code": r["hierarchy_code"],
            "channel":        r["channel"],
            "current_week":   r["current_week"],
            "current":        r.get(field, 0),
            "proposed":       proposed,
            "weight_pct":     round(share * 100, 2),
        })

    current_total = sum(r.get(field, 0) for r in planning_rows)
    return {
        "rows":           rows_out,
        "current_total":  round(current_total, 2),
        "proposed_total": round(target, 2),
        "weeks":          len({r["current_week"] for r in planning_rows}),
        "field":          field,
    }


def compare_snapshots(snap_a_id: int, snap_b_id: int) -> Dict:
    """Return side-by-side comparison of two snapshots at week×SKU×channel grain.

    snap_b_id=0 means "current live plan" (no save required).
    Uses get_agg_rows with each snapshot's override set so the BOP→EOP chain
    is computed correctly for both.  WOS/recomm values use current in-memory
    demand indexes (noted in UI); Sales/GM/EOP are fully accurate.
    """
    snap_a = db_get_snapshot(snap_a_id)
    if not snap_a:
        return {}

    rows_a = get_agg_rows(_overrides_override=snap_a["overrides"])

    # snap_b_id == 0 → use current live overrides (no snapshot required)
    if snap_b_id == 0:
        rows_b_list = get_agg_rows()
        live_plan = [r for r in rows_b_list if not r.get("actualised")]
        total_u = sum(r["written_sales_units"] for r in live_plan)
        total_d = round(sum(r["written_sales_dollars"] for r in live_plan), 2)
        total_g = round(sum(r["written_gm_dollar"] for r in live_plan), 2)
        snap_b_meta    = {"id": 0, "name": "Live Plan", "created_at": "now"}
        snap_b_summary = {
            "total_sales_units":   total_u,
            "total_sales_dollars": total_d,
            "total_gm_dollar":     total_g,
            "avg_gm_perc":         round(total_g / total_d if total_d else 0, 4),
        }
    else:
        snap_b = db_get_snapshot(snap_b_id)
        if not snap_b:
            return {}
        rows_b_list    = get_agg_rows(_overrides_override=snap_b["overrides"])
        snap_b_meta    = {"id": snap_b["id"], "name": snap_b["name"], "created_at": snap_b["created_at"]}
        snap_b_summary = snap_b["summary"]

    lkp_a = {(r["hierarchy_code"], r["channel"], r["current_week"]): r for r in rows_a}
    lkp_b = {(r["hierarchy_code"], r["channel"], r["current_week"]): r for r in rows_b_list}

    # All planning-week keys from either snapshot
    all_keys = {k for k, r in {**lkp_a, **lkp_b}.items()
                if not r.get("actualised") and not r.get("is_ongoing")}

    rows_out = []
    for (hc, ch, wk) in sorted(all_keys):
        ra = lkp_a.get((hc, ch, wk), {})
        rb = lkp_b.get((hc, ch, wk), {})
        rows_out.append({
            "hierarchy_code":   hc,
            "l2_name":          rb.get("l2_name") or ra.get("l2_name", ""),
            "channel":          ch,
            "current_week":     wk,
            "a_sales_units":    ra.get("written_sales_units", 0),
            "b_sales_units":    rb.get("written_sales_units", 0),
            "delta_sales_units": rb.get("written_sales_units", 0) - ra.get("written_sales_units", 0),
            "a_sales_dollars":  ra.get("written_sales_dollars", 0.0),
            "b_sales_dollars":  rb.get("written_sales_dollars", 0.0),
            "delta_sales_dollars": round(rb.get("written_sales_dollars", 0.0) - ra.get("written_sales_dollars", 0.0), 2),
            "a_gm_dollar":      ra.get("written_gm_dollar", 0.0),
            "b_gm_dollar":      rb.get("written_gm_dollar", 0.0),
            "delta_gm_dollar":  round(rb.get("written_gm_dollar", 0.0) - ra.get("written_gm_dollar", 0.0), 2),
            "a_eop":            ra.get("eop_units", 0),
            "b_eop":            rb.get("eop_units", 0),
            "delta_eop":        rb.get("eop_units", 0) - ra.get("eop_units", 0),
            "a_receipts":       ra.get("total_receipt_units", 0),
            "b_receipts":       rb.get("total_receipt_units", 0),
            "delta_receipts":   rb.get("total_receipt_units", 0) - ra.get("total_receipt_units", 0),
        })

    sa_sum = snap_a["summary"]
    sb_sum = snap_b_summary
    return {
        "snap_a": {"id": snap_a["id"], "name": snap_a["name"], "created_at": snap_a["created_at"]},
        "snap_b": snap_b_meta,
        "summary": {
            "a_sales_units":    sa_sum.get("total_sales_units", 0),
            "b_sales_units":    sb_sum.get("total_sales_units", 0),
            "a_sales_dollars":  sa_sum.get("total_sales_dollars", 0.0),
            "b_sales_dollars":  sb_sum.get("total_sales_dollars", 0.0),
            "a_gm_dollar":      sa_sum.get("total_gm_dollar", 0.0),
            "b_gm_dollar":      sb_sum.get("total_gm_dollar", 0.0),
        },
        "rows": rows_out,
    }


def get_exceptions_panel(year: int = DEFAULT_YEAR) -> List[Dict]:
    """Return one row per SKU×channel showing worst exception (non-ok only).

    Groups week-level coverage data into SKU×channel summary rows so the panel
    shows "N SKUs need attention" not "480 week rows."  Each row carries the
    worst-coverage week for that combo plus the actual problem weeks:
      - stockout exceptions → weeks where EOP actually hits 0 (_stockout)
      - excess exceptions   → weeks where coverage genuinely exceeds threshold
    This avoids showing "observation weeks" (weeks from which you notice an
    upcoming problem) and instead shows WHERE the problem occurs.

    Scoped to `year` so the panel matches the year the grid is showing (a panel
    hardcoded to DEFAULT_YEAR flagged the 2026 stockout while the user viewed a
    fixed 2027 plan).
    """
    all_rows = get_agg_rows(year=year)
    severity_order = {"critical": 0, "low": 1, "excess": 2}

    # Pass 1: collect actual problem weeks per combo (what the planner cares about)
    # and classify each observation week to determine exception_status.
    actual_stockout_wks: Dict[tuple, List[int]] = {}  # weeks where EOP = 0
    actual_excess_wks: Dict[tuple, List[int]] = {}    # weeks where cov > threshold

    raw: List[Dict] = []
    for r in all_rows:
        if r.get("actualised") or r.get("is_ongoing"):
            continue
        hc  = r["hierarchy_code"]
        ch  = r["channel"]
        key = (hc, ch)
        m   = get_effective_metrics(hc)
        lt  = m["lead_time_weeks"]
        tw  = get_target_wos(hc, ch)
        fc  = r.get("fwd_coverage_wks")
        cov = fc if fc is not None else r.get("wos")
        if cov is None:
            continue

        # Excess line must MATCH the cell-coloring rule, else the panel and the
        # grid disagree (panel false-flagged Hoodies as excess at FC≈13 while the
        # grid showed it green). FC carries the in-transit pipeline → excess only
        # above lead_time + target_wos. WOS (on-hand only) → target_wos × 1.5.
        excess_line = (lt + tw) if fc is not None else (tw * 1.5)

        # Track actual EOP=0 weeks (real stockout, not observation)
        if r.get("_stockout"):
            actual_stockout_wks.setdefault(key, []).append(r["current_week"])

        # Track actual excess weeks
        if cov > excess_line:
            actual_excess_wks.setdefault(key, []).append(r["current_week"])

        order_gap = max(0, r.get("recomm_receipt_units", 0) - r.get("on_order_placed_total_unit", 0))
        first_so  = r.get("first_stockout_week")

        # Classification uses the EOP chain (real stockout timing), NOT FC.
        if r.get("_stockout_in_lt"):
            status = "critical"
        elif first_so is not None and order_gap > 0:
            status = "low"
        elif cov > excess_line:
            status = "excess"
        else:
            continue
        raw.append({
            "hierarchy_code":    hc,
            "l2_name":           r.get("l2_name", ""),
            "channel":           ch,
            "current_week":      r["current_week"],
            "exception_status":  status,
            "coverage_wks":      round(cov, 1),
            "lead_time_weeks":   lt,
            "eop_units":         r["eop_units"],
            "wos":               r.get("wos"),
            "first_stockout_week": r.get("first_stockout_week"),
        })

    # Pass 2: group by SKU×channel — pick worst representative week, attach actual
    # problem week ranges (not observation weeks).
    by_combo: Dict[tuple, Dict] = {}
    for row in raw:
        key = (row["hierarchy_code"], row["channel"])
        status = row["exception_status"]
        if key not in by_combo:
            by_combo[key] = {**row}
        else:
            existing = by_combo[key]
            # Pick the representative "worst" week:
            #   - higher severity always wins
            #   - same severity: stockout → LOWEST coverage (closest to dry)
            #                    excess   → HIGHEST coverage (most overstocked)
            same_sev = status == existing["exception_status"]
            if same_sev:
                worse = (row["coverage_wks"] > existing["coverage_wks"]
                         if status == "excess"
                         else row["coverage_wks"] < existing["coverage_wks"])
            else:
                worse = severity_order[status] < severity_order[existing["exception_status"]]
            if worse:
                by_combo[key] = {**row}

    # Pass 3: attach actual problem week ranges to each combo row
    for key, v in by_combo.items():
        rep_status = v["exception_status"]
        affected: Dict[str, List[int]] = {}
        if rep_status in ("critical", "low"):
            so_wks = sorted(actual_stockout_wks.get(key, []))
            if so_wks:
                affected["critical"] = so_wks
            elif v.get("first_stockout_week"):
                # Stockout week itself may be outside planning grid (end of season);
                # fall back to flagging the first_stockout_week as a single point.
                affected["low"] = [v["first_stockout_week"]]
        else:
            ex_wks = sorted(actual_excess_wks.get(key, []))
            if ex_wks:
                affected["excess"] = ex_wks
        v["affected_by_status"] = affected
        v["affected_weeks"] = sum(len(wks) for wks in affected.values())

    result = list(by_combo.values())
    return sorted(result, key=lambda x: (severity_order[x["exception_status"]], x["coverage_wks"]))


def get_budget(hc_list: List[int] = None, ch_list: List[str] = None, year: int = DEFAULT_YEAR) -> Dict:
    """Return OTB receipt budget (ingested per SKU×channel), consumption, and category breakdown."""
    planned_cost = 0.0
    budget = 0.0
    category_costs: Dict[str, float] = {}
    seen_combos: set = set()
    for r in get_agg_rows(year=year):
        if hc_list is not None and r["hierarchy_code"] not in hc_list:
            continue
        if ch_list is not None and r["channel"] not in ch_list:
            continue
        cost = r["total_receipt_units"] * r.get("written_auc", 0)
        planned_cost += cost
        cat = r.get("l1_name", "Other")
        category_costs[cat] = category_costs.get(cat, 0.0) + cost
        combo = (r["hierarchy_code"], r["channel"])
        if combo not in seen_combos:
            seen_combos.add(combo)
            budget += BUDGET_DATA.get(combo, 0.0)

    planned_cost = round(planned_cost, 2)
    budget = round(budget, 2)
    category_breakdown = {cat: round(v, 2) for cat, v in sorted(category_costs.items())}
    remaining = round(budget - planned_cost, 2) if budget > 0 else None
    pct_consumed = round(planned_cost / budget, 4) if budget > 0 else None
    return {
        "budget":             budget,
        "planned_cost":       planned_cost,
        "remaining":          remaining,
        "pct_consumed":       pct_consumed,
        "category_breakdown": category_breakdown,
    }


def get_audit_log(limit: int = 100, hierarchy_code: int = None, field: str = None) -> List[Dict]:
    return db_get_audit_log(limit, hierarchy_code=hierarchy_code, field=field)


def get_season_progress(hc_list: List[int] = None, ch_list: List[str] = None, year: int = DEFAULT_YEAR) -> Dict:
    """Actualized-to-date vs full-year plan — season pace tracking."""
    all_rows = get_agg_rows(year=year)
    if hc_list is not None:
        all_rows = [r for r in all_rows if r["hierarchy_code"] in hc_list]
    if ch_list is not None:
        all_rows = [r for r in all_rows if r["channel"] in ch_list]
    plan_u = sum(r["written_sales_units"] for r in all_rows)
    plan_d = round(sum(r["written_sales_dollars"] for r in all_rows), 2)
    act_u  = sum(r.get("actual_sales_units", 0) for r in all_rows if r.get("actualised"))
    act_d  = round(sum(r.get("actual_sales_dollars", 0.0) for r in all_rows if r.get("actualised")), 2)
    wks_act = len({r["current_week"] for r in all_rows if r.get("actualised")})
    wks_rem = len({r["current_week"] for r in all_rows if not r.get("actualised") and not r.get("is_ongoing")})
    return {
        "actualized_units":   act_u,
        "actualized_dollars": act_d,
        "plan_units":         plan_u,
        "plan_dollars":       plan_d,
        "pct_units":          round(act_u / plan_u, 4) if plan_u else 0.0,
        "pct_dollars":        round(act_d / plan_d, 4) if plan_d else 0.0,
        "weeks_actualized":   wks_act,
        "weeks_remaining":    wks_rem,
    }


def apply_top_down(hcs: List[int], channels: List[str], target: float, field: str,
                   week_values: List[Dict] = None, year: int = DEFAULT_YEAR) -> int:
    """Distribute `target` across the viewed year's planning weeks (scoped)."""
    with _scoped_year(year):
        return _apply_top_down_impl(hcs, channels, target, field, week_values, year)


def _apply_top_down_impl(hcs: List[int], channels: List[str], target: float, field: str,
                         week_values: List[Dict] = None, year: int = DEFAULT_YEAR) -> int:
    """
    Distribute `target` across all planning weeks (not actualised, not ongoing)
    for the given HCs × channels.

    If week_values is provided (list of {hierarchy_code, channel, current_week, value}),
    those explicit values are applied directly — skipping the LY-weight computation.
    This supports the "edit preview values then confirm" UX pattern.

    Weight basis (when week_values not provided):
      1st priority – LY value for that cell
      2nd priority – LLY value (if LY == 0)
      3rd priority – current plan value (if LY == 0 AND LLY == 0)

    Returns the number of rows updated.
    """
    ly_field  = "ly_units"  if field == "written_sales_units" else "ly_dollars"
    lly_field = "lly_units" if field == "written_sales_units" else "lly_dollars"

    # Build LY / LLY weight maps from TY_LY_DATA
    ly_map:  Dict[str, float] = {}
    lly_map: Dict[str, float] = {}
    for r in TY_LY_DATA:
        if r["hierarchy_code"] not in hcs:
            continue
        if r["channel"] not in channels:
            continue
        k = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        ly_map[k]  = float(r.get(ly_field,  0) or 0)
        lly_map[k] = float(r.get(lly_field, 0) or 0)

    # Collect planning rows (not actualised, not the ongoing/current week)
    planning_rows: List[Dict] = []
    for hc in hcs:
        for ch in channels:
            for r in get_agg_rows(hc, ch, year=year):
                if not r["actualised"] and not r.get("is_ongoing", False):
                    planning_rows.append(r)

    if not planning_rows:
        return 0

    all_overrides = db_get_overrides()
    updates: Dict[str, Dict] = {}

    if week_values:
        # Direct application — frontend already computed per-row values
        value_map = {
            _ovr_key(wv["hierarchy_code"], wv["current_week"], wv["channel"]): wv["value"]
            for wv in week_values
        }
        for r in planning_rows:
            key = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
            if key not in value_map:
                continue
            new_val = value_map[key]
            if field in ("written_sales_units", "on_order_placed_total_unit"):
                new_val = float(round(new_val))
            else:
                new_val = round(new_val, 2)
            entry = dict(all_overrides.get(key, {}))
            entry[field] = new_val
            entry["_last_edited"] = field
            updates[key] = entry
    else:
        # Compute weights using LY → LLY → current plan fallback
        weights: List[float] = []
        for r in planning_rows:
            k = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
            w = ly_map.get(k, 0.0)
            if w <= 0:
                w = lly_map.get(k, 0.0)
            if w <= 0:
                w = float(r.get(field, 0) or 0)
            weights.append(w)

        total_w = sum(weights)
        if total_w <= 0:
            return 0

        for r, w in zip(planning_rows, weights):
            new_val = (w / total_w) * target
            if field in ("written_sales_units", "on_order_placed_total_unit"):
                new_val = float(round(new_val))
            else:
                new_val = round(new_val, 2)
            key = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
            entry = dict(all_overrides.get(key, {}))
            entry[field] = new_val
            entry["_last_edited"] = field
            updates[key] = entry

    # One DB transaction for all writes
    db_batch_upsert_overrides(updates)

    # Rebuild forward demand index + recomm for affected SKUs so recomm stays consistent
    if field in ("written_sales_units", "written_sales_dollars"):
        _rebuild_fwd_demand_and_recomm(hcs, channels)

    return len(updates)


# ── Startup: re-materialize persisted placeholders ────────────────────────────────
# Runs after all engine state (WP_DATA, indexes, metrics) and helpers are defined.
# Each placeholder is re-cloned from its source's immutable seed; the planner's own
# edits live in the overrides table (keyed by the placeholder hc) and replay on top.
_materialize_all_placeholders()
