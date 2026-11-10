"""The AWS Lambda handlers (infra/template.yaml) with S3, DynamoDB and SNS replaced by fakes."""

import json

import pandas as pd
import pytest
from botocore.exceptions import ClientError

import backend.aws
from backend.workers import alerts, upload


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        if ConditionExpression and Item["pk"] in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[Item["pk"]] = Item


class FakeSns:
    def __init__(self):
        self.sent = []

    def publish(self, **kwargs):
        self.sent.append(kwargs)


def sales_csv(days: int) -> bytes:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    rows = [f"{d.date().isoformat()},{1000 + (i % 7) * 50}" for i, d in enumerate(dates)]
    return ("date,sales\n" + "\n".join(rows)).encode()


def test_upload_summarizes_a_readable_file():
    item = upload.process(sales_csv(100), "uploads/abc/shop.csv", now=1_700_000_000)
    assert item["pk"] == "upload#abc/shop.csv" and item["status"] == "ok"
    assert (item["days"], item["start"], item["end"]) == (100, "2024-01-01", "2024-04-09")
    assert item["expires_at"] == 1_700_000_000 + upload.KEEP_SECONDS
    assert len(json.loads(item["daily"])) == 100


def test_upload_records_why_a_file_cannot_be_used():
    item = upload.process(sales_csv(30), "uploads/short.csv")
    assert item["status"] == "error" and "70" in item["error"]  # MIN_DAYS, in the Thai message


def test_upload_handler_writes_one_item_per_record(monkeypatch):
    table = FakeTable()

    class S3:
        def get_object(self, Bucket, Key):
            return {"Body": type("B", (), {"read": lambda self: sales_csv(80)})()}

    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setattr(upload.boto3, "client", lambda name: S3())
    monkeypatch.setattr(upload.boto3, "resource", lambda name: type("R", (), {"Table": lambda self, n: table})())
    event = {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": "uploads/my+shop.csv"}}}]}
    assert upload.handler(event, None) == [{"pk": "upload#my shop.csv", "status": "ok"}]
    assert set(table.items) == {"upload#my shop.csv"}


@pytest.fixture
def alert_env(monkeypatch):
    table, sns = FakeTable(), FakeSns()
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("TOPIC_ARN", "arn:topic")
    monkeypatch.setattr(alerts, "fetch_artifacts", lambda paths: None)  # the repo already has the file
    monkeypatch.setattr(alerts.boto3, "client", lambda name: sns)
    monkeypatch.setattr(alerts.boto3, "resource", lambda name: type("R", (), {"Table": lambda self, n: table})())
    return table, sns


def test_alerts_email_each_demo_gap_once(alert_env):
    table, sns = alert_env
    first = alerts.handler({}, None)
    assert first["alerts_sent"] == len(alerts.demo_gaps()) > 0 and len(sns.sent) == 1
    body = sns.sent[0]["Message"]
    assert "ข้อมูลจำลอง" in body and "2015-07-22" in body
    assert sns.sent[0]["Subject"].isascii()
    assert alerts.handler({}, None)["alerts_sent"] == 0 and len(sns.sent) == 1  # already alerted
    assert alerts.handler({"force": True}, None)["alerts_sent"] == first["alerts_sent"]


def test_alert_message_has_date_and_amount_for_every_gap():
    gaps = alerts.demo_gaps()
    body = alerts.message(gaps)
    for store, gap in gaps:
        assert f"ร้าน {store}: วันที่ {gap['date']} เงินขาด {gap['shortfall']:,.0f}" in body


def test_api_handler_serves_the_same_api(monkeypatch):
    monkeypatch.setattr(backend.aws, "fetch_artifacts", lambda paths=None: None)
    from backend import lambda_handler

    def call(path):
        event = {
            "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
            "headers": {"host": "example.execute-api.us-east-1.amazonaws.com"},
            "requestContext": {"http": {"method": "GET", "path": path, "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4"},
                               "stage": "$default"},
            "isBase64Encoded": False,
        }
        return lambda_handler.handler(event, None)

    health = call("/health")
    assert health["statusCode"] == 200 and json.loads(health["body"])["as_of"] == "2015-07-17"
    gaps = json.loads(call("/api/v1/merchants/1/cash-flow-gaps")["body"])
    assert gaps["gaps"][0]["date"] == "2015-07-22" and gaps["is_synthetic_expense"] is True


def test_api_handler_answers_the_warmup_ping(monkeypatch):
    monkeypatch.setattr(backend.aws, "fetch_artifacts", lambda paths=None: None)
    from backend import lambda_handler

    assert lambda_handler.handler({"warmup": True}, None) == {"warm": True}
    assert lambda_handler._handler is not None  # the ping loaded the container
