"""Pydantic models for the data contract in CLAUDE.md.

Dates are ISO `YYYY-MM-DD` strings, amounts plain numbers, field names snake_case.
Do not change these shapes without telling all workstreams.
"""

from typing import Literal

from pydantic import BaseModel, Field

IsoDate = str  # YYYY-MM-DD


# --- GET /api/v1/merchants -----------------------------------------------------


class Merchant(BaseModel):
    merchant_id: int
    name: str
    is_demo: bool = Field(description="Demo store with a deliberate cash-flow gap (synthetic scenario)")
    gap_count: int
    score: int = Field(description="Experimental credit signal, not a credit score")
    forecast_wape: float


# --- GET /api/v1/merchants/{id}/forecast ---------------------------------------


class ForecastPoint(BaseModel):
    date: IsoDate
    forecast: float
    lower: float | None = None
    upper: float | None = None
    actual: float | None = None


class ForecastMetrics(BaseModel):
    wape: float
    mae: float
    rmse: float


class Forecast(BaseModel):
    merchant_id: int
    model: str
    horizon_days: int
    points: list[ForecastPoint]
    metrics: ForecastMetrics


# --- GET /api/v1/merchants/{id}/sales-history (dashboard extension) -----------


class HistoryPoint(BaseModel):
    date: IsoDate
    sales: float | None = Field(description="Actual sales; null when missing or after the demo date")
    open: bool
    promo: bool
    holiday: bool
    school_holiday: bool


class SalesHistory(BaseModel):
    merchant_id: int
    as_of: IsoDate
    points: list[HistoryPoint]


# --- GET /api/v1/merchants/{id}/cash-balance (dashboard extension) ------------


class BalancePoint(BaseModel):
    date: IsoDate
    sales: float
    expenses: float
    balance: float
    is_forecast: bool


class CashBalance(BaseModel):
    merchant_id: int
    opening_balance: float
    points: list[BalancePoint]
    is_synthetic_expense: Literal[True] = True


# --- GET /api/v1/merchants/{id}/cash-flow-gaps ---------------------------------


class Contributor(BaseModel):
    type: str
    label: str
    amount: float
    due_date: IsoDate


class Gap(BaseModel):
    date: IsoDate
    shortfall: float
    balance_after: float
    contributors: list[Contributor]


class CashFlowGaps(BaseModel):
    merchant_id: int
    opening_balance: float
    gaps: list[Gap]
    is_synthetic_expense: Literal[True] = True


# --- GET /api/v1/merchants/{id}/credit-signal ----------------------------------


class CreditComponents(BaseModel):
    consistency: float
    trend: float
    active_days: float
    cash_buffer: float
    gap_frequency: float


class DataCoverage(BaseModel):
    start: IsoDate
    end: IsoDate
    days: int


class CreditSignal(BaseModel):
    merchant_id: int
    score: int = Field(ge=0, le=100)
    status: Literal["experimental"] = "experimental"
    components: CreditComponents
    positive_factors: list[str]
    risk_indicators: list[str]
    data_coverage: DataCoverage


# --- POST /api/v1/merchants/{id}/copilot (optional) ----------------------------


class CopilotRequest(BaseModel):
    question: str | None = Field(default=None, max_length=500)


class CopilotResponse(BaseModel):
    merchant_id: int
    answer: str
    source: Literal["llm", "template"]
    fallback_reason: str | None = None
    disclaimer: str
    is_synthetic_expense: Literal[True] = True


# --- GET /api/v1/model-results (Model results screen) --------------------------


class ModelResult(BaseModel):
    model: str
    split: Literal["val", "test"]
    wape: float
    mae: float
    rmse: float
    n_days: int
