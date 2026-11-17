"""MFP on AWS, drawn like the AWS reference diagrams: official icons, a dashed box per `./infra/setup.sh` step
with a black tab, square-cornered arrows. Every position is set by hand so no two lines cross.

    pip install diagrams   # only for its AWS icon set (resources/aws)
    python infra/overview.py <site-packages>/resources/aws docs/figures
    rsvg-convert -z 2 docs/figures/aws_overview.svg -o docs/figures/aws_overview.png
"""

import base64
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ICONS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
THAI = "'Sukhumvit Set', Thonburi, 'Noto Sans Thai', sans-serif"
MONO = "Menlo, 'DejaVu Sans Mono', monospace"
INK, SUB, LINE = "#111827", "#4b5563", "#374151"
R1, R2, R3 = 210, 440, 660          # rows
S = 72                               # icon size

parts: list[str] = []


def icon(path, cx, cy, title, *sub):
    data = base64.b64encode((ICONS / path).read_bytes()).decode()
    parts.append(f'<image x="{cx - S / 2}" y="{cy - S / 2}" width="{S}" height="{S}" href="data:image/png;base64,{data}"/>')
    y = cy + S / 2 + 22
    parts.append(f'<text x="{cx}" y="{y}" text-anchor="middle" font-family="{THAI}" font-size="15" fill="{INK}">{escape(title)}</text>')
    for i, line in enumerate(sub):
        font, size = (MONO, 12) if line.isascii() else (THAI, 13)   # Menlo has no Thai glyphs
        parts.append(f'<text x="{cx}" y="{y + 19 * (i + 1)}" text-anchor="middle" font-family="{font}" '
                     f'font-size="{size}" fill="{SUB}">{escape(line)}</text>')


def box(x, y, w, h, tab):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#6b7280" '
                 f'stroke-width="1.5" stroke-dasharray="7 5"/>')
    tw = 7.3 * len(tab) + 18
    parts.append(f'<rect x="{x}" y="{y}" width="{tw}" height="24" fill="#1f2937"/>')
    parts.append(f'<text x="{x + 9}" y="{y + 16.5}" font-family="{MONO}" font-size="12" fill="#fff">{escape(tab)}</text>')


def arrow(points, label=None, at=None, anchor="middle", dash=None):
    d = " ".join(f"{x},{y}" for x, y in points)
    style = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<polyline points="{d}" fill="none" stroke="{LINE}" stroke-width="1.6"{style} marker-end="url(#head)"/>')
    if label:
        x, y = at
        parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{THAI}" font-size="13" fill="{LINE}" '
                     f'stroke="#fff" stroke-width="5" stroke-linejoin="round" paint-order="stroke">{escape(label)}</text>')


# AWS Cloud
parts.append(f'<rect x="260" y="30" width="1060" height="840" rx="16" fill="none" stroke="{INK}" stroke-width="2"/>')
parts.append(f'<text x="284" y="62" font-family="{THAI}" font-size="16" fill="{INK}">AWS Cloud · us-east-1 (Learner Lab)</text>')

box(290, 345, 160, 200, "./infra/setup.sh 3")
box(490, 118, 430, 200, "./infra/setup.sh 2")
box(490, 345, 430, 490, "./infra/setup.sh 4")
box(1030, 118, 190, 650, "./infra/setup.sh 1")

icon("general/client.png", 120, R2, "ผู้ใช้", "(เบราว์เซอร์)")
icon("devtools/cloudshell.png", 120, 720, "AWS CloudShell", "OpenTofu")
icon("mobile/amplify.png", 370, R2, "AWS Amplify", "mfp-dashboard")
icon("network/api-gateway.png", 595, R1, "Amazon API Gateway", "mfp-api")
icon("compute/lambda.png", 815, R1, "AWS Lambda", "mfp-api")
icon("compute/lambda.png", 815, R2, "AWS Lambda", "mfp-upload-worker")
icon("integration/eventbridge.png", 595, R3, "Amazon EventBridge", "mfp-daily-alerts", "mfp-api-warmup")
icon("compute/lambda.png", 815, R3, "AWS Lambda", "mfp-alerts")
icon("storage/simple-storage-service-s3.png", 1125, R1, "Amazon S3", "mfp-<account>-data")
icon("database/dynamodb.png", 1125, R2, "Amazon DynamoDB", "mfp-main")
icon("integration/simple-notification-service-sns.png", 1125, R3, "Amazon SNS", "mfp-alerts")
icon("management/cloudwatch-logs.png", 370, 730, "CloudWatch Logs", "log ของ Lambda ทุกตัว")
icon("integration/simple-notification-service-sns-email-notification.png", 1450, R3, "อีเมลเตือน", "ทุกวัน 08:00")

h = S / 2
arrow([(120 + h, R2), (370 - h - 4, R2)], "เปิดเว็บ", (210, R2 - 10))
arrow([(370 + h, R2), (470, R2), (470, R1), (595 - h - 4, R1)], "/api/*", (520, R1 - 10))
arrow([(595 + h, R1), (815 - h - 4, R1)])
arrow([(815 + h, R1), (1125 - h - 4, R1)], "อ่านผลพยากรณ์", (965, R1 - 10))
arrow([(1125 - h, R1 + 22), (990, R1 + 22), (990, R2 - 20), (815 + h + 4, R2 - 20)],
      "ไฟล์ใน uploads/", (982, 336), anchor="end")
arrow([(815 + h, R2 + 15), (1125 - h - 4, R2 + 15)], "บันทึกสรุปยอด", (925, R2 + 6))
arrow([(595 + h, R3), (815 - h - 4, R3)], "ทุกวัน 08:00", (705, R3 - 10))
arrow([(815 + h, R3), (1125 - h - 4, R3)], "ส่งเตือน", (1010, R3 - 10))
arrow([(815 + h, R3 - 20), (940, R3 - 20), (940, R2 + 40), (1125 - h - 4, R2 + 40)],
      "กันส่งซ้ำ", (932, 565), anchor="end")
arrow([(1125 + h, R3), (1450 - h - 4, R3)], "ส่งอีเมล", (1270, R3 - 10))
arrow([(120, R2 - h), (120, 92), (1125, 92), (1125, R1 - h - 4)],
      "อัปโหลด CSV ตรงเข้า S3 (presigned URL)", (690, 86), dash="6 5")
arrow([(120 + h, 720), (258, 720)], "tofu apply", (205, 710), dash="6 5")

NOTE = (f'<text x="260" y="906" font-family="{THAI}" font-size="13" fill="{SUB}">ไม่ได้วาดเพื่อให้อ่านง่าย: '
        f'mfp-api อ่านผลอัปโหลดจาก DynamoDB · EventBridge (mfp-api-warmup) ปลุก mfp-api ทุก 5 นาที · '
        f'ทุก Lambda ใช้ IAM role LabRole</text>')
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1560" height="930" viewBox="0 0 1560 930">'
       f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
       f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>'
       f'<rect width="1560" height="930" fill="#fff"/>' + "".join(parts) + NOTE + "</svg>")
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "aws_overview.svg").write_text(svg, encoding="utf-8")
print(OUT / "aws_overview.svg")
