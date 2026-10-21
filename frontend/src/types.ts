// TypeScript types for the MFP API — mirror of backend/app/schemas.py.
// Copy into frontend/src/types.ts. Do not change shapes without telling all workstreams.
// Dates are ISO "YYYY-MM-DD" strings; amounts are plain numbers (no currency unit).

export type IsoDate = string;

// GET /api/v1/merchants
export interface Merchant {
  merchant_id: number;
  name: string;
  is_demo: boolean; // demo store with a deliberate synthetic gap (1, 25, 817)
  gap_count: number;
  score: number; // experimental credit signal, NOT a credit score
  forecast_wape: number; // 0.0643 = 6.43%
}

// GET /api/v1/merchants/{id}/forecast
export interface ForecastPoint {
  date: IsoDate;
  forecast: number;
  lower?: number | null; // 80% interval (actual coverage ~70%, show as "ช่วงคาดการณ์โดยประมาณ")
  upper?: number | null;
  actual?: number | null;
}

export interface Forecast {
  merchant_id: number;
  model: string; // "ensemble-v1"
  horizon_days: number; // 14
  points: ForecastPoint[]; // 42 days: 2015-06-20 .. 2015-07-31
  metrics: { wape: number; mae: number; rmse: number };
}

// GET /api/v1/merchants/{id}/sales-history?days=  (dashboard extension, max 365)
export interface HistoryPoint {
  date: IsoDate;
  sales: number | null; // actual; null when missing or after as_of
  open: boolean;
  promo: boolean;
  holiday: boolean;
  school_holiday: boolean;
}

export interface SalesHistory {
  merchant_id: number;
  as_of: IsoDate;
  points: HistoryPoint[]; // through 2015-07-31 (flags are known in advance)
}

// GET /api/v1/merchants/{id}/cash-balance  (dashboard extension)
export interface BalancePoint {
  date: IsoDate;
  sales: number; // actual up to as_of, forecast after
  expenses: number; // synthetic
  balance: number; // synthetic
  is_forecast: boolean;
}

export interface CashBalance {
  merchant_id: number;
  opening_balance: number;
  points: BalancePoint[];
  is_synthetic_expense: true;
}

// GET /api/v1/merchants/{id}/cash-flow-gaps?min_buffer=
export interface Contributor {
  type: "supplier_invoice" | "rent" | "payroll" | "utilities" | string;
  label: string; // Thai, ready to display
  amount: number;
  due_date: IsoDate;
}

export interface Gap {
  date: IsoDate; // first day the balance falls below the buffer
  shortfall: number; // amount needed to stay at the buffer through the whole gap
  balance_after: number; // balance on `date`
  contributors: Contributor[]; // largest first
}

export interface CashFlowGaps {
  merchant_id: number;
  opening_balance: number;
  gaps: Gap[]; // only in the forecast window (2015-07-18 .. 2015-07-31)
  is_synthetic_expense: true;
}

// GET /api/v1/merchants/{id}/credit-signal
export interface CreditSignal {
  merchant_id: number;
  score: number; // 0-100
  status: "experimental";
  components: {
    consistency: number;
    trend: number;
    active_days: number;
    cash_buffer: number;
    gap_frequency: number;
  };
  positive_factors: string[]; // Thai
  risk_indicators: string[]; // Thai, cash warnings include a date and an amount
  data_coverage: { start: IsoDate; end: IsoDate; days: number };
}

// POST /api/v1/merchants/{id}/copilot  body: CopilotRequest
export interface CopilotRequest {
  question?: string | null; // max 500 chars
}

export interface CopilotResponse {
  merchant_id: number;
  answer: string; // may contain "\n"
  source: "llm" | "template";
  fallback_reason: string | null; // for debugging, do not show to shop owners
  disclaimer: string; // always show next to the answer
  is_synthetic_expense: true;
}

// GET /api/v1/model-results
export interface ModelResult {
  model: "seasonal_naive" | "lightgbm" | "lstm" | "gru" | "ensemble" | string;
  split: "val" | "test";
  wape: number;
  mae: number;
  rmse: number;
  n_days: number;
}
