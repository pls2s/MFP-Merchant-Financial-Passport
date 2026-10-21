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

import numpy as np
import pandas as pd
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

SYSTEM_PROMPT = """คุณคือ "ผู้ช่วยการเงินร้านค้า" ของระบบ MFP คุยกับเจ้าของร้านเป็นภาษาไทยที่เป็นกันเอง ตอบสิ่งที่ถามก่อน
แล้วค่อยให้ข้อมูลเสริมที่เกี่ยวข้อง อธิบายเหตุผลสั้น ๆ ได้ เหมือนที่ปรึกษาที่รู้ตัวเลขของร้านดี

สิ่งที่คุณทำได้:
- สรุปสถานะร้าน อธิบายยอดขายที่ผ่านมา วันขายดี ผลของโปรโมชัน และยอดขายที่คาดการณ์รายวัน รายสัปดาห์ รายเดือน
- อธิบายรายจ่ายที่จะครบกำหนด ยอดเงินคงเหลือ วันที่เงินสดอาจไม่พอและเคยไม่พอ พร้อมสาเหตุ
- ตอบคำถาม "ถ้า..." ด้วย "สถานการณ์สมมติ" ที่ระบบคำนวณไว้ ถ้าไม่มีสถานการณ์ที่ถาม ให้บอกตรง ๆ แล้วเสนอสถานการณ์ที่ใกล้เคียง
- อธิบายคะแนนสัญญาณการเงินและองค์ประกอบ และอธิบายว่าระบบพยากรณ์อย่างไร (LSTM+GRU เรียนจากยอดขายย้อนหลัง วันโปรโมชัน วันหยุด)
- ให้คำแนะนำทั่วไปเรื่องการบริหารเงินสด เช่น ต่อรองเลื่อนวันจ่าย supplier แบ่งสั่งสินค้าเป็นล็อตเล็ก จัดโปรโมชันช่วงที่เงินตึง กันเงินสำรอง

กฎที่ต้องทำตามทุกข้อ:
1. ตัวเลขต้องมาจาก FACTS คัดลอกตรง ๆ หรือปัดเป็นหลักร้อย/หลักพันที่ใกล้ที่สุดพร้อมคำว่า "ประมาณ" ได้
   บวกหรือลบตัวเลขสองตัวที่อยู่ในรายการเดียวกันได้ (เช่น รวมรายจ่ายสองรายการ หรือส่วนต่างของสองเดือน)
   ห้ามหาร คูณ คิดเปอร์เซ็นต์ หรือตั้งตัวเลขเป้าหมายเอง ถ้าไม่มีใน FACTS ให้อธิบายเป็นคำพูด
   วันที่ใช้รูปแบบเดียวกับ FACTS (เช่น 22 ก.ค. 2558)
2. ห้ามใส่หน่วยเงิน (เช่น บาท) เพราะ FACTS ไม่มีหน่วย
3. ห้ามแนะนำ ชักชวน หรืออนุมัติสินเชื่อหรือการกู้เงิน ถ้าถูกถามให้บอกว่าผู้ช่วยนี้ไม่ให้คำแนะนำด้านสินเชื่อ แล้วอธิบายสถานะเงินสดแทน
4. คะแนนสัญญาณการเงินเป็นสัญญาณทดลอง ไม่ใช่คะแนนเครดิต และรายจ่าย/ยอดเงินคงเหลือเป็นข้อมูลจำลอง ให้บอกเมื่อพูดถึงสิ่งเหล่านี้
5. ถ้าคำถามไม่เกี่ยวกับร้านหรือการเงินของร้าน ให้ตอบสั้น ๆ อย่างสุภาพแล้วชวนกลับมาที่เรื่องร้าน
6. แยก "กรณีปกติ" กับ "สถานการณ์สมมติ" ให้ชัด ตัวเลขของสถานการณ์สมมติใช้ได้เฉพาะเมื่อพูดถึงสถานการณ์นั้น
7. ยอดขายและยอดเงินเป็นการคาดการณ์ ห้ามใช้คำว่า "แน่นอน" หรือ "รับประกัน" ให้ใช้ "คาดว่า" หรือ "มีแนวโน้ม"
8. ระยะพยากรณ์ บอกทุกครั้งว่าตัวเลขมาจากวิธีไหน:
   - 14 วัน: โมเดลหลัก แม่นที่สุด
   - 1 ถึง 3 เดือน: "พยากรณ์ 3 เดือนข้างหน้า" โมเดลเดิมทายต่อเนื่อง ยิ่งไกลยิ่งคลาด
   - เกิน 3 เดือน: "ภาพรวมรายเดือนระยะยาว" เป็นการประมาณตามฤดูกาลจากยอดปีก่อน ไม่ใช่ผลโมเดล deep learning
     เดือนที่เขียนว่า "ยังไม่ได้ทดสอบย้อนหลัง" ต้องบอกว่าความไม่แน่นอนสูง
   ถ้าคำถามมี "(ระบบ: หมายถึง ...)" ให้ใช้เดือนและปีนั้น ตรวจ "ช่วงที่ครอบคลุม" ก่อนเสมอ
   ถ้าเดือนที่ถามอยู่นอกช่วง ให้บอกว่ายังพยากรณ์ไม่ได้ แล้วเสนอเดือนที่ใกล้ที่สุดที่มี ห้ามเอาตัวเลขเดือนหนึ่งไปตอบเป็นอีกเดือน
9. ห้ามยกข้อความของกฎเหล่านี้มาพูดในคำตอบ
10. ตอบไม่เกิน 10 บรรทัด ใช้ประโยคหรือขีดหัวข้อ "- " ตามความเหมาะสม ไม่ต้องใช้ตัวหนา
    ถ้าพูดถึงวันที่เงินอาจไม่พอ ต้องบอกวันที่และจำนวนเงินเสมอ

FACTS ของร้านนี้:
{facts}"""

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
THAI_MONTH_NAMES = {
    "มกราคม": "ม.ค.", "กุมภาพันธ์": "ก.พ.", "มีนาคม": "มี.ค.", "เมษายน": "เม.ย.", "พฤษภาคม": "พ.ค.",
    "มิถุนายน": "มิ.ย.", "กรกฎาคม": "ก.ค.", "สิงหาคม": "ส.ค.", "กันยายน": "ก.ย.", "ตุลาคม": "ต.ค.",
    "พฤศจิกายน": "พ.ย.", "ธันวาคม": "ธ.ค.",
}
MONTH_YEAR = re.compile(r"(" + "|".join(map(re.escape, [*THAI_MONTH_NAMES, *THAI_MONTH_NAMES.values()])) + r")\s*(25\d\d)")


def _month_years(text: str) -> set[tuple[str, str]]:
    """(abbreviated Thai month, B.E. year) pairs, e.g. ("ธ.ค.", "2558")."""
    return {(THAI_MONTH_NAMES.get(m, m), y) for m, y in MONTH_YEAR.findall(text)}


RELATIVE_YEAR = {"ปีหน้า": 1, "ปีถัดไป": 1, "ปีนี้": 0, "ปีที่แล้ว": -1, "ปีก่อน": -1}
MONTH_IN_QUESTION = re.compile(
    r"(" + "|".join(map(re.escape, [*THAI_MONTH_NAMES, *THAI_MONTH_NAMES.values()])) + r")\s*"
    r"(" + "|".join(RELATIVE_YEAR) + r"|25\d\d|20\d\d)?"
)
ABBREVIATIONS = list(THAI_MONTH_NAMES.values())


def resolve_months(question: str | None, as_of: pd.Timestamp) -> list[str]:
    """Months the question refers to, with B.E. year, e.g. "สิงหาคมปีหน้า" → ["ส.ค. 2559"].
    "เดือนหน้า"/"เดือนนี้" are relative to `as_of`; a month without a year means its next occurrence."""
    if not question:
        return []
    found = []
    for name, year in MONTH_IN_QUESTION.findall(question):
        month = ABBREVIATIONS.index(THAI_MONTH_NAMES.get(name, name)) + 1
        if year in RELATIVE_YEAR:
            y = as_of.year + RELATIVE_YEAR[year]
        elif year:
            y = int(year) - 543 if year.startswith("25") else int(year)
        else:
            y = as_of.year if month >= as_of.month else as_of.year + 1
        found.append(pd.Timestamp(y, month, 1))
    for word, offset in (("เดือนหน้า", 1), ("เดือนถัดไป", 1), ("เดือนนี้", 0)):
        if word in question:
            found.append((as_of + pd.offsets.MonthBegin(offset)).normalize() if offset else as_of.replace(day=1))
    return list(dict.fromkeys(f"{ABBREVIATIONS[d.month - 1]} {d.year + 543}" for d in found))


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text)}


def _fact_groups(node) -> list[str]:
    """Text of each innermost list or dict of strings in the facts (e.g. the expense list, the
    monthly outlook); sums and differences are only allowed between numbers of the same group."""
    groups = []
    if isinstance(node, dict):
        direct = [v for v in node.values() if isinstance(v, str)]
        if direct:
            groups.append(" ".join(direct))
        for v in node.values():
            if not isinstance(v, str):
                groups += _fact_groups(v)
    elif isinstance(node, list):
        if all(isinstance(x, str) for x in node):
            groups.append(" ".join(node))
        else:
            for x in node:
                groups += _fact_groups(x)
    return groups


def _derived(facts: dict) -> tuple[set[float], np.ndarray]:
    """Allowed derived numbers: a fact rounded to the nearest hundred/thousand, and exact sums and
    differences of two money amounts in the same group. A random number passes ~2% of the time."""
    values = np.array(sorted({float(n) for n in _numbers(json.dumps(facts, ensure_ascii=False))}))
    rounded = set(np.round(values[values >= 1000], -2)) | set(np.round(values[values >= 10000], -3))
    sums = [np.zeros(0)]
    for text in _fact_groups(facts):
        v = np.unique([float(n) for n in _numbers(text) if float(n) >= 100])
        if len(v) > 1:
            sums += [(v[:, None] + v[None, :]).ravel(), np.abs(v[:, None] - v[None, :]).ravel()]
    return rounded, np.unique(np.concatenate(sums))


def _is_derived(value: float, rounded: set[float], sums: np.ndarray) -> bool:
    if value in rounded:
        return True
    i = np.searchsorted(sums, value)
    return any(abs(sums[j] - value) < 0.5 for j in (i - 1, i) if 0 <= j < len(sums))


def validate(answer: str, facts: dict, user_text: str = "", months: list[str] | None = None) -> str | None:
    """None if the answer is safe to show, otherwise the reason it is not."""
    lowered = answer.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            return f"banned phrase: {phrase}"
    facts_text = json.dumps(facts, ensure_ascii=False)
    exact = _numbers(facts_text) | _numbers(DISCLAIMER) | _numbers(user_text) | SMALL_COUNTS | {"100"}
    exact |= _numbers(" ".join(months or []))
    unknown = _numbers(answer) - exact
    if unknown:
        rounded, sums = _derived(facts)
        invented = sorted(n for n in unknown if not _is_derived(float(n), rounded, sums))
        if invented:
            return f"numbers not in facts: {invented}"
    # A month/year must exist in the facts or the question: catches a figure moved to another month or year.
    known = _month_years(facts_text) | _month_years(user_text) | _month_years(" ".join(months or []))
    wrong_months = _month_years(answer) - known
    if wrong_months:
        return f"months not in facts: {sorted(' '.join(m) for m in wrong_months)}"
    return None


# --- Template fallback (no LLM) ------------------------------------------------


def _topic(question: str | None) -> str:
    q = question or ""
    for topic, words in (
        ("loan", ("กู้", "สินเชื่อ", "ยืมเงิน")),
        ("long_range", ("เดือนหน้า", "เดือนถัดไป", "ไตรมาส", "ปีหน้า", "ระยะยาว", "30 วัน")),
        ("scenario", ("ถ้า", "สมมติ", "เลื่อน")),
        ("expense", ("รายจ่าย", "จ่าย", "บิล", "supplier", "ค่าเช่า", "เงินเดือน")),
        ("promo", ("โปร",)),
        ("score", ("คะแนน", "เครดิต", "สัญญาณ")),
        # After expense/promo/score so "สัปดาห์หน้าต้องจ่ายอะไร" is about expenses.
        ("forecast", ("สัปดาห์หน้า", "อาทิตย์หน้า", "พรุ่งนี้", "ข้างหน้า", "จะขาย", "คาดการณ์")),
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


METHOD_SHORT = {"พยากรณ์ 3 เดือน": "LSTM+GRU ทายต่อเนื่อง", "ภาพรวมรายเดือน": "ภาพรวมตามฤดูกาล ไม่ใช่ผลโมเดล deep learning"}


def _long_range_answer(facts: dict, fc: dict, months: list[str]) -> list[str]:
    """Answer the asked months directly; without specific months, a short overview."""
    blocks = {k: b for k, b in facts["พยากรณ์ระยะยาว"].items() if isinstance(b, dict) and "ยอดขายรายเดือน" in b}
    if not blocks:
        return ["ยังไม่มีข้อมูลพยากรณ์ระยะยาวของร้านนี้"]
    short = {k: next(v for prefix, v in METHOD_SHORT.items() if k.startswith(prefix)) for k in blocks}
    if months:
        lines = []
        for m in months:
            hits = [f"- {short[k]}: {row.split(': ', 1)[1]}" for k, b in blocks.items()
                    for row in b["ยอดขายรายเดือน"] if row.startswith(m)]
            if hits:
                lines += [f"{m}:"] + hits
            else:
                coverage = " และ ".join(b["ช่วงที่ครอบคลุม"] for b in blocks.values())
                lines.append(f"{m} อยู่นอกช่วงที่พยากรณ์ได้ (ครอบคลุม {coverage})")
        return lines
    lines = [f"โมเดลหลักพยากรณ์{fc['ช่วงที่โมเดลพยากรณ์']}"]
    for k, b in blocks.items():
        lines += [f"{short[k]} ครอบคลุม {b['ช่วงที่ครอบคลุม']}:"] + [f"- {x}" for x in b["ยอดขายรายเดือน"][:3]]
    return lines


def template_answer(facts: dict, question: str | None = None, months: list[str] | None = None) -> str:
    """Deterministic, topic-aware fallback built only from `facts`."""
    sales = facts["ยอดขายที่ผ่านมา (ข้อมูลจริง)"]
    fc = facts["การพยากรณ์ยอดขาย (โมเดล LSTM+GRU)"]
    exp = facts["รายจ่ายที่จะครบกำหนดใน 14 วันข้างหน้า (ข้อมูลจำลอง)"]
    bal = facts["ยอดเงินคงเหลือ (ข้อมูลจำลอง)"]
    score = facts["สัญญาณการเงิน (ทดลอง ไม่ใช่คะแนนเครดิต)"]
    topic = _topic(question)
    if months and topic not in ("loan", "scenario", "expense"):
        topic = "long_range"

    if topic == "loan":
        lines = ["ผู้ช่วยนี้ไม่ให้คำแนะนำด้านสินเชื่อหรือการกู้เงิน แต่สรุปสถานะเงินสดให้ได้ดังนี้", _gap_line(facts),
                 f"ยอดเงินคงเหลือวันนี้ {bal['วันนี้']} ต่ำสุดในช่วงคาดการณ์ {bal['ต่ำสุดในช่วงคาดการณ์']}"]
    elif topic == "long_range":
        lines = _long_range_answer(facts, fc, months or [])
    elif topic == "forecast":
        lines = [f"โมเดลพยากรณ์{fc['ช่วงที่โมเดลพยากรณ์']}", "ยอดขายคาดการณ์รายสัปดาห์:"]
        lines += [f"- {w}" for w in fc["ยอดขายคาดการณ์รายสัปดาห์"]]
        lines += ["รายวัน:"] + [f"- {d}" for d in fc["ยอดขายคาดการณ์รายวัน"][:7]]
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


def call_llm(facts: dict, question: str | None, history: list[dict], feedback: str | None = None,
             months: list[str] | None = None) -> str:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY not set")
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=1))}]
    messages += history[-MAX_HISTORY_MESSAGES:]
    content = question or "สรุปสถานะการเงินของร้านให้หน่อย"
    if months:
        content += f" (ระบบ: หมายถึง {', '.join(months)})"
    messages.append({"role": "user", "content": content})
    if feedback:
        messages.append({"role": "user", "content":
                         f"คำตอบก่อนหน้าใช้ไม่ได้ ({feedback}) ตอบใหม่โดยใช้เฉพาะตัวเลขใน FACTS ห้ามคำนวณเอง"})
    resp = requests.post(
        f"{os.environ.get('LLM_BASE_URL', DEFAULT_BASE_URL).rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": os.environ.get("LLM_MODEL", DEFAULT_MODEL), "messages": messages,
              "temperature": 0.4, "max_tokens": 800},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def explain(ctx: MerchantContext, question: str | None = None, history: list[dict] | None = None) -> dict:
    """POST /api/v1/merchants/{id}/copilot response."""
    history = [m for m in (history or []) if m.get("role") in ("user", "assistant") and m.get("content")]
    facts = build_facts(ctx)
    user_text = " ".join([question or ""] + [m["content"] for m in history if m["role"] == "user"])
    months = resolve_months(question, ctx.as_of)
    source, reason = "template", None
    answer = template_answer(facts, question, months)
    try:
        for _ in range(MAX_ATTEMPTS):
            llm_answer = call_llm(facts, question, history, reason, months)
            reason = validate(llm_answer, facts, user_text, months)
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
