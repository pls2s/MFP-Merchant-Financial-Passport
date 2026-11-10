# Step 3 - Web: the React dashboard on S3 behind CloudFront, with /api/* forwarded to API Gateway.
# Needs frontend/dist built for the same-origin API (infra/setup.sh 3 builds it).

locals {
  web_dir   = "${var.repo_root}/frontend/dist"
  web_files = fileset(local.web_dir, "**")
  mime = {
    html  = "text/html; charset=utf-8"
    js    = "text/javascript"
    css   = "text/css"
    json  = "application/json"
    svg   = "image/svg+xml"
    png   = "image/png"
    jpg   = "image/jpeg"
    webp  = "image/webp"
    ico   = "image/x-icon"
    woff2 = "font/woff2"
    txt   = "text/plain"
    map   = "application/json"
  }
}

# Made with the AWS CLI for the same reason as the data bucket (1-storage.tf).
resource "terraform_data" "web_bucket" {
  input = "${local.prefix}-web"
  provisioner "local-exec" {
    command = format(local.create_bucket, self.input, self.input)
  }
  provisioner "local-exec" {
    when    = destroy
    command = "aws s3 rb s3://${self.input} --force"
  }
}

locals {
  web_bucket     = terraform_data.web_bucket.output
  web_bucket_arn = "arn:aws:s3:::${terraform_data.web_bucket.output}"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = local.web_bucket
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "web" {
  for_each     = local.web_files
  bucket       = local.web_bucket
  key          = each.value
  source       = "${local.web_dir}/${each.value}"
  etag         = filemd5("${local.web_dir}/${each.value}")
  content_type = lookup(local.mime, regex("[^.]+$", each.value), "application/octet-stream")
  # index.html names the hashed bundles, so it must never be cached or a redeploy shows the old app.
  cache_control = each.value == "index.html" ? "no-cache" : null
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${local.prefix}-web-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# The app uses BrowserRouter (/merchants/1, /upload ...): paths without a file extension get index.html.
# Only on the default behavior, so API 404s under /api/* reach the frontend unchanged.
resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "${var.project}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Serve index.html for client-side routes"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      if (!request.uri.includes('.')) {
        request.uri = '/index.html';
      }
      return request;
    }
  EOT
}

resource "aws_cloudfront_distribution" "web" {
  comment             = "MFP dashboard and API"
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    origin_id                = "web"
    domain_name              = "${local.web_bucket}.s3.${var.aws_region}.amazonaws.com"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = "api"
    domain_name = replace(aws_apigatewayv2_api.http.api_endpoint, "https://", "")
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # Managed-CachingDisabled
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac" # Managed-AllViewerExceptHostHeader
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = local.web_bucket
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "CloudFrontReadOnly"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${local.web_bucket_arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.web.arn } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.web]
}

output "website_url" {
  description = "Open this to use the dashboard (CloudFront takes a few minutes to deploy)"
  value       = "https://${aws_cloudfront_distribution.web.domain_name}"
}
