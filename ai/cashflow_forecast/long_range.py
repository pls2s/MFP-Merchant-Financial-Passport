"""Longer views for the dashboard, each with a backtest on real sales.

Usage:
    python -m ai.cashflow_forecast.long_range

A. 3 months — the trained LSTM+GRU ensemble rolled forward recursively: forecast 14 days,
   feed the forecast back as input, repeat (6 blocks = 84 days). No retraining.
   Backtest: rolled out from the end of Train (2015-05-08) and compared with actual sales.
   Forward: rolled out from the demo date. Days after the data ends (2015-07-31) use a
   synthetic calendar of known-in-advance inputs: open/promo copied from the same weekday
   52 weeks earlier, holidays from the same date a year earlier.

B. 1–2 years — seasonal outlook, not a deep-learning model: each month = the same month a year
   earlier × the change of the last 12 weeks against the same 12 weeks a year earlier.
   Backtest: from 2014-07-31 over Aug 2014 – Jul 2015.

C. Synthetic sales (ข้อมูลจำลอง) from the day after the data ends to SYNTHETIC_END, only so the
   dashboard's sales line can run past the real data. Each day = the actual sales on the same
   weekday in the last real year (52·k weeks earlier) × (1 + the store's 12-week trend, capped at
   ±10% a year)^k × fresh random noise. Independent of the LSTM/GRU, never used in any metric,
   backtest, cash simulation or copilot fact.

Intervals for both are symmetric 80% ranges: the 80th percentile of the backtest's absolute
relative error per step ahead (so the point always sits inside its band). They are calibrated on
the same backtest they are scored on, so their coverage is in-sample, not a validation.

Writes  models/forecasts/long_forecast.parquet     (store, date, forecast, lower, upper)
        models/forecasts/long_backtest.parquet     (store, date, forecast, actual)
        models/forecasts/seasonal_outlook.parquet  (store, month, outlook, lower, upper)
        models/forecasts/seasonal_backtest.parquet (store, month, outlook, actual)
        models/forecasts/long_range_metrics.json
        models/forecasts/synthetic_sales.parquet   (store, date, sales) — ข้อมูลจำลอง
"""

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from ai.cashflow_forecast.preprocess import PROCESSED_PATH, ROOT, ROSSMANN, TRAIN_END, add_calendar_features
from ai.cashflow_forecast.train import HORIZON, TEST_ORIGINS, gather, sequence_arrays

FORECASTS_DIR = ROOT / "models" / "forecasts"
AS_OF = TEST_ORIGINS[-1]                       # demo "today", 2015-07-17
BLOCKS = 6                                     # 6 × 14 = 84 days
DATA_END = ROSSMANN.test_end                   # 2015-07-31
CALENDAR_END = AS_OF + pd.Timedelta(days=HORIZON * BLOCKS)
SEASONAL_BACKTEST_ORIGIN = pd.Timestamp("2014-07-31")
TREND_WEEKS = 12
INTERVAL = 0.80
OUTLOOK_MONTHS = 24            # seasonal outlook length; only the first 12 months are backtested
OUTLOOK_EXTRA_WIDTH = 1.5      # band widening for untested months 13+
SYNTHETIC_END = pd.Timestamp("2018-07-31")  # three years past the real data; extend freely
SYNTHETIC_TREND_CAP = 0.10                  # max |yearly growth| applied to synthetic sales
SYNTHETIC_NOISE = 0.08                      # lognormal sigma of daily synthetic sales
SEED = 42


# --- A. Recursive LSTM+GRU -------------------------------------------------------


def synthetic_calendar(df: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Rows after DATA_END with assumed known-in-advance inputs (ข้อมูลจำลอง)."""
    dates = pd.date_range(DATA_END + pd.Timedelta(days=1), end)
    src = df.set_index(["store", "date"])
    stores = df["store"].unique()
    rows = []
    for lag_weekday, lag_date in ((364, 365), (728, 730)):  # fall back two years for missing store-days
        idx = pd.MultiIndex.from_product([stores, dates], names=["store", "date"])
        wk = src.reindex(pd.MultiIndex.from_arrays([idx.get_level_values(0), idx.get_level_values(1) - pd.Timedelta(days=lag_weekday)]))
        dt = src.reindex(pd.MultiIndex.from_arrays([idx.get_level_values(0), idx.get_level_values(1) - pd.Timedelta(days=lag_date)]))
        rows.append(pd.DataFrame({
            "open": wk["open"].to_numpy(), "promo": wk["promo"].to_numpy(), "missing": wk["is_missing"].to_numpy(),
            "school_holiday": dt["school_holiday"].to_numpy(), "state_holiday": dt["state_holiday"].to_numpy(),
        }, index=idx))
    first, second = rows
    use_second = (first["missing"] == 1).to_numpy()
    cal = first.copy()
    cal.loc[use_second] = second.loc[use_second].to_numpy()
    cal = cal.drop(columns="missing").fillna(0).reset_index()

    static = df.groupby("store")[["store_type", "assortment", "competition_distance_log", "store_mean_sales"]].first()
    cal = cal.join(static, on="store")
    cal = cal.assign(sales=0.0, is_missing=0, zero_sales_open=0, is_eval_day=0, split="future",
                     sales_log=0.0, sales_scaled=0.0)
    cal = add_calendar_features(cal)
    return cal.astype({c: df[c].dtype for c in df.columns if c in cal.columns})[df.columns]


def load_models():
    import keras

    models = {}
    for cell in ("lstm", "gru"):
        cfg = json.loads((ROSSMANN.models_dir / cell / "config.json").read_text())
        models[cell] = (keras.models.load_model(ROSSMANN.models_dir / cell / "model.keras", compile=False), cfg["window"])
    return models


def rollout(models: dict, arrays: dict, origin: pd.Timestamp, blocks: int = BLOCKS) -> np.ndarray:
    """Recursive ensemble forecast (stores × blocks·14) in sales units; writes each block's
    forecast back into `arrays` as if it were actual sales, so later blocks never see actuals."""
    o = arrays["dates"].get_loc(origin)
    n = len(arrays["stores"])
    s_idx = np.arange(n)
    out = np.zeros((n, blocks * HORIZON), "float32")
    for b in range(blocks):
        start = o + b * HORIZON
        preds = []
        for model, window in models.values():
            inputs, _, level = gather(arrays, s_idx, np.full(n, start), window)
            rel = model.predict(inputs, batch_size=2048, verbose=0)
            preds.append(rel * level[:, None] * inputs["future"][..., 0])  # × open
        block = np.clip(np.mean(preds, axis=0), 0, None)
        out[:, b * HORIZON:(b + 1) * HORIZON] = block
        days = slice(start + 1, start + HORIZON + 1)
        is_open = arrays["known"][:, days, 0]
        arrays["past"][:, days, 0] = block / arrays["store_mean"][:, None] * is_open
        arrays["past"][:, days, 1] = is_open
    return out


def recursive_forecasts(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    ext = pd.concat([df, synthetic_calendar(df, CALENDAR_END)], ignore_index=True).sort_values(["store", "date"])
    ds = replace(ROSSMANN, test_end=CALENDAR_END)
    models = load_models()

    def run(origin):
        arrays = sequence_arrays(ext.reset_index(drop=True), ds)
        values = rollout(models, arrays, origin)
        dates = pd.date_range(origin + pd.Timedelta(days=1), periods=BLOCKS * HORIZON)
        return pd.DataFrame({"store": np.repeat(arrays["stores"], len(dates)), "date": np.tile(dates, len(arrays["stores"])),
                             "forecast": values.reshape(-1), "step": np.tile(np.arange(len(dates)), len(arrays["stores"]))})

    # Backtest from the end of Train: the models never trained on these days.
    back = run(TRAIN_END).merge(df[["store", "date", "sales", "is_eval_day"]], on=["store", "date"])
    back["block"] = back["step"] // HORIZON + 1
    ev = back[(back["is_eval_day"] == 1) & (back["forecast"] > 0)]
    width = ((ev["sales"] - ev["forecast"]) / ev["forecast"]).abs().groupby(ev["block"]).quantile(INTERVAL)

    def wape(frame):
        return float((frame["forecast"] - frame["sales"]).abs().sum() / frame["sales"].sum())

    metrics = {
        "origin": TRAIN_END.strftime("%Y-%m-%d"),
        "days": BLOCKS * HORIZON,
        "wape_all_stores": wape(ev),
        "wape_by_block": {f"{(b - 1) * HORIZON + 1}-{b * HORIZON}": wape(g) for b, g in ev.groupby("block")},
        "interval_coverage_in_sample": float(
            ((ev["sales"] - ev["forecast"]).abs() <= ev["forecast"] * ev["block"].map(width)).mean()),
        "wape_by_store": {int(s): wape(g) for s, g in ev.groupby("store")},
    }

    fwd = run(AS_OF)
    # The first 14 days are the main forecast shown everywhere else. They match the rollout except
    # on the last data day, whose "next day" inputs the main model saw as missing (0); use the main
    # values so every view shows the same numbers.
    main = pd.DataFrame([{"store": o["merchant_id"], "date": p["date"], "main": p["forecast"]}
                         for o in json.loads((FORECASTS_DIR / "ensemble.json").read_text()) for p in o["points"]])
    main["date"] = pd.to_datetime(main["date"])
    fwd = fwd.merge(main, on=["store", "date"], how="left")
    fwd["forecast"] = fwd["main"].fillna(fwd["forecast"])
    fwd["block"] = fwd["step"] // HORIZON + 1
    fwd["lower"] = (fwd["forecast"] * (1 - fwd["block"].map(width))).clip(lower=0)
    fwd["upper"] = fwd["forecast"] * (1 + fwd["block"].map(width))
    fwd["synthetic_inputs"] = fwd["date"] > DATA_END
    back_out = back[["store", "date", "forecast", "sales"]].rename(columns={"sales": "actual"})
    fwd_out = fwd[["store", "date", "forecast", "lower", "upper", "synthetic_inputs"]]
    return fwd_out, back_out, metrics


# --- B. Seasonal outlook --------------------------------------------------------


def monthly_actuals(df: pd.DataFrame) -> pd.DataFrame:
    """Store × month sales; a month counts only if it has no missing days."""
    m = df.assign(month=df["date"].dt.to_period("M"))
    g = m.groupby(["store", "month"]).agg(sales=("sales", "sum"), missing=("is_missing", "sum"), last=("date", "max"))
    g.loc[g["missing"] > 0, "sales"] = np.nan
    return g["sales"].unstack()  # stores × months


def trend(df: pd.DataFrame, origin: pd.Timestamp) -> pd.Series:
    """Per store: last TREND_WEEKS weeks vs the same weeks 52 weeks earlier, minus 1; NaN if incomplete."""
    s = df.pivot(index="date", columns="store", values="sales")
    miss = df.pivot(index="date", columns="store", values="is_missing")
    days = TREND_WEEKS * 7
    now = (s.index > origin - pd.Timedelta(days=days)) & (s.index <= origin)
    before = (s.index > origin - pd.Timedelta(days=days + 364)) & (s.index <= origin - pd.Timedelta(days=364))
    ok = (miss[now].sum() == 0) & (miss[before].sum() == 0) & (now.sum() == days) & (before.sum() == days)
    return (s[now].sum() / s[before].sum() - 1).where(ok)


def seasonal(monthly: pd.DataFrame, growth: pd.Series, origin: pd.Timestamp, months: int = 12) -> pd.DataFrame:
    """Outlook for the `months` months after `origin`'s month: the same month k years earlier
    × (1 + growth)^k, with the smallest k whose month ended by `origin` (no peeking past it)."""
    first = origin.to_period("M") + 1
    empty = pd.Series(np.nan, index=monthly.index)
    rows = []
    for step in range(months):
        m = first + step
        value = empty
        for k in (1, 2, 3):
            base = m - 12 * k
            if base.end_time.normalize() <= origin:
                value = monthly[base] * (1 + growth) ** k if base in monthly.columns else empty
                break
        rows.append(pd.DataFrame({"store": monthly.index, "month": str(m), "step": step + 1, "outlook": value.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def seasonal_outlooks(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    monthly = monthly_actuals(df)
    back = seasonal(monthly, trend(df, SEASONAL_BACKTEST_ORIGIN), SEASONAL_BACKTEST_ORIGIN)
    actual = monthly.stack().rename("actual").reset_index()
    actual["month"] = actual["month"].astype(str)
    back = back.merge(actual, on=["store", "month"], how="left")
    ev = back.dropna(subset=["outlook", "actual"])
    ev = ev[ev["outlook"] > 0]
    width = ((ev["actual"] - ev["outlook"]) / ev["outlook"]).abs().groupby(ev["step"]).quantile(INTERVAL)

    def wape(frame):
        return float((frame["outlook"] - frame["actual"]).abs().sum() / frame["actual"].sum())

    metrics = {
        "origin": SEASONAL_BACKTEST_ORIGIN.strftime("%Y-%m-%d"),
        "months": 12,
        "store_months": int(len(ev)),
        "wape_all_stores": wape(ev),
        "wape_by_month": {m: wape(g) for m, g in ev.groupby("month")},
        "interval_coverage_in_sample": float(
            ((ev["actual"] - ev["outlook"]).abs() <= ev["outlook"] * ev["step"].map(width)).mean()),
        "wape_by_store": {int(s): wape(g) for s, g in ev.groupby("store")},
    }

    # Forward outlook runs OUTLOOK_MONTHS; the backtest only covers 12 months, so steps 13+ (based on
    # sales two years back × growth²) get the 12-month width × OUTLOOK_EXTRA_WIDTH — wider, untested.
    fwd = seasonal(monthly, trend(df, AS_OF), AS_OF, OUTLOOK_MONTHS)
    step_width = fwd["step"].map(width).fillna(width.iloc[-1] * OUTLOOK_EXTRA_WIDTH)
    fwd["lower"] = (fwd["outlook"] * (1 - step_width)).clip(lower=0)
    fwd["upper"] = fwd["outlook"] * (1 + step_width)
    fwd["backtested"] = fwd["step"] <= 12
    return fwd[["store", "month", "outlook", "lower", "upper", "backtested"]], back[["store", "month", "outlook", "actual"]], metrics


# --- C. Synthetic sales after the data ends -----------------------------------


def synthetic_sales(df: pd.DataFrame, end: pd.Timestamp = SYNTHETIC_END) -> pd.DataFrame:
    """Synthetic daily sales from DATA_END + 1 to `end` (see the module docstring, part C)."""
    rng = np.random.default_rng(SEED)
    sales = df.pivot(index="date", columns="store", values="sales")
    sales = sales.mask(df.pivot(index="date", columns="store", values="is_missing").astype(bool))
    growth = trend(df, AS_OF).reindex(sales.columns).fillna(0.0).clip(-SYNTHETIC_TREND_CAP, SYNTHETIC_TREND_CAP)
    dates = pd.date_range(DATA_END + pd.Timedelta(days=1), end)
    years = np.ceil((dates - DATA_END).days.to_numpy() / 364).astype(int)  # 52-week steps back into real data
    base_dates = dates - pd.to_timedelta(years * 364, unit="D")
    base = sales.reindex(base_dates).to_numpy()
    fallback = sales.reindex(base_dates - pd.Timedelta(days=364)).to_numpy()  # stores missing that year
    base = np.where(np.isnan(base), fallback, base)
    factor = (1 + growth.to_numpy())[None, :] ** years[:, None]
    noise = rng.lognormal(0.0, SYNTHETIC_NOISE, base.shape)
    values = np.where(base > 0, base * factor * noise, 0.0)
    out = pd.DataFrame(values, index=dates, columns=sales.columns).stack().rename("sales").reset_index()
    out.columns = ["date", "store", "sales"]
    return out[["store", "date", "sales"]].astype({"sales": "float32"})


def main() -> None:
    df = pd.read_parquet(PROCESSED_PATH)
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)

    fwd, back, m_rec = recursive_forecasts(df)
    fwd.to_parquet(FORECASTS_DIR / "long_forecast.parquet", index=False)
    back.to_parquet(FORECASTS_DIR / "long_backtest.parquet", index=False)
    print(f"3-month recursive LSTM+GRU — backtest from {m_rec['origin']}: WAPE {m_rec['wape_all_stores']:.2%}, "
          f"80% interval coverage (in-sample) {m_rec['interval_coverage_in_sample']:.1%}")
    for k, v in m_rec["wape_by_block"].items():
        print(f"  days {k}: WAPE {v:.2%}")

    out, back_s, m_sea = seasonal_outlooks(df)
    out.to_parquet(FORECASTS_DIR / "seasonal_outlook.parquet", index=False)
    back_s.to_parquet(FORECASTS_DIR / "seasonal_backtest.parquet", index=False)
    print(f"1-year seasonal outlook — backtest from {m_sea['origin']}: WAPE {m_sea['wape_all_stores']:.2%} "
          f"over {m_sea['store_months']:,} store-months, 80% interval coverage (in-sample) {m_sea['interval_coverage_in_sample']:.1%}")
    print(f"  stores with a forward outlook: {out.groupby('store')['outlook'].apply(lambda x: x.notna().all()).sum()}")

    syn = synthetic_sales(df)
    syn.to_parquet(FORECASTS_DIR / "synthetic_sales.parquet", index=False)
    print(f"Synthetic sales (ข้อมูลจำลอง): {syn['date'].min().date()}..{syn['date'].max().date()}, {len(syn):,} rows")

    (FORECASTS_DIR / "long_range_metrics.json").write_text(json.dumps(
        {"recursive_3_months": m_rec, "seasonal_1_year": m_sea}, indent=1))


if __name__ == "__main__":
    main()
