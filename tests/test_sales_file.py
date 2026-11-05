import datetime as dt

import pandas as pd
import pytest

from ai.cashflow_forecast.sales_file import (
    MIN_DAYS, SalesFileError, guess_mapping, inspect, normalize, parse_amounts, parse_dates, read_table,
)

DAYS = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(84)]


def csv(header="date,sales", fmt=lambda d: d.isoformat(), val=lambda i: "4000", enc="utf-8") -> bytes:
    return (header + "\n" + "".join(f"{fmt(d)},{val(i)}\n" for i, d in enumerate(DAYS))).encode(enc)


def read(data: bytes, name="shop.csv", mapping=None):
    df, _ = read_table(data, name)
    return normalize(df, {**guess_mapping(df), **(mapping or {})})


def assert_jan_to_mar(daily, report):
    assert report["date_range"] == {"start": "2024-01-01", "end": "2024-03-24"}
    assert report["days"] == 84 and report["open_days"] == 84
    assert daily["sales"].mean() == pytest.approx(4000)


@pytest.mark.parametrize("header", ["date,sales", " Date , SALES ", "วันที่,ยอดขาย", "วันที่,ยอดรวม", "Day,Total", "order_date,net_sales",
                                    "วันที่ขาย,ยอดรวม (บาท)", "Date,Sales (THB)"])
def test_header_names(header):
    assert_jan_to_mar(*read(csv(header)))


def test_thai_day_first_dates_are_not_misread():
    daily, report = read(csv(fmt=lambda d: d.strftime("%d/%m/%Y")))
    assert_jan_to_mar(daily, report)
    assert report["date_format"] == "วัน/เดือน/ปี"


def test_month_first_is_detected_from_values_over_12():
    daily, report = read(csv(fmt=lambda d: d.strftime("%m/%d/%Y")))
    assert_jan_to_mar(daily, report)
    assert report["date_format"] == "เดือน/วัน/ปี"


@pytest.mark.parametrize("fmt", [
    lambda d: f"{d.year + 543}-{d.month:02d}-{d.day:02d}",          # 2567-01-05
    lambda d: f"{d.day}/{d.month}/{d.year + 543}",                    # 5/1/2567
    lambda d: f"{d.day} {['ม.ค.', 'ก.พ.', 'มี.ค.'][d.month - 1]} {d.year + 543}",   # 5 ม.ค. 2567
    lambda d: f"{d.day} {['มกราคม', 'กุมภาพันธ์', 'มีนาคม'][d.month - 1]} {(d.year + 543) % 100}",  # 5 มกราคม 67
])
def test_buddhist_years_and_thai_month_names(fmt):
    assert_jan_to_mar(*read(csv(fmt=fmt)))


def test_excel_serial_dates():
    assert_jan_to_mar(*read(csv(fmt=lambda d: str((d - dt.date(1899, 12, 30)).days))))


@pytest.mark.parametrize("val", ['"4,000"', '"฿4,000.00"', "4000 บาท", '"4.000,00"'])
def test_amount_formats(val):
    assert_jan_to_mar(*read(csv(val=lambda i: val)))


def test_decimal_points_are_not_mistaken_for_thousands():
    assert parse_amounts(pd.Series(["0.001", "1.234", "1.234.567", "1.234,5"])).tolist() == [0.001, 1.234, 1234567.0, 1234.5]


def test_parentheses_are_negative():
    assert parse_amounts(pd.Series(["(500)", "1,200", "x"])).tolist()[:2] == [-500.0, 1200.0]


def test_cp874_thai_csv():
    assert_jan_to_mar(*read(csv("วันที่,ยอดขาย", enc="cp874")))


def test_semicolon_separated():
    assert_jan_to_mar(*read(csv().replace(b",", b";")))


def test_skipped_rows_are_reported_with_row_numbers():
    daily, report = read(csv(val=lambda i: "n/a" if i in (0, 10) else "4000"))
    skipped = {s["reason"]: s for s in report["skipped"]}
    assert skipped["อ่านยอดขายไม่ได้"]["count"] == 2
    assert skipped["อ่านยอดขายไม่ได้"]["rows"] == [2, 12]  # header is row 1
    assert report["rows_used"] == 82


def test_transactions_are_summed_per_day():
    rows = ["InvoiceDate,Quantity,UnitPrice"] + [f"{d} 10:00,2,1000" for d in DAYS] + [f"{d} 15:00,1,2000" for d in DAYS]
    daily, report = read("\n".join(rows).encode())
    assert_jan_to_mar(daily, report)
    assert report["amount_source"] == "Quantity × UnitPrice"
    assert any("หลายแถวต่อวัน" in n for n in report["notes"])


def test_single_numeric_column_is_used_as_sales():
    assert_jan_to_mar(*read(csv("วัน,มูลค่า")))


def test_user_mapping_overrides_the_guess():
    data = ("d,a,b\n" + "".join(f"{d},1,4000\n" for d in DAYS)).encode()
    df, _ = read_table(data, "x.csv")
    assert guess_mapping(df)["sales"] is None  # two numeric columns: ambiguous
    assert_jan_to_mar(*normalize(df, {**guess_mapping(df), "sales": "b"}))


def test_missing_columns_explain_what_to_pick():
    df, _ = read_table(b"x,y\nfoo,bar\n", "x.csv")
    with pytest.raises(SalesFileError, match="วันที่"):
        normalize(df, guess_mapping(df))


def test_inspect_never_raises_on_a_bad_mapping_and_reports_short_files():
    out = inspect(csv(), "shop.csv", {"sales": "nope"})
    assert out["ok"] is False and "nope" in out["error"]
    short = inspect(b"date,sales\n2024-01-01,1\n2024-01-02,2\n", "s.csv")
    assert short["ok"] and short["report"]["enough_days"] is False and short["report"]["min_days"] == MIN_DAYS
    assert short["preview"][0] == {"date": "2024-01-01", "sales": "1"}


def test_parse_dates_ambiguous_prefers_thai_day_first():
    # all values ≤ 12 in both positions and equally contiguous → day first (Thai convention)
    s = pd.Series(["01/02/2024", "02/02/2024", "03/02/2024"])
    assert parse_dates(s).dates.dt.month.tolist() == [2, 2, 2]
