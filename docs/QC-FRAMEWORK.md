# IA Planning Tool — End-to-End QC Framework

> Hand this to a test-engineer agent. It is grounded in the real endpoint surface
> (40 routes across `/wp`, `/admin`, `/ty-ly`, `/scenario`), the 5 frontend routes,
> the engine invariants, and the known-bug regression set in this codebase.
> Runnable fixtures live in `qc-fixtures/` (see that folder's README).

## 0. How to use this

- Execute layer by layer (§3): **invariants → engine → API contract → feature flows → regression → non-functional**. A failure in an earlier layer blocks the later ones.
- **Never test against live (`:8000`/`:3000`).** Spin a hermetic instance: `IA_DB_PATH=/tmp/qc.db IA_SEEDS_DIR=qc-fixtures/<set>` so each run is isolated and the user's data is never touched.
- Each case reports: `ID · status(PASS/FAIL/BLOCKED) · expected · actual · evidence · severity(S1–S4)`.
- Every item in §9 (Known-Bug Regression Set) is a **must-pass guard** — each is a real defect already shipped once.

## 1. Environment & setup matrix

| Aspect | Detail |
|---|---|
| Backend | FastAPI, `uvicorn main:app`; reads `IA_SEEDS_DIR` (default `backend/seeds/`) + `IA_DB_PATH` (default `planning.db`) at import |
| Frontend | Next.js 14 dev (`next dev`), `NEXT_PUBLIC_API_BASE` → backend `/api` |
| Clock | `IA_PINNED_WEEK` (default 202620) → `IA_LIVE_CLOCK` → data-derived (week after last actual) |
| Years | `selectedYear` ∈ {2026, 2027, 2028} (multi-year) |
| Frontend routes | `/`, `/wp`, `/master`, `/placeholders`, `/admin` |
| Regression harnesses (existing) | `backend/_regression/golden.py` (byte-identical), `backend/_gate_basestock.py`, `backend/_test_marginal_recomm.py`, `backend/_test_recomm_cadence.py` |

## 2. Severity rubric

- **S1** — data corruption, crash on load, wrong inventory/$ math, byte-identical gate broken, cross-year/cross-SKU bleed, irreversible action without guard.
- **S2** — feature flow produces wrong output but recoverable (panel disagrees with grid, accept over/under-supplies).
- **S3** — display/coloring/label wrong, edge-case only.
- **S4** — cosmetic / copy.

## 3. Test layers (execution order)

1. Core invariants (§4)
2. Engine unit/property tests (§5)
3. API contract — every endpoint, happy + error (§6)
4. Feature & UI flows (§7)
5. Seeding & data validation (§8)
6. Known-bug regression guards (§9)
7. Non-functional: concurrency, perf, multi-year, caching (§10)

## 4. Core invariants (hold for ALL SKU×channel×year — assert as properties, not examples)

- **INV-1 Chain:** `EOP[w] = max(0, BOP[w] − sales[w] + receipt[w])`, `BOP[w+1] = EOP[w]`. Never negative EOP.
- **INV-2 Receipt identity:** `receipt[w] = ingested[w] + OOP[w − effLT]`. Actualised-week OOP is display-only and must NOT land.
- **INV-3 Stockout def:** `_stockout = sales>0 AND BOP+receipt < sales AND week < season_end`. Terminal runout to 0 is NOT a stockout.
- **INV-4 oo_locked:** locked ⇔ `w + effLT > season_end`; recomputed off effective LT each read (never stale after an LT edit).
- **INV-5 Recomm idempotency:** after Accept, re-read recomm = 0 everywhere; Accept-again is a no-op.
- **INV-6 Recomm credit:** placing OOP in ANY week reduces total recomm by exactly that amount; recomm never negative.
- **INV-7 Byte-identical:** with no CSV seeds (`F-DEMO`), output is byte-identical to golden baseline (`golden.py verify_core`). Any optional feature absent → output unchanged. **Capture the baseline from the demo path too** — `IA_SEEDS_DIR=qc-fixtures/F-DEMO python3 backend/_regression/golden.py capture`. `baseline.json` is gitignored and defaults to whatever seed is loaded; if captured against the working `backend/seeds/` (60-SKU set) it key-mismatches the demo run. Same seed for capture + verify.
- **INV-8 Year isolation:** editing/ordering in year Y changes only year Y. EVERY panel/endpoint that takes `year` must reflect the requested year. (Regression: exceptions panel was year-blind.)
- **INV-9 SKU/channel isolation:** an edit to (hc,ch) never changes another, except the documented New-SKU Disc% borrow.
- **INV-10 Reversibility:** every mutation has an inverse that restores prior state byte-for-byte (cell undo, undo-recomm, undo top-down, reset overrides, snapshot restore).

## 5. Engine unit / property tests

| ID | Area | Assert |
|---|---|---|
| ENG-01 | Price math | `Sales$=AUR×units`, `AUR=AIR×(1−Disc%)`, `GM$=Sales$−AUC×units`, `GM%=GM$/Sales$`, `Disc$=units×AIR×Disc%` |
| ENG-02 | Disc% modes | Hold Units: edit Disc% keeps units, recalcs Sales$. Hold $: keeps Sales$, back-calcs units |
| ENG-03 | Opening stock | `BOP[first]=round(open_wos × fwd_8wk_avg)` |
| ENG-04 | WOS | planning = forward demand-curve walk of EOP; actualised = trailing 4-wk avg; terminal → None |
| ENG-05 | FC | forward walk of EOP+pipeline; pipeline = `OOP[w−LT+1..w]` (ingested NOT added) |
| ENG-06 | Recomm schedule | leveled min-peak deadline-feasible; covers every week incl. locked tail; `Σcolumn = total`; case-pack multiples |
| ENG-07 | Recomm top-up | `recomm[i]=max(0, Σtarget≤i − Σ(OOP+recomm)≤i)`; need() ignores OOP |
| ENG-08 | Accept | single batch `OOP+=recomm`; INV-5; long-LT converges in one pass |
| ENG-09 | Exception status | critical=stockout-in-LT; low=stockout beyond LT; excess=no stockout & cov>(LT+target)[FC] or target×1.5[WOS]; planned runout ≠ critical |
| ENG-10 | New-SKU borrow | New Disc% = tagged Old's Disc% at week×channel during 52-wk window; planner override wins; outside window → own |
| ENG-11 | Lifecycle | rows exist only between activation_week and deactivation_week |
| ENG-12 | forecast.csv | `expected_sales_units` replaces planning forecast; `oo_placed` lands at W+effLT; actuals win; partial OK. Fixture `F-FORECAST-CONSUME` (60/40 on 2026 wk30-40): assert `written_sales_units==60` + `on_order_placed_total_unit==40` on those cells; blank `F-CSV6` keeps engine forecast. |

Run across `F-DEMO`, `F-CSV6`, `F-CSV60`, `F-LONGLT`.

## 6. API contract tests — every endpoint (happy + error)

Each endpoint: valid 200 + correct schema; invalid params → 4xx (never 5xx); year honored where applicable; respects current overrides.

**`/wp`** — `GET` /filters, /by-week (hc/ch/week_from/week_to/year), /summary (+baseline=true), /portfolio, /season-progress, /budget, /exceptions?year=, /audit (limit/hc/field), /master-sku, /sku-settings, /target-wos, /snapshots, /snapshots/compare, /compare. `PUT` /row (units|sales$|disc%|oo_placed; mode hold_units|hold_$), /master-sku/{hc}/tag, /sku-settings/{hc}, /target-wos/{hc}/{ch}, /snapshots/{id}/restore. `PATCH/POST/DELETE` /snapshots. `POST` /accept-recomm, /undo-recomm, /bulk-shift, /top-down/preview, /top-down, /top-down/undo, /placeholders. `DELETE` /placeholders/{pid}, /overrides, /overrides/{hc}/{week}/{ch}, /sku-settings/{hc}, /target-wos/{hc}/{ch}.

**`/admin`** — `GET /seed-status`; `POST /upload-seeds` (multipart, validate-before-promote); `POST /reload`.

**`/ty-ly`, `/scenario`** — confirm present/responding (orphaned-but-live); no 500.

Error matrix per mutating endpoint: missing body, unknown hc, bad channel, **locked-week OOP edit → 403**, out-of-range year/week, negative values.

## 7. Feature & UI flows (by surface)

For each: action → assert grid + KPIs + chart + exceptions update consistently → assert inverse restores state.

**Plan tab (`/wp`)**: F-01 weekly table + filters (dropdown scrolls @60 SKUs); F-02..06 cell edits (units, Sales$, Disc% hold-units, Disc% hold-$, OO Placed); F-07 cell undo; F-17 reset all overrides (must NOT wipe sku_settings); F-08 EOP chain propagation; F-09 WOS coloring; F-10 forward coverage; F-11 recomm; F-12 accept; F-35 undo accept; F-36 undo split; F-13/14 top-down (preview→confirm, editable weights, undo); F-28 bulk receipt shift; F-37 SKU×ch focus drives chart/scope; F-39/40/41/51 KPI cards filter-responsive; F-63 KPI edit-impact delta (current−baseline-overrides-stripped; `—` at zero edits; selection-scoped); F-58/59 TY/LY/LLY tab; F-24 exception panel (year-scoped; View→ jumps).

**SKU settings / Portfolio**: F-15 LT/case-pack/safety/WOS edits persist + recolor + recompute locks/recomm; F-16 per-channel target WOS.

**Master SKU (`/master`)**: tagged_to edit persists (drives borrow); Old/New status; active-year filter.

**Placeholders (`/placeholders`)**: clone-from lists Old SKUs only; create (hc 90000+) clones across years; full WP edit; isolated from main views; delete.

**Snapshots**: capture/restore/delete/rename/compare(A-vs-B, A-vs-Live); restore brings back cell overrides AND sku/channel settings.

**Data Import (`/admin`)**: upload validated before save (bad set rejected, live untouched); seed-status shows source; hot-reload applies; frontend polls until back.

**Multi-year**: switch 2026↔2027↔2028, re-run F-08/11/12/24 per year (INV-8).

## 8. Seeding & data-validation tests (`POST /upload-seeds` and cold-load)

| ID | Fixture | Expected |
|---|---|---|
| SEED-01 | `F-DEMO` | demo literals; byte-identical (INV-7) |
| SEED-02 | `F-MALFORMED/missing-column` | SeedError 400, live untouched |
| SEED-03 | `F-MALFORMED/dup-hc` | rejected |
| SEED-04 | `F-MALFORMED/bad-status` | rejected |
| SEED-05 | `F-MALFORMED/bad-tag` | rejected |
| SEED-06 | `F-MALFORMED/no-old` | rejected |
| SEED-07 | `F-MALFORMED/missing-supply` | rejected |
| SEED-08 | `F-MALFORMED/bad-channel` | rejected |
| SEED-09 | `F-MALFORMED/bad-history` | rejected |
| SEED-10 | `F-MALFORMED/bad-forecast` | rejected |
| SEED-11 | `F-CSV60` | loads, 60 SKUs/180 budgets, materializes, no crash |
| SEED-12 | `F-DUPNAME` | loads but flag duplicate l2_name (data-quality) |
| SEED-13 | `F-FORECAST-LTMISMATCH` | accept → no over-supply (LT-mismatch guard) |
| SEED-14 | any valid + `/reload` + restart | overrides+sku_settings survive; wp_facts/master_sku regenerate |

## 9. Known-bug regression guards (each a defect already shipped — must stay fixed)

- REG-01 **Exceptions year-scope** (`d2daba1`): fix a stockout in 2027 → 2027 panel clean; 2026/2028 unaffected.
- REG-02 **forecast + LT override over-supply**: accept on forecast-seeded SKU under LT override → 0 stockout, sane WOS (old → 40–121).
- REG-03 **Accept over-supply**: cross-week OOP lump → no double-order; end-EOP ≈ 0.
- REG-04 **Long-LT accept convergence**: LT≥14 accept leaves 0 unmet (was 234).
- REG-05 **KPI phantom delta**: zero edits → `—` (not identical Sales$/GM$).
- REG-06 **KPI delta on selection**: survives a product/channel selection.
- REG-07 **BOP chain propagation**: edit → all downstream BOP/EOP update on screen.
- REG-08 **oo_locked after LT change**: change LT → lock window + historical-OOP display recompute.
- REG-09 **WOS/FC season-end**: terminal weeks not false-red; long-LT pipeline not false-red.
- REG-10 **Exception false-critical on planned runout**: intentional runout = excess/neutral, not critical.
- REG-11 **Dropdown overflow** (`4e1f908`): Product list @60 SKUs scrolls, no off-screen.
- REG-12 **Reset overrides keeps sku_settings**: DELETE /overrides leaves LT/case-pack edits.
- REG-13 **Concurrency**: parallel reads/writes across years don't error (RLock).
- REG-14 **Placeholder isolation**: placeholder edits never touch live portfolio/KPIs.

## 10. Non-functional

- PERF-01 60-SKU cold load + materialize ≤ ~5s; warm `get_agg_rows(all)` fast (read-through cache, 13–23× warm).
- PERF-02 Cache invalidation: an edit busts the per-(year,hc,ch) cache (no stale read).
- CONC-01 Concurrent accept on disjoint SKUs → no cross-contamination.
- CLOCK-01 Advance `IA_PINNED_WEEK` / add actuals → "now" boundary + year window roll correctly.

## 11. Fixtures (in `qc-fixtures/`, regenerate via `qc-fixtures/generate_fixtures.py`)

`F-DEMO` (empty), `F-CSV6`, `F-CSV60`, `F-NOHIST`, `F-LONGLT`, `F-EARLYPEAK`, `F-DUPNAME`, `F-FORECAST-LTMISMATCH`, `F-MALFORMED/{missing-column,dup-hc,bad-status,bad-tag,no-old,missing-supply,bad-channel,bad-history,bad-forecast}`.

## 12. Exit criteria

- 100% of §4 invariants + §9 regression guards PASS.
- 0 open S1/S2.
- `golden.py verify_core` green on `F-DEMO`.
- Every §6 endpoint: correct schema on happy path, 4xx (never 5xx) on bad input.
- Every mutating flow has its inverse verified (INV-10).
