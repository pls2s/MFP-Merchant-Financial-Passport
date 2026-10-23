import pandas as pd

from ai.gap_detection.synthetic_expenses import ExpenseParams, add_owner_draws, generate, reserve_target

STORES = pd.DataFrame({"store": [1, 2], "avg_daily_sales": [1000.0, 5000.0]})


def test_deterministic_with_seed():
    a = generate(STORES, "2015-01-01", "2015-03-31")
    b = generate(STORES, "2015-01-01", "2015-03-31")
    pd.testing.assert_frame_equal(a, b)


def test_schedule_and_labels():
    exp = generate(STORES, "2015-01-01", "2015-03-31")
    one = exp[exp["store"] == 1]
    rent = one[one["type"] == "rent"]
    assert list(rent["due_date"].dt.day) == [1, 1, 1]
    payroll_days = sorted(one[one["type"] == "payroll"]["due_date"].dt.strftime("%m-%d"))
    assert payroll_days == ["01-15", "01-31", "02-15", "02-28", "03-15", "03-31"]
    gaps = one[one["type"] == "supplier_invoice"]["due_date"].diff().dropna().dt.days.unique()
    assert len(gaps) == 1 and gaps[0] in (7, 14)
    assert exp["is_synthetic"].all()
    assert exp["label"].notna().all()


def test_expenses_scale_with_sales_and_leave_a_margin():
    exp = generate(STORES, "2015-01-01", "2015-06-30")
    days = 181
    per_day = exp.groupby("store")["amount"].sum() / days
    ratio = per_day / STORES.set_index("store")["avg_daily_sales"]
    # 0.60 supplier + 0.26 monthly costs ≈ 0.86 of sales
    assert ((ratio > 0.78) & (ratio < 0.94)).all()


def test_reserve_is_days_of_expenses():
    params = ExpenseParams(reserve_days=(10, 10))
    exp = generate(STORES, "2015-01-01", "2015-06-30", params)
    reserve = reserve_target(exp, params)
    assert reserve[2] > reserve[1] * 4.5


def test_owner_draws_sweep_cash_above_reserve():
    dates = pd.date_range("2015-01-01", "2015-03-31")
    sales = pd.DataFrame({"date": dates, "sales": 1000.0})
    exp = generate(STORES, "2015-01-01", "2015-03-31")
    exp = exp[exp["store"] == 1]
    draws = add_owner_draws(1, sales, exp, reserve=5000.0, until=pd.Timestamp("2015-02-28"))
    assert list(draws["due_date"].dt.strftime("%m-%d")) == ["01-25", "02-25"]  # none after `until`
    assert (draws["amount"] > 0).all() and (draws["type"] == "owner_draw").all()
    # Right after each draw the balance is back at the reserve.
    from ai.gap_detection.gaps import simulate_balance
    bal = simulate_balance(sales, pd.concat([exp, draws]), 5000.0).set_index("date")["balance"]
    assert abs(bal[pd.Timestamp("2015-01-25")] - 5000.0) < 0.01
    assert abs(bal[pd.Timestamp("2015-02-25")] - 5000.0) < 0.01
