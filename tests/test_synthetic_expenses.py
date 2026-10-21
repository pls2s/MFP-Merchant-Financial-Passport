import pandas as pd

from ai.gap_detection.synthetic_expenses import ExpenseParams, generate, opening_balance

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


def test_opening_balance_is_days_of_expenses():
    params = ExpenseParams(opening_balance_days=(10, 10))
    exp = generate(STORES, "2015-01-01", "2015-06-30", params)
    ob = opening_balance(exp, params)
    assert ob[2] > ob[1] * 4.5
