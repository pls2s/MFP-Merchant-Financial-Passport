"""AI Financial Copilot — a Thai chat assistant over figures the system already computed.

Usage:
    python -m ai.copilot.explain --merchant 1
    python -m ai.copilot.explain --merchant 1 --question "ถ้ายอดขายลดลงจะเป็นยังไง"

It can summarise the store, answer questions about sales patterns, the forecast,
upcoming expenses, the projected balance and the experimental credit signal, walk
through precomputed what-if scenarios, explain how the system works, and give general
cash-management advice. Conversations are multi-turn (`history`).

Rules (CLAUDE.md):
- Figures come only from `build_facts` (ai/copilot/facts.py). Every number in an answer
  must appear in the facts, the user's own messages, or be a small count (1-10);
  anything else → one retry with the reason, then the template fallback.
- It must not recommend or approve loans; such wording → template fallback.
- No API key, a timeout or an API error → template fallback (topic-aware).

LLM: Typhoon (OpenAI-compatible chat completions). Configure in .env:
    LLM_API_KEY, LLM_BASE_URL (default https://api.opentyphoon.ai/v1), LLM_MODEL
"""

import argparse
import json
import os
import re

import requests

from ai.cashflow_forecast.preprocess import ROOT
from ai.copilot.facts import MerchantContext, build_facts, load_context

DEFAULT_BASE_URL = "https://api.opentyphoon.ai/v1"
DEFAULT_MODEL = "typhoon-v2.5-30b-a3b-instruct"
TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 2
MAX_HISTORY_MESSAGES = 8
BANNED_PHRASES = ["อนุมัติ", "approve", "ควรกู้", "แนะนำให้กู้", "ควรขอสินเชื่อ", "แนะนำสินเชื่อ", "ยื่นกู้"]
DISCLAIMER = "รายจ่ายเป็นข้อมูลจำลอง และคะแนนเป็นสัญญาณทดลอง ไม่ใช่คะแนนเครดิต"
SMALL_COUNTS = {str(n) for n in range(1, 11)}  # "3 วิธี", "2 ครั้ง" — counts, not business figures

SYSTEM_PROMPT = """คุณคือ "ผู้ช่วยการเงินร้านค้า" ของระบบ MFP พูดคุยกับเจ้าของร้านเป็นภาษาไทยที่เป็นกันเองและเข้าใจง่าย

สิ่งที่คุณทำได้:
- สรุปสถานะร้าน อธิบายยอดขายที่ผ่านมา วันขายดี ผลของโปรโมชัน และยอดขายที่คาดการณ์รายวัน
- อธิบายรายจ่ายที่จะครบกำหนด ยอดเงินคงเหลือ และวันที่เงินสดอาจไม่พอ พร้อมสาเหตุ
- ตอบคำถาม "ถ้า..." โดยใช้ "สถานการณ์สมมติ" ที่ระบบคำนวณไว้ใน FACTS เท่านั้น ถ้าสถานการณ์ที่ถามไม่มีใน FACTS ให้บอกตรง ๆ ว่ายังคำนวณไม่ได้ แล้วเสนอสถานการณ์ที่มี
- อธิบายคะแนนสัญญาณการเงินและองค์ประกอบ และอธิบายว่าระบบพยากรณ์อย่างไร (โมเดล LSTM+GRU เรียนจากยอดขายย้อนหลัง วันโปรโมชัน วันหยุด)
- ให้คำแนะนำทั่วไปเรื่องการบริหารเงินสด เช่น ต่อรองเลื่อนวันจ่าย supplier แบ่งสั่งสินค้าเป็นล็อตเล็ก จัดโปรโมชันในช่วงที่เงินตึง กันเงินสำรอง ติดตามยอดขายรายวัน

กฎที่ต้องทำตามทุกข้อ:
1. ตัวเลขและวันที่ต้องคัดลอกจาก FACTS ให้ตรงทุกตัว ห้ามคำนวณเอง ห้ามปัดเศษ ห้ามแปลงรูปแบบวันที่ ถ้าต้องใช้ตัวเลขที่ไม่มีใน FACTS ให้อธิบายเป็นคำพูดแทน
2. ห้ามใส่หน่วยเงิน (เช่น บาท) เพราะ FACTS ไม่มีหน่วย
3. ห้ามแนะนำ ชักชวน หรืออนุมัติสินเชื่อหรือการกู้เงิน ถ้าถูกถามให้บอกว่าผู้ช่วยนี้ไม่ให้คำแนะนำด้านสินเชื่อ แล้วอธิบายสถานะเงินสดแทน
4. คะแนนสัญญาณการเงินเป็นสัญญาณทดลอง ไม่ใช่คะแนนเครดิต และรายจ่าย/ยอดเงินคงเหลือเป็นข้อมูลจำลอง ให้บอกเมื่อพูดถึงสิ่งเหล่านี้
5. ถ้าคำถามไม่เกี่ยวกับร้านหรือการเงินของร้าน ให้ตอบสั้น ๆ อย่างสุภาพแล้วชวนกลับมาที่เรื่องร้าน
6. แยก "กรณีปกติ" กับ "สถานการณ์สมมติ" ให้ชัด ตัวเลขของสถานการณ์สมมติใช้ได้เฉพาะเมื่อพูดถึงสถานการณ์นั้น
7. ยอดขายและยอดเงินเป็นการคาดการณ์ ห้ามใช้คำว่า "แน่นอน" หรือ "รับประกัน" ให้ใช้ "คาดว่า" หรือ "มีแนวโน้ม"
8. ตอบกระชับ ไม่เกิน 8 บรรทัด ใช้ขีดหัวข้อ "- " ได้ ไม่ต้องใช้ตัวหนาหรือ markdown อื่น ถ้าพูดถึงวันที่เงินอาจไม่พอ ต้องบอกวันที่และจำนวนเงินเสมอ

FACTS ของร้านนี้:
{facts}"""

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text)}


def validate(answer: str, facts: dict, user_text: str = "") -> str | None:
    """None if the answer is safe to show, otherwise the reason it is not."""
    lowered = answer.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            return f"banned phrase: {phrase}"
    allowed = (_numbers(json.dumps(facts, ensure_ascii=False)) | _numbers(DISCLAIMER)
               | _numbers(user_text) | SMALL_COUNTS | {"100"})
    invented = _numbers(answer) - allowed
    if invented:
        return f"numbers not in facts: {sorted(invented)}"
    return None


# --- Template fallback (no LLM) ------------------------------------------------


def _topic(question: str | None) -> str:
    q = question or ""
    for topic, words in (
        ("loan", ("กู้", "สินเชื่อ", "ยืมเงิน")),
        ("scenario", ("ถ้า", "สมมติ", "เลื่อน")),
        ("expense", ("รายจ่าย", "จ่าย", "บิล", "supplier", "ค่าเช่า", "เงินเดือน")),
        ("promo", ("โปร",)),
        ("score", ("คะแนน", "เครดิต", "สัญญาณ")),
        ("accuracy", ("แม่น", "ทาย", "พยากรณ์", "โมเดล")),
        ("sales", ("ขายดี", "ยอดขาย", "วันไหน")),
    ):
        if any(w in q for w in words):
            return topic
    return "summary"


def _gap_line(facts: dict) -> str:
    gaps = facts["วันที่เงินสดอาจไม่พอ"]
    if not gaps:
        return "ยังไม่พบวันที่เงินสดอาจไม่พอใน 14 วันข้างหน้า"
    g = gaps[0]
    line = f"ระวังวันที่ {g['วันที่']} เงินสดอาจไม่พอ ขาดประมาณ {g['ขาดประมาณ']}"
    if g["รายจ่ายหลัก"]:
        line += f" เพราะมี{' และ'.join(g['รายจ่ายหลัก'])}"
    if len(gaps) > 1:
        line += f" และอาจเกิดอีกวันที่ {', '.join(x['วันที่'] for x in gaps[1:])}"
    return line


def template_answer(facts: dict, question: str | None = None) -> str:
    """Deterministic, topic-aware fallback built only from `facts`."""
    sales = facts["ยอดขายที่ผ่านมา (ข้อมูลจริง)"]
    fc = facts["การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)"]
    exp = facts["รายจ่ายที่จะครบกำหนดใน 14 วันข้างหน้า (ข้อมูลจำลอง)"]
    bal = facts["ยอดเงินคงเหลือ (ข้อมูลจำลอง)"]
    score = facts["สัญญาณการเงิน (ทดลอง ไม่ใช่คะแนนเครดิต)"]
    topic = _topic(question)

    if topic == "loan":
        lines = ["ผู้ช่วยนี้ไม่ให้คำแนะนำด้านสินเชื่อหรือการกู้เงิน แต่สรุปสถานะเงินสดให้ได้ดังนี้", _gap_line(facts),
                 f"ยอดเงินคงเหลือวันนี้ {bal['วันนี้']} ต่ำสุดในช่วงคาดการณ์ {bal['ต่ำสุดในช่วงคาดการณ์']}"]
    elif topic == "scenario":
        lines = ["สถานการณ์สมมติที่ระบบคำนวณไว้:"] + [
            f"- {k}: {v}" for k, v in facts["สถานการณ์สมมติ (ระบบคำนวณให้แล้ว)"].items()]
    elif topic == "expense":
        lines = ["รายจ่ายที่จะครบกำหนดใน 14 วันข้างหน้า:"] + [f"- {x}" for x in exp["รายการ"]] + [
            f"รวม {exp['รวม']}", _gap_line(facts)]
    elif topic == "promo":
        uplift = sales.get("วันที่มีโปรโมชันขายได้มากกว่าวันปกติ")
        promo_days = [d for d in fc["ยอดขายคาดการณ์รายวัน"] if "โปรโมชัน" in d]
        lines = [f"วันที่มีโปรโมชันร้านขายได้มากกว่าวันปกติ {uplift}" if uplift else "ยังไม่มีข้อมูลผลของโปรโมชัน"]
        if promo_days:
            lines += ["วันโปรโมชันใน 14 วันข้างหน้า:"] + [f"- {d}" for d in promo_days]
    elif topic == "score":
        lines = [f"คะแนนสัญญาณการเงิน {score['คะแนน']}" + (f" {score['เทียบกับร้านอื่น']}" if "เทียบกับร้านอื่น" in score else ""),
                 "องค์ประกอบ:"] + [f"- {x}" for x in score["องค์ประกอบ (0 ถึง 1, ยิ่งสูงยิ่งดี)"]]
    elif topic == "accuracy":
        acc = fc.get("ความแม่นของการพยากรณ์ร้านนี้ (ทดสอบย้อนหลัง)")
        lines = ["ระบบใช้โมเดล LSTM+GRU เรียนจากยอดขายย้อนหลัง วันโปรโมชัน และวันหยุด",
                 f"ยอดขายคาดการณ์รวม 14 วันข้างหน้า {fc['ยอดขายคาดการณ์รวม 14 วันข้างหน้า']}"]
        if acc:
            lines.append(f"ทดสอบย้อนหลังกับร้านนี้: {acc}")
    elif topic == "sales":
        lines = [f"{k}: {v}" for k, v in sales.items()]
    else:
        lines = [f"ข้อมูลถึง{facts['วันนี้ (ข้อมูลล่าสุด)']} คาดว่าใน 14 วันข้างหน้าร้านจะมียอดขายรวมประมาณ "
                 f"{fc['ยอดขายคาดการณ์รวม 14 วันข้างหน้า']}", _gap_line(facts),
                 f"คะแนนสัญญาณการเงิน {score['คะแนน']}"]
        if facts["จุดแข็ง"]:
            lines.append(f"จุดแข็งคือ{facts['จุดแข็ง'][0]}")
    return "\n".join(lines + [DISCLAIMER])


# --- LLM -------------------------------------------------------------------------


def call_llm(facts: dict, question: str | None, history: list[dict], feedback: str | None = None) -> str:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY not set")
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=1))}]
    messages += history[-MAX_HISTORY_MESSAGES:]
    messages.append({"role": "user", "content": question or "สรุปสถานะการเงินของร้านให้หน่อย"})
    if feedback:
        messages.append({"role": "user", "content":
                         f"คำตอบก่อนหน้าใช้ไม่ได้ ({feedback}) ตอบใหม่โดยใช้เฉพาะตัวเลขใน FACTS ห้ามคำนวณเอง"})
    resp = requests.post(
        f"{os.environ.get('LLM_BASE_URL', DEFAULT_BASE_URL).rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": os.environ.get("LLM_MODEL", DEFAULT_MODEL), "messages": messages,
              "temperature": 0.3, "max_tokens": 700},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def explain(ctx: MerchantContext, question: str | None = None, history: list[dict] | None = None) -> dict:
    """POST /api/v1/merchants/{id}/copilot response."""
    history = [m for m in (history or []) if m.get("role") in ("user", "assistant") and m.get("content")]
    facts = build_facts(ctx)
    user_text = " ".join([question or ""] + [m["content"] for m in history if m["role"] == "user"])
    source, reason = "template", None
    answer = template_answer(facts, question)
    try:
        for _ in range(MAX_ATTEMPTS):
            llm_answer = call_llm(facts, question, history, reason)
            reason = validate(llm_answer, facts, user_text)
            if reason is None:
                break
        if reason is None:
            answer, source = llm_answer, "llm"
    except (RuntimeError, requests.RequestException, KeyError, IndexError, ValueError) as e:
        reason = f"llm unavailable: {e}"
    return {
        "merchant_id": int(ctx.merchant_id),
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--merchant", type=int, required=True)
    parser.add_argument("--question")
    args = parser.parse_args()
    load_dotenv()
    result = explain(load_context(args.merchant), args.question)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
