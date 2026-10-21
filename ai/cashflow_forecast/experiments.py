"""Robustness experiments for the report (Rossmann). Main results stay at seed 42;
nothing here changes the chosen models or their saved predictions.

Usage:
    python -m ai.cashflow_forecast.experiments ablation
    python -m ai.cashflow_forecast.experiments seeds
    python -m ai.cashflow_forecast.experiments curves

ablation  LSTM (w56/h128/l1, seed 42) with one component switched off at a time.
seeds     LightGBM, LSTM, GRU and the LSTM+GRU average re-trained with seeds 1-4;
          seed 42 reuses the main predictions.
curves    Per-epoch train loss and validation WAPE of every tuning run, parsed
          from models/logs/tune.log.

Writes  models/experiments/{ablation,seeds,learning_curves}.csv
        models/experiments/<experiment>/<run>/<model>.parquet   (resumable)
"""

import argparse
import re

import pandas as pd

from ai.cashflow_forecast.evaluate import score
from ai.cashflow_forecast.preprocess import ROSSMANN, SEED
from ai.cashflow_forecast.train import load, train_lightgbm, train_rnn

EXPERIMENTS_DIR = ROSSMANN.models_dir / "experiments"
RNN_CONFIGS = {"lstm": {"window": 56, "hidden": 128, "layers": 1}, "gru": {"window": 28, "hidden": 128, "layers": 2}}
RNN_DEFAULTS = {"dropout": 0.2, "epochs": 30, "samples_per_epoch": 200_000, "batch_size": 512, "patience": 4}
ABLATIONS = {
    "no_window_norm": {"window_norm": False},
    "no_neighbour_features": {"neighbours": False},
    "no_store_embedding": {"embedding": False},
    "unweighted_loss": {"weighted_loss": False},
}
SEEDS = [SEED, 1, 2, 3, 4]


def run_rnn(df: pd.DataFrame, cell: str, out_dir, seed: int = SEED, options: dict | None = None) -> pd.DataFrame:
    cfg = RNN_CONFIGS[cell]
    return train_rnn(
        df, cell, cfg["window"], cfg["hidden"], cfg["layers"], RNN_DEFAULTS["dropout"],
        RNN_DEFAULTS["epochs"], RNN_DEFAULTS["samples_per_epoch"], RNN_DEFAULTS["batch_size"],
        RNN_DEFAULTS["patience"], out_dir=out_dir, seed=seed, options=options,
    )


def cached(path, make) -> pd.DataFrame:
    """Load predictions if this run already finished, otherwise train and save."""
    if path.exists():
        print(f"  reuse {path.relative_to(EXPERIMENTS_DIR)}")
        return pd.read_parquet(path)
    preds = make()[["store", "date", "split", "forecast"]].copy()
    preds["forecast"] = preds["forecast"].clip(lower=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(path, index=False)
    return preds


def scores(preds: pd.DataFrame, actuals: pd.DataFrame, **labels) -> list[dict]:
    return [
        {**labels, "split": split, **score(preds[preds["split"] == split], actuals)}
        for split in ("val", "test")
    ]


def ablation(df: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    rows = scores(pd.read_parquet(ROSSMANN.predictions_dir / "lstm.parquet"), actuals, variant="full")
    for name, options in ABLATIONS.items():
        print(f"\n=== ablation {name} ===")
        out_dir = EXPERIMENTS_DIR / "ablation" / name
        preds = cached(out_dir / "lstm.parquet", lambda: run_rnn(df, "lstm", out_dir, options=options))
        rows += scores(preds, actuals, variant=name)
        print(f"  {name}: " + ", ".join(f"{r['split']} WAPE {r['wape']:.4f}" for r in rows[-2:]))
    return pd.DataFrame(rows)


def seeds(df: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seed in SEEDS:
        if seed == SEED:
            preds = {m: pd.read_parquet(ROSSMANN.predictions_dir / f"{m}.parquet") for m in ("lightgbm", "lstm", "gru")}
        else:
            print(f"\n=== seed {seed} ===")
            run_dir = EXPERIMENTS_DIR / "seeds" / f"seed{seed}"
            preds = {
                "lightgbm": cached(run_dir / "lightgbm.parquet",
                                   lambda: train_lightgbm(df, seed=seed, out_dir=run_dir / "lightgbm_model")),
                "lstm": cached(run_dir / "lstm.parquet", lambda: run_rnn(df, "lstm", run_dir / "lstm_model", seed)),
                "gru": cached(run_dir / "gru.parquet", lambda: run_rnn(df, "gru", run_dir / "gru_model", seed)),
            }
        keys = ["store", "date", "split"]
        ens = preds["lstm"][keys + ["forecast"]].merge(
            preds["gru"][keys + ["forecast"]], on=keys, suffixes=("_lstm", "_gru"), validate="one_to_one"
        )
        ens["forecast"] = (ens["forecast_lstm"] + ens["forecast_gru"]) / 2
        preds["ensemble"] = ens
        for model, p in preds.items():
            rows += scores(p, actuals, seed=seed, model=model)
        test = {r["model"]: r["wape"] for r in rows if r["seed"] == seed and r["split"] == "test"}
        print(f"  seed {seed} test WAPE: " + ", ".join(f"{m} {w:.4f}" for m, w in test.items()))
    return pd.DataFrame(rows)


def summarize_seeds(table: pd.DataFrame) -> pd.DataFrame:
    test = table[table["split"] == "test"]
    summary = test.groupby("model")["wape"].agg(["mean", "std", "min", "max"])
    wide = test.pivot(index="seed", columns="model", values="wape")
    summary["beats_lightgbm"] = [(wide[m] < wide["lightgbm"]).sum() if m != "lightgbm" else None for m in summary.index]
    return summary


EPOCH_LINE = re.compile(r"loss: (?P<loss>[\d.]+) - val_wape: (?P<val_wape>[\d.]+)")


def learning_curves(log_path=ROSSMANN.models_dir / "logs" / "tune.log") -> pd.DataFrame:
    rows, config = [], None
    for line in log_path.read_text().splitlines():
        if line.startswith("=== tune "):
            config, epoch = line.removeprefix("=== tune ").strip(" ="), 0
        elif config and (m := EPOCH_LINE.search(line)):
            epoch += 1
            rows.append({"config": config, "epoch": epoch, "loss": float(m["loss"]), "val_wape": float(m["val_wape"])})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("experiment", choices=["ablation", "seeds", "curves"])
    args = parser.parse_args()

    if args.experiment == "curves":
        table = learning_curves()
        path = EXPERIMENTS_DIR / "learning_curves.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)
        print(f"Saved {table['config'].nunique()} runs, {len(table)} epochs → {path}")
        return

    df = load()
    actuals = df[["store", "date", "sales", "is_eval_day"]]
    table = ablation(df, actuals) if args.experiment == "ablation" else seeds(df, actuals)
    path = EXPERIMENTS_DIR / f"{args.experiment}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)

    with pd.option_context("display.float_format", "{:,.4f}".format):
        print(table.to_string(index=False))
        if args.experiment == "seeds":
            print(summarize_seeds(table))
    print(f"Saved → {path}")


if __name__ == "__main__":
    main()
