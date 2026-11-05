# Step 1 - Storage and notification: S3 data bucket with the precomputed artifacts, DynamoDB, SNS.
# infra/setup.sh copies steps 1..N into infra/live/ and writes terraform.tfvars, so each step adds
# services on top of the last one (tofu plan shows only what the new step adds).
# All expenses, balances and alerts in this stack are synthetic demo data.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  type = string
}

variable "lab_role_arn" {
  description = "Existing role for every Lambda. Learner Lab cannot create roles, so this is LabRole."
  type        = string
}

variable "alert_email" {
  description = "Receives the cash-flow gap alerts (confirm the SNS subscription email)."
  type        = string
}

variable "repo_root" {
  description = "Absolute path of the repository; artifacts, app.zip and the web build are read from it."
  type        = string
}

variable "project" {
  description = "Lowercase prefix for resource names."
  type        = string
  default     = "mfp"
}

variable "pandas_layer_arn" {
  description = "AWS SDK for pandas layer (pandas, numpy, pyarrow) for Python 3.11 in us-east-1."
  type        = string
  default     = "arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python311:36"
}

variable "llm_api_key" {
  description = "Optional Typhoon API key for the copilot. Empty means the template fallback answers."
  type        = string
  default     = ""
  sensitive   = true
}

locals {
  prefix = "${var.project}-${var.account_id}"

  # Files the backend reads (found by calling every endpoint with an open() audit hook), at repo paths.
  # .env is never uploaded: secrets go in as variables.
  artifacts = concat(
    [for line in split("\n", file("${path.module}/artifacts.txt")) : trimspace(line)
    if trimspace(line) != "" && !startswith(trimspace(line), "#")],
    # Read only when present: the model-experiments screen lists the cells that have a config.
    tolist(fileset(var.repo_root, "models/{lstm,gru,tcn,transformer}/config.json")),
  )
}

# Holds artifacts/ (read by the Lambdas) and uploads/ (written by the browser, read by the upload worker).
resource "aws_s3_bucket" "data" {
  bucket        = "${local.prefix}-data"
  force_destroy = true # tofu destroy empties it first
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = ["*"]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    id     = "expire-uploads"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = 7
    }
  }
}

resource "aws_s3_object" "artifact" {
  for_each = toset(local.artifacts)
  bucket   = aws_s3_bucket.data.id
  key      = "artifacts/${each.value}"
  source   = "${var.repo_root}/${each.value}"
  etag     = filemd5("${var.repo_root}/${each.value}")
}

# One table, two kinds of item: pk = "upload#<id>" (processed upload) or "alert#<store>#<date>" (alert sent).
resource "aws_dynamodb_table" "main" {
  name         = "${var.project}-main"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_sns_topic" "alerts" {
  name         = "${var.project}-alerts"
  display_name = "MFP cash-flow alerts (synthetic data)"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

output "data_bucket" {
  description = "Put a sales file under uploads/ here to trigger the upload Lambda (step 4)"
  value       = aws_s3_bucket.data.id
}

output "dynamodb_table" {
  value = aws_dynamodb_table.main.name
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
