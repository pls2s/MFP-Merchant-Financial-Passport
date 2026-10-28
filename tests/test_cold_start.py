import numpy as np
import pytest

from ai.cashflow_forecast.cold_start import MIN_DAYS, SalesFileError, level_factor, load_sales


def test_load_sales_needs_enough_days():
    rows = "date,sales\n" + "".join(f"2024-01-{d:02d},10\n" for d in range(1, 31))
    with pytest.raises(SalesFileError, match=f"อย่างน้อย {MIN_DAYS} วัน"):
        load_sales(rows.encode(), "x.csv")


def test_level_factor_learns_only_from_given_blocks():
    assert level_factor([]) == 1.0
    blocks = [(np.array([10.0, 10.0]), np.array([5.0, 5.0])), (np.array([30.0]), np.array([15.0]))]
    assert level_factor(blocks) == pytest.approx(2.0)
