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


class SyntheticSalesPoint(BaseModel):
    date: IsoDate
    sales: float


class SyntheticSales(BaseModel):
    label: str
    method: str
    is_real: Literal[False] = False
    points: list[SyntheticSalesPoint]


class SalesHistory(BaseModel):
    merchant_id: int
    as_of: IsoDate
    points: list[HistoryPoint]
    synthetic: SyntheticSales = Field(description="ข้อมูลจำลอง after the real data ends — never use as actual sales")


# --- GET /api/v1/merchants/{id}/long-forecast (dashboard extension) -----------


class LongPoint(BaseModel):
    date: IsoDate
    forecast: float
    lower: float
    upper: float
    synthetic_inputs: bool = Field(description="Promo/open days assumed from last year (after the data ends)")


class BacktestPoint(BaseModel):
    date: IsoDate
    forecast: float
    actual: float


class LongBacktest(BaseModel):
    origin: IsoDate
    days: int
    wape_store: float | None
    wape_all_stores: float
    wape_by_block: dict[str, float]
    points: list[BacktestPoint]


class LongForecast(BaseModel):
    merchant_id: int
    method: str
    points: list[LongPoint]
    backtest: LongBacktest


# --- GET /api/v1/merchants/{id}/seasonal-outlook (dashboard extension) --------


class OutlookMonth(BaseModel):
    month: str = Field(description="YYYY-MM")
    outlook: float | None
    lower: float | None
    upper: float | None
    backtested: bool = Field(description="Within the 12 months covered by the backtest; later months are untested")


class OutlookBacktestMonth(BaseModel):
    month: str
    outlook: float | None
    actual: float | None


class SeasonalBacktest(BaseModel):
    origin: IsoDate
    wape_store: float | None
    wape_all_stores: float
    months: list[OutlookBacktestMonth]


class SeasonalOutlook(BaseModel):
    merchant_id: int
    method: str
    is_model_forecast: Literal[False] = False
    months: list[OutlookMonth]
    backtest: SeasonalBacktest


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
    past_gaps: list["Gap"] = Field(description="Shortfalls in the actual-sales history (before as_of)")
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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class CopilotRequest(BaseModel):
    question: str | None = Field(default=None, max_length=500)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20,
                                       description="Earlier turns of this conversation, oldest first")


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


CashBalance.model_rebuild()
