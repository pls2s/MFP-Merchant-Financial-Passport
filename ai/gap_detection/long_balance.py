"""Longer cash-balance projection for the 3-month / 1-year views. ข้อมูลจำลอง — less certain
than the 14-day projection, and never part of the `cash-flow-gaps` contract.

Sales after the 14-day forecast (horizon tag per day):
    .. 2015-07-17            actual sales                                   "actual"
    2015-07-18 .. 2015-07-31 14-day LSTM+GRU forecast                       "14d"
    2015-08-01 .. 2015-10-09 recursive LSTM+GRU rollout (long_forecast)     "3m"
    2015-10-10 .. 2016-07-31 monthly outlook spread over the days of the    "1y"
                             month by the store's weekday pattern (holidays ignored).
                             Stores without an outlook (no sales a year earlier) use the
                             rollout's average day instead.

Expenses after 2015-07-31 continue each store's synthetic pattern: the same supplier cycle and
average invoice, the same rent and payroll, utilities with the same noise. The owner keeps
withdrawing cash above the reserve on the 25th, as in the history.
"""

import numpy as np
import pandas as pd

from ai.gap_detection.gaps import find_gaps, simulate_balance
from ai.gap_detection.synthetic_expenses import LABELS, ExpenseParams, add_owner_draws

LONG_START = pd.Timestamp("2015-08-01")
LONG_END = pd.Timestamp("2016-07-31")
SEED_OFFSET = 1000  # rng seed = params.seed + SEED_OFFSET + store, so the base expenses are untouched


def weekday_shares(sales: pd.DataFrame) -> np.ndarray:
    """Average actual sales per weekday (Mon=0), from the non-forecast rows."""
    actual = sales[~sales["is_forecast"]]
    mean = actual.groupby(actual["date"].dt.weekday)["sales"].mean()
    return mean.reindex(range(7), fill_value=0.0).to_numpy()


def long_sales(sales: pd.DataFrame, long_forecast: pd.DataFrame, seasonal: pd.DataFrame,
               end: pd.Timestamp = LONG_END) -> pd.DataFrame:
    """Daily sales to `end` with a `horizon` column.

    sales          columns: date, sales, is_forecast (actual + 14-day forecast, from build.sales_series)
    long_forecast  columns: date, forecast (84-day rollout)
    seasonal       columns: month ("YYYY-MM"), outlook (monthly total)
    """
    base = sales[["date", "sales"]].assign(horizon=np.where(sales["is_forecast"], "14d", "actual"))
    roll = long_forecast[long_forecast["date"] > base["date"].max()]
    roll = pd.DataFrame({"date": roll["date"], "sales": roll["forecast"].clip(lower=0), "horizon": "3m"})

    shares = weekday_shares(sales)
    totals = seasonal.set_index("month")["outlook"].dropna()
    fallback_per_day = roll["sales"].mean()
    days = pd.date_range(roll["date"].max() + pd.Timedelta(days=1), end, freq="D")
    rows = []
    for month, in_range in pd.Series(days).groupby(days.strftime("%Y-%m")):
        whole = pd.date_range(f"{month}-01", periods=pd.Period(month).days_in_month, freq="D")
        weight = shares[whole.weekday].sum()
        total = totals.get(month, fallback_per_day * len(whole))
        per_unit = total / weight if weight else 0.0
        rows += [(d, per_unit * shares[d.weekday()]) for d in in_range]
    monthly = pd.DataFrame(rows, columns=["date", "sales"]).assign(horizon="1y")
    return pd.concat([base, roll, monthly], ignore_index=True)


def extend_expenses(store: int, expenses: pd.DataFrame, start: pd.Timestamp = LONG_START,
                    end: pd.Timestamp = LONG_END, params: ExpenseParams = ExpenseParams()) -> pd.DataFrame:
    """Continue the store's baseline expenses from `start` to `end` (same columns as `generate`)."""
    rng = np.random.default_rng(params.seed + SEED_OFFSET + store)
    base = expenses[expenses["scenario"] == "baseline"]
    rows = []

    supplier = base[base["type"] == "supplier_invoice"].sort_values("due_date")
    cycle = int(supplier["due_date"].diff().dt.days.mode().iloc[0])
    invoice = supplier["amount"].mean()
    due = supplier["due_date"].max() + pd.Timedelta(days=cycle)
    while due <= end:
        if due >= start:
            noise = 1 + rng.uniform(-params.supplier_noise, params.supplier_noise)
            rows.append((due, "supplier_invoice", invoice * noise))
        due += pd.Timedelta(days=cycle)

    last = {t: base.loc[base["type"] == t, "amount"] for t in ("rent", "payroll", "utilities")}
    for m in pd.date_range(start.to_period("M").to_timestamp(), end, freq="MS"):
        rows.append((m, "rent", last["rent"].iloc[-1]))
        rows.append((m + pd.Timedelta(days=14), "payroll", last["payroll"].iloc[-1]))
        rows.append((m + pd.offsets.MonthEnd(0), "payroll", last["payroll"].iloc[-1]))
        noise = 1 + rng.uniform(-params.utilities_noise, params.utilities_noise)
        rows.append((m + pd.Timedelta(days=19), "utilities", last["utilities"].mean() * noise))

    out = pd.DataFrame(rows, columns=["due_date", "type", "amount"])
    out = out[(out["due_date"] >= start) & (out["due_date"] <= end)].copy()
    out.insert(0, "store", store)
    out["amount"] = out["amount"].round(2)
    out["label"] = out["type"].map(LABELS)
    out["scenario"] = "baseline_extended"
    out["is_synthetic"] = True
    return out[expenses.columns].sort_values("due_date").reset_index(drop=True)


def long_balance(store: int, sales: pd.DataFrame, expenses: pd.DataFrame, opening: float,
                 long_forecast: pd.DataFrame, seasonal: pd.DataFrame,
                 params: ExpenseParams = ExpenseParams()) -> tuple[pd.DataFrame, list[dict]]:
    """Daily balance to LONG_END (columns: date, sales, expenses, balance, horizon) and the gaps
    from LONG_START on, each tagged with the horizon of its first day."""
    s = long_sales(sales, long_forecast, seasonal)
    exp = pd.concat([expenses, extend_expenses(store, expenses, params=params)], ignore_index=True)
    draws = add_owner_draws(store, s, exp, opening, LONG_END, params, since=LONG_START)
    if len(draws):
        exp = pd.concat([exp, draws], ignore_index=True)
    bal = simulate_balance(s, exp, opening).assign(horizon=s["horizon"].to_numpy())
    horizon = dict(zip(bal["date"].dt.strftime("%Y-%m-%d"), bal["horizon"]))
    gaps = [{**g, "horizon": horizon[g["date"]]} for g in find_gaps(bal, exp, start=LONG_START)]
    return bal, gaps
