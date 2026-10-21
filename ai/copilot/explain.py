"""AI Financial Copilot — plain-Thai explanation of numbers the system already computed.

Usage:
    python -m ai.copilot.explain --merchant 1
    python -m ai.copilot.explain --merchant 1 --question "สัปดาห์หน้าต้องระวังอะไร"

Rules (CLAUDE.md):
- The LLM only sees, and may only use, figures from `build_facts`. Every number in
  its answer is checked against those facts; any other number → template fallback.
- It must not recommend or approve loans; such wording → template fallback.
- No API key, a timeout or an API error → template fallback.

LLM: Typhoon (OpenAI-compatible chat completions). Configure in .env:
    LLM_API_KEY, LLM_BASE_URL (default https://api.opentyphoon.ai/v1), LLM_MODEL
"""

import argparse
import json
import os
import re

import requests

from ai.cashflow_forecast.preprocess import ROOT

DEFAULT_BASE_URL = "https://api.opentyphoon.ai/v1"
DEFAULT_MODEL = "typhoon-v2.5-30b-a3b-instruct"
TIMEOUT_SECONDS = 20
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
BANNED_PHRASES = ["อนุมัติ", "approve", "ควรกู้", "แนะนำให้กู้", "ควรขอสินเชื่อ", "แนะนำสินเชื่อ", "ยื่นกู้"]
DISCLAIMER = "รายจ่ายเป็นข้อมูลจำลอง และคะแนนเป็นสัญญาณทดลอง ไม่ใช่คะแนนเครดิต"

SYSTEM_PROMPT = """คุณคือผู้ช่วยการเงินที่อธิบายตัวเลขให้เจ้าของร้านค้าเข้าใจง่าย

กฎที่ต้องทำตามทุกข้อ:
1. ใช้เฉพาะตัวเลขและวันที่ที่อยู่ใน FACTS เท่านั้น คัดลอกให้ตรงตามที่เขียนไว้ ห้ามคำนวณ ห้ามปัดเศษ ห้ามแปลงรูปแบบวันที่
2. ห้ามใส่หน่วยเงินที่ไม่มีใน FACTS
3. ห้ามแนะนำหรืออนุมัติสินเชื่อหรือการกู้เงิน
4. บอกว่ารายจ่ายเป็นข้อมูลจำลอง และคะแนนเป็นสัญญาณทดลอง ไม่ใช่คะแนนเครดิต
5. ตอบภาษาไทย สั้น กระชับ ไม่เกิน 5 ประโยค ถ้ามีวันที่เงินอาจไม่พอ ให้บอกวันที่และจำนวนเงินเสมอ"""


def thai_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {THAI_MONTHS[m - 1]} {y + 543}"


def money(x: float) -> str:
    return f"{x:,.0f}"


def build_facts(forecast: dict, gaps: dict, credit: dict, as_of: str) -> dict:
    """Every figure the copilot may mention, already formatted."""
    future = [p for p in forecast["points"] if p["date"] > as_of]
    return {
        "วันที่ข้อมูลล่าสุด": thai_date(as_of),
        "จำนวนวันที่พยากรณ์": str(len(future)),
        "ยอดขายที่คาดการณ์รวม": money(sum(p["forecast"] for p in future)),
        "ช่วงเงินสดอาจไม่พอ": [
            {
                "วันที่": thai_date(g["date"]),
                "ขาดประมาณ": money(g["shortfall"]),
                "รายจ่ายหลัก": [f"{c['label']} {money(c['amount'])}" for c in g["contributors"][:2]],
            }
            for g in gaps["gaps"]
        ],
        "คะแนนสัญญาณการเงิน (ทดลอง)": f"{credit['score']}/100",
        "จุดแข็ง": credit["positive_factors"],
        "จุดที่ควรระวัง": [r for r in credit["risk_indicators"] if not r.startswith("เงินสดอาจไม่พอ")],
    }


def template_explanation(facts: dict) -> str:
    """Deterministic fallback built only from `facts`."""
    parts = [
        f"ข้อมูลถึงวันที่ {facts['วันที่ข้อมูลล่าสุด']} คาดว่าใน {facts['จำนวนวันที่พยากรณ์']} วันข้างหน้า"
        f" ร้านจะมียอดขายรวมประมาณ {facts['ยอดขายที่คาดการณ์รวม']}"
    ]
    if facts["ช่วงเงินสดอาจไม่พอ"]:
        g = facts["ช่วงเงินสดอาจไม่พอ"][0]
        parts.append(
            f"ระวังวันที่ {g['วันที่']} เงินสดอาจไม่พอ ขาดประมาณ {g['ขาดประมาณ']}"
            + (f" เพราะมี{' และ'.join(g['รายจ่ายหลัก'])}" if g["รายจ่ายหลัก"] else "")
        )
        if len(facts["ช่วงเงินสดอาจไม่พอ"]) > 1:
            others = ", ".join(x["วันที่"] for x in facts["ช่วงเงินสดอาจไม่พอ"][1:])
            parts.append(f"และอาจเกิดขึ้นอีกวันที่ {others}")
    else:
        parts.append("ยังไม่พบวันที่เงินสดอาจไม่พอในช่วงนี้")
    parts.append(f"คะแนนสัญญาณการเงิน {facts['คะแนนสัญญาณการเงิน (ทดลอง)']}")
    if facts["จุดแข็ง"]:
        parts.append(f"จุดแข็งคือ{facts['จุดแข็ง'][0]}")
    parts.append(DISCLAIMER)
    return " ".join(parts)


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text)}


def validate(answer: str, facts: dict) -> str | None:
    """None if the answer is safe to show, otherwise the reason it is not."""
    lowered = answer.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            return f"banned phrase: {phrase}"
    allowed = _numbers(json.dumps(facts, ensure_ascii=False)) | _numbers(DISCLAIMER) | {"1", "100"}
    invented = _numbers(answer) - allowed
    if invented:
        return f"numbers not in facts: {sorted(invented)}"
    return None


def call_llm(facts: dict, question: str | None) -> str:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY not set")
    user = "FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=2)
    user += f"\n\nคำถามจากเจ้าของร้าน: {question}" if question else "\n\nสรุปสถานะการเงินของร้านจาก FACTS"
    resp = requests.post(
        f"{os.environ.get('LLM_BASE_URL', DEFAULT_BASE_URL).rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": os.environ.get("LLM_MODEL", DEFAULT_MODEL),
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": 400,
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def explain(merchant_id: int, forecast: dict, gaps: dict, credit: dict, as_of: str,
            question: str | None = None) -> dict:
    """POST /api/v1/merchants/{id}/copilot response."""
    facts = build_facts(forecast, gaps, credit, as_of)
    source, reason = "template", None
    answer = template_explanation(facts)
    try:
        llm_answer = call_llm(facts, question)
        reason = validate(llm_answer, facts)
        if reason is None:
            answer, source = llm_answer, "llm"
    except (RuntimeError, requests.RequestException, KeyError, IndexError, ValueError) as e:
        reason = f"llm unavailable: {e}"
    return {
        "merchant_id": int(merchant_id),
        "answer": answer,
        "source": source,
        "fallback_reason": reason if source == "template" else None,
        "disclaimer": DISCLAIMER,
        "is_synthetic_expense": True,
    }


def load_dotenv() -> None:
    """Minimal .env reader for the CLI (the backend sets its own environment)."""
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    from ai.gap_detection.build import AS_OF, FORECASTS_PATH, GAPS_PATH
    from ai.credit_signal.build import CREDIT_PATH

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--merchant", type=int, required=True)
    parser.add_argument("--question")
    args = parser.parse_args()
    load_dotenv()

    def find(path):
        return next(x for x in json.loads(path.read_text()) if x["merchant_id"] == args.merchant)

    result = explain(args.merchant, find(FORECASTS_PATH), find(GAPS_PATH), find(CREDIT_PATH),
                     AS_OF.strftime("%Y-%m-%d"), args.question)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
