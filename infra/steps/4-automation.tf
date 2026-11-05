# Step 4 - Automation: an S3-triggered upload worker and a daily EventBridge rule that emails the
# demo stores' synthetic cash-flow gaps through SNS.

resource "aws_lambda_function" "upload" {
  function_name    = "${var.project}-upload-worker"
  description      = "Reads an uploaded sales file, aggregates daily sales, writes the result to DynamoDB"
  role             = var.lab_role_arn
  runtime          = "python3.11"
  handler          = "backend.workers.upload.handler"
  filename         = local.app_zip
  source_code_hash = filebase64sha256(local.app_zip)
  layers           = [var.pandas_layer_arn]
  memory_size      = 1024
  timeout          = 120

  environment {
    variables = local.lambda_env
  }
}

resource "aws_lambda_permission" "s3_upload" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.upload.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.data.arn
  source_account = var.account_id
}

resource "aws_s3_bucket_notification" "uploads" {
  bucket = aws_s3_bucket.data.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.upload.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }
  depends_on = [aws_lambda_permission.s3_upload]
}

resource "aws_lambda_function" "alerts" {
  function_name    = "${var.project}-alerts"
  description      = "Daily check of the demo stores' cash-flow gaps; publishes alerts to SNS"
  role             = var.lab_role_arn
  runtime          = "python3.11"
  handler          = "backend.workers.alerts.handler"
  filename         = local.app_zip
  source_code_hash = filebase64sha256(local.app_zip)
  layers           = [var.pandas_layer_arn]
  memory_size      = 512
  timeout          = 60

  environment {
    variables = merge(local.lambda_env, { TOPIC_ARN = aws_sns_topic.alerts.arn })
  }
}

# 08:00 Bangkok time = 01:00 UTC. A rule needs no IAM role, unlike EventBridge Scheduler.
resource "aws_cloudwatch_event_rule" "daily_alerts" {
  name                = "${var.project}-daily-alerts"
  description         = "Run the MFP cash-flow gap check every morning"
  schedule_expression = "cron(0 1 * * ? *)"
}

resource "aws_cloudwatch_event_target" "alerts" {
  rule = aws_cloudwatch_event_rule.daily_alerts.name
  arn  = aws_lambda_function.alerts.arn
}

resource "aws_lambda_permission" "events_alerts" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alerts.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_alerts.arn
}

output "alerts_function" {
  description = "Run it now: Lambda console -> Test with the event {\"force\": true}"
  value       = aws_lambda_function.alerts.function_name
}
