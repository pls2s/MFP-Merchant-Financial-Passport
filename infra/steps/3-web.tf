# Step 3 - Web: the React dashboard on AWS Amplify Hosting (a managed CloudFront CDN, as in the course
# labs; Learner Lab denies creating CloudFront origin access controls and functions directly).
# Amplify proxies /api/* to API Gateway, so the app calls its own domain.
# Needs infra/build/web.zip, frontend/dist built for the same-origin API (infra/setup.sh 3 builds it).

locals {
  web_zip = "${var.repo_root}/infra/build/web.zip"
}

resource "aws_amplify_app" "web" {
  name        = "${var.project}-dashboard"
  description = "MFP dashboard (synthetic expense data)"

  # Rules apply in order. The API rule comes first so API 404s reach the app unchanged.
  custom_rule {
    source = "/api/<*>"
    target = "${aws_apigatewayv2_api.http.api_endpoint}/api/<*>"
    status = "200"
  }

  # The app reads "today" (as_of) from /health, which sits outside /api.
  custom_rule {
    source = "/health"
    target = "${aws_apigatewayv2_api.http.api_endpoint}/health"
    status = "200"
  }

  # The app uses BrowserRouter (/merchants/1, /upload ...): paths that are not files get index.html.
  custom_rule {
    source = "</^[^.]+$|\\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>"
    target = "/index.html"
    status = "200"
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.web.id
  branch_name = "main"
  stage       = "PRODUCTION"
}

# Manual deployment (no Git repository): upload web.zip to Amplify's presigned URL, start the job and
# wait for it. Runs again whenever the build changes.
resource "terraform_data" "web_deploy" {
  triggers_replace = filemd5(local.web_zip)

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      APP_ID = aws_amplify_app.web.id
      BRANCH = aws_amplify_branch.main.branch_name
      ZIP    = local.web_zip
    }
    command = <<-EOT
      set -euo pipefail
      read -r JOB URL < <(aws amplify create-deployment --app-id "$APP_ID" --branch-name "$BRANCH" \
        --query '[jobId,zipUploadUrl]' --output text)
      curl -fsS -T "$ZIP" "$URL"
      aws amplify start-deployment --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB" >/dev/null
      for _ in $(seq 60); do
        STATUS=$(aws amplify get-job --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB" \
          --query job.summary.status --output text)
        echo "Amplify deployment $JOB: $STATUS"
        [[ "$STATUS" == SUCCEED ]] && exit 0
        [[ "$STATUS" == FAILED || "$STATUS" == CANCELLED ]] && exit 1
        sleep 5
      done
      exit 1
    EOT
  }
}

output "website_url" {
  description = "Open this to use the dashboard"
  value       = "https://${aws_amplify_branch.main.branch_name}.${aws_amplify_app.web.default_domain}"
}
