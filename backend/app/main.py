"""MFP backend — FastAPI endpoints for the data contract in CLAUDE.md.

Run from the repository root:
    uvicorn backend.app.main:app --reload

All expenses, balances and gaps are synthetic (`is_synthetic_expense: true`), and the
credit signal is always `status: "experimental"`.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.app import schemas
from backend.app.data import AS_OF, DataStore

store: DataStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    store = DataStore.load()
    yield


app = FastAPI(title="MFP — Merchant Financial Passport API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _require(merchant_id: int) -> None:
    if merchant_id not in store.forecasts:
        raise HTTPException(status_code=404, detail=f"merchant {merchant_id} not found")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "merchants": len(store.forecasts), "as_of": AS_OF.strftime("%Y-%m-%d")}


@app.get("/api/v1/merchants", response_model=list[schemas.Merchant])
def merchants(q: str | None = Query(default=None, description="Filter by merchant id or name")):
    items = store.merchants()
    if q:
        items = [m for m in items if q in str(m["merchant_id"]) or q in m["name"]]
    return items


@app.get("/api/v1/merchants/{merchant_id}/forecast", response_model=schemas.Forecast)
def forecast(merchant_id: int):
    _require(merchant_id)
    return store.forecasts[merchant_id]


@app.get("/api/v1/merchants/{merchant_id}/sales-history", response_model=schemas.SalesHistory)
def sales_history(merchant_id: int, days: int = Query(default=90, ge=7, le=365)):
    _require(merchant_id)
    return store.sales_history(merchant_id, days)


@app.get("/api/v1/merchants/{merchant_id}/long-forecast", response_model=schemas.LongForecast)
def long_forecast(merchant_id: int):
    _require(merchant_id)
    return store.long_forecast(merchant_id)


@app.get("/api/v1/merchants/{merchant_id}/seasonal-outlook", response_model=schemas.SeasonalOutlook)
def seasonal_outlook(merchant_id: int):
    _require(merchant_id)
    return store.seasonal_outlook(merchant_id)


@app.get("/api/v1/merchants/{merchant_id}/cash-balance", response_model=schemas.CashBalance)
def cash_balance(merchant_id: int):
    _require(merchant_id)
    return store.cash_balance(merchant_id)


@app.get("/api/v1/merchants/{merchant_id}/cash-flow-gaps", response_model=schemas.CashFlowGaps)
def cash_flow_gaps(merchant_id: int, min_buffer: float = Query(default=0.0, ge=0)):
    _require(merchant_id)
    return store.cash_flow_gaps(merchant_id, min_buffer)


@app.get("/api/v1/merchants/{merchant_id}/credit-signal", response_model=schemas.CreditSignal)
def credit_signal(merchant_id: int):
    _require(merchant_id)
    return store.credit[merchant_id]


@app.post("/api/v1/merchants/{merchant_id}/copilot", response_model=schemas.CopilotResponse)
def copilot(merchant_id: int, body: schemas.CopilotRequest | None = None):
    _require(merchant_id)
    body = body or schemas.CopilotRequest()
    return store.copilot(merchant_id, body.question, [m.model_dump() for m in body.history])


@app.get("/api/v1/model-results", response_model=list[schemas.ModelResult])
def model_results():
    return store.results.to_dict(orient="records")
