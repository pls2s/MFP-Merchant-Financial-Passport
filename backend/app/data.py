"""Precomputed data loaded once at startup. The forecasting model is never run live;
gap detection and the copilot call the Workstream 2 modules directly."""

import json
from dataclasses import dataclass

import pandas as pd

from ai.cashflow_forecast.preprocess import ROSSMANN
from ai.copilot.explain import explain, load_dotenv
from ai.credit_signal.build import CREDIT_PATH
from ai.gap_detection.build import AS_OF, DEMO_STORES, EXPENSES_PATH, FORECASTS_PATH, GAPS_PATH, sales_series
from ai.gap_detection.gaps import cash_flow_gaps

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

    def cash_flow_gaps(self, merchant_id: int, min_buffer: float = 0.0) -> dict:
        """Re-run the WS2 gap finder so the minimum buffer can be changed per request."""
        sales = self.sales[merchant_id]
        expenses = self.expenses[(self.expenses["store"] == merchant_id) & (self.expenses["due_date"] >= sales["date"].min())]
        return cash_flow_gaps(
            merchant_id, sales, expenses, self.gaps[merchant_id]["opening_balance"],
            projection_start=AS_OF + pd.Timedelta(days=1), min_buffer=min_buffer,
        )

    def copilot(self, merchant_id: int, question: str | None) -> dict:
        return explain(
            merchant_id, self.forecasts[merchant_id], self.cash_flow_gaps(merchant_id), self.credit[merchant_id],
            AS_OF.strftime("%Y-%m-%d"), question,
        )
