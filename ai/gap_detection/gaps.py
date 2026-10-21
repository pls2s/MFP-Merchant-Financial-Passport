"""Deterministic cash-flow simulation and gap finder.

    B_t = B_{t-1} + S_t - E_t

B = balance, S = sales (actual for history, forecast for the projection),
E = synthetic expenses due that day. A gap is a run of consecutive days with the
balance below `min_buffer`; it is reported on its first day, with the shortfall
needed to stay at `min_buffer` through the whole run and the expenses that caused it.

All expenses are synthetic, so every result carries `is_synthetic_expense: true`.
"""

import pandas as pd

CONTRIBUTOR_LOOKBACK_DAYS = 7  # expenses due this many days before a gap also count as causes


def simulate_balance(sales: pd.DataFrame, expenses: pd.DataFrame, opening_balance: float) -> pd.DataFrame:
    """Daily balance.

    sales     columns: date, sales  (one row per day, in order)
    expenses  columns: due_date, amount  (any number per day)
    """
    due = expenses.groupby("due_date")["amount"].sum()
    out = sales[["date", "sales"]].copy().reset_index(drop=True)
    out["expenses"] = out["date"].map(due).fillna(0.0)
    out["balance"] = opening_balance + (out["sales"] - out["expenses"]).cumsum()
    return out


def find_gaps(balance: pd.DataFrame, expenses: pd.DataFrame, min_buffer: float = 0.0,
              start: pd.Timestamp | None = None) -> list[dict]:
    """Gaps in `balance` (from simulate_balance), only on or after `start` if given.

    Each gap: first day below `min_buffer`, the balance that day, the shortfall
    (min_buffer - lowest balance in the run) and contributing expenses, largest first.
    """
    below = balance["balance"] < min_buffer
    if start is not None:
        below &= balance["date"] >= start
    run_id = (below != below.shift(fill_value=False)).cumsum()

    gaps = []
    for _, run in balance[below].groupby(run_id[below]):
        first, lowest = run.iloc[0], run.loc[run["balance"].idxmin()]
        window_start = first["date"] - pd.Timedelta(days=CONTRIBUTOR_LOOKBACK_DAYS - 1)
        causes = expenses[(expenses["due_date"] >= window_start) & (expenses["due_date"] <= lowest["date"])]
        gaps.append({
            "date": first["date"].strftime("%Y-%m-%d"),
            "shortfall": round(float(min_buffer - lowest["balance"]), 2),
            "balance_after": round(float(first["balance"]), 2),
            "contributors": [
                {
                    "type": row.type,
                    "label": row.label,
                    "amount": round(float(row.amount), 2),
                    "due_date": row.due_date.strftime("%Y-%m-%d"),
                }
                for row in causes.sort_values("amount", ascending=False).itertuples()
            ],
        })
    return gaps


def cash_flow_gaps(merchant_id: int, sales: pd.DataFrame, expenses: pd.DataFrame, opening_balance: float,
                   projection_start: pd.Timestamp, min_buffer: float = 0.0) -> dict:
    """`cash-flow-gaps` contract object. Only gaps in the projection (forecast) window are reported."""
    balance = simulate_balance(sales, expenses, opening_balance)
    return {
        "merchant_id": int(merchant_id),
        "opening_balance": round(float(opening_balance), 2),
        "gaps": find_gaps(balance, expenses, min_buffer, start=projection_start),
        "is_synthetic_expense": True,
    }
