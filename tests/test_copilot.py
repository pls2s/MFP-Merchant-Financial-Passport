import pytest
import requests

from ai.copilot import explain as cp

AS_OF = "2015-07-17"
FORECAST = {"points": [
    {"date": "2015-07-17", "forecast": 900.0, "actual": 950.0},
    {"date": "2015-07-18", "forecast": 1000.0, "actual": 0.0},
    {"date": "2015-07-19", "forecast": 2500.0, "actual": 0.0},
]}
GAPS = {"gaps": [{"date": "2015-07-22", "shortfall": 7900.0, "balance_after": -7900.0, "contributors": [
    {"type": "supplier_invoice", "label": "ค่าสินค้า supplier", "amount": 50100.0, "due_date": "2015-07-22"},
]}]}
CREDIT = {"score": 58, "positive_factors": ["ยอดขายรายสัปดาห์สม่ำเสมอ"],
          "risk_indicators": ["เงินสำรองต่ำกว่ารายจ่าย 1 เดือน", "เงินสดอาจไม่พอวันที่ 2015-07-22 ขาดประมาณ 7,900"]}


@pytest.fixture
def facts():
    return cp.build_facts(FORECAST, GAPS, CREDIT, AS_OF)


def test_facts_only_future_and_thai_dates(facts):
    assert facts["จำนวนวันที่พยากรณ์"] == "2"
    assert facts["ยอดขายที่คาดการณ์รวม"] == "3,500"
    assert facts["ช่วงเงินสดอาจไม่พอ"][0]["วันที่"] == "22 ก.ค. 2558"


def test_template_has_date_amount_disclaimer_and_passes_validation(facts):
    text = cp.template_explanation(facts)
    assert "22 ก.ค. 2558" in text and "7,900" in text
    assert cp.DISCLAIMER in text
    assert cp.validate(text, facts) is None


def test_validate_rejects_invented_numbers(facts):
    assert cp.validate("วันที่ 22 ก.ค. 2558 ขาดประมาณ 7,900", facts) is None
    assert "numbers not in facts" in cp.validate("ขาดประมาณ 8,000", facts)
    assert "numbers not in facts" in cp.validate("วันที่ 2015-07-22", facts)  # reformatted date


def test_validate_rejects_loan_wording(facts):
    assert "banned" in cp.validate("แนะนำให้กู้เงินเพื่อเสริมสภาพคล่อง", facts)
    assert "banned" in cp.validate("สินเชื่อของคุณได้รับการอนุมัติ", facts)


def test_no_api_key_falls_back_to_template(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = cp.explain(1, FORECAST, GAPS, CREDIT, AS_OF)
    assert result["source"] == "template"
    assert "LLM_API_KEY" in result["fallback_reason"]
    assert result["is_synthetic_expense"] is True


def test_valid_llm_answer_is_used(monkeypatch):
    monkeypatch.setattr(cp, "call_llm", lambda facts, q: "วันที่ 22 ก.ค. 2558 เงินอาจขาดประมาณ 7,900")
    result = cp.explain(1, FORECAST, GAPS, CREDIT, AS_OF)
    assert result["source"] == "llm" and result["fallback_reason"] is None


def test_hallucinated_llm_answer_falls_back(monkeypatch):
    monkeypatch.setattr(cp, "call_llm", lambda facts, q: "เงินจะขาด 12,345 แนะนำให้กู้")
    result = cp.explain(1, FORECAST, GAPS, CREDIT, AS_OF)
    assert result["source"] == "template"
    assert "7,900" in result["answer"]


def test_api_error_falls_back(monkeypatch):
    def boom(facts, q):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(cp, "call_llm", boom)
    assert cp.explain(1, FORECAST, GAPS, CREDIT, AS_OF)["source"] == "template"
