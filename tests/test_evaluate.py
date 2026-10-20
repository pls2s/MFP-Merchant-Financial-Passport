import numpy as np
import pandas as pd

from ai.cashflow_forecast.evaluate import mae, rmse, score, wape


def test_metrics():
    y = np.array([100.0, 200.0, 300.0])
    y_hat = np.array([110.0, 180.0, 300.0])
    assert wape(y, y_hat) == 30 / 600
    assert mae(y, y_hat) == 10.0
    assert np.isclose(rmse(y, y_hat), np.sqrt(500 / 3))


def test_score_ignores_non_eval_days():
    dates = pd.to_datetime(["2015-06-20", "2015-06-21", "2015-06-22"])
    preds = pd.DataFrame({"store": 1, "date": dates, "forecast": [100.0, 999.0, 200.0]})
    actuals = pd.DataFrame({"store": 1, "date": dates, "sales": [100.0, 0.0, 100.0], "is_eval_day": [1, 0, 1]})
    result = score(preds, actuals)
    assert result["n_days"] == 2
    assert result["wape"] == 0.5
