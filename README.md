# MFP — Merchant Financial Passport

Deep Learning course project. Forecasts daily sales for small merchants with LSTM/GRU, turns the forecast into cash-flow gap warnings and an experimental, explainable financial-health signal, and shows it in a React + FastAPI dashboard.

> All expenses, balances, invoices and product offers are **synthetic**. The credit signal is **experimental** and is not a credit score.

## Repository layout

```
frontend/                  React + Vite dashboard
backend/                   FastAPI endpoints
ai/
  cashflow_forecast/       preprocess, train, evaluate, predict (WS1)
  gap_detection/           balance simulation + gap finder (WS2)
  credit_signal/           heuristic score (WS2)
  copilot/                 LLM explanation + template fallback (WS2)
data/
  raw/                     downloaded datasets — gitignored
  processed/               cleaned data
  synthetic/               simulated expenses + README of assumptions
models/                    trained model artifacts
notebooks/                 EDA and experiments
docs/                      proposal, report, API notes
tests/
```

## Datasets

Raw data is not committed. Download into `data/raw/`:

| Dataset | Files | Source |
| --- | --- | --- |
| Rossmann Store Sales | `train.csv`, `store.csv` → `data/raw/rossmann/` | https://www.kaggle.com/c/rossmann-store-sales (accept competition rules first) |
| UCI Online Retail | `Online Retail.xlsx` → `data/raw/online_retail/` | https://archive.ics.uci.edu/dataset/352/online+retail |

With the Kaggle CLI:

```bash
kaggle competitions download -c rossmann-store-sales -p data/raw/rossmann
unzip data/raw/rossmann/rossmann-store-sales.zip -d data/raw/rossmann
```

## Setup

```bash
cp .env.example .env
```
