"""Precomputed data loaded once at startup. The forecasting model is never run live;
gap detection and the copilot call the Workstream 2 modules directly."""

import json
from dataclasses import dataclass

import pandas as pd

from ai.cashflow_forecast.experiments import config_name, trained_cells
from ai.cashflow_forecast.preprocess import ROSSMANN
from ai.cashflow_forecast.long_range import FORECASTS_DIR
from ai.cashflow_forecast.predict import HISTORY_PATH
from ai.copilot.explain import explain, load_dotenv
from ai.copilot.facts import MerchantContext, score_rank
from ai.credit_signal.build import CREDIT_PATH
from ai.gap_detection.build import (
    AS_OF, DEMO_STORES, EXPENSES_PATH, FORECASTS_PATH, GAPS_PATH, past_gaps, sales_series,
)
from ai.gap_detection.gaps import cash_flow_gaps
from ai.gap_detection.shortfall_risk import CALIBRATION_PATH, RISK_PATH
from ai.gap_detection.long_balance import long_balance

RESULTS_PATH = ROSSMANN.models_dir / "results.csv"
EXPERIMENTS_DIR = ROSSMANN.models_dir / "experiments"
FAVORITA_RESULTS_PATH = ROSSMANN.models_dir / "favorita" / "results.csv"


def _by_merchant(path) -> dict[int, dict]:
    return {obj["merchant_id"]: obj for obj in json.loads(path.read_text())}


def _by_store(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    return {int(s): g.drop(columns="store").reset_index(drop=True) for s, g in df.groupby("store")}


def _num(x) -> float | None:
    return None if pd.isna(x) else round(float(x), 2)


def _experiments() -> dict:
    """Robustness results from `python -m ai.cashflow_forecast.experiments ...` (precomputed CSVs)."""
    ens = pd.read_csv(EXPERIMENTS_DIR / "seed_ensemble.csv")
    ens["model"] = ens["model"].str.removesuffix("_5seed")
    k = pd.read_csv(EXPERIMENTS_DIR / "seed_ensemble_k.csv")
    k = k[k["split"] == "test"].groupby(["model", "k"])["wape"].agg(["mean", "std", "min", "max"]).reset_index()
    k["std"] = k["std"].astype(object).where(k["std"].notna(), None)
    return {
        "seeds": pd.read_csv(EXPERIMENTS_DIR / "seeds.csv")[["seed", "model", "split", "wape"]].to_dict(orient="records"),
        "seed_ensemble": ens.drop(columns="n_runs").to_dict(orient="records"),
        "seed_ensemble_k": k.to_dict(orient="records"),
        "ablation": pd.read_csv(EXPERIMENTS_DIR / "ablation.csv")[["variant", "split", "wape"]].to_dict(orient="records"),
        "learning_curves": pd.read_csv(EXPERIMENTS_DIR / "learning_curves.csv").to_dict(orient="records"),
        "chosen_configs": {cell: config_name(cell) for cell in trained_cells()},
        "favorita": pd.read_csv(FAVORITA_RESULTS_PATH).to_dict(orient="records"),
    }


def _shortfall() -> dict[int, dict]:
    """Shortfall probabilities (ai.gap_detection.shortfall_risk) with the Test-period check attached."""
    cal = json.loads(CALIBRATION_PATH.read_text())
    day = cal["shortfall_day"]
    check = {
        "origins": cal["origins"],
        "sales_interval_80_coverage": cal["sales_interval_80"]["coverage"],
        **{k: day[k] for k in ("store_days", "events", "brier_probability", "brier_yes_no_warning", "brier_base_rate")},
    }
    return {o["merchant_id"]: {**o, "method": cal["method"], "check": check} for o in json.loads(RISK_PATH.read_text())}


@dataclass
class DataStore:
    forecasts: dict[int, dict]
    gaps: dict[int, dict]
    credit: dict[int, dict]
    sales: dict[int, pd.DataFrame]
    expenses: pd.DataFrame
    results: pd.DataFrame
    history: dict[int, pd.DataFrame]
    long_points: dict[int, pd.DataFrame]
    long_back: dict[int, pd.DataFrame]
    seasonal_months: dict[int, pd.DataFrame]
    seasonal_back: dict[int, pd.DataFrame]
    long_metrics: dict
    synthetic_sales: dict[int, pd.DataFrame]
    experiments: dict
    shortfall: dict[int, dict]

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
            history=_by_store(pd.read_parquet(HISTORY_PATH)),
            long_points=_by_store(pd.read_parquet(FORECASTS_DIR / "long_forecast.parquet")),
            long_back=_by_store(pd.read_parquet(FORECASTS_DIR / "long_backtest.parquet")),
            seasonal_months=_by_store(pd.read_parquet(FORECASTS_DIR / "seasonal_outlook.parquet")),
            seasonal_back=_by_store(pd.read_parquet(FORECASTS_DIR / "seasonal_backtest.parquet")),
            long_metrics=json.loads((FORECASTS_DIR / "long_range_metrics.json").read_text()),
            synthetic_sales=_by_store(pd.read_parquet(FORECASTS_DIR / "synthetic_sales.parquet")),
            experiments=_experiments(),
            shortfall=_shortfall(),
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

    def sales_history(self, merchant_id: int, days: int, synthetic_days: int = 366) -> dict:
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
            "synthetic": {
                "label": "ยอดขายจำลอง (ไม่ใช่ข้อมูลจริง)",
                "method": "Same weekday in the last real year × the store's 12-week trend (capped ±10%/year) × random noise",
                "points": [{"date": r.date.strftime("%Y-%m-%d"), "sales": round(float(r.sales), 2)}
                           for r in self.synthetic_sales[merchant_id].head(synthetic_days).itertuples()],
            },
        }

    def long_forecast(self, merchant_id: int) -> dict:
        m = self.long_metrics["recursive_3_months"]
        back = self.long_back[merchant_id]
        return {
            "merchant_id": merchant_id,
            "method": "LSTM+GRU ensemble rolled forward 14 days at a time (forecasts fed back as input)",
            "points": [{"date": r.date.strftime("%Y-%m-%d"), "forecast": _num(r.forecast), "lower": _num(r.lower),
                        "upper": _num(r.upper), "synthetic_inputs": bool(r.synthetic_inputs)}
                       for r in self.long_points[merchant_id].itertuples()],
            "backtest": {
                "origin": m["origin"], "days": m["days"], "wape_store": m["wape_by_store"].get(str(merchant_id)),
                "wape_all_stores": m["wape_all_stores"], "wape_by_block": m["wape_by_block"],
                "points": [{"date": r.date.strftime("%Y-%m-%d"), "forecast": _num(r.forecast), "actual": _num(r.actual)}
                           for r in back.itertuples()],
            },
        }

    def seasonal_outlook(self, merchant_id: int) -> dict:
        m = self.long_metrics["seasonal_1_year"]
        return {
            "merchant_id": merchant_id,
            "method": "Same month last year × change of the last 12 weeks vs a year earlier (not a deep-learning forecast)",
            "months": [{"month": r.month, "outlook": _num(r.outlook), "lower": _num(r.lower), "upper": _num(r.upper),
                        "backtested": bool(r.backtested)}
                       for r in self.seasonal_months[merchant_id].itertuples()],
            "backtest": {
                "origin": m["origin"], "wape_store": m["wape_by_store"].get(str(merchant_id)),
                "wape_all_stores": m["wape_all_stores"],
                "months": [{"month": r.month, "outlook": _num(r.outlook), "actual": _num(r.actual)}
                           for r in self.seasonal_back[merchant_id].itertuples()],
            },
        }

    def _store_expenses(self, merchant_id: int) -> pd.DataFrame:
        start = self.sales[merchant_id]["date"].min()
        return self.expenses[(self.expenses["store"] == merchant_id) & (self.expenses["due_date"] >= start)]

    def cash_balance(self, merchant_id: int) -> dict:
        """Balance from 2015-01-01 to LONG_END: actual sales, then the 14-day forecast, then the
        longer projection (see ai.gap_detection.long_balance)."""
        bal, long_gaps = long_balance(
            merchant_id, self.sales[merchant_id], self._store_expenses(merchant_id),
            self.gaps[merchant_id]["opening_balance"], self.long_points[merchant_id], self.seasonal_months[merchant_id],
        )
        return {
            "merchant_id": merchant_id,
            "opening_balance": self.gaps[merchant_id]["opening_balance"],
            "points": [
                {"date": r.date.strftime("%Y-%m-%d"), "sales": round(float(r.sales), 2),
                 "expenses": round(float(r.expenses), 2), "balance": round(float(r.balance), 2),
                 "is_forecast": r.horizon != "actual", "horizon": r.horizon}
                for r in bal.itertuples()
            ],
            "past_gaps": self.past_gaps(merchant_id),
            "long_gaps": long_gaps,
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
            long_forecast=self.long_points[merchant_id], seasonal=self.seasonal_months[merchant_id],
            long_metrics=self.long_metrics,
            score_rank=score_rank(self.credit[merchant_id]["score"], [c["score"] for c in self.credit.values()]),
        )
        return explain(ctx, question, history)
