"""Compute the experimental credit signal for every store.

Usage:
    python -m ai.gap_detection.build      # first: expenses + gaps
    python -m ai.credit_signal.build

Reads   data/processed/rossmann.parquet      (actual sales history up to the demo date)
        data/synthetic/expenses.parquet, data/synthetic/cash_flow_gaps.json
        models/forecasts/ensemble.json
Writes  data/synthetic/credit_signal.json    (`credit-signal` contract, one object per store)
"""

import json

import pandas as pd

from ai.cashflow_forecast.preprocess import PROCESSED_PATH
from ai.credit_signal.signal import credit_signal
from ai.gap_detection.build import AS_OF, EXPENSES_PATH, GAPS_PATH, SYNTHETIC_DIR, past_gaps, sales_series
from ai.gap_detection.gaps import simulate_balance

CREDIT_PATH = SYNTHETIC_DIR / "credit_signal.json"


def build() -> list[dict]:
    history = pd.read_parquet(PROCESSED_PATH, columns=["store", "date", "sales", "open", "is_missing"])
    history = history[(history["is_missing"] == 0) & (history["date"] <= AS_OF)]
    expenses = pd.read_parquet(EXPENSES_PATH)
    gaps = {g["merchant_id"]: g for g in json.loads(GAPS_PATH.read_text(encoding="utf-8"))}
    series = sales_series()

    months = (expenses["due_date"].max() - expenses["due_date"].min()).days / 30
    # Operating costs only: owner withdrawals are profit taken out, not an expense of running the store.
    operating = expenses[(expenses["scenario"] == "baseline") & (expenses["type"] != "owner_draw")]
    monthly_expenses = operating.groupby("store")["amount"].sum() / months

    out = []
    for store, s in sorted(series.items()):
        store_exp = expenses[(expenses["store"] == store) & (expenses["due_date"] >= s["date"].min())]
        balance = simulate_balance(s, store_exp, gaps[store]["opening_balance"])
        projection = balance[balance["date"] > AS_OF]
        low = projection.loc[projection["balance"].idxmin()]
        out.append(credit_signal(
            store, history[history["store"] == store], AS_OF, float(low["balance"]), low["date"],
            float(monthly_expenses[store]), gaps[store]["gaps"],
            past_gaps(s, store_exp, gaps[store]["opening_balance"]),
        ))
    return out


def main() -> None:
    signals = build()
    CREDIT_PATH.write_text(json.dumps(signals, ensure_ascii=False), encoding="utf-8")
    scores = pd.Series([s["score"] for s in signals])
    print(f"Saved credit signal for {len(signals)} stores → {CREDIT_PATH}")
    print(f"Score: mean {scores.mean():.0f}, min {scores.min()}, median {scores.median():.0f}, max {scores.max()}")


if __name__ == "__main__":
    main()
