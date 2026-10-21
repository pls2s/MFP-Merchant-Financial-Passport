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
        long_forecast=pd.DataFrame({"date": pd.date_range("2015-07-18", periods=84), "forecast": 1000.0,
                                    "lower": 900.0, "upper": 1100.0}),
        seasonal=pd.DataFrame({"month": [f"2015-{m:02d}" for m in range(8, 13)] + [f"2016-{m:02d}" for m in range(1, 8)],
                               "outlook": [30000.0] * 11 + [None], "lower": [27000.0] * 11 + [None],
                               "upper": [33000.0] * 11 + [None]}),
        long_metrics={"recursive_3_months": {"wape_all_stores": 0.08, "wape_by_store": {"1": 0.076}},
                      "seasonal_1_year": {"wape_all_stores": 0.072, "wape_by_store": {"1": 0.056}}},
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
    ("เดือนหน้ายอดขายจะเป็นยังไง", "LSTM+GRU ทายต่อเนื่อง"),
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

    def fake(facts, q, history, feedback=None, months=None):
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

    def fake(facts, q, history, feedback=None, months=None):
        calls.append(feedback)
        return "รวม 123,456" if feedback is None else "วันที่ 22 ก.ค. 2558 ขาดประมาณ 7,900"

    monkeypatch.setattr(cp, "call_llm", fake)
    assert cp.explain(ctx)["source"] == "llm"
    assert calls[0] is None and "123456" in calls[1]


def test_gives_up_after_max_attempts(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(cp, "call_llm", lambda facts, q, history, feedback=None, months=None: calls.append(1) or "แนะนำให้กู้")
    result = cp.explain(ctx)
    assert result["source"] == "template" and len(calls) == cp.MAX_ATTEMPTS


def test_api_error_falls_back(ctx, monkeypatch):
    def boom(facts, q, history, feedback=None, months=None):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(cp, "call_llm", boom)
    assert cp.explain(ctx)["source"] == "template"


def test_long_range_facts_label_methods_and_accuracy(facts):
    fc = facts["การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)"]
    assert "14 วัน" in fc["ช่วงที่โมเดลพยากรณ์"] and "18 ก.ค. 2558" in fc["ช่วงที่โมเดลพยากรณ์"]
    lr = facts["พยากรณ์ระยะยาว"]
    rec = lr["พยากรณ์ 3 เดือนข้างหน้า (LSTM+GRU ทายต่อเนื่องทีละ 14 วัน)"]
    assert rec["ยอดขายรายเดือน"][1].startswith("ส.ค. 2558: 31,000")  # 31 days × 1,000
    assert "7.6%" in rec["ความแม่น (ทดสอบย้อนหลัง 84 วัน)"]
    sea = lr["ภาพรวมรายเดือนระยะยาว (ตามฤดูกาลจากยอดปีก่อน ไม่ใช่ผลโมเดล deep learning)"]
    assert len(sea["ยอดขายรายเดือน"]) == 12 and sea["ยอดขายรายเดือน"][-1].endswith("ข้อมูลไม่พอ")


def test_long_range_missing_data(ctx):
    ctx.long_forecast, ctx.seasonal = None, None
    facts = build_facts(ctx)
    assert facts["พยากรณ์ระยะยาว"] == {"สถานะ": "ไม่มีข้อมูลพยากรณ์ระยะยาว"}
    text = cp.template_answer(facts, "เดือนหน้าเป็นยังไง")
    assert "ยังไม่มีข้อมูลพยากรณ์ระยะยาว" in text and cp.validate(text, facts) is None


def test_validate_rejects_month_year_not_in_facts(facts):
    assert cp.validate("ธ.ค. 2558: 30,000", facts) is None
    assert cp.validate("ธันวาคม 2558 ยอดประมาณ 30,000", facts) is None  # full month name is fine
    assert "months not in facts" in cp.validate("ธันวาคม 2559 ยอดประมาณ 30,000", facts)  # beyond the outlook
    assert cp.validate("ธันวาคม 2559 ยังพยากรณ์ไม่ได้", facts, user_text="ธันวาคม 2559 จะเป็นยังไง") is None


@pytest.mark.parametrize("question,expected", [
    ("เดือนสิงหาคมปีหน้าจะเป็นยังไง", ["ส.ค. 2559"]),
    ("สิงหาคมจะขายได้เท่าไหร่", ["ส.ค. 2558"]),        # next occurrence after 17 Jul 2558
    ("มีนาคมเป็นยังไง", ["มี.ค. 2559"]),
    ("ธ.ค. 2558 กับ ธันวาคมปีที่แล้ว", ["ธ.ค. 2558", "ธ.ค. 2557"]),
    ("เดือนหน้าขายได้เท่าไหร่", ["ส.ค. 2558"]),
    ("December 2015", []),
])
def test_resolve_months(question, expected):
    assert cp.resolve_months(question, AS_OF) == expected


def test_validate_allows_sums_and_rounding_but_not_inventions(facts):
    # The fixture has expenses 40,000 and 3,000 and a shortfall of 7,900.
    assert cp.validate("รวมรายจ่ายสองรายการ 43,000", facts) is None            # 40,000 + 3,000
    assert cp.validate("ส่วนต่าง 37,000", facts) is None                       # 40,000 − 3,000 (same list)
    assert "numbers not in facts" in cp.validate("ส่วนต่าง 29,000", facts)    # not a sum/difference within a list
    assert "numbers not in facts" in cp.validate("ตั้งเป้าเงินสำรอง 10,000", facts)  # a made-up target
    assert cp.validate("ประมาณ 31,000 ต่อเดือน", facts) is None                # 31,000 is in the facts anyway
    assert "numbers not in facts" in cp.validate("ประมาณ 45,500", facts)
    assert "numbers not in facts" in cp.validate("เพิ่มขึ้น 37%", facts)          # no self-made percentages


def test_month_outside_horizon_gets_direct_template_answer(facts):
    months = cp.resolve_months("กรกฎาคม 2560 จะขายได้เท่าไหร่", AS_OF)
    text = cp.template_answer(facts, "กรกฎาคม 2560 จะขายได้เท่าไหร่", months)
    assert text.startswith("ก.ค. 2560 อยู่นอกช่วงที่พยากรณ์ได้")
    assert cp.validate(text, facts, months=months) is None


def test_month_inside_horizon_gets_its_value(facts):
    months = cp.resolve_months("สิงหาคมจะขายได้เท่าไหร่", AS_OF)
    text = cp.template_answer(facts, "สิงหาคมจะขายได้เท่าไหร่", months)
    assert text.startswith("ส.ค. 2558:") and "LSTM+GRU ทายต่อเนื่อง: 31,000" in text and "ภาพรวมตามฤดูกาล" in text


def test_llm_sees_resolved_month(ctx, monkeypatch):
    seen = {}

    def fake(facts, q, history, feedback=None, months=None):
        seen["months"] = months
        return "ส.ค. 2559 อยู่นอกช่วงที่พยากรณ์ได้"

    monkeypatch.setattr(cp, "call_llm", fake)
    result = cp.explain(ctx, "เดือนสิงหาคมปีหน้าจะเป็นยังไง")
    assert seen["months"] == ["ส.ค. 2559"] and result["source"] == "llm"
