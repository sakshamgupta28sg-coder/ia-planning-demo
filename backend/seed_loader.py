"""
CSV seed loader — the "warehouse door".

If backend/seeds/catalog.csv exists, the SKU catalog + supply posture + OTB
budgets are loaded from CSV instead of the hardcoded literals in dummy_data.py.
This lets an SMB drop in their own product list (edit in Excel, restart) without
touching Python. When the CSVs are absent, dummy_data falls back to its built-in
demo literals and behaves byte-identically to before (regression gate proves it).

Three files live in backend/seeds/:
  catalog.csv  one row per SKU — identity, price, curve shape, lifecycle
  supply.csv   one row per SKU — buy posture (open_wos / commit_through / mult)
  budgets.csv  one row per SKU x channel — OTB dollar budget

A malformed seed raises SeedError (fail loud) rather than silently reverting to
the demo, so an SMB never plans on accidentally-wrong data.
"""

import csv
import os
from typing import Dict, List, Optional, Tuple

CHANNELS = ("Ecom", "Indirect", "Store")

# Columns each file must carry. Extra columns are ignored; missing ones error.
_CATALOG_COLS = {
    "hierarchy_code", "l1_name", "l2_name", "sku_code", "color", "size",
    "air", "auc", "peak_week", "peak_units", "target_wos", "lead_time_weeks",
    "case_pack", "safety_weeks", "activation_week", "deactivation_week",
    "status_seed", "tagged_to",
}
_SUPPLY_COLS = {"hierarchy_code", "open_wos", "commit_through", "commit_mult"}
_BUDGET_COLS = {"hierarchy_code", "channel", "budget"}


class SeedError(ValueError):
    """Raised when seed CSVs are present but malformed."""


class SeedData:
    """Parsed seed, exposing exactly the structures dummy_data overrides."""

    def __init__(self):
        self.hierarchies: List[Dict] = []          # Old SKUs (generation order)
        self.new_hierarchies: List[Dict] = []      # New SKUs (generated last)
        self.new_hcs: set = set()
        self.metrics: Dict[int, Dict] = {}         # ALL SKUs
        self.new_lifecycle: Dict[int, Dict] = {}   # New SKUs only
        self.supply: Dict[int, Dict] = {}          # ALL SKUs
        self.budgets: Dict[Tuple[int, str], float] = {}
        self.descriptors: Dict[int, Tuple] = {}    # Old SKUs (color, size)
        self.old_activation: Optional[int] = None
        self.old_deactivation: Optional[int] = None


def _num(s: str):
    """Parse a CSV scalar preserving int-ness (so 15000 stays int, 1.0 stays float)."""
    s = (s or "").strip()
    if s == "":
        return None
    try:
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)
    except ValueError:
        return float(s)


def _read(path: str, required_cols: set, label: str) -> List[Dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = required_cols - cols
        if missing:
            raise SeedError(f"{label}: missing columns {sorted(missing)}")
        rows = [r for r in reader]
    if not rows:
        raise SeedError(f"{label}: no data rows")
    return rows


def seed_present(seeds_dir: str) -> bool:
    return os.path.isfile(os.path.join(seeds_dir, "catalog.csv"))


def load_seed(seeds_dir: str) -> Optional[SeedData]:
    """Load + validate the seed CSVs. Returns None if catalog.csv is absent."""
    if not seed_present(seeds_dir):
        return None

    catalog = _read(os.path.join(seeds_dir, "catalog.csv"), _CATALOG_COLS, "catalog.csv")
    supply = _read(os.path.join(seeds_dir, "supply.csv"), _SUPPLY_COLS, "supply.csv")
    budgets = _read(os.path.join(seeds_dir, "budgets.csv"), _BUDGET_COLS, "budgets.csv")

    sd = SeedData()
    seen_hc = set()

    for r in catalog:
        hc = _num(r["hierarchy_code"])
        if not isinstance(hc, int):
            raise SeedError(f"catalog.csv: hierarchy_code must be an integer, got {r['hierarchy_code']!r}")
        if hc in seen_hc:
            raise SeedError(f"catalog.csv: duplicate hierarchy_code {hc}")
        seen_hc.add(hc)

        status = (r["status_seed"] or "").strip()
        if status not in ("Old", "New"):
            raise SeedError(f"catalog.csv hc {hc}: status_seed must be 'Old' or 'New', got {status!r}")

        ident = {"hierarchy_code": hc, "l1_name": r["l1_name"].strip(),
                 "l2_name": r["l2_name"].strip(), "sku_code": r["sku_code"].strip()}
        sd.metrics[hc] = {
            "air": _num(r["air"]), "auc": _num(r["auc"]),
            "peak_week": _num(r["peak_week"]), "peak_units": _num(r["peak_units"]),
            "target_wos": _num(r["target_wos"]), "lead_time_weeks": _num(r["lead_time_weeks"]),
            "case_pack": _num(r["case_pack"]), "safety_weeks": _num(r["safety_weeks"]),
        }
        act, deact = _num(r["activation_week"]), _num(r["deactivation_week"])

        if status == "New":
            sd.new_hierarchies.append(ident)
            sd.new_hcs.add(hc)
            tagged = _num(r["tagged_to"])
            sd.new_lifecycle[hc] = {
                "activation_week": act, "deactivation_week": deact,
                "tagged_to": tagged, "color": r["color"].strip() or None,
                "size": r["size"].strip() or None,
            }
        else:
            sd.hierarchies.append(ident)
            sd.descriptors[hc] = (r["color"].strip() or None, r["size"].strip() or None)
            # Old SKUs share one activation/deactivation anchor; take from the first.
            if sd.old_activation is None:
                sd.old_activation, sd.old_deactivation = act, deact

    # tagged_to must reference a real SKU
    for hc, lc in sd.new_lifecycle.items():
        if lc["tagged_to"] is not None and lc["tagged_to"] not in seen_hc:
            raise SeedError(f"catalog.csv hc {hc}: tagged_to {lc['tagged_to']} is not a known hierarchy_code")

    if not sd.hierarchies:
        raise SeedError("catalog.csv: at least one 'Old' SKU is required")

    for r in supply:
        hc = _num(r["hierarchy_code"])
        if hc not in seen_hc:
            raise SeedError(f"supply.csv: hierarchy_code {hc} not in catalog")
        sd.supply[hc] = {"open_wos": _num(r["open_wos"]),
                         "commit_through": _num(r["commit_through"]),
                         "commit_mult": _num(r["commit_mult"])}
    missing_supply = seen_hc - set(sd.supply)
    if missing_supply:
        raise SeedError(f"supply.csv: missing rows for {sorted(missing_supply)}")

    for r in budgets:
        hc = _num(r["hierarchy_code"])
        ch = (r["channel"] or "").strip()
        if hc not in seen_hc:
            raise SeedError(f"budgets.csv: hierarchy_code {hc} not in catalog")
        if ch not in CHANNELS:
            raise SeedError(f"budgets.csv hc {hc}: channel must be one of {CHANNELS}, got {ch!r}")
        sd.budgets[(hc, ch)] = _num(r["budget"])

    return sd
