"""Train seasonal naive, LightGBM, LSTM, GRU, TCN and Transformer with a shared split and seed.

Usage:
    python -m ai.cashflow_forecast.train --model all
    python -m ai.cashflow_forecast.train --model lstm --window 56 --hidden 64 --layers 1
    python -m ai.cashflow_forecast.train --dataset favorita --model lightgbm
    python -m ai.cashflow_forecast.train --model transformer --tune

LSTM, GRU, TCN and Transformer share everything except the encoder that reads the
input window (see ENCODERS), so their results compare architectures only.

Every model forecasts the same 14-day blocks: three rolling origins cover the
42-day Validation period and three cover the 42-day Test period. At each origin
a model may use actual sales up to and including the origin date, plus
known-in-advance features (Open, Promo, holidays, calendar) for the horizon.

Writes  models/predictions/<model>.parquet   (store, date, split, forecast)
        models/<model>/                      (trained artifacts)
        Datasets other than Rossmann write under models/<dataset>/.
"""

import argparse
import functools
import json

import numpy as np
import pandas as pd

from ai.cashflow_forecast.evaluate import wape
from ai.cashflow_forecast.preprocess import DATASETS, HORIZON, ROSSMANN, SEED, Dataset

VAL_ORIGINS = ROSSMANN.val_origins
TEST_ORIGINS = ROSSMANN.test_origins
# The main model averages ENSEMBLE_CELLS over these seeds. Seed 42 is the tuned run in
# models/<cell>/; the others are the re-trained runs from `experiments seeds`.
ENSEMBLE_SEEDS = [SEED, 1, 2, 3, 4]
ENSEMBLE_CELLS = ("lstm", "gru")


def load(ds: Dataset = ROSSMANN) -> pd.DataFrame:
    return pd.read_parquet(ds.processed_path)


def horizon_frame(df: pd.DataFrame, origin: pd.Timestamp, split: str) -> pd.DataFrame:
    """Rows for the 14 days after `origin`, tagged with origin and split."""
    end = origin + pd.Timedelta(days=HORIZON)
    part = df[(df["date"] > origin) & (df["date"] <= end)].copy()
    part["origin"] = origin
    part["split"] = split
    return part


def save_predictions(name: str, preds: pd.DataFrame, ds: Dataset = ROSSMANN) -> None:
    ds.predictions_dir.mkdir(parents=True, exist_ok=True)
    preds = preds[["store", "date", "split", "forecast"]].copy()
    preds["forecast"] = preds["forecast"].clip(lower=0).astype("float32")
    preds["model"] = name
    path = ds.predictions_dir / f"{name}.parquet"
    preds.to_parquet(path, index=False)
    print(f"Saved {len(preds):,} predictions → {path}")


def report(df: pd.DataFrame, preds: pd.DataFrame) -> None:
    merged = preds[["store", "date", "split", "forecast"]].merge(
        df[["store", "date", "sales", "is_eval_day"]], on=["store", "date"]
    )
    for split in ("val", "test"):
        m = merged[(merged["split"] == split) & (merged["is_eval_day"] == 1)]
        print(f"  {split} WAPE: {wape(m['sales'].to_numpy(), m['forecast'].to_numpy()):.4f}")


# --- Seasonal naive ----------------------------------------------------------


def train_seasonal_naive(df: pd.DataFrame, ds: Dataset = ROSSMANN) -> pd.DataFrame:
    """Same weekday last week. If that day was closed, use the latest open day
    with the same weekday before the origin."""
    preds = []
    for split, origins in (("val", ds.val_origins), ("test", ds.test_origins)):
        for origin in origins:
            history = df[(df["date"] <= origin) & (df["is_eval_day"] == 1)]
            last = (
                history.sort_values("date")
                .groupby(["store", "day_of_week"])["sales"]
                .last()
                .rename("forecast")
                .reset_index()
            )
            part = horizon_frame(df, origin, split).merge(last, on=["store", "day_of_week"], how="left")
            part["forecast"] = part["forecast"].fillna(0) * part["open"]
            preds.append(part)
    return pd.concat(preds, ignore_index=True)


# --- LightGBM ----------------------------------------------------------------

LGBM_LAGS = [14, 21, 28, 35, 42]


def lgbm_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Feature table with lags >= 14 days so no value inside the horizon is used."""
    df = df.copy()
    observed = df["sales"].where(df["is_eval_day"] == 1)  # closed/missing days → NaN
    by_store = observed.groupby(df["store"])
    for lag in LGBM_LAGS:
        df[f"lag_{lag}"] = by_store.shift(lag)
    shifted = by_store.shift(14)
    roll = shifted.groupby(df["store"]).rolling(28, min_periods=7)
    df["roll_mean_28"] = roll.mean().reset_index(level=0, drop=True)
    df["roll_std_28"] = roll.std().reset_index(level=0, drop=True)
    df["roll_mean_7"] = (
        shifted.groupby(df["store"]).rolling(7, min_periods=3).mean().reset_index(level=0, drop=True)
    )
    df["same_weekday_mean"] = df[[f"lag_{lag}" for lag in LGBM_LAGS]].mean(axis=1)
    # Promo / holidays in the surrounding days, all known in advance.
    for col in ("promo", "state_holiday"):
        g = df.groupby("store")[col]
        df[f"{col}_prev"] = g.shift(1)
        df[f"{col}_next"] = g.shift(-1)

    features = [
        "store", "store_type", "assortment", "competition_distance_log", "store_mean_sales",
        "day_of_week", "day_of_month", "month", "week_of_year",
        "open", "promo", "school_holiday", "state_holiday",
        "promo_prev", "promo_next", "state_holiday_prev", "state_holiday_next",
        *[f"lag_{lag}" for lag in LGBM_LAGS],
        "roll_mean_7", "roll_mean_28", "roll_std_28", "same_weekday_mean",
    ]
    return df, features


def train_lightgbm(df: pd.DataFrame, ds: Dataset = ROSSMANN, seed: int = SEED, out_dir=None) -> pd.DataFrame:
    import lightgbm as lgb

    feat_df, features = lgbm_features(df)
    train = feat_df[(feat_df["split"] == "train") & (feat_df["is_eval_day"] == 1)].dropna(subset=["lag_42"])
    val = feat_df[(feat_df["split"] == "val") & (feat_df["is_eval_day"] == 1)]

    def wape_eval(preds, data):
        y = np.expm1(data.get_label())
        return "wape", wape(y, np.expm1(preds)), False

    params = {
        "objective": "regression",
        "learning_rate": 0.05,
        "num_leaves": 127,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "metric": "None",
        "seed": seed,
        "verbose": -1,
    }
    dtrain = lgb.Dataset(train[features], train["sales_log"], categorical_feature=["store"])
    dval = lgb.Dataset(val[features], val["sales_log"], reference=dtrain)
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=3000,
        valid_sets=[dval],
        feval=wape_eval,
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(100)],
    )

    out_dir = out_dir or ds.models_dir / "lightgbm"
    out_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out_dir / "model.txt"), num_iteration=booster.best_iteration)

    # Lags are >= 14 days, so a horizon day never depends on values after its origin.
    target = feat_df[feat_df["split"].isin(["val", "test"])].copy()
    target["forecast"] = np.expm1(booster.predict(target[features], num_iteration=booster.best_iteration))
    target["forecast"] *= target["open"]
    return target


# --- LSTM / GRU --------------------------------------------------------------

DOW_COLS = [f"dow_{d}" for d in range(7)]
NEIGHBOUR_COLS = ["open", "promo", "holiday"]  # also given for the previous and next day
KNOWN_COLS = [
    "open", "promo", "school_holiday", "sh_a", "sh_b", "sh_c",
    *[f"{c}_{side}" for c in NEIGHBOUR_COLS for side in ("prev", "next")],
    *DOW_COLS, "dom_scaled", "month_sin", "month_cos", "woy_scaled",
]


def standardize(x: pd.Series) -> pd.Series:
    """Zero-mean, unit-variance; a constant column (e.g. missing in a dataset) becomes 0."""
    std = x.std()
    return (x - x.mean()) / std if std > 0 else x * 0


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Per store-day model features (sales_in, eval_flag, then KNOWN_COLS). `df` is sorted by
    store and date with: store, sales_scaled, is_eval_day, open, promo, school_holiday,
    state_holiday and the calendar columns from preprocess.add_calendar_features."""
    f = pd.DataFrame(index=df.index)
    f["sales_in"] = (df["sales_scaled"] * df["is_eval_day"]).fillna(0)
    f["eval_flag"] = df["is_eval_day"]
    f["open"] = df["open"]
    f["promo"] = df["promo"]
    f["school_holiday"] = df["school_holiday"]
    for code, name in ((1, "sh_a"), (2, "sh_b"), (3, "sh_c")):
        f[name] = (df["state_holiday"] == code).astype("float32")
    # Sales jump before/after closures and holidays, so each day also sees its neighbours.
    f["holiday"] = (df["state_holiday"] > 0).astype("float32")
    by_store = f[NEIGHBOUR_COLS].groupby(df["store"])
    for col in NEIGHBOUR_COLS:
        f[f"{col}_prev"] = by_store[col].shift(1).fillna(0)
        f[f"{col}_next"] = by_store[col].shift(-1).fillna(0)
    for d in range(7):
        f[f"dow_{d}"] = (df["day_of_week"] == d).astype("float32")
    f["dom_scaled"] = df["day_of_month"] / 31
    f["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    f["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    f["woy_scaled"] = df["week_of_year"] / 53
    return f


def sequence_arrays(df: pd.DataFrame, ds: Dataset = ROSSMANN, neighbours: bool = True) -> dict:
    """Dense (stores, days, features) arrays. Relies on preprocess's contiguous calendar.
    `neighbours=False` drops the previous/next-day features (ablation)."""
    df = df.sort_values(["store", "date"]).reset_index(drop=True)
    stores = np.sort(df["store"].unique())
    dates = pd.date_range(ds.train_start, ds.test_end, freq="D")
    n_s, n_d = len(stores), len(dates)
    assert len(df) == n_s * n_d
    f = feature_frame(df)


    def cube(cols):
        return f[cols].to_numpy("float32").reshape(n_s, n_d, len(cols))

    known_cols = KNOWN_COLS if neighbours else [c for c in KNOWN_COLS if not c.endswith(("_prev", "_next"))]

    per_store = df.groupby("store").first()
    static = np.column_stack([
        np.eye(per_store["store_type"].max() + 1)[per_store["store_type"]],
        np.eye(per_store["assortment"].max() + 1)[per_store["assortment"]],
        standardize(per_store["competition_distance_log"]),
        np.log(per_store["store_mean_sales"]) - np.log(per_store["store_mean_sales"]).mean(),
    ]).astype("float32")

    return {
        "dataset": ds,
        "stores": stores,
        "dates": dates,
        "past": cube(["sales_in", "eval_flag", *known_cols]),
        "known": cube(known_cols),  # "open" stays first: forecasts are multiplied by it
        "target": df["sales_scaled"].fillna(0).to_numpy("float32").reshape(n_s, n_d),
        "eval": df["is_eval_day"].to_numpy("float32").reshape(n_s, n_d),
        "missing": df["is_missing"].to_numpy("int32").reshape(n_s, n_d),
        "store_mean": per_store["store_mean_sales"].to_numpy("float32"),
        "static": static,
    }


def train_origins(arrays: dict, window: int) -> np.ndarray:
    """(store_idx, origin_idx) pairs whose input + horizon lie in Train with no missing days."""
    dates = arrays["dates"]
    last_origin = dates.get_loc(arrays["dataset"].train_end) - HORIZON
    origins = np.arange(window - 1, last_origin + 1)
    miss_cum = np.concatenate(
        [np.zeros((arrays["missing"].shape[0], 1), "int32"), arrays["missing"].cumsum(axis=1)], axis=1
    )
    # Missing days in [o - window + 1, o + HORIZON]
    span = miss_cum[:, origins + HORIZON + 1] - miss_cum[:, origins - window + 1]
    s_idx, o_pos = np.nonzero(span == 0)
    return np.column_stack([s_idx, origins[o_pos]])


def gather(arrays: dict, s_idx: np.ndarray, o_idx: np.ndarray, window: int):
    """Build one batch. Sales are divided by the window's own level (mean of
    evaluated days in the input) so the model predicts relative to recent sales
    rather than the store's Train-period average.

    Returns inputs, y (target, weight) and the level in sales units.
    """
    past_t = o_idx[:, None] + np.arange(-window + 1, 1)
    fut_t = o_idx[:, None] + np.arange(1, HORIZON + 1)
    s = s_idx[:, None]
    past = arrays["past"][s, past_t]

    sales_in, eval_in = past[..., 0], past[..., 1]
    if arrays.get("window_norm", True):
        level = sales_in.sum(axis=1) / np.maximum(eval_in.sum(axis=1), 1)
        level = np.where(level > 0, level, 1.0).astype("float32")  # scaled units
    else:  # ablation: store-mean scaling only
        level = np.ones(len(s_idx), "float32")
    past[..., 0] = sales_in / level[:, None]

    horizon_pos = np.broadcast_to(np.arange(1, HORIZON + 1, dtype="float32") / HORIZON, fut_t.shape)
    inputs = {
        "past": past,
        "future": np.concatenate([arrays["known"][s, fut_t], horizon_pos[..., None]], axis=-1),
        "store": s_idx.astype("int32"),
        "static": np.column_stack([arrays["static"][s_idx], np.log(level)]),
    }
    level_sales = level * arrays["store_mean"][s_idx]
    if arrays.get("weighted_loss", True):
        weight = arrays["eval"][s, fut_t] * level_sales[:, None]
    else:  # ablation: every store-day counts equally in relative terms
        weight = arrays["eval"][s, fut_t]
    y = np.stack([arrays["target"][s, fut_t] / level[:, None], weight], axis=-1)
    return inputs, y, level_sales


# --- Encoders: past window (batch, window, features) → vector (batch, d) ---------------
# Everything else in the model (store embedding, static features, per-day head, loss) is
# shared, so the cells differ only in how they read the input window.


def rnn_encoder(cell: str):
    def encode(x, window, hidden, layers, dropout):
        from keras import layers as L

        rnn = {"lstm": L.LSTM, "gru": L.GRU}[cell]
        for i in range(layers):
            x = rnn(hidden, return_sequences=i < layers - 1, dropout=dropout)(x)
        return x
    return encode


TCN_KERNEL = 3
TCN_DILATIONS = (1, 2, 4, 8, 16)  # one conv per block: receptive field 1 + 2·31 = 63 days ≥ the 56-day window


def tcn_encoder(x, window, hidden, layers, dropout):
    """Temporal convolutional network: `layers` stacks of residual blocks, one dilated causal
    Conv1D each; the last time step (which sees the whole window) is the encoding."""
    from keras import layers as L

    x = L.Conv1D(hidden, 1)(x)
    for _ in range(layers):
        for d in TCN_DILATIONS:
            h = L.Conv1D(hidden, TCN_KERNEL, padding="causal", dilation_rate=d, activation="relu")(x)
            x = L.Add()([x, L.Dropout(dropout)(h)])
    return L.Flatten()(L.Cropping1D((window - 1, 0))(x))


TRANSFORMER_HEADS = 4


def transformer_encoder(x, window, hidden, layers, dropout):
    """Transformer encoder: project to `hidden`, add a learned position embedding, then
    `layers` pre-norm self-attention blocks. Encoding = last day ⊕ mean over the window."""
    from keras import layers as L

    x = position_embedding()(window, hidden)(L.Dense(hidden)(x))
    for i in range(layers):
        h = L.LayerNormalization()(x)
        h = L.MultiHeadAttention(TRANSFORMER_HEADS, hidden // TRANSFORMER_HEADS, dropout=dropout,
                                 name=f"attention_{i}")(h, h)
        x = L.Add()([x, L.Dropout(dropout)(h)])
        h = L.LayerNormalization()(x)
        h = L.Dense(2 * hidden, activation="relu")(h)
        h = L.Dense(hidden)(L.Dropout(dropout)(h))
        x = L.Add()([x, h])
    x = L.LayerNormalization()(x)
    last = L.Flatten()(L.Cropping1D((window - 1, 0))(x))
    return L.Concatenate()([last, L.GlobalAveragePooling1D()(x)])


@functools.cache
def position_embedding():
    """The custom layer class, defined (and registered for model loading) on first use so
    importing this module does not import keras."""
    import keras

    @keras.saving.register_keras_serializable(package="mfp")
    class PositionEmbedding(keras.layers.Layer):
        """Adds a learned vector per position (day in the input window)."""

        def __init__(self, length: int, dim: int, **kwargs):
            super().__init__(**kwargs)
            self.length, self.dim = length, dim
            self.table = keras.layers.Embedding(length, dim)

        def build(self, input_shape):
            self.table.build((self.length,))

        def call(self, x):
            return x + self.table(keras.ops.arange(self.length))[None]

        def get_config(self):
            return {**super().get_config(), "length": self.length, "dim": self.dim}

    return PositionEmbedding


def load_model(model_dir):
    """Load a saved forecasting model of any cell (registers custom layers first)."""
    import keras

    position_embedding()
    return keras.models.load_model(model_dir / "model.keras", compile=False)


ENCODERS = {"lstm": rnn_encoder("lstm"), "gru": rnn_encoder("gru"), "tcn": tcn_encoder, "transformer": transformer_encoder}
DEEP_CELLS = tuple(ENCODERS)


def build_model(cell: str, n_stores: int, n_past: int, n_future: int, n_static: int,
                window: int, hidden: int, layers: int, dropout: float, embedding: bool = True):
    import keras
    from keras import layers as L

    past = keras.Input((window, n_past), name="past")
    future = keras.Input((HORIZON, n_future), name="future")
    store = keras.Input((), dtype="int32", name="store")
    static = keras.Input((n_static,), name="static")

    x = ENCODERS[cell](past, window, hidden, layers, dropout)
    # embedding=False (ablation) keeps the input but freezes it at zero.
    emb_layer = L.Embedding(n_stores, 16) if embedding else L.Embedding(
        n_stores, 16, embeddings_initializer="zeros", trainable=False
    )
    emb = L.Flatten()(emb_layer(store))
    context = L.Dense(hidden, activation="relu")(L.Concatenate()([x, emb, static]))
    context = L.Dropout(dropout)(context)
    # Shared per-day head: context + that day's known features → scaled sales.
    h = L.Concatenate()([L.RepeatVector(HORIZON)(context), future])
    h = L.TimeDistributed(L.Dense(64, activation="relu"))(h)
    out = L.Reshape((HORIZON,))(L.TimeDistributed(L.Dense(1))(h))
    return keras.Model([past, future, store, static], out)


def weighted_abs_error(y_true, y_pred):
    """Mean |error| in sales units on evaluated days (scaled error × store mean),
    so minimising it minimises WAPE."""
    import keras.ops as ops

    target, weight = y_true[..., 0], y_true[..., 1]
    return ops.sum(weight * ops.abs(target - y_pred)) / (ops.sum(weight) + 1e-6)


def predict_blocks(model, arrays: dict, window: int) -> pd.DataFrame:
    rows = []
    n_s = len(arrays["stores"])
    ds = arrays["dataset"]
    for split, origins in (("val", ds.val_origins), ("test", ds.test_origins)):
        for origin in origins:
            o = arrays["dates"].get_loc(origin)
            s_idx = np.arange(n_s)
            inputs, _, level = gather(arrays, s_idx, np.full(n_s, o), window)
            relative = model.predict(inputs, batch_size=2048, verbose=0)
            forecast = relative * level[:, None] * inputs["future"][..., 0]  # × open
            dates = arrays["dates"][o + 1 : o + HORIZON + 1]
            rows.append(pd.DataFrame({
                "store": np.repeat(arrays["stores"], HORIZON),
                "date": np.tile(dates, n_s),
                "split": split,
                "forecast": forecast.reshape(-1),
            }))
    return pd.concat(rows, ignore_index=True)


def train_rnn(df: pd.DataFrame, cell: str, window: int, hidden: int, layers: int, dropout: float,
              epochs: int, samples_per_epoch: int, batch_size: int, patience: int,
              out_dir=None, ds: Dataset = ROSSMANN, seed: int = SEED, options: dict | None = None) -> pd.DataFrame:
    """`options` switches off parts of the model for ablation: neighbours,
    window_norm, weighted_loss, embedding (all True by default)."""
    import keras

    opts = {"neighbours": True, "window_norm": True, "weighted_loss": True, "embedding": True, **(options or {})}
    keras.utils.set_random_seed(seed)
    arrays = sequence_arrays(df, ds, neighbours=opts["neighbours"])
    arrays.update(window_norm=opts["window_norm"], weighted_loss=opts["weighted_loss"])
    pairs = train_origins(arrays, window)
    samples_per_epoch = min(samples_per_epoch, len(pairs))  # small datasets
    print(f"{cell.upper()}: {len(pairs):,} training windows, {samples_per_epoch:,} sampled per epoch")

    class Windows(keras.utils.PyDataset):
        def __init__(self):
            super().__init__()
            self.rng = np.random.default_rng(seed)
            self.on_epoch_end()

        def on_epoch_end(self):
            self.order = self.rng.choice(len(pairs), samples_per_epoch, replace=False)

        def __len__(self):
            return samples_per_epoch // batch_size

        def __getitem__(self, i):
            batch = pairs[self.order[i * batch_size : (i + 1) * batch_size]]
            inputs, y, _ = gather(arrays, batch[:, 0], batch[:, 1], window)
            return inputs, y

    model = build_model(
        cell, len(arrays["stores"]), arrays["past"].shape[-1], arrays["known"].shape[-1] + 1,
        arrays["static"].shape[1] + 1, window, hidden, layers, dropout, opts["embedding"],
    )
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss=weighted_abs_error)

    actual = df.set_index(["store", "date"])[["sales", "is_eval_day"]]

    class ValWape(keras.callbacks.Callback):
        def on_epoch_end(self, _epoch, logs=None):
            preds = predict_blocks(self.model, arrays, window)
            preds = preds[preds["split"] == "val"].join(actual, on=["store", "date"])
            preds = preds[preds["is_eval_day"] == 1]
            logs["val_wape"] = wape(preds["sales"].to_numpy(), preds["forecast"].to_numpy())
            print(f" — val_wape: {logs['val_wape']:.4f}")

    model.fit(
        Windows(),
        epochs=epochs,
        callbacks=[
            ValWape(),
            keras.callbacks.EarlyStopping("val_wape", mode="min", patience=patience, restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau("val_wape", mode="min", factor=0.5, patience=2),
        ],
        verbose=2,
    )

    out_dir = out_dir or ds.models_dir / cell
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(out_dir / "model.keras")
    (out_dir / "config.json").write_text(json.dumps(
        {"window": window, "hidden": hidden, "layers": layers, "dropout": dropout, "seed": seed, **opts}, indent=2
    ))
    return predict_blocks(model, arrays, window)


def ensemble_members(ds: Dataset = ROSSMANN) -> list[dict]:
    """LSTM and GRU runs averaged into the main model: every seed in ENSEMBLE_SEEDS for
    Rossmann, seed 42 only for other datasets (no seed re-runs there)."""
    seeds = ENSEMBLE_SEEDS if ds is ROSSMANN else [SEED]
    members = []
    for seed in seeds:
        for cell in ENSEMBLE_CELLS:
            if seed == SEED:
                model_dir, preds = ds.models_dir / cell, ds.predictions_dir / f"{cell}.parquet"
            else:
                run_dir = ds.models_dir / "experiments" / "seeds" / f"seed{seed}"
                model_dir, preds = run_dir / f"{cell}_model", run_dir / f"{cell}.parquet"
            members.append({"cell": cell, "seed": seed, "model_dir": model_dir, "predictions": preds})
    missing = [str(m["predictions"]) for m in members if not m["predictions"].exists()]
    if missing:
        raise FileNotFoundError(f"run `python -m ai.cashflow_forecast.experiments seeds` first; missing {missing}")
    return members


def train_ensemble(ds: Dataset = ROSSMANN) -> pd.DataFrame:
    """Plain average of the saved LSTM and GRU forecasts over 5 seeds (10 runs, equal
    weights, nothing fitted). Adopted because its Validation WAPE beat the seed-42
    LSTM+GRU average and every 5-seed single-cell average; Test was not used to choose."""
    keys = ["store", "date", "split"]
    runs = [pd.read_parquet(m["predictions"]).set_index(keys)["forecast"].clip(lower=0)
            for m in ensemble_members(ds)]
    stacked = pd.concat(runs, axis=1)
    if stacked.isna().any().any():
        raise ValueError("ensemble members do not cover the same store-days")
    return stacked.mean(axis=1).rename("forecast").reset_index()


def val_wape(df: pd.DataFrame, preds: pd.DataFrame) -> float:
    m = preds[preds["split"] == "val"][["store", "date", "forecast"]].merge(
        df[["store", "date", "sales", "is_eval_day"]], on=["store", "date"]
    )
    m = m[m["is_eval_day"] == 1]
    return wape(m["sales"].to_numpy(), m["forecast"].to_numpy())


def tune(df: pd.DataFrame, cell: str, args: argparse.Namespace, ds: Dataset = ROSSMANN) -> pd.DataFrame:
    """Grid over the CLAUDE.md budget. Chooses by Validation WAPE only — Test
    results are never printed or recorded here, so they cannot steer the choice."""
    import shutil

    rows, best = [], None
    for window in (28, 56):
        for hidden in (64, 128):
            for layers in (1, 2):
                name = f"{cell}_w{window}_h{hidden}_l{layers}"
                print(f"\n=== tune {name} ===")
                out_dir = ds.models_dir / "tuning" / name
                preds = train_rnn(
                    df, cell, window, hidden, layers, args.dropout,
                    args.epochs, args.samples_per_epoch, args.batch_size, args.patience, out_dir, ds,
                )
                preds.to_parquet(out_dir / "predictions.parquet", index=False)
                score = val_wape(df, preds)
                print(f"  {name} val WAPE: {score:.4f}")
                rows.append({"config": name, "window": window, "hidden": hidden, "layers": layers, "val_wape": score})
                if best is None or score < best[0]:
                    best = (score, out_dir, preds)

    table = pd.DataFrame(rows).sort_values("val_wape")
    table.to_csv(ds.models_dir / f"tuning_{cell}.csv", index=False)
    print(table.to_string(index=False))

    _, best_dir, best_preds = best
    print(f"Best by val WAPE: {best_dir.name} → {ds.models_dir / cell}")
    shutil.copytree(best_dir, ds.models_dir / cell, dirs_exist_ok=True)
    (ds.models_dir / cell / "predictions.parquet").unlink()
    save_predictions(cell, best_preds, ds)
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=list(DATASETS), default="rossmann")
    parser.add_argument(
        "--model", choices=["seasonal_naive", "lightgbm", *DEEP_CELLS, "ensemble", "all"], default="all"
    )
    parser.add_argument("--window", type=int, default=56, choices=[28, 56])
    parser.add_argument("--hidden", type=int, default=64, choices=[64, 128])
    parser.add_argument("--layers", type=int, default=1, choices=[1, 2])
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--samples-per-epoch", type=int, default=200_000)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--tune", action="store_true", help="grid-search LSTM/GRU, choose by val WAPE")
    args = parser.parse_args()

    ds = DATASETS[args.dataset]
    df = load(ds)
    if args.tune:
        cells = ["lstm", "gru"] if args.model == "all" else [args.model]
        assert set(cells) <= set(DEEP_CELLS), f"--tune applies to {', '.join(DEEP_CELLS)} only"
        for cell in cells:
            tune(df, cell, args, ds)
        return
    names = ["seasonal_naive", "lightgbm", "lstm", "gru", "ensemble"] if args.model == "all" else [args.model]
    for name in names:
        print(f"\n=== {name} ===")
        if name == "seasonal_naive":
            preds = train_seasonal_naive(df, ds)
        elif name == "lightgbm":
            preds = train_lightgbm(df, ds)
        elif name == "ensemble":
            preds = train_ensemble(ds)
        else:
            preds = train_rnn(
                df, name, args.window, args.hidden, args.layers, args.dropout,
                args.epochs, args.samples_per_epoch, args.batch_size, args.patience, ds=ds,
            )
        report(df, preds)
        save_predictions(name, preds, ds)


if __name__ == "__main__":
    main()
