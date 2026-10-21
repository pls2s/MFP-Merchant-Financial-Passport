// All API calls go through this file. VITE_USE_MOCK=true reads src/mocks/ instead of the backend.
import type {
  CashBalance,
  ChatMessage,
  CashFlowGaps,
  CopilotResponse,
  CreditSignal,
  Forecast,
  LongForecast,
  Merchant,
  ModelResult,
  SalesHistory,
  SeasonalOutlook,
} from "./types";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const MOCK_AS_OF = "2015-07-17";

const mocks = import.meta.glob<{ default: unknown }>("./mocks/*.json");

export class NotFoundError extends Error {}
export class MockMissingError extends Error {}

async function mock<T>(name: string): Promise<T> {
  const load = mocks[`./mocks/${name}.json`];
  if (!load) throw new MockMissingError(name);
  return (await load()).default as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (res.status === 404) throw new NotFoundError(path);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export const isMock = USE_MOCK;

export const api = {
  asOf: async (): Promise<string> =>
    USE_MOCK ? MOCK_AS_OF : (await request<{ as_of: string }>("/health")).as_of,

  merchants: (): Promise<Merchant[]> =>
    USE_MOCK ? mock("merchants") : request("/api/v1/merchants"),

  forecast: (id: number): Promise<Forecast> =>
    USE_MOCK ? mock(`forecast-${id}`) : request(`/api/v1/merchants/${id}/forecast`),

  /** One year of actual sales + promo/holiday flags; the chart slices it per range. */
  salesHistory: (id: number): Promise<SalesHistory> =>
    USE_MOCK ? mock(`sales-history-${id}`) : request(`/api/v1/merchants/${id}/sales-history?days=365`),

  longForecast: (id: number): Promise<LongForecast> =>
    USE_MOCK ? mock(`long-forecast-${id}`) : request(`/api/v1/merchants/${id}/long-forecast`),

  seasonalOutlook: (id: number): Promise<SeasonalOutlook> =>
    USE_MOCK ? mock(`seasonal-outlook-${id}`) : request(`/api/v1/merchants/${id}/seasonal-outlook`),

  cashBalance: (id: number): Promise<CashBalance> =>
    USE_MOCK ? mock(`cash-balance-${id}`) : request(`/api/v1/merchants/${id}/cash-balance`),

  cashFlowGaps: (id: number, minBuffer = 0): Promise<CashFlowGaps> =>
    USE_MOCK
      ? mock(`cash-flow-gaps-${id}`)
      : request(`/api/v1/merchants/${id}/cash-flow-gaps?min_buffer=${minBuffer}`),

  creditSignal: (id: number): Promise<CreditSignal> =>
    USE_MOCK ? mock(`credit-signal-${id}`) : request(`/api/v1/merchants/${id}/credit-signal`),

  copilot: async (id: number, question: string | null, history: ChatMessage[] = []): Promise<CopilotResponse> => {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 800)); // feel of a real call
      return mock(`copilot-${id}`);
    }
    return request(`/api/v1/merchants/${id}/copilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
  },

  modelResults: (): Promise<ModelResult[]> =>
    USE_MOCK ? mock("model-results") : request("/api/v1/model-results"),
};
