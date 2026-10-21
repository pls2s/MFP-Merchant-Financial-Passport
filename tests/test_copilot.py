import numpy as np
import pandas as pd
import pytest
import requests

from ai.copilot import explain as cp
from ai.copilot.facts import MerchantContext, build_facts, score_rank

AS_OF = pd.Timestamp("2015-07-17")


@pytest.fixture
def ctx():
    """A small synthetic store: 1 year of history, 14-day forecast, one big invoice causing a gap."""
    dates = pd.date_range(AS_OF - pd.Timedelta(days=420), AS_OF + pd.Timedelta(days=14))
    is_open = (dates.dayofweek != 6).astype(int)
    promo = ((dates.day % 14) < 5).astype(int)
    sales = np.where(is_open, 1000.0 * (1 + 0.3 * promo), 0.0)
    history = pd.DataFrame({"date": dates, "sales": np.where(dates <= AS_OF, sales, np.nan),
                            "open": is_open, "promo": promo, "holiday": 0})
    window = dates[dates > AS_OF - pd.Timedelta(days=28)]
    points = [{"date": d.strftime("%Y-%m-%d"), "forecast": float(s * 1.05), "actual": float(s)}
              for d, s in zip(window, sales[-len(window):])]
    sim = pd.DataFrame({"date": window, "sales": sales[-len(window):], "is_forecast": window > AS_OF})
    sim.loc[sim["is_forecast"], "sales"] = [p["forecast"] for p in points if p["date"] > "2015-07-17"]
    expenses = pd.DataFrame({
        "due_date": [pd.Timestamp("2015-07-01"), pd.Timestamp("2015-07-22"), pd.Timestamp("2015-07-28")],
        "type": ["rent", "supplier_invoice", "payroll"],
        "label": ["ค่าเช่าร้าน", "ค่าสินค้า supplier", "เงินเดือนพนักงาน"],
        "amount": [5000.0, 40000.0, 3000.0],
    })
    return MerchantContext(
        merchant_id=1, as_of=AS_OF, forecast={"points": points},
        gaps={"opening_balance": 2000.0, "gaps": [{"date": "2015-07-22", "shortfall": 7900.0, "balance_after": -7900.0,
              "contributors": [{"type": "supplier_invoice", "label": "ค่าสินค้า supplier", "amount": 40000.0,
                                "due_date": "2015-07-22"}]}]},
        credit={"score": 58, "components": {"consistency": 0.86, "trend": 0.46, "active_days": 1.0,
                                            "cash_buffer": 0.0, "gap_frequency": 0.33},
                "positive_factors": ["ยอดขายรายสัปดาห์สม่ำเสมอ"],
                "risk_indicators": ["เงินสำรองต่ำกว่ารายจ่าย 1 เดือน: คาดว่าเหลือต่ำสุด -7,900 วันที่ 2015-07-22",
                                    "เงินสดอาจไม่พอวันที่ 2015-07-22 ขาดประมาณ 7,900"]},
        history=history, sales=sim, expenses=expenses, score_rank=(1113, 1115),
    )


@pytest.fixture
def facts(ctx):
    return build_facts(ctx)


def test_facts_cover_sales_forecast_expenses_scenarios(facts):
    sales = facts["ยอดขายที่ผ่านมา (ข้อมูลจริง)"]
    assert sales["วันที่มีโปรโมชันขายได้มากกว่าวันปกติ"] == "+30%"
    days = facts["การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)"]["ยอดขายคาดการณ์รายวัน"]
    assert len(days) == 14 and any("ร้านปิด" in d for d in days) and any("โปรโมชัน" in d for d in days)
    weeks = facts["การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)"]["ยอดขายคาดการณ์รายสัปดาห์"]
    assert len(weeks) == 2 and weeks[0].startswith("18 ก.ค. 2558 ถึง 24 ก.ค. 2558")
    upcoming = facts["รายจ่ายที่จะครบกำหนดใน 14 วันข้างหน้า (ข้อมูลจำลอง)"]["รายการ"]
    assert upcoming[0].startswith("22 ก.ค. 2558") and len(upcoming) == 2  # rent on 1 Jul is in the past
    scenarios = facts["สถานการณ์สมมติ (ระบบคำนวณให้แล้ว)"]
    assert len(scenarios) == 3 and any("เลื่อนค่าสินค้า supplier" in k for k in scenarios)
    assert "1,113 จาก 1,115" in facts["สัญญาณการเงิน (ทดลอง ไม่ใช่คะแนนเครดิต)"]["เทียบกับร้านอื่น"]
    assert not any("2015-" in r for r in facts["จุดที่ควรระวัง"])


def test_scenarios_move_in_the_right_direction(ctx, facts):
    s = facts["สถานการณ์สมมติ (ระบบคำนวณให้แล้ว)"]
    low = {k: float(v.split("เงินต่ำสุด ")[1].split(" ")[0].replace(",", "")) for k, v in s.items()}
    lower, higher, delayed = (next(v for k, v in low.items() if word in k) for word in ("ต่ำกว่า", "สูงกว่า", "เลื่อน"))
    assert lower < higher and delayed > lower


def test_score_rank_ties_share_rank():
    assert score_rank(80, [90, 80, 80, 70]) == (2, 4)


@pytest.mark.parametrize("question,expected", [
    (None, "ยอดขายรวมประมาณ"),
    ("ถ้ายอดขายลดลงจะเป็นยังไง", "สถานการณ์สมมติ"),
    ("สัปดาห์หน้าต้องจ่ายอะไรบ้าง", "รายจ่ายที่จะครบกำหนด"),
    ("โปรโมชันช่วยไหม", "โปรโมชัน"),
    ("ทำไมคะแนนได้เท่านี้", "องค์ประกอบ"),
    ("ควรกู้เงินไหม", "ไม่ให้คำแนะนำด้านสินเชื่อ"),
    ("เดือนหน้ายอดขายจะเป็นยังไง", "พยากรณ์ได้แค่"),
    ("สัปดาห์หน้ายอดขายเป็นยังไง", "ยอดขายคาดการณ์รายสัปดาห์"),
])
def test_template_answers_by_topic_and_passes_validation(facts, question, expected):
    text = cp.template_answer(facts, question)
    assert expected in text and cp.DISCLAIMER in text
    assert cp.validate(text, facts, question or "") is None


def test_validate_numbers(facts):
    assert cp.validate("วันที่ 22 ก.ค. 2558 ขาดประมาณ 7,900", facts) is None
    assert cp.validate("มี 3 วิธีที่ช่วยได้", facts) is None  # small count
    assert "numbers not in facts" in cp.validate("ขาดประมาณ 8,123", facts)
    assert "numbers not in facts" in cp.validate("วันที่ 2015-07-22", facts)  # reformatted date
    assert cp.validate("ถ้าขายได้ 12,345 จะเป็นยังไง", facts, user_text="ถ้าขายได้ 12,345") is None  # user's own number


def test_validate_rejects_loan_wording(facts):
    assert "banned" in cp.validate("แนะนำให้กู้เงินเพื่อเสริมสภาพคล่อง", facts)
    assert "banned" in cp.validate("สินเชื่อของคุณได้รับการอนุมัติ", facts)


def test_no_api_key_falls_back_to_topic_template(ctx, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = cp.explain(ctx, "ถ้าเลื่อนจ่าย supplier ได้ไหม")
    assert result["source"] == "template" and "สถานการณ์สมมติ" in result["answer"]
    assert "LLM_API_KEY" in result["fallback_reason"] and result["is_synthetic_expense"] is True


def test_history_is_passed_and_user_numbers_allowed(ctx, monkeypatch):
    seen = {}

    def fake(facts, q, history, feedback=None):
        seen["history"] = history
        return "ถ้าขายได้ 99,999 ระบบยังไม่มีสถานการณ์นี้ แต่มีกรณียอดขายลดลงให้ดูครับ"

    monkeypatch.setattr(cp, "call_llm", fake)
    history = [{"role": "user", "content": "สวัสดี"}, {"role": "assistant", "content": "สวัสดีครับ"},
               {"role": "system", "content": "ignored"}]
    result = cp.explain(ctx, "ถ้าขายได้ 99,999 ล่ะ", history)
    assert result["source"] == "llm"
    assert [m["role"] for m in seen["history"]] == ["user", "assistant"]


def test_retry_once_with_feedback_then_accept(ctx, monkeypatch):
    calls = []

    def fake(facts, q, history, feedback=None):
        calls.append(feedback)
        return "รวม 123,456" if feedback is None else "วันที่ 22 ก.ค. 2558 ขาดประมาณ 7,900"

    monkeypatch.setattr(cp, "call_llm", fake)
    assert cp.explain(ctx)["source"] == "llm"
    assert calls[0] is None and "123456" in calls[1]


def test_gives_up_after_max_attempts(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(cp, "call_llm", lambda facts, q, history, feedback=None: calls.append(1) or "แนะนำให้กู้")
    result = cp.explain(ctx)
    assert result["source"] == "template" and len(calls) == cp.MAX_ATTEMPTS


def test_api_error_falls_back(ctx, monkeypatch):
    def boom(facts, q, history, feedback=None):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(cp, "call_llm", boom)
    assert cp.explain(ctx)["source"] == "template"


def test_next_month_outlook_is_labelled_and_uses_last_year(facts):
    fc = facts["การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)"]
    assert "14 วัน" in fc["ช่วงที่โมเดลพยากรณ์"] and "18 ก.ค. 2558" in fc["ช่วงที่โมเดลพยากรณ์"]
    outlook = facts["ภาพรวมเดือนหน้าแบบคร่าว ๆ (จากข้อมูลปีก่อน ไม่ใช่ผลโมเดล)"]
    assert outlook["เดือน"] == "ส.ค. 2558" and "ไม่ใช่ผลโมเดล" in outlook["หมายเหตุ"]
    assert "ยอดขายจริง ส.ค. 2557 (ปีก่อน)" in outlook
    # The synthetic store has no trend, so the rough estimate stays close to last year's month.
    last_year = float(outlook["ยอดขายจริง ส.ค. 2557 (ปีก่อน)"].replace(",", ""))
    estimate = float(outlook["ประมาณการคร่าว ๆ (ยอดปีก่อน × อัตราเปลี่ยนแปลง)"].replace(",", ""))
    assert abs(estimate / last_year - 1) < 0.05


def test_next_month_outlook_needs_full_last_year(ctx):
    ctx.history = ctx.history[ctx.history["date"] > AS_OF - pd.Timedelta(days=364)]
    outlook = build_facts(ctx)["ภาพรวมเดือนหน้าแบบคร่าว ๆ (จากข้อมูลปีก่อน ไม่ใช่ผลโมเดล)"]
    assert outlook["สถานะ"].startswith("ข้อมูลปีก่อนไม่ครบ")
    assert cp.validate(cp.template_answer(build_facts(ctx), "เดือนหน้าเป็นยังไง"), build_facts(ctx)) is None
