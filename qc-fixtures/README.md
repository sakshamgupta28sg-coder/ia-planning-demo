# QC Fixtures

Runnable seed sets for the QC framework ([`../docs/QC-FRAMEWORK.md`](../docs/QC-FRAMEWORK.md)).
Each folder is a complete `IA_SEEDS_DIR`. Regenerate all with:

```bash
python3 qc-fixtures/generate_fixtures.py
```

Fixtures use hierarchy_codes **70001+** (kept clear of demo 10xxx/30xxx and SMB 60xxx ranges).

## How an agent uses a fixture

```bash
# cold-load path
IA_DB_PATH=/tmp/qc.db IA_SEEDS_DIR=qc-fixtures/F-CSV60 \
  python3 -c "import seed_loader; print(len(seed_loader.load_seed('qc-fixtures/F-CSV60').metrics))"

# or via the upload endpoint (validate-before-promote)
curl -X POST :PORT/api/admin/upload-seeds \
  -F catalog=@qc-fixtures/F-CSV6/catalog.csv -F supply=@qc-fixtures/F-CSV6/supply.csv \
  -F budgets=@qc-fixtures/F-CSV6/budgets.csv -F sales_history=@qc-fixtures/F-CSV6/sales_history.csv \
  -F forecast=@qc-fixtures/F-CSV6/forecast.csv
```

## Valid sets (must load)

| Fixture | Purpose | Test cases |
|---|---|---|
| `F-DEMO` | empty (no catalog) → built-in demo literals | SEED-01, INV-7, ENG-* baseline, `golden.py verify_core` |
| `F-CSV6` | 6 SKUs (5 Old + 1 New), all optional files | ENG-*, API contract, most feature flows |
| `F-CSV60` | 60 SKUs, calibrated + unique names | SEED-11, PERF-01, REG-11 (dropdown), scale flows |
| `F-NOHIST` | catalog+supply+budgets only (no history/forecast) | parametric-curve path, optional-file inertness |
| `F-LONGLT` | lead times 12–16 | INV-4 oo_locked, REG-04 long-LT accept, locked-tail |
| `F-EARLYPEAK` | peak_week 16 (before planning boundary) | over-supply probe (Fix-1 class), WOS-spike checks |
| `F-DUPNAME` | two SKUs share `l2_name` | SEED-12, ENG-10 borrow-confusion guard |
| `F-FORECAST-LTMISMATCH` | forecast `oo_placed` sized for catalog LT=8 | SEED-13 / REG-02 (see folder README.txt: set sku-settings LT=4, then accept) |

## Malformed sets — `F-MALFORMED/*` (each must RAISE `SeedError` / 400)

| Folder | Broken rule | Test case |
|---|---|---|
| `missing-column` | catalog missing `air` column | SEED-02 |
| `dup-hc` | duplicate hierarchy_code | SEED-03 |
| `bad-status` | `status_seed = "Legacy"` | SEED-04 |
| `bad-tag` | New SKU `tagged_to` → unknown hc | SEED-05 |
| `no-old` | all SKUs New (no Old) | SEED-06 |
| `missing-supply` | supply row missing for a SKU | SEED-07 |
| `bad-channel` | budget channel = "Online" | SEED-08 |
| `bad-history` | sales_history `week_num = 99` | SEED-09 |
| `bad-forecast` | forecast `oo_placed = -5` | SEED-10 |

**Negative-test invariant:** a rejected upload must leave the live seed folder + running data **untouched** (validate-before-promote). Assert `seed-status` is unchanged after each rejection.

## Verification

`generate_fixtures.py` output is checked: all valid sets load via `seed_loader`, `F-DEMO` returns `None` (demo fallback), and every `F-MALFORMED/*` raises `SeedError` with the rule-specific message.
