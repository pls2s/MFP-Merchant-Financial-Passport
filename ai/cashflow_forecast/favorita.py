"""Build Favorita store-level daily sales in the same schema as Rossmann.

Optional generalization test (CLAUDE.md): the forecasting method chosen on
Rossmann is re-run on a second retailer without re-tuning.

Usage:
    python -m ai.cashflow_forecast.favorita

Reads   data/raw/favorita/{train,stores,holidays_events}.csv
Writes  data/processed/favorita.parquet

Mapping to the Rossmann schema:
- sales: sum over the 33 product families per store per day
- open: sales > 0. Favorita has no Open column; zero-sales days are store
  closures or days before a store opened, treated as known in advance like
  Rossmann's Open.
- promo: items on promotion / the store's 95th percentile in Train, capped at 1
- state_holiday: 1 national holiday, 2 regional/local holiday for the store's
  state/city, 3 national event; transferred holidays are ignored
- school_holiday, assortment, competition distance: not available → 0
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ai.cashflow_forecast.preprocess import (
    FAVORITA,
    ROOT,
    add_calendar_features,
    add_targets,
    assign_split,
    save,
)

RAW_DIR = ROOT / "data" / "raw" / "favorita"
HOLIDAY_TYPES = {"Holiday", "Transfer", "Additional", "Bridge"}


def holiday_codes(holidays: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    """(store, date) → state_holiday code, highest priority first: national, local, event."""
    h = holidays[~holidays["transferred"]]
    national = h[(h["locale"] == "National") & h["type"].isin(HOLIDAY_TYPES)][["date"]].assign(code=1)
    event = h[(h["locale"] == "National") & (h["type"] == "Event")][["date"]].assign(code=3)
    regional = h[(h["locale"] == "Regional") & h["type"].isin(HOLIDAY_TYPES)].merge(
        stores, left_on="locale_name", right_on="state"
    )
    local = h[(h["locale"] == "Local") & h["type"].isin(HOLIDAY_TYPES)].merge(
        stores, left_on="locale_name", right_on="city"
    )
    local = pd.concat([regional, local])[["store_nbr", "date"]].rename(columns={"store_nbr": "store"}).assign(code=2)

    per_store = stores[["store_nbr"]].rename(columns={"store_nbr": "store"})
    store_wide = pd.concat([national, event]).merge(per_store, how="cross")
    codes = pd.concat([store_wide, local])
    # Lowest code wins: national (1) > local (2) > event (3).
    return codes.groupby(["store", "date"])["code"].min().rename("state_holiday").reset_index()


def build(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    ds = FAVORITA
    train = pd.read_csv(raw_dir / "train.csv", parse_dates=["date"])
    stores = pd.read_csv(raw_dir / "stores.csv")
    holidays = pd.read_csv(raw_dir / "holidays_events.csv", parse_dates=["date"])

    daily = (
        train.groupby(["store_nbr", "date"])
        .agg(sales=("sales", "sum"), on_promotion=("onpromotion", "sum"))
        .reset_index()
        .rename(columns={"store_nbr": "store"})
    )
    calendar = pd.date_range(ds.train_start, ds.test_end, freq="D")
    full_index = pd.MultiIndex.from_product([np.sort(daily["store"].unique()), calendar], names=["store", "date"])
    df = daily.set_index(["store", "date"]).reindex(full_index).reset_index()

    # Every store is absent on 25 December.
    df["is_missing"] = df["sales"].isna().astype("int8")
    df[["sales", "on_promotion"]] = df[["sales", "on_promotion"]].fillna(0)
    df["sales"] = df["sales"].astype("float32")
    df["open"] = (df["sales"] > 0).astype("int8")
    df["zero_sales_open"] = np.int8(0)
    df["is_eval_day"] = ((df["open"] == 1) & (df["is_missing"] == 0)).astype("int8")

    p95 = df[df["date"] <= ds.train_end].groupby("store")["on_promotion"].quantile(0.95).replace(0, np.nan)
    df["promo"] = (df["on_promotion"] / df["store"].map(p95)).fillna(0).clip(upper=1).astype("float32")
    df = df.drop(columns="on_promotion")

    df = df.merge(holiday_codes(holidays, stores), on=["store", "date"], how="left")
    df["state_holiday"] = df["state_holiday"].fillna(0).astype("int8")
    df["school_holiday"] = np.int8(0)

    store_type = stores.set_index("store_nbr")["type"].map({t: i for i, t in enumerate("ABCDE")})
    df["store_type"] = df["store"].map(store_type).astype("int8")
    df["assortment"] = np.int8(0)
    df["competition_distance_log"] = np.float32(0)

    df = add_calendar_features(df)
    df = assign_split(df, ds)
    df = add_targets(df)
    return df.sort_values(["store", "date"]).reset_index(drop=True)


def main() -> None:
    save(build(), FAVORITA.processed_path)


if __name__ == "__main__":
    main()
