"""Daily EventBridge Lambda (`alerts` in infra/template.yaml).

Emails the demo stores' cash-flow gaps through SNS, once per gap: each sent gap is recorded in DynamoDB
under pk "alert#<store>#<date>". Gaps come from data/synthetic/cash_flow_gaps.json
(ai.gap_detection.build), so every expense and balance in the email is synthetic and labelled as such.
Run it from the Lambda console with the test event {"force": true} to re-send gaps already alerted.
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

from ai.cashflow_forecast.preprocess import ROOT
from ai.gap_detection.build import AS_OF, DEMO_STORES, GAPS_PATH
from backend.aws import fetch_artifacts

SUBJECT = "MFP: cash-flow gap alert (synthetic demo data)"  # SNS subjects must be ASCII
CONTRIBUTORS_SHOWN = 3


def demo_gaps() -> list[tuple[int, dict]]:
    """(store, gap) for every forecast gap of the demo stores, in store order."""
    by_store = {o["merchant_id"]: o for o in json.loads(GAPS_PATH.read_text(encoding="utf-8"))}
    return [(s, g) for s in DEMO_STORES for g in by_store.get(s, {}).get("gaps", [])]


def message(alerts: list[tuple[int, dict]]) -> str:
    """Thai email body. Every warning carries a date and an amount; amounts have no currency unit."""
    lines = [
        "[ข้อมูลจำลอง] แจ้งเตือนเงินสดไม่พอจ่าย — MFP",
        f"ณ วันที่ {AS_OF.date().isoformat()} (วันที่สมมติของเดโม) คาดว่าเงินสดจะไม่พอในวันต่อไปนี้",
        "",
    ]
    for store, gap in alerts:
        lines.append(f"ร้าน {store}: วันที่ {gap['date']} เงินขาด {gap['shortfall']:,.0f}")
        for c in gap["contributors"][:CONTRIBUTORS_SHOWN]:
            lines.append(f"  - {c['label']} {c['amount']:,.0f} (ครบกำหนด {c['due_date']})")
    lines += ["", "รายจ่าย ยอดเงินคงเหลือ และช่วงเงินขาดมือทั้งหมดเป็นข้อมูลจำลองเพื่อการสาธิต ไม่ใช่ข้อมูลจริงของร้าน"]
    return "\n".join(lines)


def first_time(table, store: int, gap: dict) -> bool:
    """Record the gap; False when it was alerted before."""
    try:
        table.put_item(Item={"pk": f"alert#{store}#{gap['date']}", "store": store, "date": gap["date"]},
                       ConditionExpression="attribute_not_exists(pk)")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def handler(event, context):
    force = bool((event or {}).get("force"))
    fetch_artifacts([GAPS_PATH.relative_to(ROOT).as_posix()])
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    alerts = [(s, g) for s, g in demo_gaps() if first_time(table, s, g) or force]
    if alerts:
        boto3.client("sns").publish(TopicArn=os.environ["TOPIC_ARN"], Subject=SUBJECT, Message=message(alerts))
    result = {"as_of": AS_OF.date().isoformat(), "alerts_sent": len(alerts), "force": force}
    print(json.dumps(result))
    return result
