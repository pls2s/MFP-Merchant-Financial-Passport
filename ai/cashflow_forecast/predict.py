"""Export Test-period forecasts for every store in the `forecast` contract shape.

Usage:
    python -m ai.cashflow_forecast.predict --model ensemble

Reads   data/processed/rossmann.parquet, models/predictions/<model>.parquet
Writes  models/forecasts/<model>.json   (list of contract objects, one per store)
        models/forecasts/sales_history.parquet   (daily sales + known-in-advance flags, last year)

The backend loads this file at startup; the model is never run live.

`lower` / `upper` form an 80% split-conformal interval: relative errors
(actual - forecast) / forecast on Validation open days give the 10th and 90th
percentiles for each horizon day 1-14, which are then applied to Test forecasts.
"""

import argparse
import json

import numpy as np
import pandas as pd

from ai.cashflow_forecast.evaluate import PREDICTIONS_DIR, score
from ai.cashflow_forecast.preprocess import HORIZON, PROCESSED_PATH, ROOT
from ai.cashflow_forecast.train import TEST_ORIGINS, VAL_ORIGINS

FORECASTS_DIR = ROOT / "models" / "forecasts"
HISTORY_PATH = FORECASTS_DIR / "sales_history.parquet"
HISTORY_DAYS = 365  # shown before the Test period so the dashboard has real context
MODEL_VERSION = "v2"  # v2: LSTM+GRU averaged over 5 seeds
INTERVAL = 0.8


def add_horizon(preds: pd.DataFrame) -> pd.DataFrame:
    """Horizon day 1-14 relative to the block's origin."""
    preds = preds.copy()
    preds["horizon"] = 0
    for split, origins in (("val", VAL_ORIGINS), ("test", TEST_ORIGINS)):
        m = preds["split"] == split
        preds.loc[m, "horizon"] = (preds.loc[m, "date"] - origins[0]).dt.days.sub(1) % HORIZON + 1
    return preds


def conformal_quantiles(val: pd.DataFrame, interval: float = INTERVAL) -> pd.DataFrame:
    """Per-horizon quantiles of relative error on evaluated Validation days."""
    v = val[(val["is_eval_day"] == 1) & (val["forecast"] > 0)]
    rel = (v["sales"] - v["forecast"]) / v["forecast"]
    alpha = (1 - interval) / 2
    return rel.groupby(v["horizon"]).quantile([alpha, 1 - alpha]).unstack().set_axis(["q_lo", "q_hi"], axis=1)


def add_interval(test: pd.DataFrame, quantiles: pd.DataFrame) -> pd.DataFrame:
    test = test.join(quantiles, on="horizon")
    test["lower"] = (test["forecast"] * (1 + test["q_lo"])).clip(lower=0)
    test["upper"] = test["forecast"] * (1 + test["q_hi"])
    return test.drop(columns=["q_lo", "q_hi"])


def coverage(test: pd.DataFrame) -> tuple[float, float]:
    """Share of evaluated Test days inside [lower, upper], and mean width relative to forecast."""
    t = test[test["is_eval_day"] == 1]
    inside = (t["sales"] >= t["lower"]) & (t["sales"] <= t["upper"])
    width = ((t["upper"] - t["lower"]) / t["forecast"]).mean()
    return float(inside.mean()), float(width)


def export(model: str) -> list[dict]:
    actuals = pd.read_parquet(PROCESSED_PATH, columns=["store", "date", "sales", "is_eval_day"])
    preds = pd.read_parquet(PREDICTIONS_DIR / f"{model}.parquet")[["store", "date", "split", "forecast"]]
    merged = add_horizon(preds.merge(actuals, on=["store", "date"], how="left"))

    quantiles = conformal_quantiles(merged[merged["split"] == "val"])
    test = add_interval(merged[merged["split"] == "test"], quantiles).sort_values(["store", "date"])
    cov, width = coverage(test)
    print(f"{INTERVAL:.0%} interval on Test: coverage {cov:.1%}, mean width {width:.1%} of forecast")

    out = []
    for store, part in test.groupby("store"):
        metrics = score(part[["store", "date", "forecast"]], part[["store", "date", "sales", "is_eval_day"]])
        out.append({
            "merchant_id": int(store),
            "model": f"{model}-{MODEL_VERSION}",
            "horizon_days": HORIZON,
            "points": [
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "forecast": round(float(f), 2),
                    "lower": round(float(lo), 2),
                    "upper": round(float(hi), 2),
                    "actual": round(float(a), 2),
                }
                for d, f, lo, hi, a in zip(
                    part["date"], part["forecast"], part["lower"], part["upper"], part["sales"]
                )
            ],
            "metrics": {k: round(metrics[k], 4) for k in ("wape", "mae", "rmse")},
        })
    return out


def export_history() -> pd.DataFrame:
    """Actual daily sales for the year before the Test period through its end, with the
    known-in-advance flags that explain spikes (promo, holidays, open). Missing store-days stay null."""
    cols = ["store", "date", "sales", "open", "promo", "state_holiday", "school_holiday", "is_missing"]
    df = pd.read_parquet(PROCESSED_PATH, columns=cols)
    start = TEST_ORIGINS[0] - pd.Timedelta(days=HISTORY_DAYS - 1)
    df = df[df["date"] >= start].copy()
    df["sales"] = df["sales"].where(df["is_missing"] == 0).astype("float32")
    df["holiday"] = (df["state_holiday"] > 0).astype("int8")
    return df.drop(columns=["state_holiday", "is_missing"]).sort_values(["store", "date"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="ensemble", choices=["seasonal_naive", "lightgbm", "lstm", "gru", "tcn", "transformer", "ensemble"])
    args = parser.parse_args()

    forecasts = export(args.model)
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)
    path = FORECASTS_DIR / f"{args.model}.json"
    path.write_text(json.dumps(forecasts, ensure_ascii=False))
    print(f"Saved {len(forecasts)} stores → {path}")

    history = export_history()
    history.to_parquet(HISTORY_PATH, index=False)
    print(f"Saved {len(history):,} days of sales history → {HISTORY_PATH}")


if __name__ == "__main__":
    main()
