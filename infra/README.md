# คำสั่ง AWS ของ MFP

รันทุกคำสั่งใน AWS CloudShell (us-east-1) ของบัญชี Learner Lab ไม่ต้องติดตั้งอะไรในเครื่องตัวเอง
ดูไฟล์นี้ใน CloudShell ได้ด้วย `cat ~/MFP-Merchant-Financial-Passport/infra/README.md`

ข้อมูลรายจ่าย ยอดเงิน และอีเมลแจ้งเตือนทั้งหมดเป็นข้อมูลจำลอง

## เปิด CloudShell

1. Learner Lab → **Start Lab** → รอไฟเขียว → กด **AWS**
2. ใน Console กดไอคอน CloudShell (`>_`) ข้างช่องค้นหา ดูว่ามุมบนเขียน `us-east-1`

## ครั้งแรก

```bash
git clone https://github.com/pls2s/MFP-Merchant-Financial-Passport.git
cd MFP-Merchant-Financial-Passport && git switch cloud-aws
```

## ทุกครั้งที่เปิด CloudShell ใหม่

```bash
cd ~/MFP-Merchant-Financial-Passport
export PATH=$HOME/.local/bin:$PATH     # ให้หา tofu และ node ที่ setup.sh ติดตั้งไว้เจอ
git pull
```

## สร้างระบบ 4 ขั้น

แต่ละขั้นรัน setup ก่อน แล้วตามด้วย tofu ในโฟลเดอร์ `infra/live`

```bash
# ขั้น 1: S3 data bucket + artifact, DynamoDB, SNS (ใส่อีเมลครั้งเดียว ไม่ต้องมี < >)
./infra/setup.sh 1 you@example.com
cd infra/live && tofu init && tofu plan && tofu apply -auto-approve && cd ../..
# → เปิดอีเมล "AWS Notification - Subscription Confirmation" แล้วกด Confirm subscription

# ขั้น 2: Lambda api + API Gateway
./infra/setup.sh 2
cd infra/live && tofu plan && tofu apply -auto-approve && cd ../..

# ขั้น 3: S3 web + CloudFront (build หน้าเว็บ ใช้เวลาหลายนาที)
./infra/setup.sh 3
cd infra/live && tofu plan && tofu apply -auto-approve && cd ../..

# ขั้น 4: upload worker (S3 trigger) + alerts (EventBridge ทุกวัน 08:00)
./infra/setup.sh 4
cd infra/live && tofu plan && tofu apply -auto-approve && cd ../..
```

## ดูผล

```bash
cd ~/MFP-Merchant-Financial-Passport/infra/live
tofu output                                        # URL เว็บ, URL API, ชื่อ bucket, ตาราง, topic
curl -s "$(tofu output -raw api_url)/health"       # ขั้น 2 ขึ้นไป: ต้องได้ "as_of":"2015-07-17"
curl -s "$(tofu output -raw api_url)/api/v1/merchants/1/cash-flow-gaps" | head -c 300
```

- เปิด `website_url` ในเบราว์เซอร์ (ขั้น 3 ขึ้นไป) CloudFront ที่เพิ่งสร้างใช้เวลา 5–15 นาทีกว่าจะเปิดได้
- request แรกช้าไม่กี่วินาที เพราะ Lambda ต้องดาวน์โหลดข้อมูลก่อน (cold start)

ดู resource ที่สร้างแล้ว:

```bash
aws s3 ls
aws dynamodb list-tables
aws sns list-topics
aws lambda list-functions --query 'Functions[].FunctionName'
```

## ทดสอบแจ้งเตือน (ขั้น 4)

ส่งอีเมลเตือนทันทีโดยไม่ต้องรอ 08:00 (`force` ส่งซ้ำได้แม้เคยส่งแล้ว):

```bash
aws lambda invoke --function-name mfp-alerts \
  --cli-binary-format raw-in-base64-out --payload '{"force": true}' /tmp/alerts.json && cat /tmp/alerts.json
```

หรือทำบน Console: Lambda → `mfp-alerts` → Test → event `{"force": true}`

## ทดสอบอัปโหลดไฟล์ (ขั้น 4)

```bash
cd ~/MFP-Merchant-Financial-Passport/infra/live
# สร้างไฟล์ยอดขายตัวอย่าง 100 วัน
python3 -c "
import datetime as d
print('date,sales')
for i in range(100): print(d.date(2024,1,1)+d.timedelta(i), 1000+(i%7)*50)
" > /tmp/sample.csv

aws s3 cp /tmp/sample.csv "s3://$(tofu output -raw data_bucket)/uploads/test/sample.csv"
sleep 10
aws dynamodb get-item --table-name "$(tofu output -raw dynamodb_table)" \
  --key '{"pk": {"S": "upload#test/sample.csv"}}' --query 'Item.[status.S, days.N, start.S, end.S]'
```

ต้องได้ `["ok", "100", "2024-01-01", "2024-04-09"]` หรือทำบน Console ได้: S3 → bucket `mfp-<account>-data` → อัปไฟล์ไว้ในโฟลเดอร์ `uploads/` → DynamoDB → `mfp-main` → Explore items

## ดู log ของ Lambda (CloudWatch)

```bash
aws logs tail /aws/lambda/mfp-api --since 10m
aws logs tail /aws/lambda/mfp-upload-worker --since 10m
aws logs tail /aws/lambda/mfp-alerts --since 10m
```

## อัปเดตโค้ดหลังแก้

```bash
cd ~/MFP-Merchant-Financial-Passport && git pull
./infra/setup.sh 4                     # build app.zip และหน้าเว็บใหม่
cd infra/live && tofu apply -auto-approve
```

Lambda อัปเดตเมื่อ `app.zip` เปลี่ยน ส่วนหน้าเว็บอัปเดตเฉพาะไฟล์ที่เปลี่ยน

## Architecture Diagram

```bash
./infra/setup.sh graph                 # ได้ infra/live/arch.svg
```

ดาวน์โหลดไฟล์ทาง CloudShell → Actions → Download file → `/home/cloudshell-user/MFP-Merchant-Financial-Passport/infra/live/arch.svg`

## ลบทุกอย่าง

```bash
cd ~/MFP-Merchant-Financial-Passport/infra/live && tofu destroy    # พิมพ์ yes
```

ต้อง `tofu destroy` **ก่อน** กด Delete environment ใน CloudShell เพราะ state เก็บอยู่ใน `infra/live/` ถ้า state หายแล้วจะลบ resource ด้วย tofu ไม่ได้ ต้องลบเองทีละตัวบน Console

## แก้ปัญหา

| อาการ | ทำอย่างไร |
| --- | --- |
| `tofu: command not found` | `export PATH=$HOME/.local/bin:$PATH` |
| `ExpiredToken` หรือ `security token ... expired` | session ของ lab หมด: Start Lab ใหม่ แล้วเปิด CloudShell ใหม่ ส่วน resource ที่สร้างไว้ยังอยู่ |
| `First run needs the alert email` | ขั้น 1 ต้องใส่อีเมล: `./infra/setup.sh 1 you@example.com` |
| `Missing artifact: ...` | ไฟล์ข้อมูลหาย: `git pull` หรือ `git status` ดูว่าไฟล์ถูกลบไหม |
| `BucketAlreadyExists` / `already exists` | เคยสร้างไว้แต่ state หาย: ลบ resource ชื่อ `mfp-...` บน Console ก่อน แล้ว apply ใหม่ |
| เว็บขึ้น 403 หรือหน้าเปล่า | CloudFront ยัง deploy ไม่เสร็จ รอ 5–15 นาที |
| ไม่ได้อีเมลเตือน | กด Confirm subscription แล้วหรือยัง และดูในโฟลเดอร์ Spam |
| API ตอบ 500 | `aws logs tail /aws/lambda/mfp-api --since 10m` แล้วส่ง error ให้ทีม |
