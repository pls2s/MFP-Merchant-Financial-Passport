"""Turn any shop sales file into our daily format: date, sales, open (one row per calendar day).

The middle layer between an uploaded file and the cold-start model (cold_start.py). Everything
messy about real files is handled here, and every row that is not used is reported with a reason —
nothing is dropped silently.

    read_table   bytes → DataFrame        .csv (UTF-8, UTF-8 BOM, cp874/TIS-620; , ; tab) or .xlsx
    guess_mapping                          which column is the date / sales / quantity / unit price
    parse_dates                            ISO, d/m/y or m/d/y (decided from the data), Buddhist
                                           years (พ.ศ.), Thai month names, Excel serial numbers
    parse_amounts                          "4,000", "฿1,200.50", "(500)" = −500, "1.234,5"
    normalize    → (daily, report)         per-invoice rows are summed per day; negative days → 0

`inspect()` does all of that without the model, for the preview step of the upload screen.
"""

import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MIN_DAYS = 70                    # 56-day input window + one 14-day block to backtest
PREVIEW_ROWS = 5
EXAMPLE_ROWS = 5                 # row numbers listed per skip reason
BUDDHIST_OFFSET = 543
EXCEL_EPOCH = pd.Timestamp("1899-12-30")


class SalesFileError(ValueError):
    """The file cannot be used; the message is shown to the user (Thai)."""


# --- Reading -------------------------------------------------------------------------------

ENCODINGS = ("utf-8-sig", "cp874")


def read_table(data: bytes, filename: str) -> tuple[pd.DataFrame, str]:
    """(table with every cell as text, encoding or "xlsx")."""
    if filename.lower().endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(io.BytesIO(data), dtype=object), "xlsx"
        except Exception as e:
            raise SalesFileError("เปิดไฟล์ Excel ไม่ได้") from e
    for enc in ENCODINGS:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        try:  # sep=None sniffs , ; and tab
            return pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str, skipinitialspace=True), enc
        except Exception as e:
            raise SalesFileError("อ่านไฟล์ CSV ไม่ได้ — ตรวจว่าเป็นตารางที่มีหัวคอลัมน์") from e
    raise SalesFileError("อ่านตัวอักษรในไฟล์ไม่ได้ — บันทึกเป็น CSV UTF-8 แล้วลองใหม่")


# --- Columns -------------------------------------------------------------------------------

ALIASES = {
    "date": ("date", "invoicedate", "day", "orderdate", "transactiondate", "datetime", "timestamp",
             "วันที่", "วัน", "วันเวลา", "วันที่ขาย"),
    "sales": ("sales", "amount", "revenue", "total", "netsales", "totalamount", "grandtotal",
              "ยอดขาย", "ยอดรวม", "รายได้", "ยอด", "จำนวนเงิน", "ราคารวม", "ยอดเงิน"),
    "quantity": ("quantity", "qty", "units", "จำนวน", "จำนวนชิ้น"),
    "price": ("unitprice", "price", "ราคา", "ราคาต่อหน่วย", "ราคาต่อชิ้น"),
}


def _key(name: object) -> str:
    return re.sub(r"[\s_\-./()]+", "", str(name).strip().lower())


def guess_mapping(df: pd.DataFrame) -> dict[str, str | None]:
    """Column for each role by name; if no sales column is named, the only numeric-looking column."""
    keys = {_key(c): c for c in df.columns}

    def by_name(names):  # exact name first, then a header that starts with it: "ยอดรวม (บาท)"
        exact = next((keys[a] for a in names if a in keys), None)
        return exact or next((c for k, c in keys.items() for a in names if len(a) >= 3 and k.startswith(a)), None)

    mapping = {role: by_name(names) for role, names in ALIASES.items()}
    if mapping["date"] is None:  # a column that is mostly dates
        for c in df.columns:
            if parse_dates(df[c]).dates.notna().mean() > 0.8:
                mapping["date"] = c
                break
    if mapping["sales"] is None and not (mapping["quantity"] and mapping["price"]):
        numeric = [c for c in df.columns if c != mapping["date"] and parse_amounts(df[c]).notna().mean() > 0.8]
        if len(numeric) == 1:
            mapping["sales"] = numeric[0]
    return mapping


# --- Values --------------------------------------------------------------------------------

THAI_MONTHS = {
    m: i for i, names in enumerate([
        ("ม.ค.", "มกราคม", "มค"), ("ก.พ.", "กุมภาพันธ์", "กพ"), ("มี.ค.", "มีนาคม", "มีค"), ("เม.ย.", "เมษายน", "เมย"),
        ("พ.ค.", "พฤษภาคม", "พค"), ("มิ.ย.", "มิถุนายน", "มิย"), ("ก.ค.", "กรกฎาคม", "กค"), ("ส.ค.", "สิงหาคม", "สค"),
        ("ก.ย.", "กันยายน", "กย"), ("ต.ค.", "ตุลาคม", "ตค"), ("พ.ย.", "พฤศจิกายน", "พย"), ("ธ.ค.", "ธันวาคม", "ธค"),
    ], start=1) for m in names
}


@dataclass
class ParsedDates:
    dates: pd.Series                     # Timestamp (day) or NaT
    format: str = ""                     # human description (Thai) of how they were read
    notes: list[str] = field(default_factory=list)


def _assemble(y: pd.Series, m: pd.Series, d: pd.Series) -> pd.Series:
    y, m, d = (pd.to_numeric(s, errors="coerce") for s in (y, m, d))
    y = y.where(y >= 100, y + 2000)                                  # 24 → 2024
    y = y.where(y <= 2400, y - BUDDHIST_OFFSET)                      # 2567 → 2024
    frame = pd.DataFrame({"year": y, "month": m, "day": d})
    return pd.to_datetime(frame, errors="coerce")


def _contiguity(dates: pd.Series) -> float:
    """Share of the calendar span covered by distinct dates (1 = no gaps)."""
    d = dates.dropna().drop_duplicates()
    if len(d) < 2:
        return 0.0
    return len(d) / ((d.max() - d.min()).days + 1)


def parse_dates(s: pd.Series) -> ParsedDates:
    if pd.api.types.is_datetime64_any_dtype(s):
        return ParsedDates(s.dt.normalize(), "วันที่จาก Excel")
    text = s.astype("string").str.strip()
    notes = []

    # Excel serial day numbers (e.g. 45292 = 2024-01-01)
    num = pd.to_numeric(text, errors="coerce")
    if num.notna().mean() > 0.8 and num.between(20000, 80000).mean() > 0.8:
        return ParsedDates((EXCEL_EPOCH + pd.to_timedelta(num.round(), unit="D")).where(num.between(20000, 80000)),
                           "ตัวเลขวันที่แบบ Excel")

    # Already datetimes inside an object column (xlsx cells)
    as_dt = s.map(lambda v: v if isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year") else None)
    if as_dt.notna().mean() > 0.8:
        d = pd.to_datetime(as_dt, errors="coerce")
        be = d.dt.year > 2400
        if be.any():
            d = d.where(~be, d - pd.DateOffset(years=BUDDHIST_OFFSET))
            notes.append("แปลงปี พ.ศ. เป็น ค.ศ.")
        return ParsedDates(d.dt.normalize(), "วันที่จาก Excel", notes)

    date_part = text.str.split(r"[ T]", n=1, regex=True).str[0]

    # Thai month names: 5 ม.ค. 2567 / 5 มกราคม 67
    th = text.str.extract(r"^(\d{1,2})\s*([ก-๙.]+)\s*(\d{2,4})")
    if th[0].notna().mean() > 0.8:
        months = th[1].str.strip().map(THAI_MONTHS)
        y = pd.to_numeric(th[2], errors="coerce")
        y = y.where(y >= 100, y + 2500)  # two-digit Thai years are Buddhist: 67 → 2567
        return ParsedDates(_assemble(y, months, th[0]), "วัน เดือน(ภาษาไทย) ปี",
                           ["แปลงปี พ.ศ. เป็น ค.ศ."] if (y > 2400).any() else [])

    # Year first: 2024-01-05, 2567/1/5
    ymd = date_part.str.extract(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
    if ymd[0].notna().mean() > 0.8:
        y = pd.to_numeric(ymd[0], errors="coerce")
        if (y > 2400).any():
            notes.append("แปลงปี พ.ศ. เป็น ค.ศ.")
        return ParsedDates(_assemble(ymd[0], ymd[1], ymd[2]), "ปี-เดือน-วัน", notes)

    # a/b/year — day first (Thai) or month first (US): decide from the data
    abc = date_part.str.extract(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$")
    if abc[0].notna().mean() > 0.8:
        a, b = pd.to_numeric(abc[0], errors="coerce"), pd.to_numeric(abc[1], errors="coerce")
        y = pd.to_numeric(abc[2], errors="coerce")
        if (y > 2400).any():
            notes.append("แปลงปี พ.ศ. เป็น ค.ศ.")
        dmy, mdy = _assemble(abc[2], abc[1], abc[0]), _assemble(abc[2], abc[0], abc[1])
        if (a > 12).any() and not (b > 12).any():
            return ParsedDates(dmy, "วัน/เดือน/ปี", notes + ["รู้ว่าเป็น วัน/เดือน เพราะตัวเลขแรกมีค่าเกิน 12"])
        if (b > 12).any() and not (a > 12).any():
            return ParsedDates(mdy, "เดือน/วัน/ปี", notes + ["รู้ว่าเป็น เดือน/วัน เพราะตัวเลขที่สองมีค่าเกิน 12"])
        if _contiguity(mdy) > _contiguity(dmy) + 0.05:
            return ParsedDates(mdy, "เดือน/วัน/ปี", notes + ["ตัวเลขไม่เกิน 12 ทั้งสองตำแหน่ง — เลือกแบบที่ได้วันที่ต่อเนื่องกว่า กรุณาตรวจช่วงวันที่"])
        return ParsedDates(dmy, "วัน/เดือน/ปี", notes + ["ตัวเลขไม่เกิน 12 ทั้งสองตำแหน่ง — ใช้ วัน/เดือน แบบไทย กรุณาตรวจช่วงวันที่"])

    # Anything else (e.g. "Jan 5, 2024")
    return ParsedDates(pd.to_datetime(text, errors="coerce", format="mixed", dayfirst=True).dt.normalize(), "รูปแบบอื่น")


def parse_amounts(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    t = s.astype("string").str.strip()
    neg = t.str.match(r"^\(.*\)$", na=False)
    t = t.str.replace(r"[()\s฿$€£]|บาท|THB|thb", "", regex=True)
    # 1.234,50 or 1.234.567 — only when unambiguous: "1.234" and "0.001" stay decimals
    euro = t.str.match(r"^-?[1-9]\d{0,2}((\.\d{3})+,\d+|(\.\d{3}){2,})$", na=False)
    t = t.where(~euro, t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    t = t.where(euro, t.str.replace(",", "", regex=False))                 # 1,234.50
    out = pd.to_numeric(t, errors="coerce")
    out = pd.Series(out.to_numpy(dtype=float, na_value=np.nan), index=s.index)  # nullable Int64 → float64
    return out.where(~neg.to_numpy(dtype=bool, na_value=False), -out.abs())


# --- Normalize -----------------------------------------------------------------------------


def _rows(mask: pd.Series) -> list[int]:
    """Spreadsheet row numbers (header = row 1) of the first rows in `mask`."""
    return [int(i) + 2 for i in np.flatnonzero(mask.to_numpy())[:EXAMPLE_ROWS]]


def normalize(df: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[pd.DataFrame, dict]:
    """(daily, report). Raises SalesFileError when nothing usable is left."""
    for role, col in mapping.items():
        if col is not None and col not in df.columns:
            raise SalesFileError(f"ไม่มีคอลัมน์ '{col}' ในไฟล์")
    if mapping.get("date") is None:
        raise SalesFileError("ไม่พบคอลัมน์วันที่ — เลือกคอลัมน์วันที่เอง")
    parsed = parse_dates(df[mapping["date"]])
    if mapping.get("sales"):
        amount = parse_amounts(df[mapping["sales"]])
        source = f"คอลัมน์ {mapping['sales']}"
    elif mapping.get("quantity") and mapping.get("price"):
        amount = parse_amounts(df[mapping["quantity"]]) * parse_amounts(df[mapping["price"]])
        source = f"{mapping['quantity']} × {mapping['price']}"
    else:
        raise SalesFileError("ไม่พบคอลัมน์ยอดขาย — เลือกคอลัมน์ยอดขาย หรือ จำนวน + ราคาต่อหน่วย")

    blank = df.isna().all(axis=1)
    bad_date = parsed.dates.isna() & ~blank
    bad_amount = amount.isna() & ~blank & ~bad_date
    skipped = [{"reason": reason, "count": int(m.sum()), "rows": _rows(m)}
               for reason, m in (("อ่านวันที่ไม่ได้", bad_date), ("อ่านยอดขายไม่ได้", bad_amount), ("แถวว่าง", blank)) if m.any()]
    ok = parsed.dates.notna() & amount.notna()
    if not ok.any():
        raise SalesFileError("ไม่มีแถวที่อ่านทั้งวันที่และยอดขายได้ — ตรวจคอลัมน์ที่เลือก")

    per_day = amount[ok].groupby(parsed.dates[ok]).sum()
    negative_days = int((per_day < 0).sum())
    per_day = per_day.clip(lower=0)
    days = pd.date_range(per_day.index.min(), per_day.index.max(), freq="D")
    daily = pd.DataFrame({"date": days, "sales": per_day.reindex(days, fill_value=0.0).to_numpy()})
    daily["open"] = (daily["sales"] > 0).astype("float32")

    notes = list(parsed.notes)
    rows_per_day = int(ok.sum()) / max(len(per_day), 1)
    if rows_per_day > 1.5:
        notes.append(f"หลายแถวต่อวัน (เฉลี่ย {rows_per_day:.0f}) — รวมเป็นยอดรายวัน")
    if negative_days:
        notes.append(f"{negative_days} วันยอดรวมติดลบ (เช่น คืนสินค้ามากกว่าขาย) — นับเป็น 0")
    if len(days) > 3660:
        notes.append("ช่วงวันที่ยาวเกิน 10 ปี — ตรวจว่าอ่านวันที่ถูกต้อง")
    report = {
        "rows": int(len(df)),
        "rows_used": int(ok.sum()),
        "skipped": skipped,
        "date_format": parsed.format,
        "amount_source": source,
        "date_range": {"start": days[0].strftime("%Y-%m-%d"), "end": days[-1].strftime("%Y-%m-%d")},
        "days": int(len(days)),
        "open_days": int(daily["open"].sum()),
        "notes": notes,
        "enough_days": len(days) >= MIN_DAYS,
        "min_days": MIN_DAYS,
    }
    return daily, report


def inspect(data: bytes, filename: str, mapping: dict[str, str | None] | None = None) -> dict:
    """Preview for the upload screen: columns, first rows, the mapping used, and the read report
    (or the reason it cannot be read). Never runs the model."""
    df, encoding = read_table(data, filename)
    if df.empty or len(df.columns) == 0:
        raise SalesFileError("ไฟล์ว่าง")
    guessed = guess_mapping(df)
    used = {**guessed, **{k: v for k, v in (mapping or {}).items() if v}}
    preview = df.head(PREVIEW_ROWS).astype(object).where(df.head(PREVIEW_ROWS).notna(), None)
    out = {
        "filename": filename,
        "encoding": encoding,
        "columns": [str(c) for c in df.columns],
        "preview": [{str(k): (None if v is None else str(v)) for k, v in row.items()} for row in preview.to_dict("records")],
        "mapping": used,
        "guessed": guessed,
    }
    try:
        daily, report = normalize(df, used)
        out |= {"ok": True, "report": report, "error": None,
                "daily": [{"date": d.strftime("%Y-%m-%d"), "sales": round(float(v), 2)} for d, v in zip(daily["date"], daily["sales"])][-730:]}
    except SalesFileError as e:
        out |= {"ok": False, "report": None, "error": str(e), "daily": []}
    return out
