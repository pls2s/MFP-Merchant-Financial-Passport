import numpy as np
import pytest

from ai.cashflow_forecast.preprocess import HORIZON
from ai.cashflow_forecast.train import DEEP_CELLS, build_model, load_model

N_STORES, N_PAST, N_FUTURE, N_STATIC, WINDOW = 5, 4, 3, 2, 28


def inputs(batch=6):
    rng = np.random.default_rng(0)
    return {
        "past": rng.normal(size=(batch, WINDOW, N_PAST)).astype("float32"),
        "future": rng.normal(size=(batch, HORIZON, N_FUTURE)).astype("float32"),
        "store": rng.integers(0, N_STORES, batch).astype("int32"),
        "static": rng.normal(size=(batch, N_STATIC)).astype("float32"),
    }


@pytest.mark.parametrize("cell", DEEP_CELLS)
@pytest.mark.parametrize("layers", [1, 2])
def test_every_cell_forecasts_14_days(cell, layers):
    model = build_model(cell, N_STORES, N_PAST, N_FUTURE, N_STATIC, WINDOW, 16, layers, 0.2)
    assert model.predict(inputs(), verbose=0).shape == (6, HORIZON)


@pytest.mark.parametrize("cell", ["tcn", "transformer"])
def test_save_and_load_roundtrip(cell, tmp_path):
    model = build_model(cell, N_STORES, N_PAST, N_FUTURE, N_STATIC, WINDOW, 16, 1, 0.2)
    model.save(tmp_path / "model.keras")
    x = inputs()
    np.testing.assert_allclose(load_model(tmp_path).predict(x, verbose=0), model.predict(x, verbose=0), rtol=1e-5)


def test_tcn_sees_whole_window():
    """The dilated stack's receptive field must reach the oldest day of the window."""
    model = build_model("tcn", N_STORES, N_PAST, N_FUTURE, N_STATIC, WINDOW, 16, 1, 0.0)
    x = inputs(1)
    y = model.predict(x, verbose=0)
    x["past"][:, 0] += 10.0  # oldest day in the window
    assert not np.allclose(model.predict(x, verbose=0), y)
