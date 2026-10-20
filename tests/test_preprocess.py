import pandas as pd

from ai.cashflow_forecast import preprocess as pp


def _write_fake_raw(raw_dir):
    dates = pd.date_range(pp.TRAIN_START, pp.TEST_END, freq="D")
    rows = []
    for store in (1, 2):
        for i, date in enumerate(dates):
            # Store 2 is missing a block of days, like real Rossmann stores.
            if store == 2 and pd.Timestamp("2014-07-01") <= date <= pd.Timestamp("2014-07-10"):
                continue
            is_open = int(date.dayofweek != 6)
            sales = 1000.0 * store if is_open else 0.0
            if store == 1 and i == 3 and is_open:
                sales = 0.0  # open with zero sales
            rows.append({
                "Store": store, "DayOfWeek": date.dayofweek + 1, "Date": date.strftime("%Y-%m-%d"),
                "Sales": sales, "Customers": 0, "Open": is_open, "Promo": 0,
                "StateHoliday": "0" if i % 2 else 0, "SchoolHoliday": 0,
            })
    pd.DataFrame(rows).to_csv(raw_dir / "train.csv", index=False)
    pd.DataFrame({
        "Store": [1, 2], "StoreType": ["a", "c"], "Assortment": ["a", "b"],
        "CompetitionDistance": [500.0, None],
    }).to_csv(raw_dir / "store.csv", index=False)


def test_split_day_counts(tmp_path):
    _write_fake_raw(tmp_path)
    df = pp.build(tmp_path)
    days = df.groupby("split")["date"].nunique()
    assert days.to_dict() == {"train": 858, "val": 42, "test": 42}


def test_missing_days_are_filled_and_not_evaluated(tmp_path):
    _write_fake_raw(tmp_path)
    df = pp.build(tmp_path)
    missing = df[df["is_missing"] == 1]
    assert len(missing) == 10
    assert (missing["store"] == 2).all()
    assert (missing["is_eval_day"] == 0).all()
    assert df.groupby("store").size().nunique() == 1  # contiguous calendar per store


def test_open_zero_sales_flagged(tmp_path):
    _write_fake_raw(tmp_path)
    df = pp.build(tmp_path)
    flagged = df[df["zero_sales_open"] == 1]
    assert len(flagged) == 1
    assert flagged["is_eval_day"].iloc[0] == 0


def test_store_mean_uses_train_period_only(tmp_path):
    _write_fake_raw(tmp_path)
    df = pp.build(tmp_path)
    means = df.groupby("store")["store_mean_sales"].first()
    assert means.to_dict() == {1: 1000.0, 2: 2000.0}
    assert df["competition_distance_log"].notna().all()
