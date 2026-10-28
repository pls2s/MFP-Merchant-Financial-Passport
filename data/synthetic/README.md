# Synthetic expenses — assumptions

**All data in this folder is synthetic (ข้อมูลจำลอง). Never present it as real.**
Expenses, owner withdrawals, invoices and balances are generated; only the sales they are compared
against come from Rossmann (actual) and the WS1 forecast. Every API response built from these files
carries `is_synthetic_expense: true`, and the credit signal is always `status: "experimental"`.

Regenerate:

```bash
python -m ai.gap_detection.build     # expenses.parquet, cash_flow_gaps.json
python -m ai.credit_signal.build     # credit_signal.json
```

Parameters live in `ExpenseParams` (`ai/gap_detection/synthetic_expenses.py`) and the demo settings in
`ai/gap_detection/build.py`. Keep this file in sync with them.

## Expense parameters

Amounts scale with each store's **average sales per calendar day** (Train period, closed days counted
as zero), so expenses stay realistic relative to income. Monthly costs use 30 × that daily average.

| Item | Pattern | Parameter | Value |
| --- | --- | --- | --- |
| Supplier invoice | Issued every 7 or 14 days (fixed per store, random), paid 7 days after issue | Share of sales over the cycle | 60%, ± 10% uniform noise |
| Rent | Fixed, due on the 1st | Share of monthly sales | 8% |
| Payroll | 24 times a year: 15th and last day of the month | Share of monthly sales (half each payment) | 15% |
| Utilities | Monthly, due on the 20th | Share of monthly sales | 3%, ± 15% uniform noise |
| Cash reserve | Kept by the owner; also the opening balance on 2015-01-01 | Days of average daily expenses | 5–45, uniform per store |
| Owner withdrawal | On the 25th of each month up to the demo date | Amount | Whatever cash is above the reserve that day (none if below) |

Operating costs ≈ 86% of sales, leaving a ~14% margin. Without withdrawals that margin would pile up
over 6½ months and no store would ever run short; owners take profit out, so the balance hovers around
each store's reserve and dips when invoices bunch up. Withdrawals are not simulated in the forecast
window, and they are excluded from "average monthly expenses" in the credit signal.

- Random seed: **42** for expenses, **43** (seed + 1) for reserve sizes
- Expenses generated for 2015-01-01 to 2015-07-31
- Settlement delay for sales cash-in: **0 days** (not simulated)

## Simulation timeline

| Period | Sales used | Gaps |
| --- | --- | --- |
| 2015-01-01 to 2015-07-17 | Actual sales (`models/forecasts/sales_history.parquet`) | Past gaps (`cash-balance.past_gaps`) |
| 2015-07-18 to 2015-07-31 | WS1 forecast (`models/forecasts/ensemble.json`) | Upcoming gaps (`cash-flow-gaps`) |
| 2015-08-01 to 2015-10-09 | Recursive LSTM+GRU rollout (`long_forecast.parquet`) | `cash-balance.long_gaps`, `horizon: "3m"` |
| 2015-10-10 to 2016-07-31 | Monthly outlook (`seasonal_outlook.parquet`) spread over the days of each month by the store's average sales per weekday (holidays ignored; stores without an outlook use the rollout's average day) | `cash-balance.long_gaps`, `horizon: "1y"` |

The two longer periods feed only the 3-month / 1-year views of the balance chart
(`ai/gap_detection/long_balance.py`, computed on request). They are less certain, shown faded, and never
reported through `cash-flow-gaps`. Expenses after 2015-07-31 continue each store's baseline pattern
(`scenario: "baseline_extended"`): the same supplier cycle with the store's average invoice ± 10%, the
same rent and payroll, utilities at the store's average ± 15%; rng seed **42 + 1000 + store**, so the
base expenses above are unchanged. The owner keeps withdrawing cash above the reserve on the 25th from
2015-08-25 on. With these settings 66 stores (5.9%) may run short in the 3-month part and 96 (8.6%) in
the monthly-outlook part; the demo stores, with their 5-day reserve, run short several times.

Demo "today" is **2015-07-17**, the last forecast origin. Minimum buffer **0**.

With these settings **88 of 1,115 stores (7.9%)** ran short at least once before the demo date, and
**9 of the other 1,112 stores (0.8%)** are projected to run short in the forecast window.

## Demo stores with a deliberate gap

Stores **1, 25 and 817** represent a store with a thin cash reserve that places a large order:

- reserve of **5 days** of average expenses, so their history has natural shortfalls
  (store 1: 1, store 25: 6, store 817: 3 since 1 January)
- one extra supplier invoice ("ค่าสินค้า supplier (สั่งล็อตใหญ่)", `scenario: "demo_gap"`) due on
  **2015-07-22**, sized to leave a balance of −2 days of average sales that day (rounded to 100);
  this comes to 1.3–2.1× a normal invoice

So the demo always shows an upcoming alert with a date and an amount, and a history of past shortfalls.

## Files

| File | Content |
| --- | --- |
| `expenses.parquet` | store, due_date, type (`supplier_invoice` / `rent` / `payroll` / `utilities` / `owner_draw`), label, amount, scenario (`baseline` / `demo_gap`), is_synthetic |
| `cash_flow_gaps.json` | `cash-flow-gaps` contract object per store (upcoming gaps; `opening_balance` = reserve on 2015-01-01) |
| `credit_signal.json` | `credit-signal` contract object per store (risk indicators include past shortfalls) |
| `shortfall_risk.json` | Probability of a shortfall per forecast day (share of 200 simulated sales paths: MC-dropout ensemble × Validation error blocks), seed 42 — see `docs/shortfall_probability.md` |
| `shortfall_calibration.json` | Test-period checks of those probabilities (interval coverage, Brier scores, reliability) |
