# SKU Planning Tool — QA Test Plan
**Tool:** IA Planning Demo (FastAPI + Next.js)  
**Scope:** `/wp` Working Plan page — all modules, business logic, edge cases, and data integrity  
**Environment:** Backend `http://localhost:8000` · Frontend `http://localhost:3001/wp`  
**Tester role:** Senior QA Engineer — merchandise planning domain  
**Format:** TC-ID | Module | Steps | Expected vs Actual | Pass/Fail | Severity | Notes

---

## Assumptions & Prerequisites

1. Backend is running: `cd backend && uvicorn main:app --reload --port 8000`
2. Frontend is running: `cd frontend && npm run dev -- --port 3001`
3. Browser: Chrome latest (DevTools available for network inspection)
4. `random.seed(42)` is set in `dummy_data.py` — data is deterministic across restarts
5. "Actuals" exist for weeks 202501–202519 (week_num < 20); future weeks have actuals = 0
6. 8 products (hierarchy_code 10001–10008), 3 channels (Ecom, Indirect, Store)
7. Fiscal year = 2025, weeks 202501–202552
8. All state is in-memory — a server restart resets all overrides and snapshots
9. Editable fields are: `written_sales_units`, `written_sales_dollars`, `on_order_placed_total_unit`

---

## Module Index

| # | Module |
|---|--------|
| A | Filter / Multi-Select |
| B | Portfolio KPI Cards |
| C | Cross-Product Impact Table |
| D | Weekly Detail — Plan Tab |
| E | Weekly Detail — Actuals Tab |
| F | Weekly Detail — Inventory Tab |
| G | Weekly Detail — TY/LY Tab |
| H | Inline Editing & Derived-Field Recalculation |
| I | Exception Row Coloring |
| J | Chart (Units by Week) |
| K | Snapshot — Save / Restore / Delete |
| L | Reset All Edits |
| M | CSV Export |
| N | Edge Cases & Boundary Values |
| O | API Contract Tests (curl) |
| P | Known Defects (pre-logged) |

---

## A — Filter / Multi-Select

---

### TC-A01 | Filter | Empty state on page load

**Steps:**
1. Navigate to `http://localhost:3001/wp`
2. Observe both Product and Channel dropdowns before interacting

**Expected:**
- Product dropdown displays `— Product —` with slate text
- Channel dropdown displays `— Channel —` with slate text
- Weekly detail table shows: "Select at least 1 product and 1 channel above to view and edit weekly values."
- No chart is visible
- No tab buttons (Plan / Actuals / Inventory / TY/LY) are visible
- No CSV button is visible
- The filter badge reads "Select at least 1 product + 1 channel to enable editing"

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-A02 | Filter | Product dropdown lists all 8 hierarchies

**Steps:**
1. Click the Product dropdown
2. Count and verify all listed options

**Expected:**
- 8 options rendered: 7.5ft Pre-Lit Slim Tree, 9ft Grand Fir Tree, 6ft Tabletop Tree, 24in Classic Wreath, 36in Grand Wreath, 9ft Garland, 50-Piece Ornament Set, Personalized Ornament
- Each option has a checkbox (unchecked by default)
- "✕ Clear selection" button is NOT visible when nothing is selected

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-A03 | Filter | Channel dropdown lists all 3 channels

**Steps:**
1. Click the Channel dropdown
2. Count and verify options

**Expected:**
- 3 options: Ecom, Indirect, Store
- Each with unchecked checkbox

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-A04 | Filter | Single product + single channel selection

**Steps:**
1. Open Product dropdown → select "9ft Grand Fir Tree"
2. Open Channel dropdown → select "Ecom"
3. Observe header badge, table header, and data

**Expected:**
- Product button turns blue-bordered: "9ft Grand Fir Tree"
- Channel button turns blue-bordered: "Ecom"
- Green badge appears: "✏️ Editing: 9ft Grand Fir Tree · Ecom"
- Weekly table header shows: "9ft Grand Fir Tree · Ecom"
- Exactly 52 rows appear (one per fiscal week 202501–202552)
- Tab buttons (Plan / Actuals / Inventory / TY/LY) appear
- CSV button appears
- Chart appears with 4 lines

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-A05 | Filter | Multiple products selected

**Steps:**
1. Select Products: "9ft Grand Fir Tree" + "24in Classic Wreath"
2. Select Channel: "Ecom"
3. Observe label and row count

**Expected:**
- Product dropdown label: "2 Products selected"
- Green badge: "✏️ Editing: 2 Products · Ecom"
- Weekly table has 104 rows (52 weeks × 2 products) sorted by week then hierarchy_code
- Each row shows distinct Product and Channel columns
- No duplicate-key React warnings in browser console

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-A06 | Filter | All 3 channels selected

**Steps:**
1. Select Product: "9ft Grand Fir Tree"
2. Open Channel dropdown → select Ecom, Indirect, Store
3. Observe label

**Expected:**
- Channel label: "All Channels" (because all options are selected)
- 156 rows (52 weeks × 3 channels)
- Chart aggregates all 3 channels per week (sums, not triples per week)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-A07 | Filter | Clear selection via "✕ Clear selection" button

**Steps:**
1. Select 2 products
2. Re-open Product dropdown
3. Click "✕ Clear selection"
4. Observe state

**Expected:**
- All product checkboxes become unchecked
- Dropdown closes
- Product button returns to `— Product —`
- If channel was already selected, `canEdit` becomes false
- Weekly table reverts to empty-state message

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-A08 | Filter | Dropdown closes on outside click

**Steps:**
1. Open Product dropdown
2. Click anywhere outside the dropdown (e.g., page heading)

**Expected:** Dropdown closes without any selection change

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-A09 | Filter | Portfolio table click toggles product selection

**Steps:**
1. Select Channel: "Ecom" (product unselected)
2. Click on the "9ft Grand Fir Tree" row in the Cross-Product Impact table

**Expected:**
- Row highlights blue (bg-blue-900/30)
- Product checkbox in that row becomes checked
- Product dropdown badge updates to "9ft Grand Fir Tree"
- Green editing badge appears
- Weekly rows load

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

## B — Portfolio KPI Cards

---

### TC-B01 | KPI Cards | Cards render on load

**Steps:**
1. Load page without any filter selection

**Expected:**
- 4 KPI cards visible: "Portfolio Sales $", "Portfolio GM $", "GM %", "Portfolio Units"
- All show non-zero values (full portfolio aggregation)
- Delta badges show `—` if no edits have been made (current = baseline)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-B02 | KPI Cards | Delta badge reflects edit

**Steps:**
1. Note the current "Portfolio Units" value
2. Select a product + channel
3. Edit a row's Sales Units (increase by 1,000)
4. Observe the KPI cards

**Expected:**
- "Portfolio Units" value increases
- Delta badge next to "Portfolio Units" shows `+1,000` in emerald green
- "Portfolio Sales $" and "Portfolio GM $" also increase proportionally
- "GM %" may change if edit was not proportional

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-B03 | KPI Cards | Negative delta shows red

**Steps:**
1. Edit a row's Sales Units — decrease by 500

**Expected:**
- Delta badge shows `-500` in red (text-red-400)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-B04 | KPI Cards | GM % calculation accuracy

**Steps:**
1. Record Portfolio Sales $ and GM $ values
2. Manually compute: `GM % = GM $ / Sales $`
3. Compare with displayed GM %

**Expected:**
- Displayed GM % = `(total_gm_dollar / total_sales_dollars) × 100`, accurate to 1 decimal place
- Example: $500K GM / $1M Sales = 50.0%

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — incorrect GM % has direct business impact

---

### TC-B05 | KPI Cards | Card border turns amber when edits active

**Steps:**
1. Edit any cell
2. Observe KPI card borders

**Expected:**
- All 4 cards switch from `border-slate-700` to `border-amber-900/50` (visible amber tint)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

## C — Cross-Product Impact Table

---

### TC-C01 | Portfolio Table | Shows all 8 products by default

**Steps:**
1. Load page (no filters)
2. Count rows in "Cross-Product Impact" table

**Expected:**
- 8 rows, one per hierarchy
- Columns: (checkbox), Product, Category, Sales Units, Sales $, GM $, GM %, Status
- Status column shows "—" for all rows

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-C02 | Portfolio Table | Filtering by selection narrows the table

**Steps:**
1. Select Products: "9ft Grand Fir Tree" and "6ft Tabletop Tree"
2. Observe Cross-Product table

**Expected:**
- Header shows "2 of 8 products"
- Only 2 rows visible (matching selected hierarchies)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-C03 | Portfolio Table | Modified badge appears after edit

**Steps:**
1. Select product + channel, edit a cell
2. Look at the Cross-Product table row for that product

**Expected:**
- Status cell shows amber "Modified" badge
- Row has subtle amber background (bg-amber-900/10)
- Sales Units cell has a small ✎ icon

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-C04 | Portfolio Table | GM % accuracy per product

**Steps:**
1. Note Sales $ and GM $ for "24in Classic Wreath"
2. Compute expected GM % = GM $ / Sales $
3. Compare with table value

**Expected:** Matches to 1 decimal place

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

## D — Weekly Detail — Plan Tab

---

### TC-D01 | Plan Tab | Columns present

**Steps:**
1. Select product + channel
2. Ensure "Plan" tab is active (default)
3. Verify all column headers

**Expected columns (in order):**
Week | Product | Channel | Sales U ✎ | Sales $ ✎ | AUC | AUR | GM $ | GM % | OO Placed ✎ | BOP | EOP | WOS | Recomm Rcpt

- Editable columns (Sales U, Sales $, OO Placed) have blue header text
- "✎ blue cells are editable" badge visible above table

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-D02 | Plan Tab | Week column shows fiscal week + status dots

**Steps:**
1. Inspect rows for weeks 202501–202519 vs 202520–202552

**Expected:**
- Past weeks (202501–202519): violet `●` dot beside week number
- Future weeks: no dot
- Modified rows: amber week text + small ✎ icon

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-D03 | Plan Tab | Product and Channel columns display correctly

**Steps:**
1. Select products "9ft Grand Fir Tree" + "24in Classic Wreath", channel "Ecom"
2. Inspect Product and Channel columns for all rows

**Expected:**
- Each row shows the human-readable product name (l2_name), not the hierarchy_code number
- Channel column shows "Ecom" for all rows in this scenario
- Rows sorted: week ascending, then product ascending within same week

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-D04 | Plan Tab | AUR = Sales $ / Units

**Steps:**
1. For a specific row, note Sales Units and Sales $
2. Compute AUR = Sales $ / Units

**Expected:** AUR column value matches to 2 decimal places

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — AUR is the basis for all price-point calculations

---

### TC-D05 | Plan Tab | GM $ = Sales $ − Cost $

**Steps:**
1. For a row note: Sales $, AUC, Sales Units
2. Compute expected: Cost $ = AUC × Units; GM $ = Sales $ − Cost $
3. Compare with displayed GM $

**Expected:** Matches to nearest dollar

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-D06 | Plan Tab | GM % = GM $ / Sales $

**Steps:**
1. Use same row as TC-D05
2. Compute GM % = GM $ / Sales $

**Expected:**
- Displayed GM % = computed value × 100, shown as `XX.X%`
- Color: green if ≥ 50%, slate if ≥ 30%, amber if < 30%

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-D07 | Plan Tab | WOS = EOP / Sales Units

**Steps:**
1. For a row note: EOP units, Sales Units
2. Compute WOS = EOP / Sales Units

**Expected:**
- Displayed WOS matches (rounded to 2 decimal places)
- When Sales Units = 0, WOS = 99.0 (sentinel value, not ∞)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — WOS drives replenishment decisions

---

### TC-D08 | Plan Tab | WOS color thresholds

**Steps:**
1. Identify rows with WOS < 2, WOS 2–4, WOS 4–12, WOS 12–16, WOS > 16

**Expected colors:**
| WOS Range | Color |
|-----------|-------|
| < 2 | red + font-semibold |
| 2–4 | amber |
| 4–12 | emerald (normal) |
| 12–16 | amber |
| > 16 | red |

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — wrong color causes planners to miss stockout/overstock risk

---

### TC-D09 | Plan Tab | EOP continuity check

**Steps:**
1. For consecutive weeks (e.g., wk 202510 and 202511) of the same product+channel, note EOP[n] and BOP[n+1]

**Expected:**
- `BOP[n+1]` should equal `EOP[n]`

> **Note:** Due to how dummy_data.py generates sub-channel rows (BOP carries forward per channel in the loop), this may not hold exactly across sub-channel aggregation. Flag if the discrepancy exceeds 5%.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — broken BOP/EOP chain corrupts the entire inventory plan

---

### TC-D10 | Plan Tab | Recomm Rcpt logic

**Steps:**
1. For a row note: Sales Units (U), BOP
2. Compute expected Recomm Rcpt = max(0, round(U × 1.05 − BOP × 0.3))
3. Compare with displayed value

**Expected:** Matches exactly

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

## E — Weekly Detail — Actuals Tab

---

### TC-E01 | Actuals Tab | Columns present

**Steps:**
1. Select product + channel
2. Click "Actuals" tab

**Expected columns:**
Week | Product | Channel | Plan U | Plan $ | Act U | Act $ | Var U | Var U% | Var $ | Var $% | ST% | MD U | MD $

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-E02 | Actuals Tab | Past weeks show actuals; future weeks show dashes

**Steps:**
1. Inspect rows for weeks 202501–202519 (past) vs 202520–202552 (future)

**Expected:**
- Past weeks: Act U, Act $, Var U, Var U%, Var $, Var $%, ST% all populated with real values
- Future weeks: all 7 actuals/variance columns show "—" (dash)
- Markdown (MD U, MD $) shows for all weeks

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-E03 | Actuals Tab | Variance = Plan − Actual

**Steps:**
1. Pick any past-week row (e.g., 202510)
2. Note Plan U and Act U
3. Compute Var U = Plan U − Act U
4. Compare with displayed Var U

**Expected:** Exact match. Positive = over-plan. Negative = under-plan.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-E04 | Actuals Tab | Var U% = Var U / Plan U

**Steps:**
1. Same row as TC-E03
2. Compute Var U% = (Plan U − Act U) / Plan U × 100

**Expected:** Displayed Var U% matches to 1 decimal place (e.g., "-12.3%")

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-E05 | Actuals Tab | Var U% coloring

**Expected color mapping:**
| Var U% | Color |
|--------|-------|
| < −15% | red |
| −15% to −5% | amber |
| −5% to +5% | slate |
| > +5% | emerald |

**Steps:** Identify a row in each range and verify the color of Var U%, Var U, and Var $ cells.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-E06 | Actuals Tab | Var $% column always shows "—" (known defect)

**Steps:**
1. On any past-week row, observe the "Var $%" column

**Expected (per current code):** Always renders "—" — the column header exists but the cell is hardcoded to dash (line 708 of page.tsx). There is no `variance_dollars_perc` field in the backend or TypeScript type.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — column is labelled but non-functional; misleads planners  
**Defect:** See P-01

---

### TC-E07 | Actuals Tab | Sell-Through % = Actual Units / (BOP + Total Receipt Units)

**Steps:**
1. For a past week, note Act U, BOP, Total Rcpt from Inventory tab
2. Compute ST% = Act U / (BOP + Total Rcpt) × 100
3. Compare with displayed ST%

**Expected:** Matches to 1 decimal place. Shows 0.0% for future weeks.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — ST% is the primary sell-through KPI

---

### TC-E08 | Actuals Tab | ST% color thresholds

**Expected:**
| ST% | Color |
|-----|-------|
| > 60% | emerald |
| 40–60% | slate |
| < 40% | amber |

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-E09 | Actuals Tab | Markdown range is 0%–40% of plan

**Steps:**
1. Inspect MD Units and MD $ for weeks before and after peak (e.g., peak_week=44 for hc 10002)

**Expected:**
- Pre-peak weeks: MD U ≈ 0–5% of Plan U (low discount rate 0–5%)
- Post-peak weeks: MD U increases (discount rate 15–40%)
- MD $ = MD Units × base AIR × discount_rate (e.g., for 9ft Grand Fir AIR = $999.99)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

## F — Weekly Detail — Inventory Tab

---

### TC-F01 | Inventory Tab | Columns present

**Expected columns:**
Week | Product | Channel | BOP | EOP | WOS | OTB U | OTB $ | OO Placed ✎ | OO Unplaced | Rcpt Total | Recomm Rcpt

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-F02 | Inventory Tab | OTB U = OO Unplaced Units

**Steps:**
1. For a row, note OO Unplaced and OTB U

**Expected:** `OTB U = OO Unplaced Total Unit` (they should be equal)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — OTB drives buy budget decisions

---

### TC-F03 | Inventory Tab | OTB $ = OTB U × AUC

**Steps:**
1. For a row note OTB U and AUC (from Plan tab)
2. Compute OTB $ = OTB U × AUC

**Expected:** Displayed OTB $ matches to nearest dollar

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-F04 | Inventory Tab | Rcpt Total = OO Placed + OO Unplaced

**Steps:**
1. For a row note OO Placed, OO Unplaced, and Rcpt Total

**Expected:** `Rcpt Total = OO Placed + OO Unplaced`

> **Note:** After editing OO Placed, backend recalculates: `total_receipt_units = on_order_placed + on_order_unplaced`. Verify this holds post-edit too (see TC-H05).

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-F05 | Inventory Tab | WOS color consistency with Plan tab

**Steps:**
1. Note WOS and its color for a row on Plan tab
2. Switch to Inventory tab, find same row

**Expected:** WOS value and color are identical on both tabs

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

## G — Weekly Detail — TY/LY Tab

---

### TC-G01 | TY/LY Tab | Columns present

**Expected columns:**
Week | Product | Channel | TY U | LY U | Var U | TY/LY U% | TY $ | LY $ | Var $ | TY/LY $%

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-G02 | TY/LY Tab | LY data is non-zero

**Steps:**
1. Inspect LY U and LY $ columns for several rows

**Expected:**
- LY U and LY $ are > 0 for all 52 weeks
- LY U ≈ TY U × random.uniform(0.85, 1.15) (generated from TY_LY_DATA)
- Values are different from TY values (not duplicates)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — zero LY data means planners cannot do YoY analysis

---

### TC-G03 | TY/LY Tab | Var U = TY U − LY U

**Steps:**
1. For a row note TY U and LY U
2. Compute Var U = TY U − LY U

**Expected:** Displayed "Var U" matches exactly

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-G04 | TY/LY Tab | TY/LY U% = (TY U − LY U) / LY U × 100

**Steps:**
1. Same row as TC-G03
2. Compute percentage

**Expected:** Displayed TY/LY U% matches to 1 decimal place

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-G05 | TY/LY Tab | Var color consistency

**Expected:** Var U and TY/LY U% use same color logic as `varPctColor()`:
- < −15%: red
- −15% to −5%: amber
- −5% to +5%: slate
- > +5%: emerald

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-G06 | TY/LY Tab | TY/LY $% uses dollar variance, not unit

**Steps:**
1. For a row compute: `LY $%  = (TY $ − LY $) / LY $`
2. Compare with displayed TY/LY $%

**Expected:** Uses dollar values, not unit values — the two percentages can differ significantly if AUR changed year-over-year.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

## H — Inline Editing & Derived-Field Recalculation

---

### TC-H01 | Editing | EditableNumber cell renders edit icon

**Steps:**
1. Select product + channel
2. On Plan tab, hover over a Sales U cell

**Expected:**
- Cursor changes to pointer
- Cell highlights (bg-slate-600 on hover)
- Small ✎ icon visible at bottom-right of cell
- Blue text (unmodified) or amber text (already modified)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-H02 | Editing | Click to enter edit mode

**Steps:**
1. Click a Sales U cell

**Expected:**
- Cell replaced by a small input field (w-20 px, dark background, blue border)
- Input is pre-populated with the current numeric value (integer, no commas)
- Input has focus automatically

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-H03 | Editing | Commit via Enter key

**Steps:**
1. Click a Sales U cell → changes to 500
2. Press Enter

**Expected:**
- Input disappears, cell shows formatted "500" in amber (modified state)
- PUT request sent to `/api/wp/row` with `{hierarchy_code, current_week, channel, field: "written_sales_units", value: 500}`
- Response updates the row in place
- Portfolio KPI cards update
- Cross-product table "Modified" badge appears

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-H04 | Editing | Commit via blur (click away)

**Steps:**
1. Click a Sales U cell → changes to 600
2. Click elsewhere on the page (not another editable cell)

**Expected:** Same behavior as TC-H03 — commit fires on blur

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-H05 | Editing | Escape cancels edit without saving

**Steps:**
1. Click a Sales U cell → type 9999
2. Press Escape

**Expected:**
- Input disappears, original value is displayed
- No API call made
- Row unchanged

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-H06 | Editing | Edit Sales Units → Sales $ auto-derives

**Steps:**
1. Note AUR for a row (Plan tab AUR column)
2. Edit Sales U → new value N
3. After commit, note Sales $ on same row

**Expected:** `Sales $ = AUR × N` (rounded to 2 decimal places)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — fundamental unit/dollar consistency

---

### TC-H07 | Editing | Edit Sales $ → Sales Units back-calculates

**Steps:**
1. Note AUR for a row
2. Edit Sales $ → new value D
3. After commit, note Sales U

**Expected:** `Sales U = round(D / AUR)`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-H08 | Editing | Edit Sales Units → EOP recalculates

**Steps:**
1. Note BOP, OO Placed, Sales U for a row
2. Edit Sales U → new value N
3. After commit, note EOP

**Expected:** `EOP = max(0, BOP − N + OO_Placed)`

> **Note:** Backend `_recalc()` uses `OO_placed` (not `total_receipt_units`) for EOP. This differs from how the original data was generated (`EOP = BOP − units + receipt_units`). Flag this discrepancy.

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — see Defect P-02

---

### TC-H09 | Editing | Edit OO Placed → EOP and Rcpt Total update

**Steps:**
1. Note OO Placed, OO Unplaced, Rcpt Total, and EOP for a row
2. Edit OO Placed → new value P
3. After commit, check EOP and Rcpt Total on Inventory tab

**Expected:**
- `total_receipt_units = P + OO_Unplaced`
- `EOP = max(0, BOP − Sales U + P)`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-H10 | Editing | Edit Sales Units → WOS recalculates

**Steps:**
1. Edit Sales U → halve the value (e.g., from 200 to 100)
2. Note new EOP and WOS

**Expected:** `WOS = EOP_new / 100` — WOS should roughly double

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-H11 | Editing | Edit Sales Units → Variance recalculates (past week)

**Steps:**
1. Pick a past week (202510)
2. Edit Sales U to a new value N
3. Note variance

**Expected:**
- `Variance U = N − Actual U`
- `Variance U% = (N − Actual U) / N`
- Exception row background updates accordingly

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-H12 | Editing | GM $ and GM % update after edit

**Steps:**
1. Edit Sales U for a row (e.g., increase by 200)
2. Note new Sales $, Sales Cost, GM $, GM %

**Expected:**
- `Cost = AUC × new_Units`
- `GM $ = new_Sales $ − Cost`
- `GM % = GM $ / Sales $`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-H13 | Editing | Sequential edits (units then dollars)

**Steps:**
1. Edit Sales U → 300 (commit)
2. Immediately edit Sales $ on the same row → 150000 (commit)
3. Verify final state

**Expected:**
- `_last_edited = "written_sales_dollars"` in override dict
- Final Units = round(150000 / AUR)
- Final Sales $ = 150000

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — `_last_edited` logic governs which field wins in conflict

---

### TC-H14 | Editing | Edit is scoped — only the edited row changes

**Steps:**
1. Select 2 products (hc 10001 + 10002), channel Ecom
2. Edit Sales U for hc 10001, week 202510
3. Verify hc 10002, week 202510 is unchanged

**Expected:** Only hc 10001 × Ecom × 202510 row reflects the change

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — broadcast contamination would corrupt plans

---

### TC-H15 | Editing | Non-editable field cannot be edited

**Steps:**
1. Hover over AUC, AUR, GM $, GM %, BOP, EOP columns

**Expected:**
- No cursor-pointer style
- No ✎ icon
- Clicking does not trigger an input field

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-H16 | Editing | Invalid field via API returns 400

**Steps:**
1. `curl -s -X PUT http://localhost:8000/api/wp/row -H "Content-Type: application/json" -d '{"hierarchy_code": 10001, "current_week": 202501, "channel": "Ecom", "field": "bop_units", "value": 999}'`

**Expected:**
```json
{"detail": "'bop_units' is not editable. Allowed: {'written_sales_units', 'written_sales_dollars', 'on_order_placed_total_unit'}"}
```
HTTP 400

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — protects data integrity

---

### TC-H17 | Editing | Edit error displays in UI

**Steps:**
1. Temporarily alter `EDITABLE_FIELDS` in `wp.py` to `{}` (empty), restart backend
2. Try to edit a Sales U cell

**Expected:**
- Red error banner appears in header: "Edit failed" or the API error message
- Row reverts to previous value

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium — revert backend change after test

---

## I — Exception Row Coloring

---

### TC-I01 | Exception Coloring | Red row for variance < −15%

**Steps:**
1. Find a past week where Actual U is significantly lower than Plan U (or force it: edit Plan U to 10× actual)
2. Observe row background

**Expected:** Row background `bg-red-900/20` (subtle red wash over the entire row)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-I02 | Exception Coloring | Green row for variance > +10%

**Steps:**
1. Find a past week where Actual U > Plan U × 1.10 (or force it: set Plan U to 50% of actual)

**Expected:** Row background `bg-emerald-900/15`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-I03 | Exception Coloring | Amber row for WOS > 14

**Steps:**
1. Find a row with high EOP and low Sales U (early weeks of seasonal products are candidates — e.g., week 202501 for Trees, which have WOS near 100+)

**Expected:** Row background `bg-amber-900/15`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-I04 | Exception Coloring | Red row for WOS 0 < WOS < 2

**Steps:**
1. Edit Sales U to a very high value (e.g., 10× EOP) to force WOS < 2

**Expected:** Row background `bg-red-900/15`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — WOS < 2 is a stockout alert

---

### TC-I05 | Exception Coloring | Modified row gets amber (when no other exception)

**Steps:**
1. Edit Sales U for a future week (no actuals → no variance exception; ensure WOS stays in normal range)

**Expected:** Row background `bg-amber-900/10`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-I06 | Exception Coloring | Priority order when multiple exceptions apply

**Steps:**
1. For a past week with variance < −15%, edit Sales U so that WOS also > 14 for the same row

**Expected:** Variance exception (red bg-red-900/20) takes priority over WOS amber because `rowExceptionBg()` checks `actualised && variance_units_perc` first

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-I07 | Exception Coloring | Legend matches actual behavior

**Steps:**
1. Observe the legend strip at the bottom of the weekly table
2. Verify each legend item matches the actual coloring behavior tested above

**Legend text to verify:**
- "● past (actuals available)" → violet dot on past-week rows
- "red row = below plan >15% or WOS<2"
- "amber row = WOS>14"
- "green row = tracking above plan"

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

## J — Chart (Units by Week)

---

### TC-J01 | Chart | Renders when product + channel selected

**Steps:**
1. Select "9ft Grand Fir Tree" + "Ecom"

**Expected:**
- Line chart appears between the KPI cards and the weekly table
- Title: "9ft Grand Fir Tree · Ecom — Units by Week"
- 4 lines: Sales U (blue solid), BOP (amber dashed), EOP (emerald dashed), Receipts (violet solid)
- X-axis shows 2-digit week numbers ("01" through "52")
- Y-axis shows unit counts

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-J02 | Chart | Chart aggregates correctly for multi-select

**Steps:**
1. Select 2 products + 1 channel
2. Hover over a week in the chart tooltip

**Expected:**
- Tooltip shows aggregated Sales U = sum of Sales U across both products for that week
- Chart has exactly 52 x-axis points (not 104)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — non-aggregated chart would show chaotic data

---

### TC-J03 | Chart | Chart updates after edit

**Steps:**
1. Note the Sales U value for a specific week in the chart tooltip
2. Edit Sales U for that week
3. Re-hover the chart tooltip

**Expected:** Tooltip reflects the new Sales U value

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-J04 | Chart | Seasonal peak visible

**Steps:**
1. Select "9ft Grand Fir Tree" + "Ecom"
2. Observe the Sales U line shape

**Expected:**
- Sales U peaks near week 44 (peak_week for hc 10002)
- Bell-curve shape with a clear peak and off-peak trough
- BOP starts very high (3× peak), decreases through the season

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low — validates data generation correctness

---

## K — Snapshot — Save / Restore / Delete

---

### TC-K01 | Snapshot | Save snapshot with a name

**Steps:**
1. Edit Sales U for at least one row
2. Type "Week 20 Review" in the snapshot name input
3. Click "💾 Save Snapshot"

**Expected:**
- Snapshot saved
- Snapshot counter badge increments: "📸 Snapshots (1)"
- Name input clears
- Snapshot panel (when opened) shows "Week 20 Review" with correct summary

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-K02 | Snapshot | Save button disabled when name is empty

**Steps:**
1. Clear the snapshot name input
2. Observe the Save button

**Expected:** Button has `opacity-40` style and is non-clickable (disabled)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-K03 | Snapshot | Enter key saves snapshot

**Steps:**
1. Type "Test snap" in the input field
2. Press Enter

**Expected:** Same behavior as clicking the Save button

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-K04 | Snapshot | Snapshot panel shows summary KPIs

**Steps:**
1. Save a snapshot with edits
2. Open the Snapshots panel (click "📸 Snapshots")
3. Inspect the snapshot card

**Expected panel card contains:**
- Snapshot name
- Created timestamp (formatted: "MM/DD/YYYY, HH:MM:SS")
- "N edited cells"
- KPI grid: Sales $, GM $, GM %, Units

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-K05 | Snapshot | GM % in snapshot is simple average (not dollar-weighted)

> **This is a known defect (P-03).** The backend computes snapshot `avg_gm_perc` as:
> `sum(r["written_gm_perc"] for r in all_rows) / len(all_rows)` — a simple average.
> For a cross-product snapshot, this is misleading because a $5 ornament row carries equal weight as a $1,000 tree row.

**Steps:**
1. Save a snapshot containing the full portfolio
2. Manually compute dollar-weighted GM %: `total_gm / total_sales`
3. Compare with snapshot card's GM %

**Expected (current behavior):** Simple average — will differ from dollar-weighted  
**Expected (correct behavior):** Dollar-weighted average

**Pass/Fail:** _[ ]_  
**Severity:** High — incorrect GM % in snapshots

---

### TC-K06 | Snapshot | Restore snapshot restores edits

**Steps:**
1. Edit Sales U for week 202510 → 999
2. Save snapshot "Scenario A"
3. Reset all edits
4. Edit Sales U for week 202510 → 111
5. Open snapshots panel → Restore "Scenario A"

**Expected:**
- Week 202510 Sales U returns to 999
- Other edited values from step 4 are also overwritten
- Portfolio KPI cards update

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical — snapshot restore must be atomic and complete

---

### TC-K07 | Snapshot | Delete snapshot removes it from panel

**Steps:**
1. Open Snapshots panel
2. Click 🗑 on one snapshot

**Expected:**
- Snapshot removed from list immediately (optimistic UI update)
- Snapshot counter badge decrements
- The current override state is NOT changed (only the saved copy is deleted)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-K08 | Snapshot | IDs collide after delete (known defect)

> Backend: `"id": len(SNAPSHOTS) + 1` — if you save 3 snaps (IDs 1,2,3), delete snap 2, then save a new one, it gets ID 3 — collision with the existing snap 3.

**Steps:**
1. Save 3 snapshots: "A", "B", "C"
2. Delete "B"
3. Save "D"
4. Observe assigned ID vs existing IDs

**Expected (correct):** Monotonically incrementing IDs — "D" should be ID 4  
**Expected (current):** "D" gets ID 3 — same as "C" — see Defect P-04

**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-K09 | Snapshot | Baseline summary in panel

**Steps:**
1. Open Snapshots panel (no edits made)
2. Scroll to bottom of panel

**Expected:**
- "Baseline (original)" section shows original Sales $ and GM $ before any edits
- These values match the KPI cards when `hasEdits = false`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-K10 | Snapshot | Panel closes on backdrop click

**Steps:**
1. Open Snapshots panel
2. Click the dark overlay backdrop (outside the panel)

**Expected:** Panel closes; overlay disappears

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

## L — Reset All Edits

---

### TC-L01 | Reset | Button is disabled when no edits exist

**Steps:**
1. Load the page fresh (no edits)
2. Observe "↺ Reset All Edits" button

**Expected:** Button has `opacity-40`, is disabled (not clickable)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-L02 | Reset | Button activates after any edit

**Steps:**
1. Edit any cell
2. Observe button

**Expected:** Button becomes active (full opacity)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-L03 | Reset | Reset clears all overrides

**Steps:**
1. Edit Sales U for 3 different rows across different products/channels
2. Click "↺ Reset All Edits"

**Expected:**
- All 3 rows return to their original values
- Modified indicators (amber text, ✎ icon, "Modified" badge) disappear from all rows
- KPI cards return to baseline values
- Delta badges show "—"
- Button becomes disabled again

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Critical

---

### TC-L04 | Reset | Reset does not affect saved snapshots

**Steps:**
1. Save a snapshot with edits ("Before Reset")
2. Reset all edits
3. Open Snapshots panel

**Expected:** "Before Reset" snapshot still present with its original summary and override data intact

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

## M — CSV Export

---

### TC-M01 | CSV | Export button only visible when data is loaded

**Steps:**
1. No filters selected → no CSV button
2. Select product + channel → CSV button appears

**Expected:** "⬇ CSV" button appears in weekly table header only when `canEdit && rows.length > 0`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-M02 | CSV | Export triggers file download

**Steps:**
1. Select product + channel
2. Click "⬇ CSV"

**Expected:**
- Browser downloads a file named `wp-YYYY-MM-DD.csv`
- File is not empty

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-M03 | CSV | CSV contains correct headers

**Steps:**
1. Open the downloaded CSV

**Expected first row (25 columns):**
```
Week,Product,Channel,Plan U,Plan $,Act U,Act $,Var U,Var U%,ST%,WOS,OTB U,OTB $,GM $,GM %,MD U,MD $,BOP,EOP,OO Placed,Recomm Rcpt,LY U,LY $,TY/LY U%,TY/LY $%
```

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-M04 | CSV | CSV row count matches table

**Steps:**
1. Select 2 products + 2 channels (expect 52 × 2 × 2 = 208 data rows)
2. Export CSV
3. Count rows (excluding header)

**Expected:** 208 data rows

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-M05 | CSV | Product names are quoted to handle commas

**Steps:**
1. Open CSV in a text editor
2. Find the Product column

**Expected:** Product names are wrapped in double quotes (`"9ft Grand Fir Tree"`)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium — unquoted commas in product names would break CSV parsing

---

### TC-M06 | CSV | Future weeks have empty variance/ST% fields

**Steps:**
1. Export CSV
2. Find rows for weeks 202520–202552

**Expected:**
- Var U%, ST% columns are empty string `""` (not "0%" or "—")
- Act U = 0, Act $ = 0

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-M07 | CSV | Modified values export correctly

**Steps:**
1. Edit Sales U for week 202501 → 999
2. Export CSV
3. Find week 202501 row

**Expected:** Plan U column shows "999" (the overridden value, not original)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

## N — Edge Cases & Boundary Values

---

### TC-N01 | Edge Case | Week 1 has extreme WOS due to 3× BOP init

**Steps:**
1. Select any Tree product + any channel
2. Inspect WOS for week 202501

**Context:** `bop[ch] = peak_units × channel_split × 3` sets initial BOP at 3× peak inventory. With very low week-1 sales (seasonal curve ≈ 0.03), WOS can be 100+.

**Expected (current behavior):** WOS > 100, row shows amber background (WOS > 14), no error

**Observation:** Flag if WOS > 999 causes display issues (overflow)

**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-N02 | Edge Case | Zero Sales Units → WOS sentinel

**Steps:**
1. Edit Sales U for any future low-activity week to 0
2. Check WOS

**Expected:** WOS = 99.0 (not Infinity, not NaN, not a division error)

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — division by zero must be handled

---

### TC-N03 | Edge Case | Negative EOP clamped to 0

**Steps:**
1. Find a row where BOP is small (e.g., late off-season week)
2. Edit Sales U to a value larger than BOP + OO Placed

**Expected:** EOP displayed as 0 (not negative) — `max(0, BOP − Units + OO_Placed)`

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High — negative inventory is physically impossible

---

### TC-N04 | Edge Case | Very large numbers format correctly

**Steps:**
1. Edit Sales U for a peak-week row to 1,000,000
2. Observe displayed Sales $ (which will be in the hundreds of millions)

**Expected:**
- Sales $ displays as `$XXX.XXM` format (millions)
- No overflow or `[object Object]` in cell

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-N05 | Edge Case | Decimal input for Sales U (integer field)

**Steps:**
1. Click Sales U cell → type "125.7"
2. Commit (Enter)

**Expected:** Value rounds to 126 (due to `round()` on backend). Frontend shows "126".

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium

---

### TC-N06 | Edge Case | Non-numeric input in edit field

**Steps:**
1. Click Sales U cell → type "abc"
2. Commit (Enter)

**Expected:**
- Frontend: `parseFloat("abc") = NaN` → `isNaN(num)` → no `onCommit` call → no API call
- Cell reverts to original value
- No error banner

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-N07 | Edge Case | Negative input in edit field

**Steps:**
1. Edit Sales U → type "-100"
2. Commit

**Expected:**
- API call succeeds (no validation on negative in backend for sales units)
- Sales $ becomes negative (AUR × −100)
- GM $ becomes negative
- **Observation:** No server-side validation rejects negatives — flag as defect P-05

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** High

---

### TC-N08 | Edge Case | Same value as current (no-op)

**Steps:**
1. Click Sales U cell with value "200"
2. Type "200"
3. Commit

**Expected:**
- Frontend: `num !== value` is false → `onCommit` is NOT called
- No API call made (verify in Network tab)
- Row unchanged

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Low

---

### TC-N09 | Edge Case | Server restart wipes state

**Steps:**
1. Make several edits
2. Restart backend server
3. Reload frontend

**Expected:**
- All overrides are gone (in-memory state)
- Portfolio KPIs return to baseline
- Snapshots panel is also empty

**Observation:** This is by-design for a demo tool. Document this behavior as a known limitation.

**Pass/Fail:** _[ ]_  
**Severity:** Medium (known limitation, not a bug)

---

### TC-N10 | Edge Case | All products + all channels selected

**Steps:**
1. Open Product dropdown → select all 8
2. Open Channel dropdown → select all 3
3. Let data load

**Expected:**
- Product label: "All Products" (all 8 = all options)
- Channel label: "All Channels"
- 8 × 3 × 52 = 1,248 rows in the weekly table
- Chart aggregates all into 52 weekly points
- No browser freeze within 5 seconds

**Actual:** _[record result]_  
**Pass/Fail:** _[ ]_  
**Severity:** Medium — performance/rendering concern

---

## O — API Contract Tests (curl)

Run these directly against `http://localhost:8000` to isolate backend logic from the UI.

---

### TC-O01 | API | GET /api/wp/filters returns correct structure

```bash
curl -s "http://localhost:8000/api/wp/filters" | python3 -m json.tool
```

**Expected:**
```json
{
  "hierarchies": [/* 8 objects with hierarchy_code, l1_name, l2_name */],
  "channels": ["Ecom", "Indirect", "Store"],
  "weeks": [202501, 202502, ..., 202552]
}
```

**Pass/Fail:** _[ ]_ | **Severity:** High

---

### TC-O02 | API | GET /api/wp/by-week with hc + channel returns 52 rows

```bash
curl -s "http://localhost:8000/api/wp/by-week?hierarchy_code=10001&channel=Ecom" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d), d[0].keys())"
```

**Expected:** 52 rows; each row contains all required fields including `wos`, `sell_through_perc`, `otb_units`, `ly_sales_units`, `variance_units`, `actualised`

**Pass/Fail:** _[ ]_ | **Severity:** Critical

---

### TC-O03 | API | GET /api/wp/by-week without filters aggregates all

```bash
curl -s "http://localhost:8000/api/wp/by-week" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))"
```

**Expected:** 52 rows (aggregated across all products and channels per week)

**Pass/Fail:** _[ ]_ | **Severity:** High

---

### TC-O04 | API | GET /api/wp/summary returns correct totals

```bash
curl -s "http://localhost:8000/api/wp/summary"
```

**Expected:**
```json
{
  "total_written_sales_units": <number>,
  "total_written_sales_dollars": <number>,
  "total_written_gm_dollar": <number>,
  "avg_written_gm_perc": <0.0–1.0>
}
```
All values should be > 0.

**Pass/Fail:** _[ ]_ | **Severity:** High

---

### TC-O05 | API | PUT /api/wp/row with valid data returns updated row

```bash
curl -s -X PUT "http://localhost:8000/api/wp/row" \
  -H "Content-Type: application/json" \
  -d '{"hierarchy_code": 10001, "current_week": 202501, "channel": "Ecom", "field": "written_sales_units", "value": 500}'
```

**Expected:** HTTP 200 with full updated row JSON including `_modified: true`, recalculated `written_sales_dollars`, `eop_units`, `wos`, `written_gm_dollar`

**Pass/Fail:** _[ ]_ | **Severity:** Critical

---

### TC-O06 | API | PUT with invalid field returns 400

```bash
curl -s -o /dev/null -w "%{http_code}" -X PUT "http://localhost:8000/api/wp/row" \
  -H "Content-Type: application/json" \
  -d '{"hierarchy_code": 10001, "current_week": 202501, "channel": "Ecom", "field": "bop_units", "value": 999}'
```

**Expected:** `400`

**Pass/Fail:** _[ ]_ | **Severity:** High

---

### TC-O07 | API | DELETE /api/wp/overrides resets state

```bash
# Make an edit first
curl -s -X PUT "http://localhost:8000/api/wp/row" \
  -H "Content-Type: application/json" \
  -d '{"hierarchy_code": 10001, "current_week": 202501, "channel": "Ecom", "field": "written_sales_units", "value": 9999}'

# Then reset
curl -s -X DELETE "http://localhost:8000/api/wp/overrides"

# Verify the value is gone
curl -s "http://localhost:8000/api/wp/by-week?hierarchy_code=10001&channel=Ecom" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['written_sales_units'])"
```

**Expected:** Final output should NOT be 9999 — it should be the original generated value

**Pass/Fail:** _[ ]_ | **Severity:** Critical

---

### TC-O08 | API | Snapshot create/restore/delete lifecycle

```bash
# Create snapshot
curl -s -X POST "http://localhost:8000/api/wp/snapshots" \
  -H "Content-Type: application/json" \
  -d '{"name": "API Test Snap"}'

# List
curl -s "http://localhost:8000/api/wp/snapshots"

# Restore (replace 1 with the actual id)
curl -s -X PUT "http://localhost:8000/api/wp/snapshots/1/restore"

# Delete
curl -s -X DELETE "http://localhost:8000/api/wp/snapshots/1"
```

**Expected:** Each step returns the expected shape; DELETE returns `{"deleted": 1}`; restoring a nonexistent ID returns HTTP 404

**Pass/Fail:** _[ ]_ | **Severity:** High

---

### TC-O09 | API | GET /api/wp/portfolio returns per-hierarchy aggregation

```bash
curl -s "http://localhost:8000/api/wp/portfolio" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d), [(x['l2_name'], x['avg_gm_perc']) for x in d])"
```

**Expected:** 8 rows; `avg_gm_perc` > 0 for all; values sum to approximately full portfolio total

**Pass/Fail:** _[ ]_ | **Severity:** High

---

## P — Known Defects (Pre-Logged)

The following issues were identified during code review. Each should be assigned to a developer sprint.

---

### P-01 | Actuals Tab | Var $% column hardcoded to "—"

**Location:** `frontend/src/app/wp/page.tsx` line 708  
**Code:** `<td className={...}>—</td>`  
**Issue:** The "Var $%" column header exists, and the coloring class is applied, but the value is always hardcoded to "—". There is no `variance_dollars_perc` field in the backend `get_agg_rows()`, `_recalc()`, or the TypeScript `WPRow` type.  
**Impact:** Planners cannot see dollar-variance percentage — a primary performance KPI.  
**Fix:** Add `variance_dollars_perc` field to backend computation: `round(variance_dollars / written_sales_dollars, 4)`. Add field to `WPRow` type. Render in the `actuals` tab cell.  
**Severity:** High

---

### P-02 | Edit | EOP formula differs between initial data generation and _recalc()

**Location:** `backend/dummy_data.py` line 93 vs line 280  
**Initial:** `eop = max(0, current_bop - units + receipt_units)` (uses total receipts)  
**Recalc:** `row["eop_units"] = max(0, bop - units + on_order_placed)` (uses only placed OO)  
**Issue:** An unedited row's EOP reflects `bop − units + receipt_units`. After any edit (even to a different field), `_recalc()` changes the formula to `bop − units + oo_placed`. This causes a silent jump in EOP when a row is first edited.  
**Impact:** EOP and WOS change on first edit even if the edited field is unrelated to inventory.  
**Fix:** Align `_recalc()` to use `total_receipt_units` (or align initial generation to use `oo_placed + oo_unplaced`).  
**Severity:** High

---

### P-03 | Snapshot | avg_gm_perc is simple-average, not dollar-weighted

**Location:** `backend/dummy_data.py` lines 462–465  
**Code:** `sum(r["written_gm_perc"] for r in all_rows) / len(all_rows)`  
**Issue:** A $5 ornament row has equal weight to a $999 tree row. Cross-product snapshots will show inflated or deflated GM % depending on the product mix ratio.  
**Fix:** `round(sum(r["written_gm_dollar"] for r in all_rows) / sum(r["written_sales_dollars"] for r in all_rows), 4)`  
**Severity:** High

---

### P-04 | Snapshot | ID collision after delete

**Location:** `backend/dummy_data.py` line 451  
**Code:** `"id": len(SNAPSHOTS) + 1`  
**Issue:** After deleting snapshots, `len(SNAPSHOTS)` decreases. A new snapshot can receive an ID already used by an existing snapshot.  
**Fix:** Use a monotonically incrementing counter: `_NEXT_SNAP_ID` global, incremented on each save.  
**Severity:** Medium

---

### P-05 | Editing | No server-side validation for negative or unreasonably large values

**Location:** `backend/routers/wp.py` — `edit_row()` function  
**Issue:** `apply_edit()` accepts any float for `written_sales_units`. Submitting −100 results in negative sales dollars and GM. Submitting 10,000,000 for units creates unrealistic plans with no warning.  
**Fix:** Add Pydantic validators: `value: float = Field(..., ge=0)` for units, `ge=0` for dollars, optional `le` ceiling.  
**Severity:** High

---

### P-06 | useCallback | canEdit in dependency array is redundant but harmless

**Location:** `frontend/src/app/wp/page.tsx` line 222  
**Code:** `}, [canEdit, hcsKey, chsKey]);`  
**Issue:** `canEdit` is derived from `selectedHcs.length >= 1 && selectedChannels.length >= 1`. Any change to `hcsKey` or `chsKey` that would change `canEdit` already captures the change. Including `canEdit` causes an extra re-render when the arrays transition from 0→1 or 1→0, even though `hcsKey`/`chsKey` already changed.  
**Impact:** Minor — one extra fetch on first selection/deselection. Not user-visible.  
**Fix:** Remove `canEdit` from the dep array.  
**Severity:** Low

---

### P-07 | Chart | Week label sorting is lexicographic for week "10"–"52"

**Location:** `frontend/src/app/wp/page.tsx` line 297  
**Code:** `.sort((a, b) => parseInt(a.week) - parseInt(b.week))`  
**Issue:** Week label is `String(wk).slice(-2)` which gives "01"–"52". `parseInt("01")` = 1, `parseInt("52")` = 52. Sort is numeric — this is **correct** and not a bug.  
**Observation:** However, if fiscal year ever uses non-6-digit week codes, `slice(-2)` would break. Low risk for this demo.  
**Severity:** Low (advisory)

---

### P-08 | State | Overrides/Snapshots are in-memory only

**Location:** `backend/dummy_data.py` — `OVERRIDES` dict, `SNAPSHOTS` list  
**Issue:** All planning edits and saved snapshots are lost on server restart. There is no persistence layer (database, file system, Redis).  
**Impact:** Acceptable for a demo tool, but blocking for production use by merchandise planners.  
**Fix (production):** Replace in-memory dicts with a database (PostgreSQL recommended for relational planning data).  
**Severity:** Medium (known limitation)

---

## Appendix A — Test Execution Checklist

| TC-ID | Run Date | Tester | P/F | Severity | Defect Ref |
|-------|----------|--------|-----|----------|------------|
| TC-A01 | | | | | |
| TC-A02 | | | | | |
| TC-A03 | | | | | |
| TC-A04 | | | | | |
| TC-A05 | | | | | |
| TC-A06 | | | | | |
| TC-A07 | | | | | |
| TC-A08 | | | | | |
| TC-A09 | | | | | |
| TC-B01 | | | | | |
| TC-B02 | | | | | |
| TC-B03 | | | | | |
| TC-B04 | | | | | |
| TC-B05 | | | | | |
| TC-C01 | | | | | |
| TC-C02 | | | | | |
| TC-C03 | | | | | |
| TC-C04 | | | | | |
| TC-D01 | | | | | |
| TC-D02 | | | | | |
| TC-D03 | | | | | |
| TC-D04 | | | | | |
| TC-D05 | | | | | |
| TC-D06 | | | | | |
| TC-D07 | | | | | |
| TC-D08 | | | | | |
| TC-D09 | | | | | |
| TC-D10 | | | | | |
| TC-E01 | | | | | |
| TC-E02 | | | | | |
| TC-E03 | | | | | |
| TC-E04 | | | | | |
| TC-E05 | | | | | |
| TC-E06 | | | | | |
| TC-E07 | | | | | |
| TC-E08 | | | | | |
| TC-E09 | | | | | |
| TC-F01 | | | | | |
| TC-F02 | | | | | |
| TC-F03 | | | | | |
| TC-F04 | | | | | |
| TC-F05 | | | | | |
| TC-G01 | | | | | |
| TC-G02 | | | | | |
| TC-G03 | | | | | |
| TC-G04 | | | | | |
| TC-G05 | | | | | |
| TC-G06 | | | | | |
| TC-H01 | | | | | |
| TC-H02 | | | | | |
| TC-H03 | | | | | |
| TC-H04 | | | | | |
| TC-H05 | | | | | |
| TC-H06 | | | | | |
| TC-H07 | | | | | |
| TC-H08 | | | | | |
| TC-H09 | | | | | |
| TC-H10 | | | | | |
| TC-H11 | | | | | |
| TC-H12 | | | | | |
| TC-H13 | | | | | |
| TC-H14 | | | | | |
| TC-H15 | | | | | |
| TC-H16 | | | | | |
| TC-H17 | | | | | |
| TC-I01 | | | | | |
| TC-I02 | | | | | |
| TC-I03 | | | | | |
| TC-I04 | | | | | |
| TC-I05 | | | | | |
| TC-I06 | | | | | |
| TC-I07 | | | | | |
| TC-J01 | | | | | |
| TC-J02 | | | | | |
| TC-J03 | | | | | |
| TC-J04 | | | | | |
| TC-K01 | | | | | |
| TC-K02 | | | | | |
| TC-K03 | | | | | |
| TC-K04 | | | | | |
| TC-K05 | | | | | |
| TC-K06 | | | | | |
| TC-K07 | | | | | |
| TC-K08 | | | | | |
| TC-K09 | | | | | |
| TC-K10 | | | | | |
| TC-L01 | | | | | |
| TC-L02 | | | | | |
| TC-L03 | | | | | |
| TC-L04 | | | | | |
| TC-M01 | | | | | |
| TC-M02 | | | | | |
| TC-M03 | | | | | |
| TC-M04 | | | | | |
| TC-M05 | | | | | |
| TC-M06 | | | | | |
| TC-M07 | | | | | |
| TC-N01 | | | | | |
| TC-N02 | | | | | |
| TC-N03 | | | | | |
| TC-N04 | | | | | |
| TC-N05 | | | | | |
| TC-N06 | | | | | |
| TC-N07 | | | | | |
| TC-N08 | | | | | |
| TC-N09 | | | | | |
| TC-N10 | | | | | |
| TC-O01 | | | | | |
| TC-O02 | | | | | |
| TC-O03 | | | | | |
| TC-O04 | | | | | |
| TC-O05 | | | | | |
| TC-O06 | | | | | |
| TC-O07 | | | | | |
| TC-O08 | | | | | |
| TC-O09 | | | | | |

---

## Appendix B — Severity Matrix

| Severity | Definition | Example |
|----------|-----------|---------|
| **Critical** | Wrong result causes direct financial harm; workflow cannot complete | GM % calculated incorrectly, actuals shown for wrong week |
| **High** | Core feature broken or important business logic wrong | Edit not persisted, WOS wrong color, ST% calculation off |
| **Medium** | Functional but misleading; workaround exists | Var $% shows "—", snapshot GM % is wrong average method |
| **Low** | UX polish, cosmetic, minor deviation | Button disabled state, chart legend label |

---

## Appendix C — Quick Formula Reference

| Metric | Formula |
|--------|---------|
| AUR | `Sales $ / Sales Units` |
| AUC | Fixed base cost (not editable) |
| GM $ | `Sales $ − (AUC × Units)` |
| GM % | `GM $ / Sales $` |
| EOP | `max(0, BOP − Sales U + OO Placed)` |
| WOS | `EOP / Sales U` (99.0 if Sales U = 0) |
| Sell-Through % | `Actual U / (BOP + Total Rcpt)` (past weeks only) |
| OTB Units | `OO Unplaced Total Units` |
| OTB $ | `OTB Units × AUC` |
| Variance U | `Plan U − Actual U` (past weeks only) |
| Variance U% | `(Plan U − Actual U) / Plan U` |
| Variance $ | `Plan $ − Actual $` |
| LY Var U% | `(TY U − LY U) / LY U` |
| LY Var $% | `(TY $ − LY $) / LY $` |
| Recomm Rcpt | `max(0, round(U × 1.05 − BOP × 0.3))` |
