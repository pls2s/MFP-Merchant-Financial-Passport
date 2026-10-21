# MFP backend (FastAPI)

Serves the data contract from `CLAUDE.md`. Forecasts are precomputed by Workstream 1 and loaded at
startup — the model is never run live. Gap detection and the copilot call the Workstream 2 modules.

## Run

From the repository root, with the Python 3.11 venv:

```bash
pip install -r backend/requirements.txt
cp .env.example .env            # optional: LLM_API_KEY for the copilot (Typhoon)
uvicorn backend.app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- CORS allows the Vite dev server (`http://localhost:5173`); override with `CORS_ORIGINS` (comma-separated).

Data files it loads (all committed):

| File | From |
| --- | --- |
| `models/forecasts/ensemble.json`, `sales_history.parquet` | WS1 `python -m ai.cashflow_forecast.predict --model ensemble` |
| `models/forecasts/long_*.parquet`, `seasonal_*.parquet`, `long_range_metrics.json` | WS1 `python -m ai.cashflow_forecast.long_range` |
| `models/results.csv` | WS1 `python -m ai.cashflow_forecast.evaluate` |
| `data/synthetic/expenses.parquet`, `cash_flow_gaps.json` | WS2 `python -m ai.gap_detection.build` |
| `data/synthetic/credit_signal.json` | WS2 `python -m ai.credit_signal.build` |

## Endpoints

Demo "today" is **2015-07-17**: actual sales up to that date, forecast for 2015-07-18 to 2015-07-31.

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/health` | `status`, number of merchants, `as_of` |
| GET | `/api/v1/merchants?q=` | Store list for the picker; `q` filters by id or name |
| GET | `/api/v1/merchants/{id}/forecast` | `forecast` contract (42 days of the Test period, `lower`/`upper` = 80% interval) |
| GET | `/api/v1/merchants/{id}/sales-history?days=` | Actual daily sales (7–365 days up to `as_of`) plus promo / holiday / open flags through 2015-07-31; sales after `as_of` are `null` |
| GET | `/api/v1/merchants/{id}/long-forecast` | 84-day forecast (LSTM+GRU rolled forward 14 days at a time) with intervals and `synthetic_inputs`, plus its backtest from 2015-05-08 |
| GET | `/api/v1/merchants/{id}/seasonal-outlook` | 24-month seasonal outlook (`is_model_forecast: false`; only the first 12 are `backtested`) plus its backtest from 2014-07-31 |
| GET | `/api/v1/merchants/{id}/cash-balance` | Daily simulated balance (`sales`, synthetic `expenses`, `balance`, `is_forecast`) from 2015-01-01, plus `past_gaps` (shortfalls before `as_of`) |
| GET | `/api/v1/merchants/{id}/cash-flow-gaps?min_buffer=` | `cash-flow-gaps` contract, re-computed with the given minimum buffer (default 0) |
| GET | `/api/v1/merchants/{id}/credit-signal` | `credit-signal` contract, always `status: "experimental"` |
| POST | `/api/v1/merchants/{id}/copilot` | Body `{"question": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}` (both optional) → Thai chat answer |
| GET | `/api/v1/model-results` | WAPE / MAE / RMSE of every model on val and test (Model results screen) |

Unknown merchant → `404`.

### Additions to the contract (tell frontend)

The contract in `CLAUDE.md` does not fix these shapes, so they are defined here:

`GET /api/v1/merchants` — one object per store:

```json
{"merchant_id": 1, "name": "ร้านตัวอย่าง #1", "is_demo": true, "gap_count": 2, "score": 58, "forecast_wape": 0.0643}
```

`is_demo` marks stores 1, 25 and 817, which have a deliberate synthetic gap on 2015-07-22.

`POST /api/v1/merchants/{id}/copilot`:

```json
{
  "merchant_id": 1,
  "answer": "…",
  "source": "llm",
  "fallback_reason": null,
  "disclaimer": "รายจ่ายเป็นข้อมูลจำลอง และคะแนนเป็นสัญญาณทดลอง ไม่ใช่คะแนนเครดิต",
  "is_synthetic_expense": true
}
```

The copilot sees facts computed by `ai/copilot/facts.py`: sales patterns (best weekday, promo uplift,
12-week trend), the day-by-day forecast, upcoming synthetic expenses, projected balance, forecast accuracy,
the credit signal with its rank, and three what-if scenarios (sales ±10%, delaying the largest upcoming
expense by 7 days) re-simulated with the WS2 gap finder, plus the 3-month and 24-month outlooks.
Send earlier turns as `history` for follow-ups. Month references such as "สิงหาคมปีหน้า" are resolved to
a B.E. month ("ส.ค. 2559") before the LLM sees the question.

Validation of the LLM answer: every number must be in the facts, the fact rounded to the nearest
hundred/thousand, or an exact sum/difference of two amounts in the same facts list (a random number
passes about 2% of the time); every "month year" must be in the facts or the question.

`source` is `"template"` when there is no API key, the API fails or times out (20 s), or the LLM
answer used a number not in the computed facts or loan wording (after one retry). Show `disclaimer`
next to the answer.

`GET /api/v1/model-results` — rows of `models/results.csv`:

```json
{"model": "ensemble", "split": "test", "wape": 0.0818, "mae": 570.7, "rmse": 861.8, "n_days": 40282}
```

## UI reminders (CLAUDE.md)

- Badge every synthetic element (`ข้อมูลจำลอง`): expenses, balances, gaps, product offers.
- The credit signal always shows "experimental"; never use "approve" / "อนุมัติ".
- Every warning shows a date and an amount.

## Tests

```bash
pytest tests/test_backend.py
```
