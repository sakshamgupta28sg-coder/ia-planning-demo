ENG-12 (forecast-consumption guard):
  Load: IA_DB_PATH=/tmp/qc.db IA_SEEDS_DIR=qc-fixtures/F-FORECAST-CONSUME
  forecast.csv sets expected_sales_units=60 + oo_placed=40 for 2026 wk30-40, all channels.
Assert on those cells: written_sales == 60 AND on_order_placed_total_unit == 40
  (a blank/0 forecast, as in F-CSV6, must instead keep the engine's own forecast).
