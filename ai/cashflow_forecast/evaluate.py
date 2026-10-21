"""Report WAPE, MAE and RMSE on open days in the Test period.

Usage:
    python -m ai.cashflow_forecast.evaluate
    python -m ai.cashflow_forecast.evaluate --dataset favorita

Reads   data/processed/rossmann.parquet, models/predictions/*.parquet
Writes  models/results.csv
"""

import argparse

import numpy as np
import pandas as pd

from ai.cashflow_forecast.preprocess import DATASETS, ROSSMANN, Dataset

PREDICTIONS_DIR = ROSSMANN.predictions_dir
MODEL_ORDER = ["seasonal_naive", "lightgbm", "lstm", "gru", "ensemble"]


def wape(y: np.ndarray, y_hat: np.ndarray) -> float:
    return float(np.abs(y - y_hat).sum() / np.abs(y).sum())


def mae(y: np.ndarray, y_hat: np.ndarray) -> float:
    return float(np.abs(y - y_hat).mean())


def rmse(y: np.ndarray, y_hat: np.ndarray) -> float:
    return float(np.sqrt(((y - y_hat) ** 2).mean()))


def score(predictions: pd.DataFrame, actuals: pd.DataFrame) -> dict[str, float]:
    """Score forecasts on evaluated days only (open, not missing, not zero-sales-open)."""
    df = predictions.merge(actuals, on=["store", "date"], how="inner")
    df = df[df["is_eval_day"] == 1]
    y, y_hat = df["sales"].to_numpy(), df["forecast"].to_numpy()
    return {"wape": wape(y, y_hat), "mae": mae(y, y_hat), "rmse": rmse(y, y_hat), "n_days": len(df)}


def results_table(ds: Dataset = ROSSMANN) -> pd.DataFrame:
    actuals = pd.read_parquet(ds.processed_path, columns=["store", "date", "sales", "is_eval_day"])
    rows = []
    for path in sorted(ds.predictions_dir.glob("*.parquet")):
        preds = pd.read_parquet(path)
        for split in ("val", "test"):
            part = preds[preds["split"] == split]
            if len(part):
                rows.append({"model": path.stem, "split": split, **score(part, actuals)})
    table = pd.DataFrame(rows)
    order = {m: i for i, m in enumerate(MODEL_ORDER)}
    return table.sort_values(["split", "model"], key=lambda c: c.map(order).fillna(99) if c.name == "model" else c)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=list(DATASETS), default="rossmann")
    ds = DATASETS[parser.parse_args().dataset]

    table = results_table(ds)
    path = ds.models_dir / "results.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    with pd.option_context("display.float_format", "{:,.4f}".format):
        print(table.to_string(index=False))
    print(f"Saved → {path}")


if __name__ == "__main__":
    main()
