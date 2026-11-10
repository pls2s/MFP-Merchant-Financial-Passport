"""Helpers for the AWS Lambda deployment (infra/steps/). Local runs never import this."""

import json
import os
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import boto3
from botocore.config import Config

UPLOAD_PREFIX = "uploads/"  # the prefix the upload worker is triggered on (infra/steps/4-automation.tf)


def fetch_artifacts(paths: list[str] | None = None) -> None:
    """Download s3://$ARTIFACT_BUCKET/$ARTIFACT_PREFIX<path> to $MFP_ROOT/<path>, keeping repo-relative
    paths so ai.* finds them through ROOT. `paths` limits it to those repo-relative files.
    Files already present (a warm container) are skipped."""
    bucket = os.environ["ARTIFACT_BUCKET"]
    prefix = os.environ.get("ARTIFACT_PREFIX", "artifacts/")
    root = Path(os.environ["MFP_ROOT"])
    s3 = boto3.client("s3")
    if paths is None:
        pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        keys = [obj["Key"] for page in pages for obj in page.get("Contents", [])]
    else:
        keys = [prefix + p for p in paths]
    for key in keys:
        dst = root / key[len(prefix):]
        if key.endswith("/") or dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_name(dst.name + ".part")  # a timeout mid-download must not leave a half file behind
        s3.download_file(bucket, key, str(part))
        part.rename(dst)


def presign_upload(bucket: str, filename: str, mapping: dict[str, str | None]) -> dict:
    """A presigned PUT for uploads/<random id>.<ext>. The original name and the confirmed columns ride
    along as object metadata for the upload worker, percent-encoded because S3 metadata is ASCII only
    (Thai column names are common). The browser must send `headers` with the PUT."""
    ext = PurePosixPath(filename).suffix.lower()
    upload_id = uuid.uuid4().hex + ext
    meta = {"filename": quote(filename),
            "mapping": quote(json.dumps({k: v for k, v in mapping.items() if v}, ensure_ascii=False))}
    url = boto3.client("s3", config=Config(signature_version="s3v4")).generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": UPLOAD_PREFIX + upload_id, "Metadata": meta}, ExpiresIn=600)
    return {"upload_id": upload_id, "url": url, "headers": {f"x-amz-meta-{k}": v for k, v in meta.items()}}


def read_upload(table: str, upload_id: str) -> dict:
    """The upload worker's DynamoDB item as an UploadStatus; "pending" until the worker has written it."""
    item = boto3.resource("dynamodb").Table(table).get_item(Key={"pk": f"upload#{upload_id}"}).get("Item")
    if not item:
        return {"upload_id": upload_id, "status": "pending"}
    out = {"upload_id": upload_id, "status": item["status"], "filename": item.get("filename"), "error": item.get("error")}
    if item["status"] == "ok":
        out.update(days=int(item["days"]), date_range={"start": item["start"], "end": item["end"]},
                   total_sales=float(item["total_sales"]), mean_daily_sales=float(item["mean_daily_sales"]),
                   daily=json.loads(item["daily"]), report=json.loads(item["report"]))
    return out
