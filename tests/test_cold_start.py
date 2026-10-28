import io

import numpy as np
import pandas as pd
import pytest

from ai.cashflow_forecast.cold_start import MIN_DAYS, SalesFileError, daily_sales, level_factor, read_file


def transactions(days=MIN_DAYS + 10):
    dates = pd.date_range("2011-01-01 09:00", periods=days, freq="D")
    rows = [{"InvoiceDate": d, "Quantity": 2, "UnitPrice": 5.0} for d in dates if d.dayofweek != 5]  # closed Saturdays
    rows.append({"InvoiceDate": dates[3], "Quantity": -1, "UnitPrice": 5.0})  # a cancellation
    return pd.DataFrame(rows)


def test_transactions_become_a_contiguous_daily_series():
    daily = daily_sales(transactions())
    assert (daily["date"].diff().dropna() == pd.Timedelta(days=1)).all()
    sat = daily[daily["date"].dt.dayofweek == 5]
    assert (sat["sales"] == 0).all() and (sat["open"] == 0).all()
    day4 = daily.set_index("date").loc["2011-01-04", "sales"]
    assert day4 == 5.0  # 10 sold, 5 cancelled


def test_daily_file_with_thai_or_english_headers():
    d = pd.DataFrame({"วันที่": pd.date_range("2024-01-01", periods=MIN_DAYS).astype(str), "ยอดขาย": 100.0})
    assert len(daily_sales(d)) == MIN_DAYS
    csv = io.BytesIO(b"date,sales\n" + b"".join(f"2024-03-{i % 28 + 1:02d},10\n".encode() for i in range(3)))
    with pytest.raises(SalesFileError, match="อย่างน้อย"):
        daily_sales(read_file(csv, "x.csv"))


def test_missing_columns_are_explained():
    with pytest.raises(SalesFileError, match="วันที่"):
        daily_sales(pd.DataFrame({"x": [1]}))
    with pytest.raises(SalesFileError, match="ยอดขาย"):
        daily_sales(pd.DataFrame({"date": ["2024-01-01"]}))


def test_level_factor_learns_only_from_given_blocks():
    assert level_factor([]) == 1.0
    blocks = [(np.array([10.0, 10.0]), np.array([5.0, 5.0])), (np.array([30.0]), np.array([15.0]))]
    assert level_factor(blocks) == pytest.approx(2.0)
