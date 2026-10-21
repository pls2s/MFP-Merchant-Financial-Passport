# Synthetic expenses — assumptions

**All data in this folder is synthetic (ข้อมูลจำลอง). Never present it as real.**
Expenses, invoices and balances are generated; only the sales they are compared against come from
Rossmann (actual) and the WS1 forecast. Every API response built from these files carries
`is_synthetic_expense: true`, and the credit signal is always `status: "experimental"`.

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
| Opening balance | Once, at the start of the simulation | Days of average daily expenses | 5–45, uniform per store |

Total expenses ≈ 86% of sales, leaving a ~14% margin before the opening balance.

- Random seed: **42** for expenses, **43** (seed + 1) for opening balances
- Expenses generated for 2015-01-01 to 2015-07-31
- Settlement delay for sales cash-in: **0 days** (not simulated)

## Simulation timeline

| Period | Sales used |
| --- | --- |
| 2015-06-20 to 2015-07-17 | Actual sales (balance history) |
| 2015-07-18 to 2015-07-31 | WS1 forecast (`models/forecasts/ensemble.json`) |

Demo "today" is **2015-07-17**, the last forecast origin. The opening balance applies on 2015-06-20.
Gaps are reported only in the forecast window, with a minimum buffer of **0**.

## Demo stores with a deliberate gap

Stores **1, 25 and 817** each get one extra supplier invoice ("ค่าสินค้า supplier (สั่งล็อตใหญ่)",
`scenario: "demo_gap"`) due on **2015-07-22**. Its amount is the projected balance that day plus
2 days of average sales, rounded to 100, so the demo always shows an alert with a date and an amount.

Without these, 4 of the other 1,112 stores (0.4%) have a gap in the forecast window.

## Files

| File | Content |
| --- | --- |
| `expenses.parquet` | store, due_date, type, label, amount, scenario (`baseline` / `demo_gap`), is_synthetic |
| `cash_flow_gaps.json` | `cash-flow-gaps` contract object per store |
| `credit_signal.json` | `credit-signal` contract object per store |
