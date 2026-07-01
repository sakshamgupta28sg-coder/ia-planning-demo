REG-02 (LT-override regression guard):
  1. Load this set  (IA_DB_PATH=/tmp/qc.db IA_SEEDS_DIR=qc-fixtures/F-FORECAST-LTMISMATCH)
  2. update_sku_setting(70001, 'lead_time_weeks', 4)   # or PUT /wp/sku-settings/70001 {lead_time_weeks:4}
  3. accept_recomm_receipts([70001], ['Ecom','Indirect','Store'], year=2026)
Assert: 0 stockout AND max WOS < 40 (old code blew up to WOS 40-121).
Validated 2026-07: applied=17, maxWOS=17, stockout=0.
