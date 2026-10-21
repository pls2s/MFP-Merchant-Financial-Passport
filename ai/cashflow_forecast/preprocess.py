"""Clean Rossmann data, build features, and apply the fixed time-based split.

Usage:
    python -m ai.cashflow_forecast.preprocess

Reads   data/raw/rossmann/{train,store}.csv
Writes  data/processed/rossmann.parquet
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "rossmann"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_PATH = PROCESSED_DIR / "rossmann.parquet"

SEED = 42

# Fixed split — do not change without telling the team.
TRAIN_START = pd.Timestamp("2013-01-01")
TRAIN_END = pd.Timestamp("2015-05-08")
VAL_END = pd.Timestamp("2015-06-19")
TEST_END = pd.Timestamp("2015-07-31")

HORIZON = 14


@dataclass(frozen=True)
class Dataset:
    """Dates and output locations for one dataset. Rossmann keeps the original
    top-level paths; other datasets write under models/<name>/."""

    name: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_end: pd.Timestamp
    test_end: pd.Timestamp

    @property
    def processed_path(self) -> Path:
        return PROCESSED_DIR / f"{self.name}.parquet"

    @property
    def models_dir(self) -> Path:
        return ROOT / "models" if self.name == "rossmann" else ROOT / "models" / self.name

    @property
    def predictions_dir(self) -> Path:
        return self.models_dir / "predictions"

    @property
    def val_origins(self) -> list[pd.Timestamp]:
        return [self.train_end + pd.Timedelta(days=HORIZON * k) for k in range(3)]

    @property
    def test_origins(self) -> list[pd.Timestamp]:
        return [self.val_end + pd.Timedelta(days=HORIZON * k) for k in range(3)]


ROSSMANN = Dataset("rossmann", TRAIN_START, TRAIN_END, VAL_END, TEST_END)
# Optional generalization test: same structure, last 42 + 42 days as Test / Validation.
FAVORITA = Dataset(
    "favorita",
    pd.Timestamp("2013-01-01"),
    pd.Timestamp("2017-05-23"),
    pd.Timestamp("2017-07-04"),
    pd.Timestamp("2017-08-15"),
)
DATASETS = {d.name: d for d in (ROSSMANN, FAVORITA)}

CALENDAR_FEATURES = ["day_of_week", "day_of_month", "month", "week_of_year"]
KNOWN_FEATURES = ["open", "promo", "school_holiday", "state_holiday"]
STORE_FEATURES = ["store_type", "assortment", "competition_distance_log"]


def load_raw(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(
        raw_dir / "train.csv",
        parse_dates=["Date"],
        dtype={"StateHoliday": str},
    )
    store = pd.read_csv(raw_dir / "store.csv")
    return train, store


def clean(train: pd.DataFrame) -> pd.DataFrame:
    """Normalise columns and reindex every store to the full daily calendar.

    Days a store is absent from the raw file get `is_missing = 1` with
    Open = 0 and Sales = 0, so sequence windows stay contiguous. Missing days
    and closed days are excluded from loss and metrics via `is_eval_day`.
    """
    df = train.rename(
        columns={
            "Store": "store",
            "Date": "date",
            "Sales": "sales",
            "Open": "open",
            "Promo": "promo",
            "SchoolHoliday": "school_holiday",
            "StateHoliday": "state_holiday",
        }
    ).drop(columns=["DayOfWeek", "Customers"])  # Customers is not known in advance

    # StateHoliday mixes "0" and 0; map to integer codes (0 = none, a/b/c).
    df["state_holiday"] = (
        df["state_holiday"].astype(str).map({"0": 0, "a": 1, "b": 2, "c": 3}).astype("int8")
    )

    calendar = pd.date_range(TRAIN_START, TEST_END, freq="D")
    full_index = pd.MultiIndex.from_product(
        [np.sort(df["store"].unique()), calendar], names=["store", "date"]
    )
    df = df.set_index(["store", "date"]).reindex(full_index).reset_index()
    df["is_missing"] = df["sales"].isna().astype("int8")
    df[["sales", "open", "promo", "school_holiday", "state_holiday"]] = (
        df[["sales", "open", "promo", "school_holiday", "state_holiday"]].fillna(0)
    )
    df = df.astype(
        {"sales": "float32", "open": "int8", "promo": "int8", "school_holiday": "int8"}
    )

    # Open but zero sales: suspicious rows, kept but flagged and not evaluated.
    df["zero_sales_open"] = ((df["open"] == 1) & (df["sales"] == 0)).astype("int8")
    df["is_eval_day"] = (
        (df["open"] == 1) & (df["is_missing"] == 0) & (df["zero_sales_open"] == 0)
    ).astype("int8")
    return df


def add_store_features(df: pd.DataFrame, store: pd.DataFrame) -> pd.DataFrame:
    s = store[["Store", "StoreType", "Assortment", "CompetitionDistance"]].rename(
        columns={
            "Store": "store",
            "StoreType": "store_type",
            "Assortment": "assortment",
            "CompetitionDistance": "competition_distance",
        }
    )
    s["store_type"] = s["store_type"].map({"a": 0, "b": 1, "c": 2, "d": 3}).astype("int8")
    s["assortment"] = s["assortment"].map({"a": 0, "b": 1, "c": 2}).astype("int8")
    # 3 stores have no competitor distance; treat as "far away".
    s["competition_distance"] = s["competition_distance"].fillna(s["competition_distance"].max())
    s["competition_distance_log"] = np.log1p(s["competition_distance"]).astype("float32")
    return df.merge(s.drop(columns="competition_distance"), on="store", how="left")


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df["date"].dt
    df["day_of_week"] = d.dayofweek.astype("int8")  # 0 = Monday
    df["day_of_month"] = d.day.astype("int8")
    df["month"] = d.month.astype("int8")
    df["week_of_year"] = d.isocalendar().week.astype("int8")
    return df


def assign_split(df: pd.DataFrame, ds: Dataset = ROSSMANN) -> pd.DataFrame:
    df["split"] = np.select(
        [df["date"] <= ds.train_end, df["date"] <= ds.val_end],
        ["train", "val"],
        default="test",
    )
    return df


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """log1p target plus per-store mean scaling, using Train-period stats only."""
    df["sales_log"] = np.log1p(df["sales"]).astype("float32")
    train_open = df[(df["split"] == "train") & (df["is_eval_day"] == 1)]
    store_mean = train_open.groupby("store")["sales"].mean().rename("store_mean_sales")
    df = df.merge(store_mean, on="store", how="left")
    # Stores that opened after Train have no Train sales; use the median store.
    df["store_mean_sales"] = df["store_mean_sales"].fillna(store_mean.median())
    df["sales_scaled"] = (df["sales"] / df["store_mean_sales"]).astype("float32")
    return df


def build(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    train, store = load_raw(raw_dir)
    df = clean(train)
    df = add_store_features(df, store)
    df = add_calendar_features(df)
    df = assign_split(df)
    df = add_targets(df)
    return df.sort_values(["store", "date"]).reset_index(drop=True)


def save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)

    days = df.groupby("split")["date"].agg(["min", "max", "nunique"])
    print(f"Saved {len(df):,} rows, {df['store'].nunique()} stores → {path}")
    print(days)
    print(f"Missing store-days: {df['is_missing'].sum():,}")
    print(f"Open with zero sales: {df['zero_sales_open'].sum():,}")


def main() -> None:
    save(build(), PROCESSED_PATH)


if __name__ == "__main__":
    main()
