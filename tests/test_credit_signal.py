import json

import numpy as np
import pandas as pd

from ai.credit_signal.signal import WEIGHTS, components, credit_signal

AS_OF = pd.Timestamp("2015-07-17")


def _history(weekly_growth=0.0, noise=0.0, seed=0):
    dates = pd.date_range(AS_OF - pd.Timedelta(days=200), AS_OF, freq="D")
    rng = np.random.default_rng(seed)
    weeks = (dates - dates[0]).days // 7
    sales = 1000.0 * (1 + weekly_growth) ** weeks * (1 + rng.normal(0, noise, len(dates)))
    is_open = (dates.dayofweek != 6).astype(int)
    return pd.DataFrame({"date": dates, "sales": sales * is_open, "open": is_open})


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1) < 1e-9


def test_steady_store_scores_high():
    comp = components(_history(), AS_OF, lowest_balance=50_000, avg_monthly_expenses=20_000, n_gaps=0)
    assert comp["consistency"] > 0.95
    assert abs(comp["trend"] - 0.5) < 0.05
    assert comp["active_days"] == 1.0
    assert comp["cash_buffer"] == 1.0
    assert comp["gap_frequency"] == 1.0


def test_growth_and_decline_move_trend():
    up = components(_history(weekly_growth=0.01), AS_OF, 1, 1, 0)["trend"]
    down = components(_history(weekly_growth=-0.01), AS_OF, 1, 1, 0)["trend"]
    assert up > 0.6 > 0.4 > down


def test_negative_balance_and_gaps_floor_at_zero():
    comp = components(_history(), AS_OF, lowest_balance=-5_000, avg_monthly_expenses=20_000, n_gaps=5)
    assert comp["cash_buffer"] == 0.0
    assert comp["gap_frequency"] == 0.0


def test_contract_shape_status_and_wording():
    gaps = [{"date": "2015-07-22", "shortfall": 3200.0}]
    result = credit_signal(1, _history(noise=0.3), AS_OF, lowest_balance=-3200,
                           lowest_date=pd.Timestamp("2015-07-22"), avg_monthly_expenses=20_000, gaps=gaps)
    assert set(result) == {"merchant_id", "score", "status", "components",
                           "positive_factors", "risk_indicators", "data_coverage"}
    assert result["status"] == "experimental"
    assert 0 <= result["score"] <= 100
    assert any("2015-07-22" in r and "3,200" in r for r in result["risk_indicators"])
    buffer_warning = next(r for r in result["risk_indicators"] if r.startswith("เงินสำรอง"))
    assert "-3,200" in buffer_warning and "2015-07-22" in buffer_warning and "20,000" in buffer_warning
    text = json.dumps(result, ensure_ascii=False).lower()
    assert "approve" not in text and "อนุมัติ" not in text
