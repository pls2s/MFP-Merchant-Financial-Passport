"""S3-triggered Lambda (`upload-worker` in infra/template.yaml).

Reads a sales file put under uploads/ with the same reader as POST /api/v1/upload, aggregates it to
daily sales and stores a summary in DynamoDB under pk "upload#<path after uploads/>".
It does not run the forecasting model: that needs TensorFlow, which does not fit a zip Lambda.
"""

import json
import os
import time
import traceback
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import unquote_plus

import boto3
import pandas as pd

from ai.cashflow_forecast.cold_start import SalesFileError, load_sales

PREFIX = "uploads/"
KEEP_SECONDS = 7 * 86400  # DynamoDB TTL, matching the bucket's 7-day expiry of uploads/
DAILY_SHOWN = 400         # keeps the item far below DynamoDB's 400 KB limit


def summarize(daily: pd.DataFrame) -> dict:
    """Plain-number summary of the daily frame from load_sales (columns date, sales)."""
    sales = daily["sales"].astype(float)
    shown = daily.tail(DAILY_SHOWN)
    return {
        "days": len(daily),
        "start": daily["date"].min().date().isoformat(),
        "end": daily["date"].max().date().isoformat(),
        "total_sales": Decimal(str(round(sales.sum(), 2))),
        "mean_daily_sales": Decimal(str(round(sales.mean(), 2))),
        "daily": json.dumps([{"date": d.date().isoformat(), "sales": round(float(s), 2)}
                             for d, s in zip(shown["date"], shown["sales"])]),
    }


def process(data: bytes, key: str, now: int | None = None) -> dict:
    """The DynamoDB item for one uploaded file. Unreadable files become status "error" with the reason
    (Thai, from SalesFileError), so the upload screen can show why."""
    now = now or int(time.time())
    filename = PurePosixPath(key).name
    item = {"pk": f"upload#{key.removeprefix(PREFIX)}", "filename": filename, "s3_key": key,
            "processed_at": now, "expires_at": now + KEEP_SECONDS}
    try:
        daily, report = load_sales(data, filename)
        item.update(status="ok", **summarize(daily), report=json.dumps(report, ensure_ascii=False, default=str))
    except SalesFileError as e:
        item.update(status="error", error=str(e))
    except Exception as e:  # a bad file must not be retried by S3 forever; record it and move on
        traceback.print_exc()
        item.update(status="error", error=f"อ่านไฟล์ไม่ได้: {e}")
    return item


def handler(event, context):
    s3 = boto3.client("s3")
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    done = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        item = process(s3.get_object(Bucket=bucket, Key=key)["Body"].read(), key)
        table.put_item(Item=item)
        print(json.dumps({k: v for k, v in item.items() if k not in ("daily", "report")}, ensure_ascii=False, default=str))
        done.append({"pk": item["pk"], "status": item["status"]})
    return done
