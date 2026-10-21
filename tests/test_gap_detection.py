import pandas as pd

from ai.gap_detection.gaps import cash_flow_gaps, find_gaps, simulate_balance

DATES = pd.date_range("2015-07-18", periods=10, freq="D")


def _sales(amount=1000.0):
    return pd.DataFrame({"date": DATES, "sales": amount})


def _expenses(*items):
    """items: (day index, amount, type)"""
    return pd.DataFrame(
        [{"due_date": DATES[i], "amount": a, "type": t, "label": t} for i, a, t in items],
        columns=["due_date", "amount", "type", "label"],
    )


def test_balance_formula():
    exp = _expenses((1, 500.0, "rent"), (1, 200.0, "utilities"))
    bal = simulate_balance(_sales(), exp, opening_balance=100.0)
    # B_t = B_{t-1} + S_t - E_t
    assert bal["balance"].iloc[0] == 1100.0
    assert bal["balance"].iloc[1] == 1100.0 + 1000.0 - 700.0
    assert bal["expenses"].sum() == 700.0


def test_no_gap():
    exp = _expenses((3, 2000.0, "rent"))
    bal = simulate_balance(_sales(), exp, opening_balance=0.0)
    assert find_gaps(bal, exp) == []


def test_one_gap_with_contributors_largest_first():
    exp = _expenses((2, 1000.0, "utilities"), (2, 5000.0, "supplier_invoice"))
    bal = simulate_balance(_sales(), exp, opening_balance=0.0)
    # day 2: 3000 - 6000 = -3000; day 3: -2000; day 4: -1000; day 5: 0 (not below)
    gaps = find_gaps(bal, exp)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["date"] == "2015-07-20"
    assert gap["balance_after"] == -3000.0
    assert gap["shortfall"] == 3000.0
    assert [c["type"] for c in gap["contributors"]] == ["supplier_invoice", "utilities"]


def test_multiple_gaps():
    exp = _expenses((0, 1500.0, "rent"), (5, 7000.0, "supplier_invoice"))
    bal = simulate_balance(_sales(), exp, opening_balance=0.0)
    # day 0: -500 (gap 1), day 1: 500 ... day 4: 3500, day 5: 4500 - 7000 = -2500 (gap 2)
    gaps = find_gaps(bal, exp)
    assert [g["date"] for g in gaps] == ["2015-07-18", "2015-07-23"]
    assert [g["shortfall"] for g in gaps] == [500.0, 2500.0]


def test_min_buffer_flags_low_but_positive_balance():
    exp = _expenses((2, 2500.0, "supplier_invoice"))
    bal = simulate_balance(_sales(), exp, opening_balance=0.0)
    # day 2: 3000 - 2500 = 500, positive but below a 1000 buffer
    assert find_gaps(bal, exp, min_buffer=0.0) == []
    gaps = find_gaps(bal, exp, min_buffer=1000.0)
    assert len(gaps) == 1
    assert gaps[0]["date"] == "2015-07-20"
    assert gaps[0]["shortfall"] == 500.0


def test_shortfall_uses_lowest_point_of_the_run():
    exp = _expenses((2, 3500.0, "supplier_invoice"), (3, 2000.0, "payroll"))
    bal = simulate_balance(_sales(), exp, opening_balance=0.0)
    # day 2: -500, day 3: -1500 (lowest), day 4: -500, day 5: 500
    gap = find_gaps(bal, exp)[0]
    assert gap["balance_after"] == -500.0
    assert gap["shortfall"] == 1500.0
    assert {c["type"] for c in gap["contributors"]} == {"supplier_invoice", "payroll"}


def test_only_projection_window_reported_and_contract_shape():
    exp = _expenses((0, 1500.0, "rent"), (5, 7000.0, "supplier_invoice"))
    result = cash_flow_gaps(1, _sales(), exp, opening_balance=0.0, projection_start=DATES[3])
    assert set(result) == {"merchant_id", "opening_balance", "gaps", "is_synthetic_expense"}
    assert result["is_synthetic_expense"] is True
    assert [g["date"] for g in result["gaps"]] == ["2015-07-23"]
