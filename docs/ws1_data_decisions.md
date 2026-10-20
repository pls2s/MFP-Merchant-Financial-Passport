# WS1 — Rossmann data decisions

Produced by `python -m ai.cashflow_forecast.preprocess` → `data/processed/rossmann.parquet`
(1,115 stores × 942 days = 1,050,330 rows after reindexing to a full daily calendar).

## Split (fixed)

| Set | Dates | Days | Evaluated store-days |
| --- | --- | --- | --- |
| Train | 2013-01-01 to 2015-05-08 | 858 | 766,584 |
| Validation | 2015-05-09 to 2015-06-19 | 42 | 37,472 |
| Test | 2015-06-20 to 2015-07-31 | 42 | 40,282 |

Seed: 42.

## Missing date ranges

| Stores | Missing | Days each |
| --- | --- | --- |
| 180 | 2014-07-01 to 2014-12-31 | 184 |
| 1 (store 988) | 2013-01-01 | 1 |

All 33,121 missing store-days are in Train; Validation and Test are complete for every store.

**Decision:** keep all stores. Missing days are filled (Open = 0, Sales = 0) and flagged `is_missing = 1`
so every store has a contiguous calendar. Training windows whose input or target overlaps a
missing day are skipped. Missing days never count towards loss or metrics.

## Open = 1 and Sales = 0

54 rows across 41 stores (53 Train, 1 Validation, 0 Test).

**Decision:** keep the rows, flag `zero_sales_open = 1`, exclude from loss and metrics.

## Evaluation days

`is_eval_day = open AND NOT is_missing AND NOT zero_sales_open`. All metrics (WAPE, MAE, RMSE)
are computed on these days only.

## Scaling

- `sales_log = log1p(sales)`
- `sales_scaled = sales / store_mean_sales`, where the store mean uses Train-period evaluated days only
  (range 2,708 to 21,820 per store).
