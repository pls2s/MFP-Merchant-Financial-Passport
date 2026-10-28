"""Forecast a shop that is not in the training data (cold start) from its own sales file.

Usage:
    python -m ai.cashflow_forecast.cold_start                 # UCI Online Retail demo → precomputed JSON
    python -m ai.cashflow_forecast.cold_start path/to/file.csv
    python -m ai.cashflow_forecast.cold_start --rossmann-check    # pipeline check on known stores

The trained LSTM+GRU ensemble (Rossmann, 5 seeds) is reused without retraining (report 9.2):

- store embedding  → the average embedding of all Rossmann stores ("an average store")
- store features   → average store type / assortment, average competition distance, average size
- sales scale      → the shop's own average sales on open days; the model forecasts sales
                     relative to the level of the input window, so currency and size do not matter
- known-in-advance → open days repeat the shop's weekly pattern (a weekday is open if it was open
                     in most of the last 8 weeks); promotions and holidays are unknown and set to 0
- level correction → without promotion dates the model forecasts too low (Rossmann check: 85% of
                     actual), and a very different shop can be far off (UCI: ~50%). The forecast is
                     multiplied by Σ actual ÷ Σ forecast over the shop's previous CALIB_BLOCKS
                     14-day blocks — only days before the forecast origin, so nothing is peeked at.

Files are read by sales_file.py (any .csv/.xlsx layout: daily or per invoice, Thai or English
headers, d/m/y, Buddhist years, "4,000"); it reports every row it skips. At least MIN_DAYS calendar
days are needed (the longest model input window is 56 days plus one block to backtest).

Accuracy is checked with a backtest on the shop's own last BACKTEST_BLOCKS × 14 days (raw model,
level-corrected model, and seasonal naive = same weekday last week). UCI Online Retail is a UK online wholesaler, very unlike a
German drugstore, so the backtest — not the Rossmann results — says how far to trust it.

Writes  models/forecasts/uci_demo.json          (demo: the screen loads it, the model is not run live)
        models/forecasts/cold_start_check.json  (--rossmann-check)
"""

import argparse
import functools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ai.cashflow_forecast.preprocess import HORIZON, PROCESSED_PATH, ROOT, ROSSMANN, add_calendar_features
from ai.cashflow_forecast.sales_file import MIN_DAYS, SalesFileError, guess_mapping, normalize, read_table
from ai.cashflow_forecast.train import KNOWN_COLS, ensemble_members, feature_frame, gather, load_model

UCI_PATH = ROOT / "data" / "raw" / "online_retail" / "Online Retail.xlsx"
DEMO_PATH = ROOT / "models" / "forecasts" / "uci_demo.json"
CHECK_PATH = ROOT / "models" / "forecasts" / "cold_start_check.json"
BACKTEST_BLOCKS = 6
CALIB_BLOCKS = 4                 # previous blocks used for the level correction
HISTORY_SHOWN = 120              # days of history returned for the chart
OPEN_WEEKS = 8                   # weekly pattern used for future open days


# --- File → daily sales (sales_file.py does the reading and reports what it skipped) -------


def load_sales(data: bytes, filename: str, mapping: dict[str, str | None] | None = None) -> tuple[pd.DataFrame, dict]:
    """(daily, read report); raises SalesFileError with a Thai message when it cannot be used."""
    df, _ = read_table(data, filename)
    daily, report = normalize(df, {**guess_mapping(df), **{k: v for k, v in (mapping or {}).items() if v}})
    if not report["enough_days"]:
        raise SalesFileError(f"ต้องมีข้อมูลอย่างน้อย {MIN_DAYS} วัน (อ่านได้ {report['days']} วัน "
                             f"{report['date_range']['start']} – {report['date_range']['end']})")
    return daily, report


# --- Model inputs for one new shop -------------------------------------------------------


def future_open(daily: pd.DataFrame, days: pd.DatetimeIndex) -> np.ndarray:
    recent = daily.tail(OPEN_WEEKS * 7)
    by_dow = recent.groupby(recent["date"].dt.dayofweek)["open"].mean()
    return np.array([float(by_dow.get(d.dayofweek, 0.0) >= 0.5) for d in days], "float32")


@functools.cache
def average_static() -> np.ndarray:
    """Store features of "an average Rossmann store", in sequence_arrays' static order."""
    s = pd.read_parquet(PROCESSED_PATH, columns=["store", "store_type", "assortment"]).drop_duplicates("store")
    return np.concatenate([
        np.eye(s["store_type"].max() + 1)[s["store_type"]].mean(axis=0),
        np.eye(s["assortment"].max() + 1)[s["assortment"]].mean(axis=0),
        [0.0, 0.0],  # competition distance and size: standardized → the average is 0
    ]).astype("float32")


def shop_arrays(daily: pd.DataFrame, origin: pd.Timestamp, known: pd.DataFrame | None = None) -> dict:
    """Arrays shaped like sequence_arrays for one shop (index 0), history up to `origin`.
    `known` (date, promo, school_holiday, state_holiday) replaces the zeros when those are known."""
    hist = daily[daily["date"] <= origin]
    fut_days = pd.date_range(origin + pd.Timedelta(days=1), periods=HORIZON)
    df = hist.set_index("date").reindex(hist["date"].tolist() + list(fut_days)).rename_axis("date").reset_index()
    df.loc[len(hist):, "open"] = future_open(hist, fut_days)
    df = df.assign(store=0, promo=0.0, school_holiday=0.0, state_holiday=0)
    if known is not None:
        k = known.set_index("date").reindex(df["date"])
        for col in ("promo", "school_holiday", "state_holiday"):
            df[col] = k[col].fillna(0).to_numpy()
    mean_open = hist.loc[hist["open"] == 1, "sales"].mean()
    df["sales_scaled"] = df["sales"] / mean_open
    df["is_eval_day"] = ((df["open"] == 1) & (df["sales"] > 0)).astype("float32")
    f = feature_frame(add_calendar_features(df))
    n = len(df)
    return {
        "dates": pd.DatetimeIndex(df["date"]),
        "past": f[["sales_in", "eval_flag", *KNOWN_COLS]].to_numpy("float32").reshape(1, n, -1),
        "known": f[KNOWN_COLS].to_numpy("float32").reshape(1, n, -1),
        "target": df["sales_scaled"].fillna(0).to_numpy("float32").reshape(1, n),
        "eval": df["is_eval_day"].to_numpy("float32").reshape(1, n),
        "store_mean": np.array([mean_open], "float32"),
        "static": average_static()[None],
    }


@functools.cache
def cold_models() -> list[tuple]:
    """Ensemble models with store 0's embedding replaced by the average embedding (in memory only)."""
    import keras

    models = []
    for m in ensemble_members():
        model = load_model(m["model_dir"])
        emb = next(layer for layer in model.layers if isinstance(layer, keras.layers.Embedding))
        w = emb.get_weights()[0].copy()
        w[0] = w.mean(axis=0)
        emb.set_weights([w])
        models.append((model, json.loads((m["model_dir"] / "config.json").read_text())["window"]))
    return models


def forecast_blocks(daily: pd.DataFrame, origins: list[pd.Timestamp],
                    known: pd.DataFrame | None = None) -> list[pd.DataFrame]:
    """Ensemble forecast for the 14 days after each origin. All origins go through each model in
    one batch (one call per model), each origin with its own history-only inputs."""
    shops = [shop_arrays(daily, o, known) for o in origins]
    idx = [a["dates"].get_loc(o) for a, o in zip(shops, origins)]
    total = np.zeros((len(origins), HORIZON), "float32")
    for model, window in cold_models():
        parts = [gather(a, np.array([0]), np.array([i]), window) for a, i in zip(shops, idx)]
        inputs = {k: np.concatenate([p[0][k] for p in parts]) for k in parts[0][0]}
        level = np.concatenate([p[2] for p in parts])
        rel = np.asarray(model(inputs, training=False))  # direct call: no tf.function retracing per shop
        total += np.clip(rel, 0, None) * level[:, None] * inputs["future"][..., 0]
    total /= len(cold_models())
    return [pd.DataFrame({"date": a["dates"][i + 1: i + HORIZON + 1], "forecast": f})
            for a, i, f in zip(shops, idx, total)]


def forecast_block(daily: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    return forecast_blocks(daily, [origin])[0]


# --- Backtest + response -----------------------------------------------------------------


def wape(y: np.ndarray, y_hat: np.ndarray) -> float | None:
    return float(np.abs(y - y_hat).sum() / y.sum()) if y.sum() > 0 else None


def level_factor(blocks: list[tuple[np.ndarray, np.ndarray]]) -> float:
    """Σ actual ÷ Σ forecast over earlier blocks (open days); 1 if there is nothing to learn from."""
    y = sum(float(b[0].sum()) for b in blocks)
    f = sum(float(b[1].sum()) for b in blocks)
    return y / f if y > 0 and f > 0 else 1.0


def backtest(daily: pd.DataFrame, blocks: int = BACKTEST_BLOCKS) -> tuple[dict, float, pd.DataFrame]:
    """Non-overlapping 14-day blocks ending at the last day; open days only. Each scored block is
    level-corrected with the CALIB_BLOCKS blocks before it. Also returns the factor for the next
    (live) forecast, learned from the last CALIB_BLOCKS blocks, and that raw forecast."""
    end = daily["date"].max()
    first_possible = daily["date"].min() + pd.Timedelta(days=56)
    sales = daily.set_index("date")["sales"]
    origins = [end - pd.Timedelta(days=HORIZON * k) for k in range(blocks + CALIB_BLOCKS, 0, -1)]
    origins = [o for o in origins if o >= first_possible]
    *past, nxt = forecast_blocks(daily, origins + [end])
    done = []  # (origin, actual, raw forecast, naive) on open days, oldest first
    for origin, fc in zip(origins, past):
        fc = fc.set_index("date")["forecast"]
        y = sales.reindex(fc.index).to_numpy()
        naive = sales.reindex(fc.index - pd.Timedelta(days=7)).to_numpy()
        open_ = y > 0
        done.append((origin, y[open_], fc.to_numpy()[open_], naive[open_]))

    rows, scored = [], []
    for i, (origin, y, raw, naive) in enumerate(done):
        if i < len(done) - blocks:
            continue
        factor = level_factor([(b[1], b[2]) for b in done[max(0, i - CALIB_BLOCKS):i]])
        rows.append({"origin": origin.strftime("%Y-%m-%d"), "level_factor": round(factor, 3),
                     "wape_model": wape(y, raw * factor), "wape_raw": wape(y, raw), "wape_naive": wape(y, naive)})
        scored.append((y, raw * factor, raw, naive))
    y, m, r, n = (np.concatenate([s[i] for s in scored]) if scored else np.array([]) for i in range(4))
    summary = {"blocks": rows, "wape_model": wape(y, m), "wape_raw": wape(y, r), "wape_naive": wape(y, n),
               "days": int(len(y)), "calib_blocks": CALIB_BLOCKS}
    return summary, level_factor([(b[1], b[2]) for b in done[-CALIB_BLOCKS:]]), nxt


def run(daily: pd.DataFrame, name: str, source: str, read_report: dict | None = None) -> dict:
    end = daily["date"].max()
    bt, factor, fc = backtest(daily)
    fc["forecast"] *= factor
    hist = daily.tail(HISTORY_SHOWN)
    notes = [
        "โมเดลเทรนจากร้าน Rossmann (เยอรมนี) ไม่เคยเห็นร้านนี้ ใช้แบบ 'ร้านเฉลี่ย' (cold start) โดยไม่เทรนใหม่",
        "วันเปิดร้านใน 14 วันข้างหน้าเดาจากรูปแบบรายสัปดาห์ 8 สัปดาห์ล่าสุด ไม่รู้วันโปรโมชันและวันหยุด",
        f"ปรับระดับยอดขาย × {factor:.2f} จากที่โมเดลทายพลาดใน {CALIB_BLOCKS * HORIZON} วันล่าสุดของร้านนี้",
    ]
    if bt["wape_model"] is not None and bt["wape_naive"] is not None and bt["wape_model"] > bt["wape_naive"]:
        notes.append("ทดสอบย้อนหลังแล้วแย่กว่าวิธีง่าย (ยอดเท่าสัปดาห์ก่อน) — ไม่ควรใช้ค่าพยากรณ์นี้ตัดสินใจ")
    return {
        "name": name,
        "source": source,
        "date_range": {"start": daily["date"].min().strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
        "days": int(len(daily)),
        "open_days": int(daily["open"].sum()),
        "history": [{"date": d.strftime("%Y-%m-%d"), "sales": round(float(s), 2)} for d, s in zip(hist["date"], hist["sales"])],
        "forecast": [{"date": d.strftime("%Y-%m-%d"), "forecast": round(float(v), 2)} for d, v in zip(fc["date"], fc["forecast"])],
        "backtest": bt,
        "level_factor": round(factor, 3),
        "notes": notes,
        "model": "ensemble-v2 cold start",
        "read_report": read_report,
    }


def rossmann_check(n_stores: int = 15) -> dict:
    """Run the cold-start pipeline on Rossmann stores (whose answers we know) at the Test origins:
    without promotion/holiday dates (as for an uploaded file) and with them. No level correction,
    so this measures the raw cold-start model. The normal model (with the store's embedding) is
    the reference."""
    from ai.cashflow_forecast.train import load

    df = load()
    stores = np.random.default_rng(0).choice(df["store"].unique(), n_stores, replace=False)
    scores = {"cold_start_no_promo": [], "cold_start_with_promo": []}
    for store in stores:
        g = df[df["store"] == store].sort_values("date")
        daily = pd.DataFrame({"date": g["date"].to_numpy(), "sales": g["sales"].fillna(0).to_numpy(),
                              "open": g["open"].to_numpy("float32")})
        actual = g.set_index("date")
        for name, known in (("cold_start_no_promo", None),
                            ("cold_start_with_promo", g[["date", "promo", "school_holiday", "state_holiday"]])):
            for fc in forecast_blocks(daily, list(ROSSMANN.test_origins), known):
                ev = actual["is_eval_day"].reindex(fc["date"]).to_numpy() == 1
                scores[name].append((actual["sales"].reindex(fc["date"]).to_numpy()[ev], fc["forecast"].to_numpy()[ev]))
    out = {"stores": [int(s) for s in stores], "origins": [o.strftime("%Y-%m-%d") for o in ROSSMANN.test_origins]}
    for name, parts in scores.items():
        y, f = np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])
        out[name] = {"wape": wape(y, f), "forecast_over_actual": float(f.sum() / y.sum())}
    p = pd.read_parquet(ROSSMANN.predictions_dir / "ensemble.parquet")
    p = p[(p["split"] == "test") & p["store"].isin(stores)].merge(df[["store", "date", "sales", "is_eval_day"]], on=["store", "date"])
    p = p[p["is_eval_day"] == 1]
    out["normal_model"] = {"wape": wape(p["sales"].to_numpy(), p["forecast"].to_numpy())}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", type=Path, help="sales file; default: UCI Online Retail → demo JSON")
    parser.add_argument("--rossmann-check", action="store_true", help="check the pipeline on known Rossmann stores")
    args = parser.parse_args()
    if args.rossmann_check:
        out = rossmann_check()
        CHECK_PATH.write_text(json.dumps(out, indent=1) + "\n")
        print(json.dumps(out, indent=1))
        return
    path = args.path or UCI_PATH
    daily, report = load_sales(path.read_bytes(), path.name)
    out = run(daily, path.name if args.path else "UCI Online Retail (ตัวอย่าง)", "precomputed", report)
    print(json.dumps({k: v for k, v in out.items() if k not in ("history", "forecast")}, ensure_ascii=False, indent=1))
    if not args.path:
        DEMO_PATH.write_text(json.dumps(out, ensure_ascii=False) + "\n")
        print(f"Saved → {DEMO_PATH}")


if __name__ == "__main__":
    main()
