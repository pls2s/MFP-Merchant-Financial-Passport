# Step 2 - API: the FastAPI backend on Lambda behind an API Gateway HTTP API.
# Needs infra/build/app.zip (infra/setup.sh 2 builds it).

locals {
  app_zip = "${var.repo_root}/infra/build/app.zip"
  # Shared by every Lambda: ai.* reads its files under MFP_ROOT, downloaded from the data bucket.
  lambda_env = {
    MFP_ROOT        = "/tmp/mfp"
    ARTIFACT_BUCKET = local.data_bucket
    ARTIFACT_PREFIX = "artifacts/"
    TABLE_NAME      = aws_dynamodb_table.main.name
  }
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project}-api"
  description      = "FastAPI backend (backend.app.main) through Mangum"
  role             = var.lab_role_arn
  runtime          = "python3.11"
  handler          = "backend.lambda_handler.handler"
  filename         = local.app_zip
  source_code_hash = filebase64sha256(local.app_zip)
  layers           = [var.pandas_layer_arn]
  memory_size      = 2048 # CPU scales with memory: halves the first-request load of pandas + artifacts
  timeout          = 30

  environment {
    variables = merge(local.lambda_env, {
      UPLOAD_BUCKET = local.data_bucket
      LLM_API_KEY   = var.llm_api_key
    })
  }

  depends_on = [aws_s3_object.artifact] # the first request downloads them
}

# Quick-create HTTP API: one $default route and stage that proxy every request to the API Lambda.
resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project}-api"
  protocol_type = "HTTP"
  target        = aws_lambda_function.api.arn
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*"
}

output "api_url" {
  description = "Try <api_url>/health and <api_url>/api/v1/merchants/1/cash-flow-gaps"
  value       = aws_apigatewayv2_api.http.api_endpoint
}
