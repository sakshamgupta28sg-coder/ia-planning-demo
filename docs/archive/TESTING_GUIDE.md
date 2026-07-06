# SKU Planning Tool — Complete Feature Testing Guide

**Tool:** ia-planning-demo  
**Stack:** FastAPI (port 8000) + Next.js 14 (port 3000)  
**Data:** 8 SKUs × 3 Channels × 52 Fiscal Weeks (FY2026)  
**Week context:** Wks 1–19 = actualized (locked) | Wk 20 = in-flight (read-only) | Wks 21–52 = planning (editable)

---

## How to Start

```bash
# Terminal 1 — backend
cd ia-planning-demo/backend
uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd ia-planning-demo/frontend
npm run dev
```

Open: http://localhost:3000/wp

---

## Testing Progress

**Last tested:** Feature #13 (Top-Down Distribution)  
**Remaining:** Features 14–34  
**Next up:** #14 — Editable Top-Down Weights (Plan tab)

---

## Feature Index

| # | Feature | Tab/Location | Status |
|---|---|---|---|
| 1 | Weekly Table + Filters | Plan tab | ✅ Done |
| 2 | Single-Cell Edit — Units | Plan tab | ✅ Done |
| 3 | Single-Cell Edit — Sales $ | Plan tab | ✅ Done |
| 4 | Single-Cell Edit — Disc% (Hold Units) | Plan tab | ✅ Done |
| 5 | Single-Cell Edit — Disc% (Hold $) | Plan tab | ✅ Done |
| 6 | Single-Cell Edit — OO Placed | Plan tab | ✅ Done |
| 7 | Cell Undo | Plan tab | ✅ Done |
| 8 | EOP Chain Propagation | Plan tab | ✅ Done |
| 9 | WOS Coloring | Plan tab | ✅ Done |
| 10 | Forward Coverage | Plan tab | ✅ Done |
| 11 | Recommended Receipt Engine | Plan tab | ✅ Done |
| 12 | Accept Recommendations | Plan tab | ✅ Done |
| 13 | Top-Down Distribution (Preview + Confirm) | Plan tab | ✅ Done |
| 14 | Editable Top-Down Weights | Plan tab | ⬜ Next |
| 15 | SKU Settings (Lead Time, Case Pack, Safety, Target WOS) | Portfolio tab | ⬜ Pending |
| 16 | Per-Channel Target WOS | Plan tab | ⬜ Pending |
| 17 | Reset All Overrides | Header | ⬜ Pending |
| 18 | Snapshot Save | Snapshots panel | ⬜ Pending |
| 19 | Snapshot Restore | Snapshots panel | ⬜ Pending |
| 20 | Snapshot Delete | Snapshots panel | ⬜ Pending |
| 21 | Snapshot Rename | Snapshots panel | ⬜ Pending |
| 22 | Snapshot Compare (A vs B) | Snapshots panel | ⬜ Pending |
| 23 | Snapshot Compare (A vs Live) | Snapshots panel | ⬜ Pending |
| 24 | Exception Panel | KPI area | ⬜ Pending |
| 25 | Audit Log + Filters | Change Log panel | ⬜ Pending |
| 26 | OTB Budget + Category Drill-Down | KPI area | ⬜ Pending |
| 27 | Season Progress KPI | Header KPI | ⬜ Pending |
| 28 | Bulk Receipt Shift | Inventory tab | ⬜ Pending |
| 29 | TY/LY/LLY Comparison Tab | TY/LY tab | ⬜ Pending |
| 30 | Actuals Tab (Variance + Sell-Through) | Actuals tab | ⬜ Pending |
| 31 | Inventory Tab | Inventory tab | ⬜ Pending |
| 32 | Portfolio View | Portfolio tab | ⬜ Pending |
| 33 | SKU Create / Delete | Portfolio tab | ⬜ Pending |
| 34 | CSV Export | Plan tab | ⬜ Pending |

---

---

## 1. Weekly Table + Filters

### Business Context
Planners start every morning by selecting a product and channel to review the 52-week plan. The filter controls scope — you can review a single SKU×channel combo or aggregate multiple SKUs across channels.

### How to Test

1. Open http://localhost:3000/wp
2. Click **Product** dropdown → select `Running Shoes` (hierarchy code 10001)
3. Click **Channel** dropdown → select `Ecom`
4. Table loads with 52 rows (one per fiscal week)
5. Toggle **Planning Weeks Only** → rows 1–20 disappear; only weeks 21–52 remain
6. Set **Week From: 202621 / Week To: 202630** → table shows only 10 rows
7. Multi-select: add `Casual Sneakers` to Product → rows now show aggregate of both SKUs

### Technical Detail
- `GET /api/wp/by-week?hierarchy_code=10001&channel=Ecom`
- Backend: `get_agg_rows(hc_filter=10001, ch_filter="Ecom")` — aggregates sub-channels (Ecom_Direct + Ecom_Marketplace) into one row per week
- Locked rows (actualized + is_ongoing) render `🔒` icon via `EditableNumber locked={isLocked(r)}`

### Verification
- Weeks 1–19: all cells show 🔒
- Week 20 (202620): shows 🔒, is_ongoing=true
- Weeks 21–52: cells show ✎ (editable)

---

## 2. Single-Cell Edit — Sales Units

### Business Context
A planner adjusts the unit forecast for a planning week when trend data suggests demand is stronger or weaker than the baseline model. Editing units should cascade to sales $, GM$, and trigger recomm recalc.

### Math
```
AUR = AIR × (1 − Disc%)
Sales $ = AUR × Units
Sales Cost = AUC × Units
GM $ = Sales $ − Sales Cost
GM % = GM $ / Sales $
EOP = max(0, BOP − Units + Receipts)
```

**Example (Running Shoes, Ecom, Wk 21):**
- AIR = $119.99, AUC = $44.00, Disc% ≈ 5%
- AUR = $119.99 × 0.95 = $113.99
- Original units = ~286
- Edit units to 400
- Expected: Sales $ = 400 × $113.99 = $45,596; Cost = 400 × $44 = $17,600; GM$ = $27,996; GM% ≈ 61.4%

### How to Test

1. Select Running Shoes / Ecom
2. Find week 202621 (first planning row)
3. Click the Units cell (blue, shows ✎)
4. Type `400` → press Enter
5. **Verify:** Sales $ updates to ~$45,596; GM$ updates; EOP changes
6. Row highlights **amber** (modified indicator)
7. Check Recomm Receipt changes (EOP changed → recomm recalcs)

### Technical Detail
- `PUT /api/wp/row` body: `{hierarchy_code: 10001, current_week: 202621, channel: "Ecom", field: "written_sales_units", value: 400}`
- Backend `_recalc()` Scenario 1: units edited → keeps Disc%, recalcs AUR, Sales$, Disc$
- `_rebuild_fwd_demand_and_recomm([10001], ["Ecom"])` fires — rebuilds forward demand index for all 52 weeks then recomputes recomm for every planning week of this SKU×channel
- Audit entry written: field=`written_sales_units`, old_value=286, new_value=400

---

## 3. Single-Cell Edit — Sales $

### Business Context
Some planners plan in dollars, not units (e.g., during OTB review). Editing Sales $ back-calculates units assuming the same AUR.

### Math
```
AUR = AIR × (1 − Disc%)          [Disc% held constant]
Units = round(Sales $ / AUR)
Sales Cost = AUC × Units
GM $ = Sales $ − Sales Cost
```

**Example:**
- AUR = $113.99; edit Sales $ to $50,000
- Units = round(50,000 / 113.99) = 439
- Cost = 439 × $44 = $19,316; GM$ = $30,684; GM% = 61.4%

### How to Test

1. Running Shoes / Ecom, week 202621
2. Click Sales $ cell → enter `50000` → Enter
3. **Verify:** Units back-calculates to ~439; GM$ updates; EOP changes
4. Compare: AUR should be unchanged (~$113.99)

### Technical Detail
- `field: "written_sales_dollars"` triggers `_recalc()` Scenario 2
- `units = round(sales_dollars / aur)` where aur = air × (1 - existing_dr_perc)

---

## 4. Single-Cell Edit — Disc% (Hold Units mode)

### Business Context
When a planner increases promotional depth (e.g., from 5% to 20% off), units sold stay the same but revenue and margin drop. This is the "Hold Units" anchor — units fixed, $ recalcs.

### Math
```
Disc% input: 20% (0.20)
AUR = AIR × (1 − 0.20) = $119.99 × 0.80 = $95.99
Sales $ = AUR × Units = $95.99 × 400 = $38,396
GM $ = $38,396 − (400 × $44) = $38,396 − $17,600 = $20,796
GM% = $20,796 / $38,396 = 54.2%
```

### How to Test

1. First ensure mode toggle is set to **Hold Units** (top of table, default)
2. Running Shoes / Ecom, week 202621 (with 400 units from test #2)
3. Click Disc% cell → enter `20` → Enter (tool inputs as 0–100, stores as 0–1)
4. **Verify:** AUR drops from ~$114 to ~$96; Sales $ drops; GM% drops ~7pp
5. Units should remain 400

### Technical Detail
- `field: "written_dr_perc"`, `mode: "hold_units"` triggers `_recalc()` Scenario 3
- value sent = 0.20 (frontend divides input by 100)
- Clamp: `min(max(value, 0.0), 1.0)` — prevents >100% or negative discount

---

## 5. Single-Cell Edit — Disc% (Hold $ mode)

### Business Context
A planner wants revenue to stay flat but increases discount depth. Result: more units sold at lower price, same dollar revenue. Used when there's a hard OTB dollar constraint.

### Math
```
Sales $ held at $38,396
New Disc% = 30% → AUR = $119.99 × 0.70 = $83.99
Units = round($38,396 / $83.99) = 457
Cost = 457 × $44 = $20,108
GM$ = $38,396 − $20,108 = $18,288; GM% = 47.6%
```

### How to Test

1. Switch mode toggle to **Hold $**
2. Running Shoes / Ecom, week 202621
3. Click Disc% → enter `30` → Enter
4. **Verify:** Sales $ unchanged (~$38,396); Units increases (~457); GM% drops further
5. AUR should reflect new 30% disc

### Technical Detail
- `mode: "hold_dollars"` triggers Scenario 4 in `_recalc()`
- `units = round(sales_dollars / aur)` where sales_dollars comes from existing override

---

## 6. Single-Cell Edit — OO Placed

### Business Context
OO Placed = Open Orders already placed with the supplier (in-transit or committed). Editing this directly models a purchase order change — cancelling an order or adding a new one.

### Math
```
EOP = max(0, BOP − Sales_Units + OO_Placed)
      [total_receipt_units = OO_Placed after edit]

Forward Coverage = (EOP + pipeline_next_LT_weeks) / 8wk_avg_demand
```

**Example (Running Shoes, LT = 14 weeks):**
- BOP = 1,500, Sales = 400, original OO = 300
- Edit OO to 600 → EOP = max(0, 1500 − 400 + 600) = 1,700
- Pipeline for next 14 weeks also updates → FC recalcs for earlier weeks

### How to Test

1. Running Shoes / Ecom, week 202621
2. Click OO Placed cell → enter `600` → Enter
3. **Verify:** EOP increases; Forward Coverage (FC) column updates for weeks 21–34 (14-week pipeline window)
4. Check: Recomm Receipt for week 21 should DROP because pipeline is now larger
5. Check Inventory tab to see the change reflected

### Technical Detail
- `field: "on_order_placed_total_unit"` → `_recalc()` sets `total_receipt_units = OO_Placed`
- `_rebuild_pipeline_and_recomm([10001], ["Ecom"])` fires — lighter rebuild than demand rebuild
- Pipeline index: sum of OO Placed for next `lead_time_weeks` rows

---

## 7. Cell Undo (Single-Cell Revert)

### Business Context
Planners make exploratory edits. Cell undo reverts exactly one cell without resetting all other edits — scoped and non-destructive.

### How to Test

1. Make any edit (e.g., Units = 400 for week 202621)
2. Hover over the amber cell → small `↩` undo icon appears
3. Click it
4. **Verify:** Cell reverts to original value; row color returns to default blue
5. Check: the **other** edits you made (if any) are untouched

### Mathematical Verification
- After undo, the cell value should match `GET /api/wp/by-week` without any override applied
- If a units edit was undone, Recomm Receipt should revert too (demand indexes rebuilt)

### Technical Detail
- `DELETE /api/wp/overrides/{hc}/{week}/{channel}`
- Backend `clear_single_override()`: checks `_last_edited` field, routes to correct rebuild (`_rebuild_fwd_demand_and_recomm` for sales edits, `_rebuild_pipeline_and_recomm` for OO edits)

---

## 8. EOP Chain Propagation

### Business Context
Every week's ending inventory becomes next week's beginning inventory. This chain means one edit in week 21 ripples through weeks 22–52 automatically. Planners must see this propagation or they can't trust the plan.

### Math (the chain):
```
EOP[wk21] = max(0, BOP[wk21] − Sales[wk21] + Receipts[wk21])
BOP[wk22] = EOP[wk21]
EOP[wk22] = max(0, BOP[wk22] − Sales[wk22] + Receipts[wk22])
... and so on for all 32 planning weeks
```

### How to Test

1. Select Running Shoes / Ecom, planning weeks view
2. Note BOP and EOP for weeks 21, 22, 23
3. Edit **Receipts (OO Placed) week 21** → add 500 units
4. **Verify:** EOP[21] increases by 500; BOP[22] = new EOP[21]; EOP[22] changes accordingly; this propagates all the way to week 52
5. WOS column for all downstream weeks should update

### Technical Detail
- `get_agg_rows()` does a stream-walk: sorts by `current_week`, carries `prev_eop` forward
- Line: `b["bop_units"] = prev_eop` then `b["eop_units"] = max(0, bop - units + receipts)`
- This is re-executed on every API call — no "stale" BOP values possible

---

## 9. WOS (Weeks of Supply) Coloring

### Business Context
WOS tells a planner how many weeks of demand the current ending inventory covers. Too low = stockout risk. Too high = excess capital tied up. Color coding provides instant visual health check.

### Math
```
WOS = EOP / (8-week forward avg demand)
8wk_avg = sum(planned_sales[wk+1 to wk+8]) / 8

Color thresholds (relative to lead_time_weeks):
  🔴 Critical:  WOS < lead_time × 0.5
  🟡 Low:       WOS < lead_time
  🟢 Healthy:   lead_time ≤ WOS ≤ lead_time × 3
  🟡 High:      WOS > lead_time × 3 (but not excess)
  🔴 Excess:    WOS > lead_time × 3 (from exception panel)
```

**Running Shoes (LT=14):**
- Critical: WOS < 7 weeks
- Low: 7 ≤ WOS < 14
- Healthy: 14 ≤ WOS ≤ 42
- High/Excess: WOS > 42

### How to Test

1. Select Running Shoes / Ecom
2. Note WOS column — verify colors match thresholds above
3. Edit OO Placed of week 21 to `0` → EOP drops → WOS drops → color should turn red/amber
4. Edit OO Placed to `5000` → EOP spikes → WOS jumps to 40+ → color should turn amber (excess)
5. Check: Sandals (LT=10) has different thresholds than Ankle Boots (LT=16)

### Technical Detail
- `WOS_WINDOW = 8` is fixed — always 8-week denominator regardless of LT
- `_WOS_DEMAND_INDEX[(hc, ch, wk)]` = precomputed sum of demand for wk+1 to wk+8
- WOS for actualized weeks = null (shown as "—")
- WOS for ongoing week (wk 20) = trailing 4-week actual avg

---

## 10. Forward Coverage (FC)

### Business Context
WOS uses only EOP. Forward Coverage adds in-transit pipeline — orders already placed that haven't arrived yet. This is the more accurate metric for reorder decisions: "if I have 500 units on hand AND 300 more arriving in the next 12 weeks, am I covered?"

### Math
```
FC = (EOP + pipeline) / 8wk_avg_demand

pipeline = sum(OO_Placed for next lead_time_weeks)
         = sum(receipts for wk+1, wk+2, ... wk+LT)
```

**Example (Running Shoes, LT=14, 8wk_avg=350):**
- EOP = 400
- Pipeline (wks 22–35) = 2,800 total OO placed
- FC = (400 + 2800) / 350 = 9.1 weeks
- WOS (EOP only) = 400 / 350 = 1.1 weeks — dramatically different!

### How to Test

1. Running Shoes / Ecom, week 202621
2. Note both WOS and FC columns
3. Note FC should be > WOS (pipeline adds coverage)
4. Set OO Placed for weeks 22–35 to 0 → FC should converge to WOS
5. Set OO Placed for weeks 22–35 to very large values → FC spikes while WOS stays low

### Technical Detail
- FC computed in `get_agg_rows()` stream-walk:
  `pipeline = sum(stream[i+1 : i+1+lead_time].total_receipt_units)`
- `fwd_coverage_wks = (eop + pipeline) / wos_avg`
- FC is null for actualized and ongoing weeks (no forward pipeline meaning)

---

## 11. Recommended Receipt Engine

### Business Context
The system's core intelligence: for each planning week, it calculates exactly how many units you need to order NOW (given lead time) to avoid running out AND maintain your target stock buffer. This replaces hours of manual OTB calculation.

### Math
```
recomm = max(0, fwd_demand + target_EOP − EOP − pipeline)
         rounded UP to nearest case_pack

where:
  fwd_demand = sum(sales for next lead_time + safety_weeks)
  target_EOP = (8wk_avg_demand) × target_wos
  pipeline   = sum(OO_Placed for next lead_time_weeks)

Example (Running Shoes, Ecom, Wk 21):
  lead_time = 14, safety_weeks = 2
  fwd_demand = sum(wks 22–36 sales) ≈ 5,200
  8wk_avg = 350; target_wos = 6
  target_EOP = 350 × 6 = 2,100
  EOP[21] = 1,500; pipeline[21] = 2,800
  raw = max(0, 5200 + 2100 − 1500 − 2800) = 3,000
  case_pack = 6 → recomm = ceil(3000/6) × 6 = 3,000
```

### How to Test

**Test A — Reduce EOP, watch recomm increase:**
1. Running Shoes / Ecom, week 202630
2. Edit OO Placed to 0 → EOP drops → recomm should INCREASE (needs more orders)

**Test B — Increase OO Placed, watch recomm decrease:**
1. Week 202630: set OO Placed to 2,000
2. Recomm should drop or go to 0 (already have enough in pipeline)

**Test C — Case pack rounding:**
1. Running Shoes has case_pack = 6
2. Find any week where recomm is not a multiple of 6 → there shouldn't be any
3. Verify: all recomm values are divisible by 6

**Test D — No recomm for actualized weeks:**
1. Any week 1–19 → Recomm column shows 0 or "—"

### Technical Detail
- `_compute_recomm_receipt()` in `dummy_data.py:131`
- `_FORWARD_DEMAND_INDEX[(hc, ch, wk)]` = sum of fwd_demand
- `_PIPELINE_INDEX[(hc, ch, wk)]` = sum of next LT weeks' OO Placed
- Recomm re-fires on every `_recalc()` call (edit cascade)

---

## 12. Accept Recommendations

### Business Context
After reviewing the recomm column, a planner can accept all recommendations with one click — sets OO Placed = Recomm for every planning week. Replaces cell-by-cell data entry.

### Math
After acceptance:
```
OO_Placed[wk] = Recomm_Receipt[wk] for all planning weeks
→ pipeline recalculates
→ recomm recalculates (now should drop to 0 or near 0 since pipeline ≈ demand)
```

### How to Test

1. Running Shoes / Ecom
2. Note Recomm and OO Placed columns — they should differ
3. Click **Accept Recomm** button (in toolbar area)
4. **Verify:** OO Placed for all planning weeks = previous Recomm values
5. **Verify:** After accepting, Recomm values drop to near 0 (or small residuals from rounding)
6. Check audit log: should show ~32 entries for `on_order_placed_total_unit`

### Technical Detail
- `POST /api/wp/accept-recomm` body: `{hierarchy_codes: [10001], channels: ["Ecom"]}`
- Backend: `accept_recomm_receipts()` — batch upsert all 32 planning weeks
- Single `_rebuild_pipeline_and_recomm()` call after batch write
- Why recomm ≈ 0 after: pipeline now equals what was needed, so `fwd_demand + target_EOP - EOP - pipeline ≈ 0`

---

## 13. Top-Down Distribution

### Business Context
A merchandising director sets a total sales target for the season ("we need $2M in Running Shoes") and the system distributes it across all 32 planning weeks and all channels automatically, weighted by last year's seasonal curve.

### Math
```
Weight[row] = LY_value[row]         (last year actuals)
            OR LLY_value[row]       (fallback if no LY)
            OR current_plan[row]    (fallback if no history)

Proposed[row] = target × (weight[row] / sum_of_all_weights)
```

**Example:**
- Target = 10,000 units total
- If LY week 26 had 800 units (peak), weight_26 = 800 / 25,000 = 3.2%
- Proposed week 26 = 10,000 × 3.2% = 320 units

### How to Test

**Step 1 — Preview:**
1. Select Running Shoes + Ecom
2. Switch to **Units** in the field selector
3. Enter target `10000` in the top-down panel
4. Click **Preview**
5. Preview panel shows each week with: current | proposed | weight%
6. Total "proposed" column should sum to exactly 10,000

**Step 2 — Verify LY weights:**
1. In preview, look at weeks near 25–26 (Running Shoes peak)
2. They should have higher weight% and therefore higher proposed values

**Step 3 — Confirm:**
1. Click **Confirm Distribution**
2. **Verify:** Weekly sales units now reflect the distributed values
3. Audit log: ~32 entries for `written_sales_units`

**Step 4 — Math check:**
1. Sum the Units column for all planning weeks
2. Should equal exactly 10,000 (rounding may cause ±1)

### Technical Detail
- `POST /api/wp/top-down/preview` for dry-run; `POST /api/wp/top-down` to commit
- `apply_top_down()` in backend; `preview_top_down()` for dry-run
- After confirm: `_rebuild_fwd_demand_and_recomm()` fires — all recomm values recalc

---

## 14. Editable Top-Down Weights

### Business Context
Sometimes LY weights are wrong — a product was out-of-stock in a key week last year, depressing the seasonal curve artificially. Planners need to override individual week targets before confirming.

### How to Test

1. Run Preview (same as test #13 steps 1–3)
2. In preview panel, each week shows an editable number input
3. Find week 202626 (Running Shoes peak) — it should show a high proposed value
4. Click the value for week 202626 → type `500` → Enter
5. **Verify:** Orange override indicator appears; badge shows "1 week overridden"
6. Other weeks auto-adjust (or not — explicit override bypasses weight calc for that week)
7. Click **✕** next to overridden week to revert it
8. Click **Confirm** → only the overridden weeks use explicit values; rest use LY weights

### Technical Detail
- Frontend: `weekValueOverrides` state, key = `"wk__{week}"`
- When confirming: overrides built as `week_values: [{hierarchy_code, channel, current_week, value}]`
- Backend `apply_top_down(week_values=...)`: if week_values provided, applies them directly, bypasses LY weight for those specific cells
- Non-overridden weeks still use LY weight distribution

---

## 15. SKU Settings (Lead Time, Case Pack, Safety, Target WOS)

### Business Context
These are the "levers" of the inventory model. Change them and the entire planning recommendation changes:
- **Lead time:** How long from PO to receipt arrival (affects how far ahead you must plan)
- **Case pack:** Minimum order quantity (affects recomm rounding)
- **Safety weeks:** Buffer added to look-ahead (extra conservative buffer)
- **Target WOS:** How many weeks of stock to maintain at EOP (determines buffer)

### Math Impact of Target WOS change:
```
target_EOP = 8wk_avg × target_wos
recomm = fwd_demand + target_EOP - EOP - pipeline

If target_wos 6 → 8:
  target_EOP increases by (8wk_avg × 2)
  recomm increases by same amount
  AND Pass 1b recalibrates all planning receipts to hit new target WOS
```

### How to Test

**Test A — Change Case Pack:**
1. Go to **Portfolio** tab
2. Find Running Shoes row → Case Pack = 6
3. Edit to `12`
4. Switch to Plan tab, Running Shoes / Ecom
5. **Verify:** All Recomm values are now multiples of 12 (not 6)

**Test B — Change Lead Time:**
1. Portfolio tab → Running Shoes → Lead Time = 14
2. Edit to `8`
3. Plan tab, note WOS color thresholds shift (new critical: WOS < 4, not < 7)
4. Recomm forward demand window shrinks: fwd_demand now = 8+2=10 weeks ahead instead of 14+2=16
5. FC column reflects 8-week pipeline instead of 14-week

**Test C — Change Target WOS:**
1. Portfolio → Running Shoes → Target WOS = 6
2. Edit to `10`
3. **Verify:** Planning week receipts increase (Pass 1b recalibrates)
4. EOP values should be higher (targeting 10 weeks of stock instead of 6)
5. Recomm should be higher (larger target buffer)

**Test D — Verify persistence:**
1. Change Case Pack to 12
2. Restart backend (`Ctrl+C` then `uvicorn main:app --reload`)
3. Reopen frontend — Case Pack should still be 12 (persisted in SQLite `sku_settings`)

### Technical Detail
- `PUT /api/wp/sku-settings/{hc}` body: `{field: "case_pack", value: 12}`
- Backend `update_sku_setting()`:
  1. Merges into `_SKU_SETTINGS_OVERRIDES[hc]`
  2. Persists via `db_upsert_sku_setting()`
  3. Calls `recompute_recomm_for_sku(hc)`
  4. If `target_wos` changed: also calls `_recalibrate_pass1b(hc)`
- `_recalibrate_pass1b()` re-runs the receipt calibration using updated target_wos, writes results as overrides

---

## 16. Per-Channel Target WOS

### Business Context
Ecom and Store channels often have different stock requirements. Ecom might need 8 weeks of supply (fast shipping from DC), while Store only needs 4 weeks (floor display). This allows channel-granular inventory targets.

### Math
```
WOS lookup precedence:
1. Channel-level override: _CHANNEL_TARGET_WOS["{hc}_{channel}"]
2. SKU-level override: _SKU_SETTINGS_OVERRIDES[hc]["target_wos"]
3. Base: HIERARCHY_METRICS[hc]["target_wos"]
```

### How to Test

1. Inventory tab → Target WOS panel
2. Find Running Shoes / Store row (default = 6)
3. Edit to `4`
4. Switch to Plan tab → Running Shoes / Store
5. **Verify:** Receipts for Store channel drop (lower WOS target = less buffer ordered)
6. Compare to Ecom channel (still target_wos=6) — Ecom receipts should be higher
7. Check Recomm: Store recomm should be lower than Ecom recomm for same week

### Technical Detail
- `PUT /api/wp/target-wos/{hc}/{channel}` body: `{value: 4}`
- Backend `update_channel_target_wos()`: persists to `channel_settings` table, calls `_recalibrate_pass1b(hc, [channel])`
- Only the specified channel's receipts recalibrate — other channels unaffected

---

## 17. Reset All Overrides

### Business Context
Destructive operation: wipes every edit made this session, returning to the baseline generated plan. Used when a planning session went off-track and you want a clean start.

### How to Test

1. Make several edits across multiple SKUs and weeks
2. Click the **Reset** button (header)
3. **Confirm dialog** appears — confirm it
4. **Verify:** All edited cells return to default values (no amber highlighting)
5. **Verify:** Recomm values return to baseline
6. Check that snapshots are **not** affected (snapshots survive reset)

### Caveat
**Snapshot data is not deleted.** This only clears the `overrides` table. Snapshots live in `snapshots` table.

### Technical Detail
- `DELETE /api/wp/overrides`
- Backend `reset_overrides()`: calls `db_clear_overrides()` then `_reset_fwd_demand_and_recomm()`
- `_reset_fwd_demand_and_recomm()` rebuilds demand indexes from original WP_DATA (not overrides) → recomm snaps back to baseline

---

## 18. Snapshot Save

### Business Context
A snapshot freezes the current plan state for future comparison. Planners save before major re-plans: "save Baseline", make aggressive changes, then compare vs Baseline to see the impact.

### What's saved:
- All override records (every cell that was edited)
- Summary metrics: total sales units, total sales $, total GM$, avg GM%
- Timestamp + name

### How to Test

1. Make some edits (e.g., increase sales units for week 26 by 20%)
2. Click **Snapshots** panel → expand it
3. Enter name `"Aggressive Plan"` → click **Save**
4. **Verify:** New card appears with: name, timestamp, override count, summary metrics
5. Verify: summary sales $ on the card matches the KPI header total

### Technical Detail
- `POST /api/wp/snapshots` body: `{name: "Aggressive Plan"}`
- Backend `save_snapshot()`: calls `get_agg_rows()` to compute summary, then `db_insert_snapshot()`
- GM% is dollar-weighted: `avg_gm_perc = total_gm / total_sales` (not simple average)
- `overrides_count` = number of individual overridden cells

---

## 19. Snapshot Restore

### Business Context
Returns the entire plan to a previously saved state. Critical safety net: if you over-edited and want to go back to your "Baseline" snapshot, restore it.

### How to Test

1. Save snapshot A ("Baseline")
2. Make aggressive edits
3. Save snapshot B ("Aggressive")
4. Click **Restore** on Baseline → Confirm dialog → Restore
5. **Verify:** Plan reverts to Baseline state (cells show Baseline values)
6. **Verify:** Recomm values recalculate from restored overrides
7. Snapshot B still exists (restore doesn't delete other snapshots)

### Mathematical Verification
After restoring Baseline:
- Sales units should match Baseline snapshot card's summary
- GM$ should match Baseline card's GM$

### Technical Detail
- `PUT /api/wp/snapshots/{id}/restore`
- Backend `restore_snapshot()`: `db_replace_overrides(snap["overrides"])` — atomic swap
- Calls `_rebuild_fwd_demand_and_recomm()` for all SKUs after restore (without this, demand indexes stay stale)

---

## 20. Snapshot Delete

### Business Context
Clean up stale snapshots. Destructive — snapshot is permanently gone.

### How to Test

1. Have 2+ snapshots
2. Click 🗑 on one → **Confirm dialog** appears
3. Confirm deletion
4. Card disappears
5. Try to compare using a deleted snapshot ID → should get error

### Technical Detail
- `DELETE /api/wp/snapshots/{id}`
- Confirm dialog added specifically to prevent accidental deletion — no undo

---

## 21. Snapshot Rename

### Business Context
After initial save, planners often want to rename snapshots to reflect what changed: "Week 21 replan" → "Week 21 replan — aggressive summer".

### How to Test

1. Click on a snapshot **name** in the card
2. Inline edit field appears (replaces the name text)
3. Type new name → press **Enter** or click away
4. **Verify:** Name updates immediately in the card
5. Press **Escape** to cancel → original name preserved

### Technical Detail
- `PATCH /api/wp/snapshots/{id}` body: `{name: "new name"}`
- Frontend: `renamingSnapId` state controls inline edit visibility
- `onBlur` commits; `Escape` cancels without API call

---

## 22. Snapshot Compare (A vs B)

### Business Context
The heart of scenario planning: compare two saved scenarios side-by-side. "If I go aggressive on summer, how much more GM do I make vs the baseline plan?"

### What's compared (per week, per SKU, per channel):
- Sales Units: A | B | Δ
- Sales $: A | B | Δ
- GM$: A | B | Δ
- EOP: A | B | Δ
- Receipts: A | B | Δ

### How to Test

1. Save "Baseline" snapshot (before edits)
2. Make significant edits (increase units 30%, change receipts)
3. Save "Aggressive" snapshot
4. Click checkbox on Baseline → checkbox on Aggressive → click **A vs B →**
5. **Verify:** Comparison panel shows row-by-row delta
6. Rows with positive delta (Aggressive > Baseline) show green Δ
7. Rows where Aggressive has lower EOP (more aggressively sold) show negative red Δ
8. Summary header shows total Δ Sales$, Δ GM$

### Mathematical Verification
- Sum all `delta_sales_units` rows = difference in snapshot summary totals
- Sum all `delta_gm_dollar` rows = difference in snapshot GM totals

### Technical Detail
- `GET /api/wp/snapshots/compare?a={id_a}&b={id_b}`
- Backend: runs `get_agg_rows(_overrides_override=snap_a["overrides"])` and same for B
- BOP→EOP chain computed fresh for each snapshot — accurate inventory for both states

---

## 23. Snapshot Compare (A vs Live)

### Business Context
You don't always need to save a second snapshot to compare. "A vs Live" compares any saved snapshot against whatever is currently on your screen — useful for "how far have I moved from the Baseline today?"

### How to Test

1. Have "Baseline" snapshot saved
2. Make new edits (don't save)
3. Check Baseline checkbox → click **A vs Live →**
4. **Verify:** Shows Baseline vs your current un-saved edits
5. Make more edits → click the same button again → delta updates

### Technical Detail
- Frontend sends `b=0` to API: `GET /api/wp/snapshots/compare?a={id}&b=0`
- Backend: `snap_b_id == 0 → rows_b_list = get_agg_rows()` (current live overrides)
- No snapshot save required for the "B" side

---

## 24. Exception Panel

### Business Context
Instead of scanning 52 weeks × 8 SKUs × 3 channels = 1,248 rows for problems, the exception panel surfaces the worst issues in a single ranked list. One glance tells you which SKUs need immediate action.

### Exception Types

| Type | Condition | What it means |
|---|---|---|
| 🔴 Critical | FC < lead_time × 0.5 | Severe stockout risk even with in-transit pipeline |
| 🟡 Low | FC < lead_time AND order_gap > 0 | Below safety threshold AND hasn't been ordered yet |
| 🔵 Excess | FC > lead_time × 3 | Over-stocked, capital tied up |

**order_gap = max(0, Recomm − OO_Placed)** — "Low" only flags if there's something actionable to order.

**Example (Running Shoes, LT=14):**
- Critical: FC < 7 weeks
- Low: 7 ≤ FC < 14 AND recomm > oo_placed
- Excess: FC > 42 weeks

### How to Test

1. View the **Exceptions** panel (opens by default or via button)
2. Note rows: each is one SKU×channel, not one week
3. **Affected Weeks** column: how many weeks in the planning horizon have this issue
4. **Test Critical:** Set OO Placed to 0 for all weeks for one SKU → that SKU×channel should appear as Critical
5. **Test Excess:** Set OO Placed to 50,000 for every week → Forward Coverage spikes → Excess exception
6. **Test Low suppression:** Set OO Placed = Recomm exactly → Low exception disappears (order_gap = 0)

### Technical Detail
- `GET /api/wp/exceptions`
- Backend `get_exceptions_panel()`: groups week-level rows by SKU×channel, keeps worst week, counts affected_weeks
- Severity order: critical(0) < low(1) < excess(2) — lower = worse
- "Low" requires `order_gap > 0` to filter noise: if OO Placed already covers recomm, there's nothing to do

---

## 25. Audit Log + Filters

### Business Context
Enterprise-grade change tracking: every edit is logged with who changed what, from what value, to what value, and when. Essential for compliance and for understanding how a plan evolved.

### How to Test

**Basic log:**
1. Make 5 edits (different SKUs, different fields)
2. Open **Change Log** panel
3. **Verify:** Each edit appears with: timestamp | SKU | channel | week | field | old_value | new_value

**Filter by Product:**
4. Select a product in the "Product" filter dropdown
5. **Verify:** Only entries for that SKU appear

**Filter by Field:**
6. Select "OO Placed" in the Field filter
7. **Verify:** Only `on_order_placed_total_unit` edits appear

**Filter by both:**
8. Set Product=Running Shoes AND Field=Sales Units
9. **Verify:** Only Running Shoes sales unit edits appear

**Clear filter:**
10. Click ✕ Clear → all 100 most recent entries return

### Technical Detail
- `GET /api/wp/audit?limit=200&hierarchy_code=10001&field=written_sales_units`
- Backend `db_get_audit_log()`: builds WHERE clause dynamically based on optional params
- `FIELD_LABELS` constant maps DB field names to human-readable labels: `written_sales_units → "Sales Units"`
- Each `apply_edit()` call writes one audit row via `db_log_audit()`

---

## 26. OTB Budget + Category Drill-Down

### Business Context
Open-to-Buy (OTB) budget is the dollar limit the buying team has to spend on inventory purchases. The tool tracks how much of the season's planned cost (AUC × units) consumes that budget, and breaks it down by category (Footwear vs Apparel).

### Math
```
planned_cost = sum(AUC × planned_units) for all planning weeks
remaining = budget − planned_cost
pct_consumed = planned_cost / budget × 100%

Category drill-down:
  Footwear cost = sum(AUC × units) for l1_name = "Footwear"
  Apparel cost  = sum(AUC × units) for l1_name = "Apparel"
```

### How to Test

**Basic budget:**
1. Find the **OTB Budget** KPI card in the header
2. Note: Budget | Planned Cost | Remaining | % Consumed
3. Planned Cost should be < Budget initially (baseline is calibrated to be slightly under)

**Edit budget:**
4. Click the budget input → change from $2,000,000 to $1,500,000
5. **Verify:** Remaining becomes negative (red); % consumed > 100%

**Category drill-down:**
6. In OTB card, expand category breakdown
7. **Verify:** Footwear bar and Apparel bar shown separately
8. Footwear bar shows Footwear planned cost / total budget
9. If Footwear cost > 60% of budget, bar turns red

**Edit units → see budget change:**
10. Increase units for several weeks of Denim Jeans (Apparel)
11. **Verify:** Apparel bar fills further; total pct_consumed increases

### Technical Detail
- `GET /api/wp/budget` returns `{budget, planned_cost, remaining, pct_consumed, category_breakdown}`
- `category_breakdown = {l1_name: total_cost}` where cost = sum(written_sales_cost) per category
- `PUT /api/wp/budget` body: `{budget: 1500000}`

---

## 27. Season Progress KPI

### Business Context
Real-time view of how much of the season has actualized vs plan. The "On Pace" run-rate projects whether the full-year plan will be hit based on current actualization speed.

### Math
```
Actualized through wk 19 (weeks 1–19 have actuals):
  actualized_units = sum(actual_sales_units, wks 1–19)
  pct_units = actualized_units / plan_units

Run-rate projection:
  run_rate = (actualized_units / 19 weeks) × 52 weeks
  → "On pace → $X (Y% of plan)"
```

### How to Test

1. Look at **Season Pace** KPI card in the 6-card header
2. Note: "Wk 20 in-flight · Planning Wk 21–52" badge
3. **Verify:** "Actualized" % ≈ 19/52 ≈ 36.5% of units (weeks 1–19 of 52)
4. The projection should say something like "On pace → $3.2M (98% of plan)"

**Simulate over/underperformance:**
5. Go to Actuals tab → note actuals vs plan
6. Actuals are generated with ±30% noise — some SKUs will show variance

### Technical Detail
- `GET /api/wp/season-progress`
- Backend `get_season_progress()`: sums actual_sales for wks 1–19, plan for all 52 weeks
- Run-rate = (actualized/weeks_gone) × 52

---

## 28. Bulk Receipt Shift

### Business Context
When a supplier notifies you of a delivery delay ("all orders pushed 2 weeks"), you shouldn't have to edit 32 weeks × 8 SKUs × 3 channels = 768 cells. Bulk shift moves all OO Placed for selected SKUs simultaneously.

### Math
```
shift = +2 (push later)
OO_Placed[wk21] moves to OO_Placed[wk23]
OO_Placed[wk22] moves to OO_Placed[wk24]
...
OO_Placed[wk51] moves to OO_Placed[wk53] → DROPPED (out of range)
OO_Placed[wk52] moves to OO_Placed[wk54] → DROPPED
```

### How to Test

**Setup:** Select Running Shoes + Ecom. Go to **Inventory** tab.

**Test forward shift (+2):**
1. Note OO Placed values for wks 21, 22, 23
2. Set shift amount to `2`
3. Click **Later →**
4. **Verify:** Old wk21 value now appears in wk23; wk22 → wk24; etc.
5. Wks 21, 22 now show 0 (source weeks cleared)
6. Toast shows: "Shifted N receipts +2 wks · M dropped (out of range)"
7. **Verify:** FC for early planning weeks drops (pipeline shifted out)

**Test backward shift (−1):**
8. Click **← Earlier**
9. OO Placed moves one week earlier
10. If any receipts would land in wk 20 or earlier → dropped

**Test multi-SKU shift:**
11. Select Running Shoes + Sandals, both Ecom + Store
12. Shift +3 → all selected SKU×channel combos shift simultaneously

### Technical Detail
- `POST /api/wp/bulk-shift` body: `{hierarchy_codes: [10001], channels: ["Ecom"], shift_weeks: 2}`
- Backend `shift_receipts()`:
  1. Reads current OO Placed for all planning weeks (respects existing overrides)
  2. Computes destination week index: `dst_idx = src_idx + shift_weeks`
  3. Drops any that land outside `planning_wks` set
  4. Writes zero to all source weeks, new values to destination weeks
  5. Single `_rebuild_pipeline_and_recomm()` call
- Returns `{shifted: N, dropped: M}`

---

## 29. TY / LY / LLY Comparison Tab

### Business Context
Year-over-year tracking: compare current year plan to last year actuals (LY) and two-years-ago actuals (LLY). Essential for understanding if the current plan is realistic relative to history.

### Columns
- TY Units / TY $ (current plan)
- LY Units / LY $ (last year actual)
- LLY Units / LLY $ (two years ago)
- Δ vs LY (units and %)
- Δ vs LLY (units and %)

### How to Test

1. Select any SKU + channel
2. Click **TY/LY** tab
3. **Verify:** LY and LLY rows show different values per week (±15% noise in demo data)
4. Δ vs LY should be positive where TY plan > LY (growth) and negative where below
5. Filter to planning weeks → delta shows where you're planning above/below history

**Math check:**
- `Δ_units = TY_units − LY_units`
- `Δ%_units = Δ_units / LY_units × 100%`
- Example: TY=400, LY=350 → Δ=+50, Δ%=+14.3%

### Technical Detail
- `GET /api/ty-ly/by-week?hierarchy_code=10001&channel=Ecom`
- Data from `TY_LY_DATA` (separate from WP_DATA)
- TY values in this tab come from WP_DATA (live plan) joined to TY_LY table

---

## 30. Actuals Tab (Variance + Sell-Through)

### Business Context
For actualized weeks (1–19), compare what was planned vs what actually happened. Sell-through shows what % of available inventory was sold.

### Columns
- Written Sales (plan) vs Actual Sales
- Variance Units = Plan − Actual
- Variance $ = Plan$ − Actual$
- Variance % = Variance / Plan × 100%
- Sell-Through % = Actual Units / (BOP + Receipts) × 100%

### How to Test

1. Select any SKU + channel
2. Click **Actuals** tab
3. **Verify:** Only weeks 1–19 show data; weeks 21+ show blank
4. Find a row where Actual > Plan → Variance should be negative (outperformance)
5. Find a row where Actual < Plan → Variance should be positive (underperformance)

**Sell-Through math:**
- BOP = 1,200; Receipts = 300; Available = 1,500
- Actual sales = 900
- Sell-Through = 900 / 1,500 = 60%

**Verify:**
6. Sum of Variance % across all 19 weeks should show average planning accuracy
7. High sell-through (>80%) = healthy; low (<40%) = slow-mover

### Technical Detail
- Variance fields computed in `_recalc()` and `get_agg_rows()`
- `sell_through_perc = actual_sales / (bop + receipts)` — only non-zero for actualized weeks
- Actuals generated with `random.uniform(0.78, 1.08)` noise vs plan

---

## 31. Inventory Tab

### Business Context
Pure inventory view — no sales $, no GM. Just units flow: BOP → Receipts → Sales → EOP, with WOS and FC for health monitoring. Used during receipt review sessions.

### Columns
- Week | BOP | OO Placed | Receipts | Sales | EOP | WOS | FC | Recomm

### How to Test

1. Select Running Shoes + Ecom
2. Click **Inventory** tab
3. Verify BOP chain: BOP[22] = EOP[21] — check a few consecutive rows
4. Edit OO Placed inline → watch EOP propagate
5. Compare WOS vs FC columns — FC should be ≥ WOS (pipeline adds coverage)
6. Find a week where FC is green but WOS is red — example of why FC matters

**WOS vs FC divergence test:**
7. Set OO Placed to 1,000 for weeks 22–35
8. WOS for week 21 might still be red (low EOP)
9. But FC for week 21 should be green (1,000 × 14 weeks of pipeline covers demand)

### Target WOS table:
10. Also shows per-channel target WOS editable here
11. Edit Running Shoes / Store target WOS → verify receipts recalibrate

---

## 32. Portfolio View

### Business Context
Cross-SKU overview: how is each product performing vs the portfolio? Used by a buying director to spot which SKUs are driving growth, which are underperforming, and which have exception flags.

### Columns
- Category | SKU | Sales Units | Sales $ | GM$ | GM% | Exception Status | Min Coverage

### How to Test

1. Click **Portfolio** tab
2. **Verify:** 8 rows (one per SKU), grouped by Footwear / Apparel
3. Amber row = SKU has exception (low/critical coverage somewhere in planning horizon)
4. Click any row → jumps to Plan tab with that SKU selected
5. Sort by GM% → Graphic Tees (cheapest AUC) should have high GM%; Ankle Boots lower (higher AUC)

**SKU Settings in Portfolio:**
6. Inline-editable: Case Pack, Lead Time, Safety Weeks, Target WOS
7. Edit any → see changes propagate to Plan tab recomm

### Technical Detail
- `GET /api/wp/portfolio` aggregates all weeks for each SKU (sum sales, avg GM%)
- `exception_status` = worst exception across all channels for that SKU
- `min_coverage_wks` = minimum FC across all channels

---

## 33. SKU Create / Delete

### Business Context
Add new products mid-season (e.g., a new colorway dropped, or a new wholesale account added). Delete SKUs that have been discontinued.

### How to Test

**Create:**
1. Portfolio tab → click **+ Add SKU**
2. Fill in: l1_name=Apparel, l2_name=Cargo Shorts, sku_code=AP-CRG-009, AIR=59.99, AUC=18.00
3. Submit → new row appears in Portfolio
4. Switch to Plan tab → new SKU appears in Product dropdown
5. Select it → plan table appears with demand generated from seasonal curve

**Delete:**
6. Find the new SKU in Portfolio → click 🗑
7. **Verify:** SKU disappears from Portfolio and Plan dropdowns
8. Note: only user-created SKUs (HC ≥ 20001) can be deleted; base 8 SKUs cannot

### Technical Detail
- `POST /api/skus` creates with `hierarchy_code ≥ 20001`
- `DELETE /api/skus/{hc}` — only deletes from `new_skus` table
- New SKU data is generated dynamically, not via `WP_DATA` (which is base 8 SKUs only)

---

## 34. CSV Export

### Business Context
Planners export the weekly plan to share with suppliers, finance, or to import into ERP. The export captures all overrides (not baseline values).

### How to Test

1. Make several edits
2. Select a SKU + channel
3. Click **Export CSV** button
4. Open in Excel
5. **Verify:** Edited cells show overridden values (not baseline)
6. Verify: Column order matches display (Week | Units | Sales$ | Disc% | OO | EOP | WOS | GM$...)

**Math check in CSV:**
7. Pick any row: verify Sales$ = AUR × Units (within $0.01 rounding)
8. Verify GM$ = Sales$ − (AUC × Units)
9. Verify EOP = BOP − Units + Receipts

---

---

## End-to-End Test Scenario: Full Planning Cycle

Run this to test all features working together:

### Setup
```
Reset all overrides to start clean.
```

### Step 1 — Morning Review (5 min)
- Open Portfolio tab → scan exception badges
- Check OTB Budget remaining
- Check Season Progress pace KPI

### Step 2 — Top-Down Replan (10 min)
- Select all Apparel SKUs + all channels
- Set Units target to `25,000`
- Click Preview → verify LY weights look sensible
- Override week 26 (summer peak) to `1,200` manually
- Confirm → verify rows updated, audit log shows ~94 entries

### Step 3 — Receipt Review (10 min)
- Select Denim Jeans + Store
- Inventory tab → note FC warnings
- Accept Recomm → OO Placed = Recomm
- Verify: Recomm drops to near 0 after acceptance

### Step 4 — Scenario Save and Compare (5 min)
- Save snapshot "Apparel Replan"
- Make 10% reduction to all Hoodies units
- Compare Hoodies snapshot vs Live → see GM$ delta

### Step 5 — Exception Drill (5 min)
- Open Exceptions panel
- Find first Critical row → click SKU → jumps to Plan tab
- Set OO Placed = Recomm for that SKU → exception should clear

### Step 6 — Bulk Supplier Delay (5 min)
- All Footwear SKUs + All channels
- Inventory tab → Shift +2 (supplier pushed delivery 2 weeks)
- Note toast: "Shifted N receipts +2 wks"
- Check exception panel — did any new exceptions open up?

### Expected Final State
- All edits visible in Audit Log
- OTB Budget shows updated planned cost
- Exceptions panel shows only SKUs with genuine coverage gaps
- Season Progress KPI reflects plan changes

---

## Key Formula Reference Card

| Metric | Formula |
|---|---|
| AUR | AIR × (1 − Disc%) |
| Sales $ | AUR × Sales Units |
| Sales Cost | AUC × Sales Units |
| GM $ | Sales $ − Sales Cost |
| GM % | GM $ / Sales $ |
| EOP | max(0, BOP − Sales Units + Receipts) |
| BOP[n] | = EOP[n-1] |
| WOS | EOP / (sum(sales[wk+1..wk+8]) / 8) |
| FC | (EOP + pipeline[LT weeks]) / 8wk_avg |
| Recomm | ceil((fwdDemand + targetEOP − EOP − pipeline) / casePack) × casePack |
| target_EOP | 8wk_avg × target_wos |
| fwd_demand | sum(sales[wk+1..wk+LT+safety]) |
| Sell-Through | actual_sales / (BOP + Receipts) |
| Variance | written_plan − actual |

## SKU Reference

| Code | SKU | LT | Case Pack | Safety | Target WOS | Peak Week |
|---|---|---|---|---|---|---|
| 10001 | Running Shoes | 14 | 6 | 2 | 6 | 26 |
| 10002 | Casual Sneakers | 12 | 6 | 2 | 6 | 25 |
| 10003 | Ankle Boots | 16 | 4 | 3 | 8 | 41 |
| 10004 | Sandals | 10 | 12 | 1 | 5 | 22 |
| 10005 | Denim Jeans | 14 | 12 | 2 | 8 | 38 |
| 10006 | Graphic Tees | 10 | 24 | 2 | 6 | 26 |
| 10007 | Hoodies | 12 | 12 | 3 | 8 | 42 |
| 10008 | Activewear Shorts | 10 | 24 | 1 | 5 | 24 |

Channel split: Ecom=55% | Indirect=30% | Store=15%
