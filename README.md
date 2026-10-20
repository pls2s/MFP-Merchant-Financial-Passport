# MFP — Merchant Financial Passport

**Turn Every Transaction into Financial Opportunity**

MFP (Merchant Financial Passport) is a Deep Learning course prototype that forecasts daily sales for small merchants with LSTM/GRU, turns the forecast into cash-flow gap warnings and an explainable, experimental financial-health signal, and shows it all in a React + FastAPI dashboard.

The deep-learning forecasting model is the core of the project. Everything else exists to make its output useful in the demo.

> **Prototype data notice:** All expenses, invoices, balances, POS/bank integrations, provider APIs and product offers are **mock or synthetic** and are labelled as such in the code, API and UI. The credit signal is **experimental** and is not a credit score.

---

## Problem

Small merchants may have real revenue and continuous business activity but still face difficulties accessing financial services because their business data is fragmented across multiple platforms.

For example:

* Sales data is stored in POS systems
* Payments are recorded in bank accounts or QR payment systems
* Delivery revenue is stored on delivery platforms
* Expenses may exist in accounting systems or bank statements

As a result, the merchant's overall financial situation may not be clearly represented.

---

## Solution

MFP turns a merchant's sales history into a forward-looking financial view.

```text
Daily Sales History
      ↓
Sales Forecast (LSTM / GRU)
      ↓
Cash-Flow Gap Detection
      ↓
Alternative Credit Signal (experimental)
      ↓
Merchant Financial Passport
```

MFP does **not replace financial institutions' credit decision systems** and does not approve loans. It provides additional, explainable signals about merchant activity.

---

## Core Features

| Component | How | Trained? | Priority |
| --- | --- | --- | --- |
| Cash-Flow Forecasting | LSTM + GRU, one global model over all stores | Yes | Core |
| Cash-Flow Gap Detection | Deterministic balance calculation | No | Core |
| Alternative Credit Signal | Transparent heuristic score, labelled experimental | No | Core |
| AI Financial Copilot | LLM API explains numbers the system already computed | No | Optional |
| Financial Product Matching | Simple rules + mock offers | No | Optional |

### Cash-Flow Forecasting

Forecasts the next 14 days of sales for each store from a 56-day input window, using calendar features, known-in-advance features (`Open`, `Promo`, holidays), store attributes and a store embedding.

| Model | Method | Role |
| --- | --- | --- |
| Seasonal naive | Same weekday last week | Baseline |
| LightGBM | Feature table + lags ≥ 14 days | Stronger baseline |
| LSTM | 56-day input → 14-day multi-output + store embedding | Main model |
| GRU | Same architecture, GRU cell | Comparison |

Evaluated on open days in the Test period with WAPE, MAE and RMSE. Target: WAPE ≤ 20% and better than both baselines.

```text
WAPE = sum(|y - y_hat|) / sum(|y|)
```

Time-based split only:

| Set | Dates |
| --- | --- |
| Train | 2013-01-01 to 2015-05-08 |
| Validation | 2015-05-09 to 2015-06-19 |
| Test | 2015-06-20 to 2015-07-31 |

### Cash-Flow Gap Detection

Simulates the daily balance from forecast sales and synthetic expenses:

```text
B_t = B_{t-1} + S_hat_t - E_t
```

Reports the first day the balance falls below zero (or a minimum buffer), the shortfall, and the contributing expenses, largest first.

Example (synthetic):

```text
Opening Balance:          ฿5,000
Expected Sales:          ฿20,000
Supplier Invoice Due:    ฿32,000

Projected Shortfall:      ฿7,000
```

### Alternative Credit Signal (experimental)

A transparent 0–100 heuristic, not a trained model and not a credit score. There are no default labels, so no predictive metrics are reported.

| Component | Calculation | Weight |
| --- | --- | --- |
| Consistency | 1 − coefficient of variation of weekly sales | 30% |
| Trend | Last 12 weeks vs previous 12 weeks | 20% |
| Active days | Share of open days with sales | 20% |
| Cash buffer | Lowest projected balance ÷ average monthly expenses | 20% |
| Gap frequency | Number of gaps in forecast window | 10% |

Each component also produces positive factors and risk indicators.

### AI Financial Copilot (optional)

Explains figures the system has already computed in plain Thai. It never invents numbers, never recommends or approves loans, and falls back to templates when the LLM API is unavailable.

Example:

> ยอดขายของร้านค่อนข้างสม่ำเสมอ แต่ค่าสินค้า supplier ที่ครบกำหนดวันที่ 22 ก.ค. อาจทำให้เงินขาดประมาณ ฿7,000

### Financial Product Matching (optional)

Matches a detected gap with **mock** product offers such as working capital or revenue advance, using simple rules. No real provider is integrated.

---

## Data Sources

| Dataset | Role |
| --- | --- |
| [Rossmann Store Sales](https://www.kaggle.com/c/rossmann-store-sales) | Train and evaluate forecasting models (1,115 stores, 2013-01-01 to 2015-07-31) |
| [UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online+retail) | Demo of CSV upload → daily aggregation |
| Roast Coffee Shop 2023 Financials (Kaggle) | Template for synthetic expense categories (itself mock data) |
| Favorita Store Sales (Kaggle) | Optional generalization test |

Expenses, invoices and opening balances are generated synthetically per store. Parameters and the random seed are recorded in [`data/synthetic/README.md`](data/synthetic/README.md).

### Download

Raw data is not committed. Download into `data/raw/`:

| Dataset | Files |
| --- | --- |
| Rossmann Store Sales | `train.csv`, `store.csv` → `data/raw/rossmann/` (accept competition rules first) |
| UCI Online Retail | `Online Retail.xlsx` → `data/raw/online_retail/` |

With the Kaggle CLI:

```bash
kaggle competitions download -c rossmann-store-sales -p data/raw/rossmann
unzip data/raw/rossmann/rossmann-store-sales.zip -d data/raw/rossmann
```

---

## Technology Stack

| Layer | Tools |
| --- | --- |
| Frontend | React, Vite, Recharts |
| Backend | Python, FastAPI, Pydantic |
| AI / Data | Python, Pandas, NumPy, LightGBM, TensorFlow / Keras |

The backend loads precomputed forecasts at startup. Models are never run live during the demo.

---

## API

| Endpoint | Returns |
| --- | --- |
| `GET /api/v1/merchants` | Store list |
| `GET /api/v1/merchants/{id}/forecast` | 14-day forecast + actuals |
| `GET /api/v1/merchants/{id}/cash-flow-gaps` | Gap dates + causes |
| `GET /api/v1/merchants/{id}/credit-signal` | Score + factors (`status: "experimental"`) |
| `POST /api/v1/merchants/{id}/copilot` | Plain-language explanation (optional) |

---

## Project Structure

```text
MFP-Merchant-Financial-Passport/
│
├── frontend/                  # React + Vite dashboard
├── backend/                   # FastAPI endpoints
├── ai/
│   ├── cashflow_forecast/     # preprocess, train, evaluate, predict
│   ├── gap_detection/         # balance simulation + gap finder
│   ├── credit_signal/         # experimental heuristic score
│   └── copilot/               # LLM explanation + template fallback
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

Each workstream works on its own branch (`ws1-ml`, `ws2-logic`, `ws3-frontend`, `ws3-backend`) and merges through a PR.

---

## Prototype Scope

### Real Implementation

* Rossmann data cleaning and feature engineering
* Sales forecasting (seasonal naive, LightGBM, LSTM, GRU)
* Cash-flow gap detection
* Experimental credit signal
* Dashboard and API

### Mock / Synthetic

* Expenses, invoices and balances
* POS, bank and delivery platform integrations
* Financial provider APIs and product offers

---

## Setup

```bash
cp .env.example .env
```

## Tagline

**MFP — Turn Every Transaction into Financial Opportunity**
