# Seed data — define the tool's data in CSV

The planning tool loads its SKU catalog, supply posture, budgets, and (optionally)
sales history from the CSV files in this folder. Edit them in Excel / Google
Sheets, save as CSV, restart the backend — no code change.

If `catalog.csv` is **absent**, the tool falls back to its built-in demo data.
If a CSV is **malformed**, the backend refuses to start and prints the exact
problem (it never silently plans on bad data).

To point the tool at a different folder (e.g. a customer's data), set
`IA_SEEDS_DIR=/path/to/their/seeds` before launching the backend.

---

## Files

| File | Required? | One row per | Purpose |
|------|-----------|-------------|---------|
| `catalog.csv` | **yes** | SKU | identity, price, curve shape, lifecycle |
| `supply.csv` | **yes** | SKU | buy posture (opening stock + commit) |
| `budgets.csv` | **yes** | SKU × channel | open-to-buy dollar budget |
| `sales_history.csv` | optional | SKU × channel × year × week | real per-year actuals (absolute year) |

Channels are fixed: `Ecom`, `Indirect`, `Store`.

---

## catalog.csv

```
hierarchy_code,l1_name,l2_name,sku_code,color,size,air,auc,peak_week,peak_units,target_wos,lead_time_weeks,case_pack,safety_weeks,activation_week,deactivation_week,status_seed,tagged_to
10001,Footwear,Running Shoes,FW-RUN-001,Blue,US 9,119.99,44.0,26,160,6,14,6,2,202401,202852,Old,
```

- `air` list price, `auc` unit cost (dollars).
- `peak_week` / `peak_units` — only used when this SKU has **no** sales history
  (drives the fallback seasonal curve). With history, they're ignored for the curve.
- `target_wos`, `lead_time_weeks`, `case_pack`, `safety_weeks` — planning settings.
- `activation_week` / `deactivation_week` — 6-digit `YYYYWW` lifecycle bounds.
- `status_seed` — `Old` (has history) or `New` (recently launched; borrows discount
  from the `tagged_to` SKU during its first year). `tagged_to` blank for Old.

## supply.csv

```
hierarchy_code,open_wos,commit_through,commit_mult
10001,5,33,1.0
```

- `open_wos` — opening inventory in weeks of forward demand.
- `commit_through` — last fiscal week with already-committed receipts; reorder after.
- `commit_mult` — how generous the committed buy is (1.0 = to target, >1 over, <1 under).

## budgets.csv

```
hierarchy_code,channel,budget
10001,Ecom,15000
```

One row per SKU × channel. `budget` is the season OTB dollar target.

## sales_history.csv (optional)

```
hierarchy_code,channel,year,week_num,units,discount_perc
10001,Ecom,2026,1,46,0.04
10001,Ecom,2025,26,150,0.02
10001,Ecom,2024,26,140,0.03
```

- `year` — the **absolute calendar year** the sales happened in (e.g. `2024`, `2025`,
  `2026`), NOT a relative `TY/LY/LLY` label. The tool maps the year you SELECT (Y) to
  TY=Y, LY=Y-1, LLY=Y-2 and, per comparison year, uses this file where a week is
  already actualised, else that year's WP forecast.
- Put **actuals only**, by the year they happened: fully-past years → all 52 weeks;
  the current year → only the weeks already closed (e.g. `1..19` if "now" is wk20);
  future years → omit.
- `week_num` — fiscal week `1..52` (NOT the 6-digit code).
- `units` ≥ 0; `discount_perc` a fraction (`0.10` = 10% off; blank = 0).
- A stream (SKU+channel) that appears here plans on its own data; forward weeks are
  reforecast from the most recent FULL prior year's shape. A SKU absent from this
  file keeps the parametric curve.

See `sales_history.csv.template` for a starter you can rename to `sales_history.csv`.
