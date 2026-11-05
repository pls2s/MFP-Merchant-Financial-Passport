"""Helpers for the AWS Lambda deployment (infra/template.yaml). Local runs never import this."""

import os
from pathlib import Path

import boto3


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
