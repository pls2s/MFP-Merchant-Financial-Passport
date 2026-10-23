"""Facts the copilot may use — every figure computed here, never by the LLM.

`build_facts` turns one merchant's data into a nested dict of already-formatted Thai
strings: sales patterns, the day-by-day forecast, upcoming (synthetic) expenses, the
projected balance, forecast accuracy, the experimental credit signal, and what-if
scenarios re-simulated with the WS2 gap finder.
"""

import json
import re
from dataclasses import dataclass

import pandas as pd

from ai.gap_detection.gaps import find_gaps, simulate_balance

THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
THAI_WEEKDAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]  # Monday first
COMPONENT_NAMES = {
    "consistency": ("ความสม่ำเสมอของยอดขายรายสัปดาห์", 30),
    "trend": ("แนวโน้มยอดขาย", 20),
    "active_days": ("สัดส่วนวันที่เปิดร้านแล้วมียอดขาย", 20),
    "cash_buffer": ("เงินสำรองเทียบกับรายจ่าย 1 เดือน", 20),
    "gap_frequency": ("ความถี่ที่เงินสดอาจไม่พอ", 10),
}
SCENARIO_SALES_CHANGE = 0.10   # ±10% sales
SCENARIO_DELAY_DAYS = 7        # postpone the largest upcoming expense
RECENT_WEEKS = 12


def thai_date(d) -> str:
    d = pd.Timestamp(d)
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"


def thai_day(d) -> str:
    d = pd.Timestamp(d)
    return f"{thai_date(d)} (วัน{THAI_WEEKDAYS[d.dayofweek]})"


def money(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float) -> str:
    return "0%" if round(x * 100) == 0 else f"{x * 100:+.0f}%"


@dataclass
class MerchantContext:
    merchant_id: int
    as_of: pd.Timestamp
    forecast: dict                 # `forecast` contract
    gaps: dict                     # `cash-flow-gaps` contract
    credit: dict                   # `credit-signal` contract
    history: pd.DataFrame          # date, sales, open, promo, holiday (actual up to as_of)
    sales: pd.DataFrame            # date, sales, is_forecast (simulation input)
    expenses: pd.DataFrame         # due_date, type, label, amount (synthetic, simulation window)
    score_rank: tuple[int, int] | None = None  # (rank by score, number of stores); 1 = highest
    past_gaps: list[dict] | None = None          # shortfalls before as_of (same shape as gaps)
    long_forecast: pd.DataFrame | None = None    # date, forecast, lower, upper (84 days, recursive LSTM+GRU)
    seasonal: pd.DataFrame | None = None         # month, outlook, lower, upper (12 months, seasonal)
    long_metrics: dict | None = None             # models/forecasts/long_range_metrics.json


def _sales_patterns(ctx: MerchantContext) -> dict:
    h = ctx.history[(ctx.history["date"] <= ctx.as_of) & ctx.history["sales"].notna()]
    recent = h[h["date"] > ctx.as_of - pd.Timedelta(weeks=RECENT_WEEKS)]
    prev = h[(h["date"] <= ctx.as_of - pd.Timedelta(weeks=RECENT_WEEKS))
             & (h["date"] > ctx.as_of - pd.Timedelta(weeks=2 * RECENT_WEEKS))]
    last28 = h[h["date"] > ctx.as_of - pd.Timedelta(days=28)]
    open_recent = recent[(recent["open"] == 1) & (recent["sales"] > 0)]
    by_dow = open_recent.groupby(open_recent["date"].dt.dayofweek)["sales"].mean()
    promo = open_recent[open_recent["promo"] == 1]["sales"].mean()
    no_promo = open_recent[open_recent["promo"] == 0]["sales"].mean()

    facts = {
        "ยอดขายรวม 28 วันล่าสุด": money(last28["sales"].sum()),
        "ยอดขายเฉลี่ยต่อวันที่เปิดร้าน (28 วันล่าสุด)": money(last28.loc[last28["sales"] > 0, "sales"].mean()),
        "จำนวนวันที่ร้านปิดใน 28 วันล่าสุด": str(int((last28["open"] == 0).sum())),
        f"ยอดขาย {RECENT_WEEKS} สัปดาห์ล่าสุดเทียบกับ {RECENT_WEEKS} สัปดาห์ก่อนหน้า":
            pct(recent["sales"].sum() / prev["sales"].sum() - 1) if prev["sales"].sum() > 0 else "ไม่มีข้อมูล",
    }
    if len(by_dow):
        facts[f"วันที่ขายดีที่สุด (เฉลี่ย {RECENT_WEEKS} สัปดาห์)"] = f"วัน{THAI_WEEKDAYS[by_dow.idxmax()]} {money(by_dow.max())}"
        facts[f"วันที่ขายน้อยที่สุด (เฉลี่ย {RECENT_WEEKS} สัปดาห์)"] = f"วัน{THAI_WEEKDAYS[by_dow.idxmin()]} {money(by_dow.min())}"
    if pd.notna(promo) and pd.notna(no_promo) and no_promo > 0:
        facts["วันที่มีโปรโมชันขายได้มากกว่าวันปกติ"] = pct(promo / no_promo - 1)
    return facts


def _forecast_facts(ctx: MerchantContext) -> dict:
    flags = ctx.history.set_index("date")
    future = [p for p in ctx.forecast["points"] if pd.Timestamp(p["date"]) > ctx.as_of]
    days = []
    for p in future:
        d = pd.Timestamp(p["date"])
        row = flags.loc[d] if d in flags.index else None
        if row is not None and not row["open"]:
            days.append(f"{thai_day(d)}: ร้านปิด")
            continue
        tags = [t for t, on in (("โปรโมชัน", row is not None and row["promo"]),
                                ("วันหยุดนักขัตฤกษ์", row is not None and row["holiday"])) if on]
        days.append(f"{thai_day(d)}: {money(p['forecast'])}" + (f" [{', '.join(tags)}]" if tags else ""))

    past = [p for p in ctx.forecast["points"]
            if pd.Timestamp(p["date"]) <= ctx.as_of and (p.get("actual") or 0) > 0 and p["forecast"] > 0]
    facts = {
        "ช่วงที่โมเดลพยากรณ์": (f"14 วัน: {thai_date(future[0]['date'])} ถึง {thai_date(future[-1]['date'])} "
                               "(โมเดลไม่ได้พยากรณ์ไกลกว่านี้)") if future else "ไม่มี",
        "ยอดขายคาดการณ์รวม 14 วันข้างหน้า": money(sum(p["forecast"] for p in future)),
        "ยอดขายคาดการณ์รายสัปดาห์": [
            f"{thai_date(week[0]['date'])} ถึง {thai_date(week[-1]['date'])}: {money(sum(p['forecast'] for p in week))}"
            for week in (future[i:i + 7] for i in range(0, len(future), 7)) if week
        ],
        "ยอดขายคาดการณ์รายวัน": days,
    }
    if past:
        err = sum(abs(p["forecast"] - p["actual"]) for p in past) / sum(p["actual"] for p in past)
        within = sum(abs(p["forecast"] - p["actual"]) / p["actual"] <= 0.1 for p in past)
        facts["ความแม่นของการพยากรณ์ร้านนี้ (ทดสอบย้อนหลัง)"] = (
            f"คลาดเคลื่อนเฉลี่ย {err * 100:.1f}% และทายคลาดไม่เกิน 10% ได้ {within} จาก {len(past)} วัน"
        )
    return facts


def _long_range(ctx: MerchantContext) -> dict:
    """3-month recursive LSTM+GRU and 12-month seasonal outlook, with their backtests."""
    out = {}
    m = ctx.long_metrics or {}
    if ctx.long_forecast is not None and len(ctx.long_forecast):
        lf = ctx.long_forecast.assign(month=ctx.long_forecast["date"].dt.to_period("M"))
        months = []
        for per, g in lf.groupby("month"):
            label = f"{THAI_MONTHS[per.month - 1]} {per.year + 543}"
            span = f" ({thai_date(g['date'].min())} ถึง {thai_date(g['date'].max())})" if len(g) < per.days_in_month else ""
            months.append(f"{label}{span}: {money(g['forecast'].sum())} (ช่วงประมาณ {money(g['lower'].sum())} ถึง {money(g['upper'].sum())})")
        rec = m.get("recursive_3_months", {})
        out["พยากรณ์ 3 เดือนข้างหน้า (LSTM+GRU ทายต่อเนื่องทีละ 14 วัน)"] = {
            "ช่วงที่ครอบคลุม": f"{thai_date(lf['date'].min())} ถึง {thai_date(lf['date'].max())}",
            "ยอดขายรายเดือน": months,
            "ความแม่น (ทดสอบย้อนหลัง 84 วัน)": (
                f"ร้านนี้คลาดเคลื่อนเฉลี่ย {rec['wape_by_store'][str(ctx.merchant_id)] * 100:.1f}% ทุกร้าน {rec['wape_all_stores'] * 100:.1f}%"
                if str(ctx.merchant_id) in rec.get("wape_by_store", {}) else "ไม่มีข้อมูล"),
            "หมายเหตุ": "ยิ่งไกลยิ่งคลาดมากขึ้น หลัง 31 ก.ค. 2558 ใช้ตารางโปรโมชันจำลองแบบเดียวกับปีก่อน",
        }
    if ctx.seasonal is not None and len(ctx.seasonal):
        sea = m.get("seasonal_1_year", {})
        tested = ctx.seasonal["backtested"] if "backtested" in ctx.seasonal else pd.Series(True, index=ctx.seasonal.index)
        rows = [f"{THAI_MONTHS[int(r.month[5:]) - 1]} {int(r.month[:4]) + 543}: "
                + (f"{money(r.outlook)} (ช่วงประมาณ {money(r.lower)} ถึง {money(r.upper)})" if pd.notna(r.outlook) else "ข้อมูลไม่พอ")
                + ("" if ok else " · ยังไม่ได้ทดสอบย้อนหลัง ความไม่แน่นอนสูง")
                for r, ok in zip(ctx.seasonal.itertuples(), tested)]
        first, last = ctx.seasonal["month"].iloc[0], ctx.seasonal["month"].iloc[-1]
        out["ภาพรวมรายเดือนระยะยาว (ตามฤดูกาลจากยอดปีก่อน ไม่ใช่ผลโมเดล deep learning)"] = {
            "ช่วงที่ครอบคลุม": (f"{THAI_MONTHS[int(first[5:]) - 1]} {int(first[:4]) + 543} ถึง "
                               f"{THAI_MONTHS[int(last[5:]) - 1]} {int(last[:4]) + 543} (หลังจากนี้พยากรณ์ไม่ได้)"),
            "ยอดขายรายเดือน": rows,
            "ความแม่น (ทดสอบย้อนหลัง 12 เดือนแรก)": (
                f"ร้านนี้คลาดเคลื่อนเฉลี่ย {sea['wape_by_store'][str(ctx.merchant_id)] * 100:.1f}% ทุกร้าน {sea['wape_all_stores'] * 100:.1f}%"
                if str(ctx.merchant_id) in sea.get("wape_by_store", {}) else "ไม่มีข้อมูล"),
        }
    return out or {"สถานะ": "ไม่มีข้อมูลพยากรณ์ระยะยาว"}


def _balance_summary(sales: pd.DataFrame, expenses: pd.DataFrame, opening: float, as_of: pd.Timestamp) -> dict:
    bal = simulate_balance(sales, expenses, opening)
    proj = bal[bal["date"] > as_of]
    low = proj.loc[proj["balance"].idxmin()]
    gaps = find_gaps(bal, expenses, start=as_of + pd.Timedelta(days=1))
    return {"balance": bal, "low": low, "gaps": gaps, "end": proj.iloc[-1]}


def _describe(s: dict) -> str:
    text = f"เงินต่ำสุด {money(s['low']['balance'])} วันที่ {thai_date(s['low']['date'])}"
    if s["gaps"]:
        first = s["gaps"][0]
        return text + (f" · เงินอาจไม่พอ {len(s['gaps'])} ครั้ง ครั้งแรก {thai_date(first['date'])}"
                       f" ขาดประมาณ {money(first['shortfall'])}")
    return text + " · ไม่มีวันที่เงินไม่พอ"


def _scenarios(ctx: MerchantContext) -> dict:
    opening = ctx.gaps["opening_balance"]
    future = ctx.sales["date"] > ctx.as_of
    out = {}
    for sign, label in ((-1, "ต่ำกว่า"), (1, "สูงกว่า")):
        s = ctx.sales.copy()
        s.loc[future, "sales"] *= 1 + sign * SCENARIO_SALES_CHANGE
        out[f"ถ้ายอดขาย 14 วันข้างหน้า{label}ที่คาดไว้ {SCENARIO_SALES_CHANGE * 100:.0f}%"] = _describe(
            _balance_summary(s, ctx.expenses, opening, ctx.as_of))

    upcoming = ctx.expenses[ctx.expenses["due_date"] > ctx.as_of]
    if len(upcoming):
        big = upcoming.loc[upcoming["amount"].idxmax()]
        moved = ctx.expenses.copy()
        moved.loc[big.name, "due_date"] = big["due_date"] + pd.Timedelta(days=SCENARIO_DELAY_DAYS)
        out[f"ถ้าเลื่อน{big['label']} {money(big['amount'])} จากวันที่ {thai_date(big['due_date'])} "
            f"ออกไป {SCENARIO_DELAY_DAYS} วัน"] = _describe(_balance_summary(ctx.sales, moved, opening, ctx.as_of))
    return out


def build_facts(ctx: MerchantContext) -> dict:
    """Every figure the copilot may mention, already formatted."""
    base = _balance_summary(ctx.sales, ctx.expenses, ctx.gaps["opening_balance"], ctx.as_of)
    bal = base["balance"]
    today = bal.loc[bal["date"] <= ctx.as_of, "balance"].iloc[-1]
    upcoming = ctx.expenses[ctx.expenses["due_date"] > ctx.as_of].sort_values("due_date")
    credit = ctx.credit

    score = {"คะแนน": f"{credit['score']}/100"}
    if ctx.score_rank is not None:
        rank, total = ctx.score_rank
        score["เทียบกับร้านอื่น"] = f"อันดับที่ {rank:,} จาก {total:,} ร้าน (อันดับ 1 คือคะแนนสูงสุด)"
    score["องค์ประกอบ (0 ถึง 1, ยิ่งสูงยิ่งดี)"] = [
        f"{COMPONENT_NAMES[k][0]} (น้ำหนัก {COMPONENT_NAMES[k][1]}%): {v:.2f}" for k, v in credit["components"].items()
    ]

    return {
        "ร้าน": f"ร้านตัวอย่าง #{ctx.merchant_id}",
        "วันนี้ (ข้อมูลล่าสุด)": thai_day(ctx.as_of),
        "ยอดขายที่ผ่านมา (ข้อมูลจริง)": _sales_patterns(ctx),
        "การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)": _forecast_facts(ctx),
        "พยากรณ์ระยะยาว": _long_range(ctx),
        "รายจ่ายที่จะครบกำหนดใน 14 วันข้างหน้า (ข้อมูลจำลอง)": {
            "รายการ": [f"{thai_date(r.due_date)}: {r.label} {money(r.amount)}" for r in upcoming.itertuples()],
            "รวม": money(upcoming["amount"].sum()),
        },
        "ยอดเงินคงเหลือ (ข้อมูลจำลอง)": {
            "วันนี้": money(today),
            "ต่ำสุดในช่วงคาดการณ์": f"{money(base['low']['balance'])} วันที่ {thai_date(base['low']['date'])}",
            "สิ้นช่วงคาดการณ์": f"{money(base['end']['balance'])} วันที่ {thai_date(base['end']['date'])}",
        },
        "จำนวนครั้งที่เงินสดอาจไม่พอ (กรณีปกติ ไม่ใช่สถานการณ์สมมติ)": str(len(ctx.gaps["gaps"])),
        "วันที่เงินสดอาจไม่พอ": [
            {
                "วันที่": thai_date(g["date"]),
                "ขาดประมาณ": money(g["shortfall"]),
                "รายจ่ายหลัก": [f"{c['label']} {money(c['amount'])}" for c in g["contributors"][:2]],
                "รวมรายจ่ายหลัก": money(sum(c["amount"] for c in g["contributors"][:2])),
            }
            for g in ctx.gaps["gaps"]
        ],
        "ประวัติวันที่เงินสดเคยไม่พอ (ข้อมูลจำลอง ตั้งแต่ 1 ม.ค. 2558)": {
            "จำนวนครั้ง": str(len(ctx.past_gaps or [])),
            "รายการ": [
                f"{thai_date(g['date'])} ขาดประมาณ {money(g['shortfall'])}"
                + (f" ({g['contributors'][0]['label']} {money(g['contributors'][0]['amount'])})" if g["contributors"] else "")
                for g in (ctx.past_gaps or [])
            ],
        },
        "สถานการณ์สมมติ (ระบบคำนวณให้แล้ว)": _scenarios(ctx),
        "สัญญาณการเงิน (ทดลอง ไม่ใช่คะแนนเครดิต)": score,
        "จุดแข็ง": credit["positive_factors"],
        "จุดที่ควรระวัง": [
            r for r in (_thai_dates(x) for x in credit["risk_indicators"]) if not r.startswith("เงินสดอาจไม่พอ")
        ],
    }


def _thai_dates(text: str) -> str:
    return re.sub(r"\d{4}-\d{2}-\d{2}", lambda m: thai_date(m.group()), text)


def _store_rows(path, merchant_id: int) -> pd.DataFrame:
    df = pd.read_parquet(path)
    return df[df["store"] == merchant_id].drop(columns="store").reset_index(drop=True)


def score_rank(score: int, all_scores: list[int]) -> tuple[int, int]:
    """1 + number of stores with a strictly higher score (ties share a rank)."""
    return 1 + sum(s > score for s in all_scores), len(all_scores)


def load_context(merchant_id: int) -> MerchantContext:
    """Build the context from the committed files (CLI use; the backend builds it from memory)."""
    from ai.cashflow_forecast.long_range import FORECASTS_DIR
    from ai.cashflow_forecast.predict import HISTORY_PATH
    from ai.credit_signal.build import CREDIT_PATH
    from ai.gap_detection.build import AS_OF, EXPENSES_PATH, FORECASTS_PATH, GAPS_PATH, past_gaps, sales_series

    def find(path):
        return next(x for x in json.loads(path.read_text()) if x["merchant_id"] == merchant_id)

    credit_all = json.loads(CREDIT_PATH.read_text())
    credit = next(c for c in credit_all if c["merchant_id"] == merchant_id)
    sales = sales_series()[merchant_id]
    expenses = pd.read_parquet(EXPENSES_PATH)
    expenses = expenses[(expenses["store"] == merchant_id) & (expenses["due_date"] >= sales["date"].min())]
    history = pd.read_parquet(HISTORY_PATH)
    gaps = find(GAPS_PATH)
    return MerchantContext(
        merchant_id=merchant_id, as_of=AS_OF, forecast=find(FORECASTS_PATH), gaps=gaps, credit=credit,
        past_gaps=past_gaps(sales, expenses, gaps["opening_balance"]),
        history=history[history["store"] == merchant_id].drop(columns="store"),
        sales=sales, expenses=expenses,
        score_rank=score_rank(credit["score"], [c["score"] for c in credit_all]),
        long_forecast=_store_rows(FORECASTS_DIR / "long_forecast.parquet", merchant_id),
        seasonal=_store_rows(FORECASTS_DIR / "seasonal_outlook.parquet", merchant_id),
        long_metrics=json.loads((FORECASTS_DIR / "long_range_metrics.json").read_text()),
    )
