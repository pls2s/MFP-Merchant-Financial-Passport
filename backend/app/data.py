"""Precomputed data loaded once at startup. The forecasting model is never run live;
gap detection and the copilot call the Workstream 2 modules directly."""

import json
from dataclasses import dataclass

import pandas as pd

from ai.cashflow_forecast.preprocess import ROSSMANN
from ai.cashflow_forecast.predict import HISTORY_PATH
from ai.copilot.explain import explain, load_dotenv
from ai.copilot.facts import MerchantContext, score_rank
from ai.credit_signal.build import CREDIT_PATH
from ai.gap_detection.build import (
    AS_OF, DEMO_STORES, EXPENSES_PATH, FORECASTS_PATH, GAPS_PATH, past_gaps, sales_series,
)
from ai.gap_detection.gaps import cash_flow_gaps, simulate_balance

RESULTS_PATH = ROSSMANN.models_dir / "results.csv"


def _by_merchant(path) -> dict[int, dict]:
    return {obj["merchant_id"]: obj for obj in json.loads(path.read_text())}


@dataclass
class DataStore:
    forecasts: dict[int, dict]
    gaps: dict[int, dict]
    credit: dict[int, dict]
    sales: dict[int, pd.DataFrame]
    expenses: pd.DataFrame
    results: pd.DataFrame
    history: dict[int, pd.DataFrame]

    @classmethod
    def load(cls) -> "DataStore":
        load_dotenv()  # LLM_API_KEY etc. for the copilot
        return cls(
            forecasts=_by_merchant(FORECASTS_PATH),
            gaps=_by_merchant(GAPS_PATH),
            credit=_by_merchant(CREDIT_PATH),
            sales=sales_series(),
            expenses=pd.read_parquet(EXPENSES_PATH),
            results=pd.read_csv(RESULTS_PATH),
            history={int(s): df.drop(columns="store") for s, df in pd.read_parquet(HISTORY_PATH).groupby("store")},
        )

    def merchants(self) -> list[dict]:
        return [
            {
                "merchant_id": m,
                "name": f"ร้านตัวอย่าง #{m}",
                "is_demo": m in DEMO_STORES,
                "gap_count": len(self.gaps[m]["gaps"]),
                "score": self.credit[m]["score"],
                "forecast_wape": self.forecasts[m]["metrics"]["wape"],
            }
            for m in sorted(self.forecasts)
        ]

    def sales_history(self, merchant_id: int, days: int) -> dict:
        """Last `days` of actual sales up to AS_OF plus the forecast window; sales after AS_OF are hidden
        (the forecast endpoint carries them for evaluation), the known-in-advance flags are not."""
        h = self.history[merchant_id]
        h = h[h["date"] > AS_OF - pd.Timedelta(days=days)]
        return {
            "merchant_id": merchant_id,
            "as_of": AS_OF.strftime("%Y-%m-%d"),
            "points": [
                {
                    "date": r.date.strftime("%Y-%m-%d"),
                    "sales": None if r.date > AS_OF or pd.isna(r.sales) else round(float(r.sales), 2),
                    "open": bool(r.open), "promo": bool(r.promo),
                    "holiday": bool(r.holiday), "school_holiday": bool(r.school_holiday),
                }
                for r in h.itertuples()
            ],
        }

    def _store_expenses(self, merchant_id: int) -> pd.DataFrame:
        start = self.sales[merchant_id]["date"].min()
        return self.expenses[(self.expenses["store"] == merchant_id) & (self.expenses["due_date"] >= start)]

    def cash_balance(self, merchant_id: int) -> dict:
        sales = self.sales[merchant_id]
        bal = simulate_balance(sales, self._store_expenses(merchant_id), self.gaps[merchant_id]["opening_balance"])
        return {
            "merchant_id": merchant_id,
            "opening_balance": self.gaps[merchant_id]["opening_balance"],
            "points": [
                {"date": r.date.strftime("%Y-%m-%d"), "sales": round(float(r.sales), 2),
                 "expenses": round(float(r.expenses), 2), "balance": round(float(r.balance), 2),
                 "is_forecast": bool(f)}
                for r, f in zip(bal.itertuples(), sales["is_forecast"])
            ],
            "past_gaps": self.past_gaps(merchant_id),
            "is_synthetic_expense": True,
        }

    def past_gaps(self, merchant_id: int) -> list[dict]:
        return past_gaps(self.sales[merchant_id], self._store_expenses(merchant_id),
                         self.gaps[merchant_id]["opening_balance"])

    def cash_flow_gaps(self, merchant_id: int, min_buffer: float = 0.0) -> dict:
        """Re-run the WS2 gap finder so the minimum buffer can be changed per request."""
        return cash_flow_gaps(
            merchant_id, self.sales[merchant_id], self._store_expenses(merchant_id),
            self.gaps[merchant_id]["opening_balance"],
            projection_start=AS_OF + pd.Timedelta(days=1), min_buffer=min_buffer,
        )

    def copilot(self, merchant_id: int, question: str | None, history: list[dict]) -> dict:
        ctx = MerchantContext(
            merchant_id=merchant_id, as_of=AS_OF, forecast=self.forecasts[merchant_id],
            gaps=self.cash_flow_gaps(merchant_id), credit=self.credit[merchant_id],
            history=self.history[merchant_id], sales=self.sales[merchant_id],
            expenses=self._store_expenses(merchant_id), past_gaps=self.past_gaps(merchant_id),
            score_rank=score_rank(self.credit[merchant_id]["score"], [c["score"] for c in self.credit.values()]),
        )
        return explain(ctx, question, history)
