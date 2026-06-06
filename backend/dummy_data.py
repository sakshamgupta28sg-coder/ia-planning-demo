import random
from typing import Dict, List

random.seed(42)

HIERARCHIES = [
    {"hierarchy_code": 10001, "l1_name": "Trees", "l2_name": "7.5ft Pre-Lit Slim Tree"},
    {"hierarchy_code": 10002, "l1_name": "Trees", "l2_name": "9ft Grand Fir Tree"},
    {"hierarchy_code": 10003, "l1_name": "Trees", "l2_name": "6ft Tabletop Tree"},
    {"hierarchy_code": 10004, "l1_name": "Wreaths", "l2_name": "24in Classic Wreath"},
    {"hierarchy_code": 10005, "l1_name": "Wreaths", "l2_name": "36in Grand Wreath"},
    {"hierarchy_code": 10006, "l1_name": "Garlands", "l2_name": "9ft Garland"},
    {"hierarchy_code": 10007, "l1_name": "Ornaments", "l2_name": "50-Piece Ornament Set"},
    {"hierarchy_code": 10008, "l1_name": "Ornaments", "l2_name": "Personalized Ornament"},
]

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

# Fiscal weeks 202501..202552
FISCAL_WEEKS = [int(f"2025{str(w).zfill(2)}") for w in range(1, 53)]

# Base metrics per hierarchy (AIR = avg initial retail price, AUC = avg unit cost)
HIERARCHY_METRICS = {
    10001: {"air": 649.99, "auc": 195.0, "peak_week": 45, "peak_units": 480},
    10002: {"air": 999.99, "auc": 290.0, "peak_week": 44, "peak_units": 320},
    10003: {"air": 249.99, "auc": 75.0,  "peak_week": 46, "peak_units": 600},
    10004: {"air": 89.99,  "auc": 27.0,  "peak_week": 46, "peak_units": 900},
    10005: {"air": 149.99, "auc": 45.0,  "peak_week": 46, "peak_units": 500},
    10006: {"air": 59.99,  "auc": 18.0,  "peak_week": 47, "peak_units": 1100},
    10007: {"air": 39.99,  "auc": 12.0,  "peak_week": 47, "peak_units": 1400},
    10008: {"air": 24.99,  "auc": 7.5,   "peak_week": 48, "peak_units": 800},
}

CHANNEL_SPLIT = {"Ecom": 0.55, "Indirect": 0.30, "Store": 0.15}


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


def generate_wp_data() -> List[Dict]:
    rows = []
    for h in HIERARCHIES:
        hc = h["hierarchy_code"]
        m = HIERARCHY_METRICS[hc]
        bop = {ch: m["peak_units"] * CHANNEL_SPLIT[ch] * 3 for ch in CHANNELS}

        for ch in CHANNELS:
            wh = WAREHOUSE_SUB_CHANNELS[ch]
            for wk in FISCAL_WEEKS:
                week_num = wk % 100
                curve = _seasonal_curve(week_num, m["peak_week"])
                dr = _dr_perc(week_num, m["peak_week"])
                units = round(m["peak_units"] * CHANNEL_SPLIT[ch] * curve * random.uniform(0.9, 1.1))
                aur = round(m["air"] * (1 - dr), 2)
                sales_dollars = round(aur * units, 2)
                sales_cost = round(m["auc"] * units, 2)
                gm_dollar = round(sales_dollars - sales_cost, 2)
                gm_perc = round((gm_dollar / sales_dollars) if sales_dollars else 0, 4)

                # inventory
                current_bop = round(bop[ch])
                receipt_units = round(units * 1.1 * random.uniform(0.8, 1.2))
                eop = max(0, current_bop - units + receipt_units)
                bop[ch] = eop

                oo_placed = round(receipt_units * 0.6)
                oo_unplaced = round(receipt_units * 0.4)

                # Actuals for past weeks (202501–202519); 0 for future weeks
                is_past = week_num < 20
                actual_units   = round(units * random.uniform(0.78, 1.08)) if is_past else 0
                actual_dollars = round(actual_units * aur, 2)
                actual_cost    = round(actual_units * m["auc"], 2)
                # Markdown: units sold at a promotional price
                md_units   = round(units * dr)
                md_dollars = round(md_units * m["air"] * dr, 2)

                rows.append({
                    "hierarchy_code": hc,
                    "l1_name": h["l1_name"],
                    "l2_name": h["l2_name"],
                    "channel": ch,
                    "sub_channel": wh,
                    "current_week": wk,
                    "written_sales_units": units,
                    "written_sales_dollars": sales_dollars,
                    "written_sales_cost": sales_cost,
                    "written_aur": aur,
                    "written_auc": m["auc"],
                    "written_air": m["air"],
                    "written_dr_perc": dr,
                    "written_gm_dollar": gm_dollar,
                    "written_gm_perc": gm_perc,
                    "bop_units": current_bop,
                    "eop_units": eop,
                    "bop_cost": round(current_bop * m["auc"], 2),
                    "eop_cost": round(eop * m["auc"], 2),
                    "on_order_placed_total_unit": oo_placed,
                    "on_order_unplaced_total_unit": oo_unplaced,
                    "total_receipt_units": receipt_units,
                    "recomm_receipt_units": max(0, round(units * 1.05 - current_bop * 0.3)),
                    "actualised": is_past,
                    "actual_sales_units":   actual_units,
                    "actual_sales_dollars": actual_dollars,
                    "actual_sales_cost":    actual_cost,
                    "markdown_units":       md_units,
                    "markdown_dollars":     md_dollars,
                })
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
                ty_dollars = round(ty_units * m["air"] * (1 - _dr_perc(week_num, m["peak_week"])), 2)
                ly_dollars = round(ly_units * m["air"] * (1 - _dr_perc(week_num, m["peak_week"])), 2)
                rows.append({
                    "hierarchy_code": hc,
                    "l1_name": h["l1_name"],
                    "l2_name": h["l2_name"],
                    "channel": ch,
                    "current_week": wk,
                    "compared_week": int(str(wk).replace("2025", "2024")),
                    "ty_units": ty_units,
                    "ly_units": ly_units,
                    "ty_dollars": ty_dollars,
                    "ly_dollars": ly_dollars,
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


_NEW_SKUS: List[Dict] = []
_NEXT_HC = 20001


def get_new_skus() -> List[Dict]:
    return list(_NEW_SKUS)


def add_new_sku(sku: Dict) -> Dict:
    global _NEXT_HC
    sku["hierarchy_code"] = _NEXT_HC
    sku["feed_type"] = "new"
    _NEXT_HC += 1
    _NEW_SKUS.append(sku)
    return sku


def delete_sku(hierarchy_code: int) -> bool:
    global _NEW_SKUS
    before = len(_NEW_SKUS)
    _NEW_SKUS = [s for s in _NEW_SKUS if s["hierarchy_code"] != hierarchy_code]
    return len(_NEW_SKUS) < before


# Pre-generate on import
WP_DATA = generate_wp_data()
TY_LY_DATA = generate_ty_ly_data()
SCENARIO_DATA = generate_scenario_data()

# ── Override / Snapshot layer ──────────────────────────────────────────────────
from datetime import datetime

OVERRIDES: Dict[str, Dict] = {}   # key: f"{hc}_{wk}_{ch}" → {field: value}
SNAPSHOTS: List[Dict] = []


def _ovr_key(hc: int, wk: int, ch: str) -> str:
    return f"{hc}_{wk}_{ch}"


def _recalc(row: Dict, ovr: Dict) -> Dict:
    row = dict(row)
    for field, val in ovr.items():
        row[field] = val

    # AUC and AUR are always base values (never overridden)
    aur   = row["written_aur"]
    auc   = row["written_auc"]
    units = row["written_sales_units"]

    # Use _last_edited to know which field was the trigger (handles the case
    # where both units and dollars exist in ovr from sequential edits)
    trigger = ovr.get("_last_edited")

    if trigger == "written_sales_units" or (
        "written_sales_units" in ovr and "written_sales_dollars" not in ovr
    ):
        # Units edited → derive Sales $
        row["written_sales_dollars"] = round(aur * units, 2)
    elif trigger == "written_sales_dollars" or (
        "written_sales_dollars" in ovr and "written_sales_units" not in ovr
    ):
        # Sales $ edited → back-calculate units (AUR stays fixed)
        if aur > 0:
            units = round(row["written_sales_dollars"] / aur)
            row["written_sales_units"] = units

    if "on_order_placed_total_unit" in ovr:
        row["total_receipt_units"] = row["on_order_placed_total_unit"] + row["on_order_unplaced_total_unit"]

    # EOP = BOP - Sales Units + OO Placed
    row["eop_units"] = max(0, row["bop_units"] - units + row["on_order_placed_total_unit"])

    row["written_sales_cost"] = round(units * auc, 2)
    row["written_gm_dollar"]  = round(row["written_sales_dollars"] - row["written_sales_cost"], 2)
    if row["written_sales_dollars"] > 0:
        row["written_gm_perc"] = round(row["written_gm_dollar"] / row["written_sales_dollars"], 4)
    row["recomm_receipt_units"] = max(0, round(units * 1.05 - row["bop_units"] * 0.3))
    # Re-derive analytics fields after override
    row["wos"] = round(row["eop_units"] / units, 2) if units > 0 else 99.0
    avail = row["bop_units"] + row["total_receipt_units"]
    row["sell_through_perc"] = round(row["actual_sales_units"] / avail, 4) if avail > 0 and row.get("actualised") else 0.0
    row["otb_units"]   = row["on_order_unplaced_total_unit"]
    row["otb_dollars"] = round(row["otb_units"] * auc, 2)
    if row.get("actualised"):
        row["variance_units"]      = row["written_sales_units"] - row["actual_sales_units"]
        row["variance_dollars"]    = round(row["written_sales_dollars"] - row["actual_sales_dollars"], 2)
        row["variance_units_perc"] = round(row["variance_units"] / row["written_sales_units"], 4) if row["written_sales_units"] > 0 else 0.0
    row["_modified"] = True
    return row


def get_agg_rows(hc_filter: int = None, ch_filter: str = None) -> List[Dict]:
    """Aggregate WP_DATA by (hc, wk, ch), sum sub_channels, apply overrides."""
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
                "written_gm_perc":           0.0,
                "bop_units":                 0,
                "eop_units":                 0,
                "bop_cost":                  0.0,
                "eop_cost":                  0.0,
                "total_receipt_units":       0,
                "recomm_receipt_units":      0,
                "on_order_placed_total_unit":   0,
                "on_order_unplaced_total_unit": 0,
                "actualised":  r["actualised"],
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
        b["recomm_receipt_units"]        += r["recomm_receipt_units"]
        b["on_order_placed_total_unit"]  += r["on_order_placed_total_unit"]
        b["on_order_unplaced_total_unit"]+= r["on_order_unplaced_total_unit"]
        b["actual_sales_units"]          += r["actual_sales_units"]
        b["actual_sales_dollars"]         = round(b["actual_sales_dollars"] + r["actual_sales_dollars"], 2)
        b["actual_sales_cost"]            = round(b["actual_sales_cost"]    + r["actual_sales_cost"], 2)
        b["markdown_units"]              += r["markdown_units"]
        b["markdown_dollars"]             = round(b["markdown_dollars"]     + r["markdown_dollars"], 2)

    # ── LY lookup (keyed same way as buckets) ────────────────────────────────────
    _ly: Dict[str, Dict] = {}
    for r in TY_LY_DATA:
        if hc_filter and r["hierarchy_code"] != hc_filter:
            continue
        if ch_filter and r["channel"] != ch_filter:
            continue
        k = _ovr_key(r["hierarchy_code"], r["current_week"], r["channel"])
        if k not in _ly:
            _ly[k] = {"ly_units": 0, "ly_dollars": 0.0}
        _ly[k]["ly_units"]   += r["ly_units"]
        _ly[k]["ly_dollars"]  = round(_ly[k]["ly_dollars"] + r["ly_dollars"], 2)

    for key, b in buckets.items():
        # AUR / GM%
        if b["written_sales_units"] > 0:
            b["written_aur"] = round(b["written_sales_dollars"] / b["written_sales_units"], 2)
        if b["written_sales_dollars"] > 0:
            b["written_gm_perc"] = round(b["written_gm_dollar"] / b["written_sales_dollars"], 4)

        # WOS (Weeks of Supply)
        b["wos"] = round(b["eop_units"] / b["written_sales_units"], 2) if b["written_sales_units"] > 0 else 99.0

        # Sell-Through % (only meaningful for actualised weeks)
        avail = b["bop_units"] + b["total_receipt_units"]
        b["sell_through_perc"] = round(b["actual_sales_units"] / avail, 4) if avail > 0 and b["actualised"] else 0.0

        # OTB
        b["otb_units"]   = b["on_order_unplaced_total_unit"]
        b["otb_dollars"] = round(b["otb_units"] * b["written_auc"], 2)

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

    for key, ovr in OVERRIDES.items():
        if key in buckets:
            buckets[key] = _recalc(buckets[key], ovr)

    return sorted(buckets.values(), key=lambda x: (x["current_week"], x["hierarchy_code"], x["channel"]))


def apply_edit(hc: int, wk: int, ch: str, field: str, value: float) -> Dict:
    key = _ovr_key(hc, wk, ch)
    if key not in OVERRIDES:
        OVERRIDES[key] = {}
    OVERRIDES[key][field] = value
    OVERRIDES[key]["_last_edited"] = field   # track which field was most recently changed
    rows = get_agg_rows(hc, ch)
    return next((r for r in rows if r["current_week"] == wk), None)


def reset_overrides():
    OVERRIDES.clear()


def restore_snapshot(snap_id: int) -> bool:
    snap = next((s for s in SNAPSHOTS if s["id"] == snap_id), None)
    if not snap:
        return False
    OVERRIDES.clear()
    OVERRIDES.update({k: dict(v) for k, v in snap["overrides"].items()})
    return True


def delete_snapshot(snap_id: int) -> bool:
    global SNAPSHOTS
    before = len(SNAPSHOTS)
    SNAPSHOTS = [s for s in SNAPSHOTS if s["id"] != snap_id]
    return len(SNAPSHOTS) < before


def save_snapshot(name: str) -> Dict:
    all_rows = get_agg_rows()
    td = sum(r["written_sales_dollars"] for r in all_rows)
    snap = {
        "id":             len(SNAPSHOTS) + 1,
        "name":           name,
        "created_at":     datetime.now().isoformat(),
        "overrides_count": len(OVERRIDES),
        "overrides":      {k: dict(v) for k, v in OVERRIDES.items()},
        "summary": {
            "total_sales_units":   sum(r["written_sales_units"] for r in all_rows),
            "total_sales_dollars": round(td, 2),
            "total_gm_dollar":     round(sum(r["written_gm_dollar"] for r in all_rows), 2),
            "avg_gm_perc":         round(
                sum(r["written_gm_perc"] for r in all_rows) / len(all_rows), 4
            ) if all_rows else 0,
        },
    }
    SNAPSHOTS.append(snap)
    return snap
