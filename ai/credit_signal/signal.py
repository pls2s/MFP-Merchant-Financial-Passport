"""Alternative credit signal — a transparent 0-100 heuristic, **not a credit score**.

Always `status: "experimental"`. There are no default labels, so no predictive
metrics exist for it. It never approves or recommends credit; it only summarises
sales behaviour and the projected (synthetic-expense) cash position.

| Component     | Calculation                                          | Weight |
| ------------- | ---------------------------------------------------- | ------ |
| consistency   | 1 - coefficient of variation of weekly sales         | 30%    |
| trend         | last 12 weeks vs previous 12 weeks                   | 20%    |
| active_days   | share of open days with sales                        | 20%    |
| cash_buffer   | lowest projected balance / average monthly expenses  | 20%    |
| gap_frequency | number of gaps in the forecast window                | 10%    |
"""

import numpy as np
import pandas as pd

WEIGHTS = {"consistency": 0.30, "trend": 0.20, "active_days": 0.20, "cash_buffer": 0.20, "gap_frequency": 0.10}
WEEKS = 12                # trend compares the last WEEKS with the WEEKS before
TREND_FULL_SCALE = 0.20   # ±20% growth maps to 1 / 0
GAPS_FOR_ZERO = 3         # this many gaps in the window → gap_frequency 0


def _clip(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def components(history: pd.DataFrame, as_of: pd.Timestamp, lowest_balance: float,
               avg_monthly_expenses: float, n_gaps: int) -> dict[str, float]:
    """history columns: date, sales, open (actual sales only, up to as_of)."""
    recent = history[(history["date"] > as_of - pd.Timedelta(weeks=2 * WEEKS)) & (history["date"] <= as_of)]
    weekly = recent.set_index("date")["sales"].resample("W-" + as_of.strftime("%a").upper()).sum()
    weekly = weekly.iloc[-2 * WEEKS:]
    last, prev = weekly.iloc[-WEEKS:].mean(), weekly.iloc[:-WEEKS].mean()
    open_days = recent[recent["open"] == 1]

    return {
        "consistency": _clip(1 - weekly.std() / weekly.mean()) if weekly.mean() > 0 else 0.0,
        "trend": _clip(0.5 + (last / prev - 1) / (2 * TREND_FULL_SCALE)) if prev > 0 else 0.5,
        "active_days": _clip((open_days["sales"] > 0).mean()) if len(open_days) else 0.0,
        "cash_buffer": _clip(lowest_balance / avg_monthly_expenses) if avg_monthly_expenses > 0 else 0.0,
        "gap_frequency": _clip(1 - n_gaps / GAPS_FOR_ZERO),
    }


def factors(comp: dict[str, float], gaps: list[dict], lowest_balance: float, lowest_date: pd.Timestamp,
            avg_monthly_expenses: float) -> tuple[list[str], list[str]]:
    """Thai positive factors and risk indicators from per-component thresholds.
    Cash warnings always carry a date and an amount."""
    positive, risk = [], []
    if comp["consistency"] >= 0.8:
        positive.append("ยอดขายรายสัปดาห์สม่ำเสมอ")
    elif comp["consistency"] < 0.6:
        risk.append("ยอดขายรายสัปดาห์ผันผวนสูง")
    if comp["trend"] >= 0.6:
        positive.append(f"ยอดขาย {WEEKS} สัปดาห์ล่าสุดเพิ่มขึ้นจาก {WEEKS} สัปดาห์ก่อนหน้า")
    elif comp["trend"] < 0.4:
        risk.append(f"ยอดขาย {WEEKS} สัปดาห์ล่าสุดลดลงจาก {WEEKS} สัปดาห์ก่อนหน้า")
    if comp["active_days"] >= 0.98:
        positive.append("เปิดร้านแล้วมียอดขายเกือบทุกวัน")
    elif comp["active_days"] < 0.9:
        risk.append("มีหลายวันที่เปิดร้านแต่ไม่มียอดขาย")
    if comp["cash_buffer"] >= 1:
        positive.append("เงินสำรองที่คาดการณ์ไม่ต่ำกว่ารายจ่าย 1 เดือน")
    else:
        risk.append(
            f"เงินสำรองต่ำกว่ารายจ่าย 1 เดือน: คาดว่าเหลือต่ำสุด {lowest_balance:,.0f} วันที่ "
            f"{lowest_date.strftime('%Y-%m-%d')} (รายจ่ายเฉลี่ยเดือนละ {avg_monthly_expenses:,.0f})"
        )
    if not gaps:
        positive.append("ไม่พบช่วงที่เงินสดอาจไม่พอใน 14 วันข้างหน้า")
    for gap in gaps:
        risk.append(f"เงินสดอาจไม่พอวันที่ {gap['date']} ขาดประมาณ {gap['shortfall']:,.0f}")
    return positive, risk


def credit_signal(merchant_id: int, history: pd.DataFrame, as_of: pd.Timestamp, lowest_balance: float,
                  lowest_date: pd.Timestamp, avg_monthly_expenses: float, gaps: list[dict]) -> dict:
    """`credit-signal` contract object."""
    comp = components(history, as_of, lowest_balance, avg_monthly_expenses, len(gaps))
    positive, risk = factors(comp, gaps, lowest_balance, lowest_date, avg_monthly_expenses)
    observed = history[(history["date"] <= as_of) & history["sales"].notna()]
    return {
        "merchant_id": int(merchant_id),
        "score": int(round(100 * sum(WEIGHTS[k] * v for k, v in comp.items()))),
        "status": "experimental",
        "components": {k: round(v, 2) for k, v in comp.items()},
        "positive_factors": positive,
        "risk_indicators": risk,
        "data_coverage": {
            "start": observed["date"].min().strftime("%Y-%m-%d"),
            "end": observed["date"].max().strftime("%Y-%m-%d"),
            "days": int(len(observed)),
        },
    }
