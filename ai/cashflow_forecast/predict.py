"""Export Test-period forecasts for every store in the `forecast` contract shape.

Usage:
    python -m ai.cashflow_forecast.predict --model lstm

Reads   data/processed/rossmann.parquet, models/predictions/<model>.parquet
Writes  models/forecasts/<model>.json   (list of contract objects, one per store)

The backend loads this file at startup; the model is never run live.
"""

import argparse
import json

import pandas as pd

from ai.cashflow_forecast.evaluate import PREDICTIONS_DIR, score
from ai.cashflow_forecast.preprocess import PROCESSED_PATH, ROOT
from ai.cashflow_forecast.train import HORIZON

FORECASTS_DIR = ROOT / "models" / "forecasts"
MODEL_VERSION = "v1"


def export(model: str) -> list[dict]:
    actuals = pd.read_parquet(PROCESSED_PATH, columns=["store", "date", "sales", "is_eval_day"])
    preds = pd.read_parquet(PREDICTIONS_DIR / f"{model}.parquet")
    preds = preds[preds["split"] == "test"][["store", "date", "forecast"]]
    merged = preds.merge(actuals, on=["store", "date"], how="left").sort_values(["store", "date"])

    out = []
    for store, part in merged.groupby("store"):
        metrics = score(part[["store", "date", "forecast"]], part[["store", "date", "sales", "is_eval_day"]])
        out.append({
            "merchant_id": int(store),
            "model": f"{model}-{MODEL_VERSION}",
            "horizon_days": HORIZON,
            "points": [
                {"date": d.strftime("%Y-%m-%d"), "forecast": round(float(f), 2), "actual": round(float(a), 2)}
                for d, f, a in zip(part["date"], part["forecast"], part["sales"])
            ],
            "metrics": {k: round(metrics[k], 4) for k in ("wape", "mae", "rmse")},
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="lstm", choices=["seasonal_naive", "lightgbm", "lstm", "gru"])
    args = parser.parse_args()

    forecasts = export(args.model)
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)
    path = FORECASTS_DIR / f"{args.model}.json"
    path.write_text(json.dumps(forecasts, ensure_ascii=False))
    print(f"Saved {len(forecasts)} stores → {path}")


if __name__ == "__main__":
    main()
