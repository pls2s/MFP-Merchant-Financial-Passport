"""Probability that cash runs short, per day of the 14-day forecast (โอกาสที่เงินจะไม่พอ).

Usage:
    python -m ai.gap_detection.shortfall_risk

The gap finder (gaps.py) answers yes/no from one forecast. This module answers "how likely":
it simulates many possible next-14-days sales paths and counts how often the balance drops
below the minimum buffer.

    P(shortfall on day t) = share of simulated paths with B_t < MIN_BUFFER
    B_t = B_origin + Σ (S_path − E)                      (same balance equation as gaps.py)

Where each sales path comes from (N_PATHS per store):

1. Deep learning — model uncertainty. Every model of the main ensemble (LSTM+GRU × 5 seeds)
   forecasts the next 14 days MC_PASSES times with dropout left ON (Monte Carlo dropout).
   Each pass drops a different random 20% of the network, so the passes disagree where the
   model is unsure. 10 models × MC_PASSES passes = N_PATHS paths.
2. Day-to-day noise the model cannot predict. Each path is multiplied by one 14-day block of
   relative errors (actual ÷ forecast) of the ensemble on Validation, drawn at random from all
   stores and Validation origins. Whole blocks keep the real day-to-day correlation (a bad
   week tends to stay bad).

Only Validation is used to build the noise; Test is used only to check the probabilities:

- sales: does the 10–90% range of the paths contain the actual sales ~80% of the time?
- shortfalls: at the three Test origins (19 Jun, 3 Jul, 17 Jul 2015) the actual balance is
  known (actual sales − the same synthetic expenses), so we compare predicted probabilities
  with what happened: Brier score against the yes/no warning and a constant base rate, plus
  a reliability table. Demo stores are excluded (their large invoice is a planted scenario).

Expenses are synthetic, so the probabilities are about a simulated shop (ข้อมูลจำลอง).

Reads   data/processed/rossmann.parquet, models/predictions/ensemble.parquet, the ensemble models,
        models/forecasts/sales_history.parquet, data/synthetic/{expenses.parquet,cash_flow_gaps.json}
Writes  data/synthetic/shortfall_risk.json         (per store, demo origin 2015-07-17)
        data/synthetic/shortfall_calibration.json  (Test-period checks)
"""

import json

import numpy as np
import pandas as pd

from ai.cashflow_forecast.predict import HISTORY_PATH
from ai.cashflow_forecast.preprocess import HORIZON, ROSSMANN
from ai.cashflow_forecast.train import ensemble_members, gather, load, load_model, sequence_arrays
from ai.gap_detection.build import AS_OF, DEMO_STORES, EXPENSES_PATH, GAPS_PATH, MIN_BUFFER, SIM_START, SYNTHETIC_DIR

MC_PASSES = 20                  # dropout passes per model → 10 models × 20 = 200 paths
RATIO_CLIP = (0.0, 3.0)         # one extreme Validation day must not dominate a path
SEED = 42
RISK_PATH = SYNTHETIC_DIR / "shortfall_risk.json"
CALIBRATION_PATH = SYNTHETIC_DIR / "shortfall_calibration.json"
RELIABILITY_BINS = [0.0, 0.05, 0.2, 0.4, 0.6, 0.8, 1.0001]


# --- 1. Deep learning: MC-dropout ensemble paths ----------------------------------------


def mc_dropout_paths(arrays: dict, origin: pd.Timestamp, passes: int = MC_PASSES) -> np.ndarray:
    """(paths, stores, 14) sales in sales units; closed days are 0."""
    o = arrays["dates"].get_loc(origin)
    n = len(arrays["stores"])
    paths = []
    for m in ensemble_members():
        cfg = json.loads((m["model_dir"] / "config.json").read_text())
        model = load_model(m["model_dir"])
        inputs, _, level = gather(arrays, np.arange(n), np.full(n, o), cfg["window"])
        is_open = inputs["future"][..., 0]
        for _ in range(passes):
            rel = np.asarray(model(inputs, training=True))  # training=True keeps dropout on
            paths.append(np.clip(rel, 0, None) * level[:, None] * is_open)
    return np.stack(paths)


# --- 2. Noise: 14-day blocks of Validation relative errors -----------------------------


def validation_ratio_blocks(actuals: pd.DataFrame) -> np.ndarray:
    """(blocks, 14) actual ÷ ensemble forecast on Validation; 1 where the day is not evaluated."""
    preds = pd.read_parquet(ROSSMANN.predictions_dir / "ensemble.parquet")
    v = preds[preds["split"] == "val"].merge(actuals, on=["store", "date"])
    v = v.sort_values(["store", "date"]).reset_index(drop=True)
    ok = (v["is_eval_day"] == 1) & (v["forecast"] > 0)
    v["ratio"] = np.where(ok, v["sales"] / v["forecast"].where(ok, 1.0), 1.0)
    v["ratio"] = v["ratio"].clip(*RATIO_CLIP)
    return v["ratio"].to_numpy().reshape(-1, HORIZON)  # 3 origins × 14 days per store, in order


def sample_paths(mc: np.ndarray, blocks: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    pick = rng.integers(0, len(blocks), size=mc.shape[:2])
    return mc * blocks[pick]


# --- 3. Balance → probability -----------------------------------------------------------


def balances(sales: pd.DataFrame, expenses: pd.DataFrame, opening: pd.Series, stores: np.ndarray,
             origin: pd.Timestamp) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Balance at the origin (actual sales), expenses due on each of the next 14 days, and the
    actual balance path over those days. Arrays are (stores,) / (stores, 14)."""
    days = pd.date_range(origin + pd.Timedelta(days=1), periods=HORIZON)
    s = sales.pivot(index="store", columns="date", values="sales").reindex(stores).fillna(0.0)
    e = expenses.pivot_table(index="store", columns="due_date", values="amount", aggfunc="sum")
    e = e.reindex(index=stores, columns=s.columns).fillna(0.0)
    flow = s - e
    hist = flow.loc[:, (flow.columns >= SIM_START) & (flow.columns <= origin)].sum(axis=1)
    b0 = (opening.reindex(stores) + hist).to_numpy()
    exp_next = e[days].to_numpy()
    actual_path = b0[:, None] + (s[days] - e[days]).cumsum(axis=1).to_numpy()
    return b0, exp_next, actual_path, days


def shortfall_probability(paths: np.ndarray, b0: np.ndarray, exp_next: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """P(B_t < MIN_BUFFER) per store-day (stores, 14), and the balance paths (paths, stores, 14)."""
    bal = b0[None, :, None] + np.cumsum(paths - exp_next[None], axis=2)
    return (bal < MIN_BUFFER).mean(axis=0), bal


# --- Checks on Test ---------------------------------------------------------------------


def reliability(p: np.ndarray, y: np.ndarray) -> list[dict]:
    rows = []
    for lo, hi in zip(RELIABILITY_BINS[:-1], RELIABILITY_BINS[1:]):
        m = (p >= lo) & (p < hi)
        if m.any():
            rows.append({"bin": f"{lo:.0%}–{min(hi, 1):.0%}", "n": int(m.sum()),
                         "mean_predicted": float(p[m].mean()), "observed_rate": float(y[m].mean())})
    return rows


def main() -> None:
    rng = np.random.default_rng(SEED)
    df = load()
    actuals = df[["store", "date", "sales", "is_eval_day"]]
    arrays = sequence_arrays(df)
    stores = arrays["stores"]
    blocks = validation_ratio_blocks(actuals)
    print(f"Noise: {len(blocks):,} Validation blocks of {HORIZON} days")

    history = pd.read_parquet(HISTORY_PATH, columns=["store", "date", "sales"])
    history = history[history["date"] >= SIM_START].assign(sales=lambda d: d["sales"].fillna(0.0))
    expenses = pd.read_parquet(EXPENSES_PATH)
    opening = pd.Series({o["merchant_id"]: o["opening_balance"] for o in json.loads(GAPS_PATH.read_text())})
    point = pd.read_parquet(ROSSMANN.predictions_dir / "ensemble.parquet")
    point = point[point["split"] == "test"].pivot(index="store", columns="date", values="forecast").reindex(stores)
    sales_actual = df[["store", "date", "sales", "is_eval_day"]].pivot(index="store", columns="date", values="sales")
    eval_day = df.pivot(index="store", columns="date", values="is_eval_day")
    keep = ~np.isin(stores, DEMO_STORES)

    checks = {"p": [], "y": [], "warn": [], "p_any": [], "y_any": [], "cover": [], "width": [], "model_share": []}
    risk = None
    for origin in ROSSMANN.test_origins:
        print(f"origin {origin.date()}: MC dropout ×{MC_PASSES} over {len(ensemble_members())} models …")
        mc = mc_dropout_paths(arrays, origin)
        paths = sample_paths(mc, blocks, rng)
        b0, exp_next, actual_path, days = balances(history, expenses, opening, stores, origin)
        p, bal = shortfall_probability(paths, b0, exp_next)
        point_path = b0[:, None] + np.cumsum(point[days].to_numpy() - exp_next, axis=1)

        y = actual_path < MIN_BUFFER
        checks["p"].append(p[keep].ravel())
        checks["y"].append(y[keep].ravel())
        checks["warn"].append((point_path < MIN_BUFFER)[keep].ravel())
        checks["p_any"].append((bal.min(axis=2) < MIN_BUFFER).mean(axis=0)[keep])
        checks["y_any"].append(y.any(axis=1)[keep])

        act = sales_actual.reindex(stores)[days].to_numpy()
        ev = eval_day.reindex(stores)[days].to_numpy() == 1
        lo, hi = np.quantile(paths, [0.1, 0.9], axis=0)
        checks["cover"].append(((act >= lo) & (act <= hi))[ev])
        checks["width"].append(((hi - lo) / np.maximum(np.median(paths, axis=0), 1))[ev])
        # How much of the spread is model uncertainty (MC dropout + ensemble) vs Validation noise?
        checks["model_share"].append(float((mc.std(axis=0)[ev] ** 2).sum() / (paths.std(axis=0)[ev] ** 2).sum()))

        if origin == AS_OF:
            q = np.quantile(bal, [0.1, 0.5, 0.9], axis=0)
            p_any = (bal.min(axis=2) < MIN_BUFFER).mean(axis=0)
            risk = [{
                "merchant_id": int(s),
                "as_of": AS_OF.strftime("%Y-%m-%d"),
                "n_paths": int(len(paths)),
                "p_any": round(float(p_any[i]), 3),
                "days": [{
                    "date": d.strftime("%Y-%m-%d"),
                    "p_shortfall": round(float(p[i, t]), 3),
                    "balance_p10": round(float(q[0, i, t]), 2),
                    "balance_p50": round(float(q[1, i, t]), 2),
                    "balance_p90": round(float(q[2, i, t]), 2),
                } for t, d in enumerate(days)],
                "is_synthetic_expense": True,
            } for i, s in enumerate(stores)]

    p, y, warn = (np.concatenate(checks[k]) for k in ("p", "y", "warn"))
    p_any, y_any = np.concatenate(checks["p_any"]), np.concatenate(checks["y_any"])
    base = y.mean()

    def brier(f, o):
        return float(((f - o) ** 2).mean())

    calibration = {
        "method": "MC dropout (10 ensemble models × 20 passes) × Validation error blocks",
        "n_paths": MC_PASSES * len(ensemble_members()),
        "origins": [o.strftime("%Y-%m-%d") for o in ROSSMANN.test_origins],
        "excluded_stores": list(DEMO_STORES),
        "sales_interval_80": {
            "coverage": float(np.concatenate(checks["cover"]).mean()),
            "mean_width_vs_median": float(np.concatenate(checks["width"]).mean()),
            "model_uncertainty_share_of_variance": float(np.mean(checks["model_share"])),
        },
        "shortfall_day": {
            "store_days": int(len(y)),
            "events": int(y.sum()),
            "base_rate": float(base),
            "brier_probability": brier(p, y),
            "brier_yes_no_warning": brier(warn.astype(float), y),
            "brier_base_rate": brier(np.full_like(p, base), y),
            "reliability": reliability(p, y),
        },
        "shortfall_any_14_days": {
            "store_windows": int(len(y_any)),
            "events": int(y_any.sum()),
            "brier_probability": brier(p_any, y_any),
            "brier_base_rate": brier(np.full_like(p_any, y_any.mean()), y_any),
            "reliability": reliability(p_any, y_any),
        },
    }
    RISK_PATH.write_text(json.dumps(risk, ensure_ascii=False) + "\n")
    CALIBRATION_PATH.write_text(json.dumps(calibration, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(calibration, ensure_ascii=False, indent=1))
    print(f"Saved {len(risk)} stores → {RISK_PATH}, checks → {CALIBRATION_PATH}")


if __name__ == "__main__":
    main()
