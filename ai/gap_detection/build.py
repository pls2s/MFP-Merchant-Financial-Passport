"""Generate synthetic expenses and cash-flow gaps for every store.

Usage:
    python -m ai.gap_detection.build

Reads   data/processed/rossmann.parquet        (average sales per store)
        models/forecasts/sales_history.parquet (actual daily sales)
        models/forecasts/ensemble.json         (forecast sales, Test period)
Writes  data/synthetic/expenses.parquet        (ข้อมูลจำลอง)
        data/synthetic/cash_flow_gaps.json     (`cash-flow-gaps` contract, one object per store)

Timeline (demo "today" is the last forecast origin):
    2015-01-01 .. 2015-07-17   actual sales      (balance history; past gaps)
    2015-07-18 .. 2015-07-31   forecast sales    (projection; `cash-flow-gaps` reports these)
"""

import json

import pandas as pd

from ai.cashflow_forecast.predict import HISTORY_PATH
from ai.cashflow_forecast.preprocess import PROCESSED_PATH, ROOT
from ai.cashflow_forecast.train import TEST_ORIGINS
from ai.gap_detection.gaps import cash_flow_gaps, find_gaps, simulate_balance
from ai.gap_detection.synthetic_expenses import ExpenseParams, add_owner_draws, generate, reserve_target

SYNTHETIC_DIR = ROOT / "data" / "synthetic"
FORECASTS_PATH = ROOT / "models" / "forecasts" / "ensemble.json"
EXPENSES_PATH = SYNTHETIC_DIR / "expenses.parquet"
GAPS_PATH = SYNTHETIC_DIR / "cash_flow_gaps.json"

EXPENSES_START = "2015-01-01"   # simulation start: about 6.5 months of balance history
EXPENSES_END = "2015-07-31"
SIM_START = pd.Timestamp(EXPENSES_START)
AS_OF = TEST_ORIGINS[-1]        # 2015-07-17
MIN_BUFFER = 0.0

# Demo stores: a thin cash reserve (DEMO_RESERVE_DAYS of expenses), so their history has natural
# shortfalls, plus one large supplier order DEMO_GAP_DAYS after AS_OF sized to leave a shortfall of
# DEMO_SHORTFALL_DAYS of sales that day — the demo always has an alert.
DEMO_STORES = (1, 25, 817)
DEMO_RESERVE_DAYS = 5
DEMO_GAP_DAYS = 5               # → 2015-07-22
DEMO_SHORTFALL_DAYS = 2
DEMO_LABEL = "ค่าสินค้า supplier (สั่งล็อตใหญ่)"


def average_daily_sales() -> pd.DataFrame:
    """Train-period sales per calendar day (closed days count as zero)."""
    df = pd.read_parquet(PROCESSED_PATH, columns=["store", "sales", "split", "is_missing"])
    df = df[(df["split"] == "train") & (df["is_missing"] == 0)]
    return df.groupby("store")["sales"].mean().rename("avg_daily_sales").reset_index()


def sales_series() -> dict[int, pd.DataFrame]:
    """Per store from SIM_START: date, sales (actual up to AS_OF, forecast after), is_forecast."""
    history = pd.read_parquet(HISTORY_PATH, columns=["store", "date", "sales"])
    history = history[(history["date"] >= SIM_START) & (history["date"] <= AS_OF)]
    actual = {int(s): df for s, df in history.groupby("store")}
    series = {}
    for obj in json.loads(FORECASTS_PATH.read_text(encoding="utf-8")):
        m = obj["merchant_id"]
        past = actual[m][["date", "sales"]].assign(sales=lambda d: d["sales"].fillna(0.0), is_forecast=False)
        fut = pd.DataFrame(obj["points"])
        fut["date"] = pd.to_datetime(fut["date"])
        fut = fut[fut["date"] > AS_OF].rename(columns={"forecast": "sales"})[["date", "sales"]].assign(is_forecast=True)
        series[m] = pd.concat([past, fut], ignore_index=True)
    return series


def past_gaps(sales: pd.DataFrame, expenses: pd.DataFrame, opening: float, min_buffer: float = MIN_BUFFER) -> list[dict]:
    """Gaps in the actual-sales history (SIM_START .. AS_OF)."""
    bal = simulate_balance(sales, expenses, opening)
    return find_gaps(bal[bal["date"] <= AS_OF], expenses, min_buffer)


def build(params: ExpenseParams = ExpenseParams()) -> tuple[pd.DataFrame, list[dict]]:
    stores = average_daily_sales()
    daily = stores.set_index("store")["avg_daily_sales"]
    base = generate(stores, EXPENSES_START, EXPENSES_END, params)
    reserve = reserve_target(base, params)
    days = (base["due_date"].max() - base["due_date"].min()).days + 1
    per_day = base.groupby("store")["amount"].sum() / days
    series = sales_series()
    due = AS_OF + pd.Timedelta(days=DEMO_GAP_DAYS)

    parts, gaps = [], []
    for store, s in sorted(series.items()):
        exp = base[base["store"] == store]
        if store in DEMO_STORES:
            reserve[store] = round(DEMO_RESERVE_DAYS * per_day[store], 2)
        draws = add_owner_draws(store, s, exp, reserve[store], AS_OF, params)
        if len(draws):
            exp = pd.concat([exp, draws], ignore_index=True)
        if store in DEMO_STORES:
            bal = simulate_balance(s, exp, reserve[store])
            balance_that_day = float(bal.loc[bal["date"] == due, "balance"].iloc[0])
            exp = pd.concat([exp, pd.DataFrame([{
                "store": store, "due_date": due, "type": "supplier_invoice", "label": DEMO_LABEL,
                "amount": round(balance_that_day + DEMO_SHORTFALL_DAYS * daily[store], -2),
                "scenario": "demo_gap", "is_synthetic": True,
            }])], ignore_index=True)
        parts.append(exp)
        gaps.append(cash_flow_gaps(store, s, exp, reserve[store],
                                   projection_start=AS_OF + pd.Timedelta(days=1), min_buffer=MIN_BUFFER))
    expenses = pd.concat(parts, ignore_index=True).sort_values(["store", "due_date", "type"]).reset_index(drop=True)
    return expenses, gaps


def main() -> None:
    expenses, gaps = build()
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    expenses.to_parquet(EXPENSES_PATH, index=False)
    GAPS_PATH.write_text(json.dumps(gaps, ensure_ascii=False), encoding="utf-8")

    with_gap = [g for g in gaps if g["gaps"]]
    series = sales_series()
    past = {g["merchant_id"]: past_gaps(series[g["merchant_id"]], expenses[expenses["store"] == g["merchant_id"]],
                                        g["opening_balance"]) for g in gaps}
    print(f"Stores with ≥1 past gap ({SIM_START.date()}..{AS_OF.date()}): "
          f"{sum(bool(v) for v in past.values())} ({sum(bool(v) for v in past.values()) / len(gaps):.1%})")
    print(f"Saved {len(expenses):,} synthetic expenses → {EXPENSES_PATH}")
    print(f"Saved gaps for {len(gaps)} stores → {GAPS_PATH}")
    print(f"Stores with ≥1 gap in {AS_OF.date() + pd.Timedelta(days=1)}..: {len(with_gap)} ({len(with_gap) / len(gaps):.1%})")
    for g in gaps:
        if g["merchant_id"] in DEMO_STORES:
            first = g["gaps"][0] if g["gaps"] else None
            print(f"  demo store {g['merchant_id']}: {len(past[g['merchant_id']])} past, {len(g['gaps'])} upcoming gap(s)"
                  + (f", first {first['date']} shortfall {first['shortfall']:,.0f}" if first else ""))


if __name__ == "__main__":
    main()
