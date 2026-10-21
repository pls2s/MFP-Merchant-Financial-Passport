"""Synthetic (mock) expenses per store. ข้อมูลจำลอง — never present as real.

Every parameter and the seed are listed in data/synthetic/README.md; keep the
two in sync. Amounts scale with each store's average sales per calendar day
(Train period, closed days included), so expenses are realistic relative to income.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

LABELS = {
    "supplier_invoice": "ค่าสินค้า supplier",
    "rent": "ค่าเช่าร้าน",
    "payroll": "เงินเดือนพนักงาน",
    "utilities": "ค่าน้ำค่าไฟ",
}


@dataclass(frozen=True)
class ExpenseParams:
    seed: int = 42
    # Supplier invoices: issued every 7 or 14 days (fixed per store), paid `payment_terms_days` later.
    supplier_share: float = 0.60          # of sales over the invoice cycle
    supplier_cycles: tuple = (7, 14)
    payment_terms_days: int = 7
    supplier_noise: float = 0.10          # uniform ± share of the amount
    # Monthly costs as a share of average monthly sales (30 × daily average).
    rent_share: float = 0.08              # due on the 1st
    payroll_share: float = 0.15           # half on the 15th, half on the last day of the month
    utilities_share: float = 0.03         # due on the 20th
    utilities_noise: float = 0.15
    # Opening balance = N days of average daily expenses, N drawn per store from this range
    # (stores differ in how much cash they keep).
    opening_balance_days: tuple = (5, 45)


def generate(stores: pd.DataFrame, start: str, end: str, params: ExpenseParams = ExpenseParams()) -> pd.DataFrame:
    """Expenses due between `start` and `end` (inclusive).

    stores  columns: store, avg_daily_sales
    returns columns: store, due_date, type, label, amount, scenario, is_synthetic
    """
    rng = np.random.default_rng(params.seed)
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    month_starts = pd.date_range(start.to_period("M").to_timestamp(), end, freq="MS")
    rows = []
    for store, daily in zip(stores["store"], stores["avg_daily_sales"]):
        monthly = daily * 30

        cycle = int(rng.choice(params.supplier_cycles))
        first_issue = start - pd.Timedelta(days=params.payment_terms_days) + pd.Timedelta(days=int(rng.integers(cycle)))
        for issue in pd.date_range(first_issue, end, freq=f"{cycle}D"):
            noise = 1 + rng.uniform(-params.supplier_noise, params.supplier_noise)
            rows.append((store, issue + pd.Timedelta(days=params.payment_terms_days), "supplier_invoice",
                         params.supplier_share * daily * cycle * noise))

        for m in month_starts:
            month_end = m + pd.offsets.MonthEnd(0)
            rows.append((store, m, "rent", params.rent_share * monthly))
            rows.append((store, m + pd.Timedelta(days=14), "payroll", params.payroll_share * monthly / 2))
            rows.append((store, month_end, "payroll", params.payroll_share * monthly / 2))
            noise = 1 + rng.uniform(-params.utilities_noise, params.utilities_noise)
            rows.append((store, m + pd.Timedelta(days=19), "utilities", params.utilities_share * monthly * noise))

    out = pd.DataFrame(rows, columns=["store", "due_date", "type", "amount"])
    out = out[(out["due_date"] >= start) & (out["due_date"] <= end)].copy()
    out["amount"] = out["amount"].round(2)
    out["label"] = out["type"].map(LABELS)
    out["scenario"] = "baseline"
    out["is_synthetic"] = True
    return out.sort_values(["store", "due_date", "type"]).reset_index(drop=True)


def opening_balance(expenses: pd.DataFrame, params: ExpenseParams = ExpenseParams()) -> pd.Series:
    """Per store: N × average daily expenses over the generated range, N ~ U(opening_balance_days)."""
    days = (expenses["due_date"].max() - expenses["due_date"].min()).days + 1
    per_day = expenses.groupby("store")["amount"].sum() / days
    lo, hi = params.opening_balance_days
    n_days = np.random.default_rng(params.seed + 1).integers(lo, hi + 1, len(per_day))
    return (per_day * n_days).round(2)
