# MFP — Merchant Financial Passport

Course final project (Deep Learning). A prototype that forecasts daily sales for small merchants with LSTM/GRU, turns the forecast into cash-flow gap warnings and an explainable financial-health score, and shows it all in a React + FastAPI dashboard.

The deep-learning forecasting model is what the course grades. Everything else exists to make its output useful in the demo.

## Scope

| Component | How | Trained? | Workstream | Priority |
| --- | --- | --- | --- | --- |
| Cash-Flow Forecasting | LSTM + GRU, one global model over all stores | Yes | 1 — ML | Core (graded) |
| Cash-Flow Gap Detection | Deterministic balance calculation | No | 2 — Logic | Core |
| Alternative Credit Signal | Transparent heuristic score, labelled experimental | No | 2 — Logic | Core |
| AI Financial Copilot | LLM API explains numbers the system already computed | No | 2 — Logic | Optional |
| Financial Product Matching | Simple rules + mock offers | No | 3 — App | Cut first if short on time |

Cut order when time runs out: product matching → copilot → Favorita experiments. Keep gap detection to the end.

## Hard rules

- **Never present synthetic or mock data as real.** All expenses, invoices, balances, POS/bank integrations, provider APIs and product offers are mock. Label them in code, API responses (`is_synthetic_expense`), the UI, and the report.
- **The credit signal is not a credit score.** Always `status: "experimental"`. Never use the words "approve" / "อนุมัติ". There are no default labels, so never report predictive metrics for it.
- **The copilot must not invent figures.** It may only use numbers passed to it, must not recommend or approve loans, and must have a template fallback for when the API is unavailable.
- **Time-based splits only.** Never random-split time-series data.
- **Never commit raw data or secrets.** `data/raw/` and `.env` are gitignored; the README explains how to download datasets.
- All models use the same split and the same random seed.

## Data

| Dataset | Role | Notes |
| --- | --- | --- |
| [Rossmann Store Sales](https://www.kaggle.com/c/rossmann-store-sales) | Train + evaluate models | 1,115 stores, 1,017,209 rows, daily, 2013-01-01 to 2015-07-31. Files: `train.csv`, `store.csv`. Must accept competition rules to download. |
| [UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online+retail) | Demo of CSV upload → daily aggregation | 541,909 transaction rows, 8 columns, CC BY 4.0, `.xlsx` |
| Roast Coffee Shop 2023 Financials (Kaggle) | Template for synthetic expense categories | Itself mock data — never cite as real |
| Favorita Store Sales (Kaggle) | Optional generalization test | Only if time remains |

Rossmann cleaning notes:
- `Open = 0` days have `Sales = 0`. Keep them with the `Open` feature, exclude them from metrics.
- Rows with `Open = 1` and `Sales = 0`: inspect, then drop or flag.
- Some stores have missing date ranges. Decide in EDA whether to fill or exclude.

## Workstream 1 — ML (forecasting)

Split (fixed, do not change without telling the team):

| Set | Dates | Days |
| --- | --- | --- |
| Train | 2013-01-01 to 2015-05-08 | 858 |
| Validation | 2015-05-09 to 2015-06-19 | 42 |
| Test | 2015-06-20 to 2015-07-31 | 42 |

Features:
- Calendar: day of week, day of month, month, week of year
- Known in advance: `Open`, `Promo`, `SchoolHoliday`, `StateHoliday`
- Store: `StoreType`, `Assortment`, `CompetitionDistance` (from `store.csv`) + store embedding
- History: input window for LSTM/GRU. For LightGBM use lags ≥ 14 days only, so the model never sees values inside the forecast horizon.
- Scale sales with `log1p` or per-store mean so small and large stores train together.

Models:

| Model | Method | Role |
| --- | --- | --- |
| Seasonal naive | Same weekday last week | Baseline, no training |
| LightGBM | Feature table + lags ≥ 14 | Stronger baseline |
| LSTM | 56-day input → 14-day multi-output + store embedding | Main model |
| GRU | Same architecture, GRU cell | Comparison |

Tuning budget is small: window 28 or 56, hidden 64 or 128, 1–2 layers, dropout 0.2, early stopping on validation WAPE.

Evaluation (open days in Test only). Target: WAPE ≤ 20% and better than both baselines.

```
WAPE = sum(|y - y_hat|) / sum(|y|)
```

Report WAPE, MAE and RMSE for all four models. Do not use MAPE (zero-sales days).

Code lives in `ai/cashflow_forecast/`: `preprocess.py`, `train.py`, `evaluate.py`, `predict.py`. Trained artifacts go in `models/`. Forecasts for every store over the Test period are exported in the `forecast` contract shape below so the app can load them without running the model live.

## Workstream 2 — Logic + synthetic data

Synthetic expenses per store (starting assumptions, adjustable; record every parameter and the seed in `data/synthetic/README.md`):

| Item | Pattern | Default |
| --- | --- | --- |
| Supplier invoice | Every 7 or 14 days, with due date | Share of average sales |
| Rent | Fixed, 1st of month | Fixed per store |
| Payroll | 24 times a year (15th and month end) | Fixed per store |
| Utilities | Monthly | Small variation |
| Opening balance | Once | N days of average expenses |

- Create 2–3 demo stores that deliberately hit a gap (e.g. large invoice during a sales dip) so the demo always has an alert.
- Optional: delay sales cash-in by 1–2 days to simulate platform settlement.

Gap detection:

```
B_t = B_{t-1} + S_hat_t - E_t
```

B = balance, S_hat = forecast sales (or actual sales for history), E = expenses due that day. Report the first day below zero (or below a configured minimum buffer), the shortfall, and contributing expenses sorted largest first. Unit tests at minimum: no gap, one gap, multiple gaps, minimum buffer.

Credit signal (0–100):

| Component | Calculation | Default weight |
| --- | --- | --- |
| Consistency | 1 − coefficient of variation of weekly sales | 30% |
| Trend | Last 12 weeks vs previous 12 weeks | 20% |
| Active days | Share of open days with sales | 20% |
| Cash buffer | Lowest projected balance ÷ average monthly expenses | 20% |
| Gap frequency | Number of gaps in forecast window | 10% |

Positive factors and risk indicators come from per-component thresholds (e.g. buffer under one month → risk indicator).

Start with actual sales in week 2–3; switch the input to Workstream 1's forecast file in week 4.

## Workstream 3 — App (React + FastAPI)

Screens:
1. Merchant picker with search
2. Financial Passport (main): summary cards (last-30-day sales, credit score, nearest gap), actual vs forecast chart with confidence band if available, gap alert cards (date, shortfall, contributors), positive/risk factors, copilot box (optional), mock product offers
3. Model results: comparison table of the four models (for the presentation)
4. CSV upload (optional): demo with UCI Online Retail

UX rules:
- Thai copy a shop owner understands. Every warning shows a date and an amount.
- Badge every mock or synthetic element (`ข้อมูลจำลอง`, `ตัวอย่าง`).
- Credit signal always shows "experimental".

Frontend: React + Vite, Recharts. All API calls through `src/api.ts`. Mock JSON in `src/mocks/`, matching the contract exactly; switch mock vs real API with an environment variable.

Backend: FastAPI + Pydantic models matching the contract. Load precomputed forecasts at startup — never run the model live during the demo. Call Workstream 2's modules for gaps and credit signal. Enable CORS for the Vite dev server.

## Data contract

Agreed in week 1. Do not change shapes without telling all workstreams. Dates are ISO `YYYY-MM-DD`, amounts are plain numbers, field names are snake_case. `lower` / `upper` may be omitted until confidence intervals exist. Values below are illustrative.

| Endpoint | Returns | Source |
| --- | --- | --- |
| `GET /api/v1/merchants` | Store list | WS1 |
| `GET /api/v1/merchants/{id}/forecast` | 14-day forecast + actuals | WS1 |
| `GET /api/v1/merchants/{id}/cash-flow-gaps` | Gap dates + causes | WS2 |
| `GET /api/v1/merchants/{id}/credit-signal` | Score + factors | WS2 |
| `POST /api/v1/merchants/{id}/copilot` | Plain-language explanation (optional) | WS2 |

`forecast`

```json
{
  "merchant_id": 1,
  "model": "lstm-v1",
  "horizon_days": 14,
  "points": [
    {"date": "2015-07-18", "forecast": 5263.0, "lower": 4800.0, "upper": 5700.0, "actual": 5120.0}
  ],
  "metrics": {"wape": 0.14, "mae": 620.5, "rmse": 845.2}
}
```

`cash-flow-gaps`

```json
{
  "merchant_id": 1,
  "opening_balance": 20000.0,
  "gaps": [
    {
      "date": "2015-07-22",
      "shortfall": 3200.0,
      "balance_after": -3200.0,
      "contributors": [
        {"type": "supplier_invoice", "label": "ค่าสินค้า supplier", "amount": 15000.0, "due_date": "2015-07-22"}
      ]
    }
  ],
  "is_synthetic_expense": true
}
```

`credit-signal`

```json
{
  "merchant_id": 1,
  "score": 72,
  "status": "experimental",
  "components": {"consistency": 0.81, "trend": 0.55, "active_days": 0.97, "cash_buffer": 0.40, "gap_frequency": 0.70},
  "positive_factors": ["ยอดขายรายสัปดาห์สม่ำเสมอ"],
  "risk_indicators": ["เงินสำรองต่ำกว่ารายจ่าย 1 เดือน"],
  "data_coverage": {"start": "2013-01-01", "end": "2015-07-31", "days": 942}
}
```

## Repository layout

```
MFP/
├── frontend/                  # React + Vite dashboard
├── backend/                   # FastAPI endpoints
├── ai/
│   ├── cashflow_forecast/     # preprocess, train, evaluate, predict (WS1)
│   ├── gap_detection/         # balance simulation + gap finder (WS2)
│   ├── credit_signal/         # heuristic score (WS2)
│   └── copilot/               # LLM explanation + template fallback (WS2)
├── data/
│   ├── raw/                   # downloaded datasets — gitignored
│   ├── processed/             # cleaned data
│   └── synthetic/             # simulated expenses + README of assumptions
├── models/                    # trained model artifacts
├── notebooks/                 # EDA and experiments
├── docs/                      # proposal, report, API notes
├── tests/
└── README.md
```

Monorepo. Each workstream works on its own branch and merges to `main` through a PR.

## Timeline (6 weeks)

| Week | WS1 ML | WS2 Logic | WS3a Frontend | WS3b Backend | Milestone |
| --- | --- | --- | --- | --- | --- |
| 1 | EDA, clean, lock split | Design synthetic expenses | User flow, wireframes | Agree contract | Contract locked |
| 2 | Features, baselines, first LSTM | Data generator + gap detection | Mockups + mock JSON | Endpoints return mock data | LSTM runs end-to-end |
| 3 | GRU, tune both | Credit signal + unit tests | Merchant picker + Passport page | All endpoints per contract | Mock API complete |
| 4 | Test-set results, tables, charts | Switch to forecast input | Model results page, UX fixes | Load real forecasts + WS2 logic | All 4 model results |
| 5 | Export forecasts | Copilot (if time) | Connect real API | Integration tests | App on real data |
| 6 | Methodology + results write-up | Logic write-up | Polish, rehearse demo | Final testing | Present + submit |

Critical path: if the first LSTM does not run end-to-end by the end of week 2, everything after slips.
