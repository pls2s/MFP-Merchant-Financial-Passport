"""Generate synthetic expenses and cash-flow gaps for every store.

Usage:
    python -m ai.gap_detection.build

Reads   data/processed/rossmann.parquet        (average sales per store)
        models/forecasts/ensemble.json         (actual + forecast sales, Test period)
Writes  data/synthetic/expenses.parquet        (ข้อมูลจำลอง)
        data/synthetic/cash_flow_gaps.json     (`cash-flow-gaps` contract, one object per store)

Timeline (demo "today" is the last forecast origin):
    2015-06-20 .. 2015-07-17   actual sales      (balance history)
    2015-07-18 .. 2015-07-31   forecast sales    (projection; gaps reported here only)
"""

import json

import pandas as pd

from ai.cashflow_forecast.preprocess import PROCESSED_PATH, ROOT
from ai.cashflow_forecast.train import TEST_ORIGINS
from ai.gap_detection.gaps import cash_flow_gaps, simulate_balance
from ai.gap_detection.synthetic_expenses import ExpenseParams, generate, opening_balance

SYNTHETIC_DIR = ROOT / "data" / "synthetic"
FORECASTS_PATH = ROOT / "models" / "forecasts" / "ensemble.json"
EXPENSES_PATH = SYNTHETIC_DIR / "expenses.parquet"
GAPS_PATH = SYNTHETIC_DIR / "cash_flow_gaps.json"

EXPENSES_START = "2015-01-01"   # long enough for a stable average of monthly expenses
EXPENSES_END = "2015-07-31"
AS_OF = TEST_ORIGINS[-1]        # 2015-07-17
MIN_BUFFER = 0.0

# Demo stores: a thin cash reserve plus one large supplier order inside the projection, so the
# demo always has an alert. The order (DEMO_ORDER_DAYS of normal purchases) is due DEMO_GAP_DAYS
# after AS_OF; the opening balance is lowered just enough to leave a shortfall of
# DEMO_SHORTFALL_DAYS of sales that day.
DEMO_STORES = (1, 25, 817)
DEMO_GAP_DAYS = 5               # → 2015-07-22
DEMO_ORDER_DAYS = 21
DEMO_SHORTFALL_DAYS = 2
DEMO_LABEL = "ค่าสินค้า supplier (สั่งล็อตใหญ่)"


def average_daily_sales() -> pd.DataFrame:
    """Train-period sales per calendar day (closed days count as zero)."""
    df = pd.read_parquet(PROCESSED_PATH, columns=["store", "sales", "split", "is_missing"])
    df = df[(df["split"] == "train") & (df["is_missing"] == 0)]
    return df.groupby("store")["sales"].mean().rename("avg_daily_sales").reset_index()


def sales_series() -> dict[int, pd.DataFrame]:
    """Per store: date, sales (actual up to AS_OF, forecast after), is_forecast."""
    series = {}
    for obj in json.loads(FORECASTS_PATH.read_text()):
        pts = pd.DataFrame(obj["points"])
        pts["date"] = pd.to_datetime(pts["date"])
        pts["is_forecast"] = pts["date"] > AS_OF
        pts["sales"] = pts["forecast"].where(pts["is_forecast"], pts["actual"])
        series[obj["merchant_id"]] = pts[["date", "sales", "is_forecast"]]
    return series


def add_demo_scenarios(expenses: pd.DataFrame, series: dict, balances: pd.Series, daily: pd.Series,
                       params: ExpenseParams) -> tuple[pd.DataFrame, pd.Series]:
    """Add the large order to each demo store and lower its opening balance to force the gap."""
    due = AS_OF + pd.Timedelta(days=DEMO_GAP_DAYS)
    balances = balances.copy()
    orders = []
    for store in DEMO_STORES:
        order = {
            "store": store, "due_date": due, "type": "supplier_invoice", "label": DEMO_LABEL,
            "amount": round(DEMO_ORDER_DAYS * params.supplier_share * daily[store], -2),
            "scenario": "demo_gap", "is_synthetic": True,
        }
        with_order = pd.concat([expenses[expenses["store"] == store], pd.DataFrame([order])])
        bal = simulate_balance(series[store], with_order[with_order["due_date"] >= series[store]["date"].min()],
                               balances[store])
        balance_that_day = float(bal.loc[bal["date"] == due, "balance"].iloc[0])
        target = -round(DEMO_SHORTFALL_DAYS * daily[store], -2)
        balances[store] = round(max(balances[store] - (balance_that_day - target), 0.0), 2)
        orders.append(order)
    expenses = pd.concat([expenses, pd.DataFrame(orders)], ignore_index=True)
    return expenses.sort_values(["store", "due_date", "type"]), balances


def build(params: ExpenseParams = ExpenseParams()) -> tuple[pd.DataFrame, list[dict]]:
    stores = average_daily_sales()
    daily = stores.set_index("store")["avg_daily_sales"]
    expenses = generate(stores, EXPENSES_START, EXPENSES_END, params)
    balances = opening_balance(expenses, params)
    series = sales_series()
    expenses, balances = add_demo_scenarios(expenses, series, balances, daily, params)
    expenses = expenses.reset_index(drop=True)

    sim_start = min(s["date"].min() for s in series.values())
    window = expenses[expenses["due_date"] >= sim_start]
    gaps = [
        cash_flow_gaps(store, s, window[window["store"] == store], balances[store],
                       projection_start=AS_OF + pd.Timedelta(days=1), min_buffer=MIN_BUFFER)
        for store, s in sorted(series.items())
    ]
    return expenses, gaps


def main() -> None:
    expenses, gaps = build()
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    expenses.to_parquet(EXPENSES_PATH, index=False)
    GAPS_PATH.write_text(json.dumps(gaps, ensure_ascii=False))

    with_gap = [g for g in gaps if g["gaps"]]
    print(f"Saved {len(expenses):,} synthetic expenses → {EXPENSES_PATH}")
    print(f"Saved gaps for {len(gaps)} stores → {GAPS_PATH}")
    print(f"Stores with ≥1 gap in {AS_OF.date() + pd.Timedelta(days=1)}..: {len(with_gap)} ({len(with_gap) / len(gaps):.1%})")
    for g in gaps:
        if g["merchant_id"] in DEMO_STORES:
            first = g["gaps"][0] if g["gaps"] else None
            print(f"  demo store {g['merchant_id']}: {len(g['gaps'])} gap(s)"
                  + (f", first {first['date']} shortfall {first['shortfall']:,.0f}" if first else ""))


if __name__ == "__main__":
    main()
