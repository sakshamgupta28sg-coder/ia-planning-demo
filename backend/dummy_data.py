import math as _math
import random
from typing import Dict, List

random.seed(42)

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

# Fiscal weeks 202601..202652
FISCAL_WEEKS = [int(f"2026{str(w).zfill(2)}") for w in range(1, 53)]
_SEASON_END_WK = FISCAL_WEEKS[-1]   # last week — planned runout to 0 here is intentional
_WK_POS = {wk: i for i, wk in enumerate(FISCAL_WEEKS)}


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
    10001: {"air": 119.99, "auc": 44.0,  "peak_week": 26, "peak_units":  520,  # Running Shoes  – spring marathon season (late-spring peak)
            "target_wos": 6, "lead_time_weeks": 14, "case_pack":  6, "safety_weeks": 2},
    10002: {"air":  89.99, "auc": 30.0,  "peak_week": 25, "peak_units":  680,  # Casual Sneakers – summer
            "target_wos": 6, "lead_time_weeks": 12, "case_pack":  6, "safety_weeks": 2},
    10003: {"air": 154.99, "auc": 55.0,  "peak_week": 41, "peak_units":  450,  # Ankle Boots    – fall
            "target_wos": 8, "lead_time_weeks": 16, "case_pack":  4, "safety_weeks": 3},
    10004: {"air":  64.99, "auc": 21.0,  "peak_week": 22, "peak_units":  750,  # Sandals        – summer
            "target_wos": 5, "lead_time_weeks": 10, "case_pack": 12, "safety_weeks": 1},
    10005: {"air":  79.99, "auc": 27.0,  "peak_week": 38, "peak_units":  900,  # Denim Jeans    – back-to-school
            "target_wos": 8, "lead_time_weeks": 14, "case_pack": 12, "safety_weeks": 2},
    10006: {"air":  34.99, "auc": 11.0,  "peak_week": 26, "peak_units": 1400,  # Graphic Tees   – summer
            "target_wos": 6, "lead_time_weeks": 10, "case_pack": 24, "safety_weeks": 2},
    10007: {"air":  69.99, "auc": 23.0,  "peak_week": 42, "peak_units":  800,  # Hoodies        – fall
            "target_wos": 8, "lead_time_weeks": 12, "case_pack": 12, "safety_weeks": 3},
    10008: {"air":  44.99, "auc": 14.0,  "peak_week": 24, "peak_units": 1100,  # Activewear Shorts – summer
            "target_wos": 5, "lead_time_weeks": 10, "case_pack": 24, "safety_weeks": 1},
}

CHANNEL_SPLIT = {"Ecom": 0.55, "Indirect": 0.30, "Store": 0.15}

# The fiscal week that is currently in-flight (not yet actualised, but not open for editing)
CURRENT_WEEK = 202620


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


def generate_wp_data() -> List[Dict]:
    global _FORWARD_DEMAND_INDEX, _WOS_DEMAND_INDEX
    rows: List[Dict] = []
    demand_index: Dict[tuple, int] = {}  # (hc, ch, wk) → planned sales units

    # ── Pass 1: generate rows + collect demand per cell ───────────────────────
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m = HIERARCHY_METRICS[hc]
        # Calibrate opening BOP so week 21 WOS ≈ (target_wos + 2) using 8-week window.
        bop = {}
        for _ch in CHANNELS:
            _fwd = sum(
                round(m["peak_units"] * CHANNEL_SPLIT[_ch] * _seasonal_curve(wn, m["peak_week"]))
                for wn in range(22, 22 + WOS_WINDOW)
            )
            _fwd_avg = _fwd / WOS_WINDOW
            bop[_ch] = round(_fwd_avg * (m["target_wos"] + 2))

        for ch in CHANNELS:
            wh = WAREHOUSE_SUB_CHANNELS[ch]
            for wk in FISCAL_WEEKS:
                week_num = wk % 100
                is_past     = week_num < 20
                is_ongoing  = (wk == CURRENT_WEEK)
                is_planning = not is_past and not is_ongoing

                curve = _seasonal_curve(week_num, m["peak_week"])
                dr    = _dr_perc(week_num, m["peak_week"])
                units = round(m["peak_units"] * CHANNEL_SPLIT[ch] * curve * random.uniform(0.9, 1.1))
                aur   = round(m["air"] * (1 - dr), 2)
                sales_dollars = round(aur * units, 2)
                sales_cost    = round(m["auc"] * units, 2)
                gm_dollar     = round(sales_dollars - sales_cost, 2)
                gm_perc       = round((gm_dollar / sales_dollars) if sales_dollars else 0, 4)

                current_bop = round(bop[ch])
                # Past / ongoing: historical receipts (random noise).
                # Planning:       placeholder 0 — Pass 1b will set correct target-WOS receipts.
                if is_past or is_ongoing:
                    receipt_units = round(units * 1.1 * random.uniform(0.8, 1.2))
                else:
                    receipt_units = 0
                eop = max(0, current_bop - units + receipt_units)
                bop[ch] = eop

                actual_units   = round(units * random.uniform(0.78, 1.08)) if is_past else 0
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
                    "on_order_placed_total_unit": 0,               # planner's NEW orders only (0 at baseline)
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
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m  = HIERARCHY_METRICS[hc]
        cp = m["case_pack"]
        for ch in CHANNELS:
            ongoing = row_lkp.get((hc, ch, CURRENT_WEEK))
            prev_eop = ongoing["eop_units"] if ongoing else 0
            for wk in FISCAL_WEEKS:
                r = row_lkp.get((hc, ch, wk))
                if not r or r.get("actualised") or r.get("is_ongoing"):
                    continue
                # BOP = previous week's EOP
                r["bop_units"] = prev_eop
                r["bop_cost"]  = round(prev_eop * m["auc"], 2)
                sales = r["written_sales_units"]
                eop_no_rcpt = max(0, prev_eop - sales)
                # Target EOP = target_wos × 8-week forward avg
                wos_dem  = _WOS_DEMAND_INDEX.get((hc, ch, wk), 0)
                fwd_avg8 = wos_dem / WOS_WINDOW if WOS_WINDOW > 0 else 0
                target_eop = round(m["target_wos"] * fwd_avg8)
                if target_eop <= eop_no_rcpt:
                    receipt = 0
                else:
                    raw     = target_eop - eop_no_rcpt
                    receipt = int(_math.ceil(raw / cp) * cp) if cp > 0 else int(raw)
                eop = eop_no_rcpt + receipt
                # This target-WOS receipt schedule IS the ingested supply baseline.
                r["total_receipt_units"]         = receipt
                r["ingested_receipt_units"]      = receipt   # independent supply (immutable)
                r["on_order_placed_total_unit"]  = 0         # planner places orders ON TOP
                r["eop_units"] = eop
                r["eop_cost"]  = round(eop * m["auc"], 2)
                prev_eop = eop

    # ── OO Placed locks (tail weeks) ─────────────────────────────────────────────
    # OOP[W] = NEW orders the planner places; they arrive at W+LT and ADD to Rcpt
    # (Rcpt[W] = ingested[W] + OOP[W−LT]). Baseline OOP = 0 (set above). A week is
    # locked when W+LT lands past season end — that order could never be received.
    for h in HIERARCHIES:
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
                ty_dollars = round(ty_units * m["air"] * (1 - _dr_perc(week_num, m["peak_week"])), 2)
                ly_dollars = round(ly_units * m["air"] * (1 - _dr_perc(week_num, m["peak_week"])), 2)
                lly_dollars = round(lly_units * m["air"] * (1 - _dr_perc(week_num, m["peak_week"])), 2)
                rows.append({
                    "hierarchy_code": hc,
                    "l1_name": h["l1_name"],
                    "l2_name": h["l2_name"],
                    "channel": ch,
                    "current_week": wk,
                    "compared_week":     int(str(wk).replace("2026", "2025")),
                    "compared_week_lly": int(str(wk).replace("2026", "2024")),
                    "ty_units": ty_units,
                    "ly_units": ly_units,
                    "lly_units": lly_units,
                    "ty_dollars": ty_dollars,
                    "ly_dollars": ly_dollars,
                    "lly_dollars": lly_dollars,
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


# Pre-generate on import
WP_DATA = generate_wp_data()
TY_LY_DATA = generate_ty_ly_data()
SCENARIO_DATA = generate_scenario_data()

# ── Override / Snapshot layer ──────────────────────────────────────────────────
from datetime import datetime
from database import (
    init_db,
    db_get_overrides, db_upsert_override, db_clear_overrides, db_replace_overrides,
    db_batch_upsert_overrides,
    db_list_snapshots, db_get_snapshot, db_insert_snapshot, db_delete_snapshot, db_rename_snapshot,
    db_get_all_sku_settings, db_upsert_sku_setting,
    db_get_all_channel_settings, db_upsert_channel_setting,
    db_get_all_new_skus, db_get_max_new_sku_hc, db_insert_new_sku, db_delete_new_sku,
    db_delete_override,
    db_log_audit, db_get_audit_log,
    db_get_setting, db_set_setting,
)

init_db()  # create tables on first import; no-op if already exist

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
            _PIPELINE_INDEX[(hc, ch, wk)] = sum(
                oo_map.get((hc, ch, fw), 0)
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


def get_agg_rows(hc_filter: int = None, ch_filter: str = None,
                 _overrides_override: Dict = None) -> List[Dict]:
    """Aggregate WP_DATA by (hc, wk, ch), sum sub_channels, apply overrides.

    _overrides_override: if provided, use this dict instead of reading from DB.
    Used by compare_snapshots() to evaluate two scenarios without touching global state.
    """
    buckets: Dict[str, Dict] = {}

    for r in WP_DATA:
        if hc_filter and r["hierarchy_code"] != hc_filter:
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
            _ly[k]  = {"ly_units": 0,  "ly_dollars":  0.0}
            _lly[k] = {"lly_units": 0, "lly_dollars": 0.0}
        _ly[k]["ly_units"]    += r["ly_units"]
        _ly[k]["ly_dollars"]   = round(_ly[k]["ly_dollars"]  + r["ly_dollars"],  2)
        _lly[k]["lly_units"]  += r.get("lly_units", 0)
        _lly[k]["lly_dollars"] = round(_lly[k]["lly_dollars"] + r.get("lly_dollars", 0.0), 2)

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

        # LY
        ly = _ly.get(key, {"ly_units": 0, "ly_dollars": 0.0})
        b["ly_sales_units"]      = ly["ly_units"]
        b["ly_sales_dollars"]    = ly["ly_dollars"]
        b["ly_units_var"]        = b["written_sales_units"] - ly["ly_units"]
        b["ly_dollars_var"]      = round(b["written_sales_dollars"] - ly["ly_dollars"], 2)
        b["ly_units_var_perc"]   = round(b["ly_units_var"]   / ly["ly_units"],   4) if ly["ly_units"]   > 0 else 0.0
        b["ly_dollars_var_perc"] = round(b["ly_dollars_var"] / ly["ly_dollars"], 4) if ly["ly_dollars"] > 0 else 0.0

        # LLY (last-to-last year)
        lly = _lly.get(key, {"lly_units": 0, "lly_dollars": 0.0})
        b["lly_sales_units"]      = lly["lly_units"]
        b["lly_sales_dollars"]    = lly["lly_dollars"]
        b["lly_units_var"]        = b["written_sales_units"] - lly["lly_units"]
        b["lly_dollars_var"]      = round(b["written_sales_dollars"] - lly["lly_dollars"], 2)
        b["lly_units_var_perc"]   = round(b["lly_units_var"]   / lly["lly_units"],   4) if lly["lly_units"]   > 0 else 0.0
        b["lly_dollars_var_perc"] = round(b["lly_dollars_var"] / lly["lly_dollars"], 4) if lly["lly_dollars"] > 0 else 0.0

    _active_ovrs = _overrides_override if _overrides_override is not None else db_get_overrides()
    for key, ovr in _active_ovrs.items():
        if key in buckets:
            buckets[key] = _recalc(buckets[key], ovr)

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

        for i, b in enumerate(stream):
            b["lead_time_weeks"] = lead_time_s   # expose on every row for frontend coloring
            b["target_wos"]      = target_wos_s  # for target-aware excess coloring
            # Dynamic lock: order placed here would arrive (W+LT) past season end.
            # Recomputed off effective LT every read → never stale after an LT change.
            b["oo_locked"] = (
                not b.get("actualised") and not b.get("is_ongoing")
                and _week_offset(b["current_week"], lead_time_s) is None
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
            # LT weeks earlier (now arriving). Ongoing week keeps ingested only.
            units_s = b["written_sales_units"]
            if not b.get("is_ongoing"):
                ingested = int(b.get("ingested_receipt_units", 0))
                src = stream[i - lead_time_s] if i - lead_time_s >= 0 else None
                oo_landing = int(src.get("on_order_placed_total_unit", 0)) if src is not None else 0
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

            if b.get("is_ongoing"):
                # Ongoing/in-flight week: show current WOS off trailing 4-week actual
                # sales rate. FC not shown (no forward pipeline meaning mid-week).
                trail_avg = sum(actual_window) / len(actual_window) if actual_window else 0
                b["wos"]                = round(b["eop_units"] / trail_avg, 2) if trail_avg > 0 else None
                b["fwd_coverage_wks"]   = None
                b["first_stockout_week"] = None
            else:
                # WOS = EOP / 8-week forward avg (current stock only)
                b["wos"] = round(b["eop_units"] / wos_avg_s, 2) if wos_avg_s > 0 else None
                # FC + first_stockout_week computed in second pass below
                # (needs full BOP chain propagated first so future eop_units are accurate)
                b["fwd_coverage_wks"]   = None
                b["first_stockout_week"] = None

        # ── Second pass: FC (display) + stockout signals (classification) ────
        # Runs after full BOP chain so future eop_units / _stockout flags are real.
        #
        # Two SEPARATE concerns, deliberately not merged into one number:
        #
        #   FC (display)  = (EOP + pipeline) / 8wk_avg
        #     pipeline = the planner's ORDERS in transit (OOP placed but not yet
        #     received = OOP over the last LT weeks). Ingested supply is NOT added
        #     here — it already flows into EOP as it lands, so adding it would
        #     double-count and inflate FC (the old Wk26=49.8 bug). At baseline
        #     (no orders) FC == WOS.
        #
        #   Stockout flags (classification) = walk the real EOP chain
        #     A back-loaded receipt (lands wk+14) leaves you dry wks 1-13 even though
        #     FC looks healthy. So exceptions classify off the chain, not off FC.
        for i, b in enumerate(stream):
            if b.get("actualised") or b.get("is_ongoing"):
                continue
            wos_s     = _WOS_DEMAND_INDEX.get((hc_s, ch_s, b["current_week"]), 0)
            wos_avg_s = wos_s / WOS_WINDOW if WOS_WINDOW > 0 else 0

            # pipeline = planner orders in transit = OOP placed in the last LT weeks
            # (weeks i-LT+1 .. i), which arrive over the next LT weeks. Not received yet.
            lo = max(0, i - lead_time_s + 1)
            pipeline = sum(
                px.get("on_order_placed_total_unit", 0)
                for px in stream[lo : i + 1]
            )
            b["fwd_coverage_wks"] = round(
                (b["eop_units"] + pipeline) / wos_avg_s, 2
            ) if wos_avg_s > 0 else None

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

    return sorted(buckets.values(), key=lambda x: (x["current_week"], x["hierarchy_code"], x["channel"]))


def apply_edit(hc: int, wk: int, ch: str, field: str, value: float, mode: str = None) -> Dict:
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

    rows = get_agg_rows(hc, ch)
    return next((r for r in rows if r["current_week"] == wk), None)


def reset_overrides():
    db_clear_overrides()
    _reset_fwd_demand_and_recomm()   # restore index + WP_DATA recomm to baseline


def restore_snapshot(snap_id: int) -> bool:
    snap = db_get_snapshot(snap_id)
    if not snap:
        return False
    db_replace_overrides(snap["overrides"])
    # Rebuild demand + pipeline indexes so recomm reflects snapshot's sales/OO state.
    # Without this, _FORWARD_DEMAND_INDEX/_PIPELINE_INDEX stay stale until server restart.
    _rebuild_fwd_demand_and_recomm([h["hierarchy_code"] for h in HIERARCHIES])
    return True


def delete_snapshot(snap_id: int) -> bool:
    return db_delete_snapshot(snap_id)


def rename_snapshot(snap_id: int, new_name: str) -> bool:
    return db_rename_snapshot(snap_id, new_name.strip())


def save_snapshot(name: str) -> Dict:
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
    return db_insert_snapshot(
        name=name,
        created_at=datetime.now().isoformat(),
        overrides_count=len(overrides),
        overrides={k: dict(v) for k, v in overrides.items()},
        summary=summary,
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
            # Build oo_ovr once (not inside the 52-week loop) — same content every iteration.
            oo_ovr = {
                r["current_week"]: overrides.get(
                    _ovr_key(hc, r["current_week"], ch), {}
                ).get("on_order_placed_total_unit", r["on_order_placed_total_unit"])
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
                _PIPELINE_INDEX[(hc, ch, wk)] = sum(
                    oo_ovr.get(fw, 0)
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
    """Remove override for one cell. Rebuilds indexes if demand/OO changed. Returns fresh row."""
    key = _ovr_key(hc, wk, ch)
    overrides = db_get_overrides()
    if key in overrides:
        last_edited = overrides[key].get("_last_edited")
        db_delete_override(key)
        if last_edited in ("written_sales_units", "written_sales_dollars", "written_dr_perc"):
            _rebuild_fwd_demand_and_recomm([hc], [ch])
        elif last_edited == "on_order_placed_total_unit":
            _rebuild_pipeline_and_recomm([hc], [ch])
    rows = get_agg_rows(hc, ch)
    return next((r for r in rows if r["current_week"] == wk), {})


def shift_receipts(hcs: List[int], channels: List[str], shift_weeks: int) -> Dict:
    """Shift all OO Placed values for given SKUs×channels by N fiscal weeks.

    Positive shift_weeks = push later (supplier delay).
    Negative shift_weeks = pull earlier (accelerate delivery).
    OOs that would land outside the planning window are dropped.

    Returns: {"shifted": count, "dropped": count}
    """
    if shift_weeks == 0:
        return {"shifted": 0, "dropped": 0}

    planning_wks = {w for w in FISCAL_WEEKS if w > CURRENT_WEEK}
    overrides = db_get_overrides()
    updates: Dict[str, Dict] = {}

    shifted = 0
    dropped = 0

    for hc in hcs:
        for ch in channels:
            # Collect current OO for planning weeks (from live agg rows so overrides are reflected)
            oo_by_week: Dict[int, float] = {}
            for r in get_agg_rows(hc, ch):
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


def accept_recomm_receipts(hcs: List[int], channels: List[str]) -> int:
    """Set OO Placed = Recomm Receipt for all planning weeks of given SKUs×channels.

    One-click replacement for manually editing OO Placed week-by-week.
    Returns count of rows updated.
    """
    overrides = db_get_overrides()
    updates: Dict[str, Dict] = {}
    count = 0
    for hc in hcs:
        for ch in channels:
            for r in get_agg_rows(hc, ch):
                if r.get("actualised") or r.get("is_ongoing"):
                    continue
                if r.get("oo_locked"):
                    continue   # order placed here can't be received this season
                recomm = int(r.get("recomm_receipt_units", 0))
                key = _ovr_key(hc, r["current_week"], ch)
                entry = dict(overrides.get(key, {}))
                entry["on_order_placed_total_unit"] = float(recomm)
                entry["_last_edited"] = "on_order_placed_total_unit"
                updates[key] = entry
                count += 1
    if updates:
        db_batch_upsert_overrides(updates)
        _rebuild_pipeline_and_recomm(hcs, channels)
    return count


def preview_top_down(hcs: List[int], channels: List[str], target: float, field: str) -> Dict:
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
            for r in get_agg_rows(hc, ch):
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


def get_exceptions_panel() -> List[Dict]:
    """Return one row per SKU×channel showing worst exception (non-ok only).

    Groups week-level coverage data into SKU×channel summary rows so the panel
    shows "N SKUs need attention" not "480 week rows."  Each row carries the
    worst-coverage week for that combo plus the actual problem weeks:
      - stockout exceptions → weeks where EOP actually hits 0 (_stockout)
      - excess exceptions   → weeks where coverage genuinely exceeds threshold
    This avoids showing "observation weeks" (weeks from which you notice an
    upcoming problem) and instead shows WHERE the problem occurs.
    """
    all_rows = get_agg_rows()
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
        cov = r.get("fwd_coverage_wks") if r.get("fwd_coverage_wks") is not None else r.get("wos")
        if cov is None:
            continue

        # Track actual EOP=0 weeks (real stockout, not observation)
        if r.get("_stockout"):
            actual_stockout_wks.setdefault(key, []).append(r["current_week"])

        # Track actual excess weeks (only unlocked — locked tail weeks can't be actioned)
        is_locked = r.get("oo_locked", False)
        if cov > get_target_wos(hc, ch) * 1.5 and not is_locked:
            actual_excess_wks.setdefault(key, []).append(r["current_week"])

        order_gap = max(0, r.get("recomm_receipt_units", 0) - r.get("on_order_placed_total_unit", 0))
        first_so  = r.get("first_stockout_week")

        # Classification uses the EOP chain (real stockout timing), NOT FC.
        # Excess in oo_locked tail weeks is not actionable (can't reduce ingested supply
        # or place fewer orders) — skip to avoid end-of-season demand-taper false positives.
        if r.get("_stockout_in_lt"):
            status = "critical"
        elif first_so is not None and order_gap > 0:
            status = "low"
        elif cov > get_target_wos(hc, ch) * 1.5 and not is_locked:
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


def get_budget() -> Dict:
    """Return OTB receipt budget, current plan consumption, and category breakdown."""
    budget_str = db_get_setting("otb_budget")
    budget = float(budget_str) if budget_str else 0.0

    planned_cost = 0.0
    category_costs: Dict[str, float] = {}
    for r in get_agg_rows():
        if not r.get("actualised"):
            cost = r["total_receipt_units"] * r.get("written_auc", 0)
            planned_cost += cost
            cat = r.get("l1_name", "Other")
            category_costs[cat] = category_costs.get(cat, 0.0) + cost

    planned_cost = round(planned_cost, 2)
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


def set_budget(value: float) -> Dict:
    db_set_setting("otb_budget", str(round(value, 2)))
    return get_budget()


def get_audit_log(limit: int = 100, hierarchy_code: int = None, field: str = None) -> List[Dict]:
    return db_get_audit_log(limit, hierarchy_code=hierarchy_code, field=field)


def get_season_progress() -> Dict:
    """Actualized-to-date vs full-year plan — season pace tracking."""
    all_rows = get_agg_rows()
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
                   week_values: List[Dict] = None) -> int:
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
            for r in get_agg_rows(hc, ch):
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
