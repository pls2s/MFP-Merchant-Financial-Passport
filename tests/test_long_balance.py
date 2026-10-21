import numpy as np
import pandas as pd

from ai.gap_detection.long_balance import LONG_END, LONG_START, extend_expenses, long_balance, long_sales


def _sales(end="2015-07-31", as_of="2015-07-17"):
    days = pd.date_range("2015-01-01", end, freq="D")
    sales = np.where(days.weekday == 6, 0.0, 1000.0)
    return pd.DataFrame({"date": days, "sales": sales, "is_forecast": days > pd.Timestamp(as_of)})


def _rollout():
    days = pd.date_range("2015-07-18", periods=84, freq="D")
    return pd.DataFrame({"date": days, "forecast": np.where(days.weekday == 6, 0.0, 900.0)})


def _expenses(store=1):
    rows = [(d, "supplier_invoice", 4000.0) for d in pd.date_range("2015-01-03", "2015-07-31", freq="7D")]
    for m in pd.date_range("2015-01-01", "2015-07-01", freq="MS"):
        rows += [(m, "rent", 2000.0), (m + pd.Timedelta(days=14), "payroll", 1500.0),
                 (m + pd.offsets.MonthEnd(0), "payroll", 1500.0), (m + pd.Timedelta(days=19), "utilities", 600.0)]
    df = pd.DataFrame(rows, columns=["due_date", "type", "amount"])
    df.insert(0, "store", store)
    return df.assign(label=df["type"], scenario="baseline", is_synthetic=True)


def test_long_sales_horizons_and_monthly_totals():
    seasonal = pd.DataFrame({"month": ["2015-11"], "outlook": [26000.0]})
    s = long_sales(_sales(), _rollout(), seasonal)
    assert s["date"].is_monotonic_increasing and s["date"].iloc[-1] == LONG_END
    assert s.groupby("horizon")["date"].min().astype(str).to_dict() == {
        "actual": "2015-01-01", "14d": "2015-07-18", "3m": "2015-08-01", "1y": "2015-10-10"}
    nov = s[s["date"].dt.strftime("%Y-%m") == "2015-11"]
    assert abs(nov["sales"].sum() - 26000.0) < 1e-6
    assert (nov.loc[nov["date"].dt.weekday == 6, "sales"] == 0).all()  # closed weekday stays closed
    # months without an outlook fall back to the rollout's average day
    dec = s[s["date"].dt.strftime("%Y-%m") == "2015-12"]
    assert dec["sales"].notna().all() and dec["sales"].sum() > 0


def test_extend_expenses_keeps_cycle_and_amounts():
    ext = extend_expenses(1, _expenses())
    assert ext["due_date"].min() >= LONG_START and ext["due_date"].max() <= LONG_END
    sup = ext[ext["type"] == "supplier_invoice"]["due_date"]
    assert (sup.diff().dropna().dt.days == 7).all()
    assert (ext.loc[ext["type"] == "rent", "amount"] == 2000.0).all()
    assert (ext["scenario"] == "baseline_extended").all() and ext["is_synthetic"].all()


def test_long_balance_keeps_history_and_draws_on_the_25th():
    sales, exp = _sales(), _expenses()
    bal, gaps = long_balance(1, sales, exp, 5000.0, _rollout(), pd.DataFrame({"month": [], "outlook": []}))
    first = bal[bal["date"] <= "2015-07-31"]
    expected = 5000.0 + (sales["sales"] - sales["date"].map(exp.groupby("due_date")["amount"].sum()).fillna(0)).cumsum()
    assert np.allclose(first["balance"].to_numpy(), expected.to_numpy())
    # owner draws keep the balance from piling up over a year
    assert bal["balance"].iloc[-1] < bal[bal["date"] <= "2015-07-31"]["balance"].max() + 30000
    assert all(g["date"] >= "2015-08-01" for g in gaps)
