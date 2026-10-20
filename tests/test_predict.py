import numpy as np
import pandas as pd

from ai.cashflow_forecast.predict import add_interval, conformal_quantiles, coverage


def _frame(forecast, sales, horizon):
    n = len(forecast)
    return pd.DataFrame({
        "forecast": forecast, "sales": sales, "horizon": horizon, "is_eval_day": np.ones(n, int),
    })


def test_quantiles_are_per_horizon_relative_errors():
    rng = np.random.default_rng(0)
    rel = rng.uniform(-0.1, 0.1, 2000)
    val = _frame(np.full(2000, 1000.0), 1000.0 * (1 + rel), np.repeat([1, 2], 1000))
    q = conformal_quantiles(val, interval=0.8)
    assert list(q.index) == [1, 2]
    assert np.allclose(q["q_lo"], -0.08, atol=0.01)
    assert np.allclose(q["q_hi"], 0.08, atol=0.01)


def test_interval_coverage_matches_on_same_distribution():
    rng = np.random.default_rng(1)
    val = _frame(np.full(5000, 500.0), 500.0 * (1 + rng.normal(0, 0.1, 5000)), np.ones(5000, int))
    test = _frame(np.full(5000, 800.0), 800.0 * (1 + rng.normal(0, 0.1, 5000)), np.ones(5000, int))
    out = add_interval(test, conformal_quantiles(val, interval=0.8))
    cov, _ = coverage(out)
    assert abs(cov - 0.8) < 0.03
    assert (out["lower"] <= out["forecast"]).all() and (out["upper"] >= out["forecast"]).all()


def test_lower_bound_never_negative():
    val = _frame(np.array([100.0, 100.0]), np.array([0.0, 300.0]), np.array([1, 1]))
    test = _frame(np.array([50.0]), np.array([50.0]), np.array([1]))
    out = add_interval(test, conformal_quantiles(val, interval=0.98))
    assert out["lower"].iloc[0] >= 0
