# REST API (API Gateway v1) in front of the query Lambda. API keys and a usage plan give
# each client a key with its own rate limit and monthly quota; /health stays open.

resource "aws_api_gateway_rest_api" "this" {
  name        = var.name
  description = "NF-e query API"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

locals {
  api_id  = aws_api_gateway_rest_api.this.id
  root_id = aws_api_gateway_rest_api.this.root_resource_id
}

# /health
resource "aws_api_gateway_resource" "health" {
  rest_api_id = local.api_id
  parent_id   = local.root_id
  path_part   = "health"
}

# /invoices/{access_key}
resource "aws_api_gateway_resource" "invoices" {
  rest_api_id = local.api_id
  parent_id   = local.root_id
  path_part   = "invoices"
}

resource "aws_api_gateway_resource" "invoice" {
  rest_api_id = local.api_id
  parent_id   = aws_api_gateway_resource.invoices.id
  path_part   = "{access_key}"
}

# /issuers/{cnpj}/invoices
resource "aws_api_gateway_resource" "issuers" {
  rest_api_id = local.api_id
  parent_id   = local.root_id
  path_part   = "issuers"
}

resource "aws_api_gateway_resource" "issuer" {
  rest_api_id = local.api_id
  parent_id   = aws_api_gateway_resource.issuers.id
  path_part   = "{cnpj}"
}

resource "aws_api_gateway_resource" "issuer_invoices" {
  rest_api_id = local.api_id
  parent_id   = aws_api_gateway_resource.issuer.id
  path_part   = "invoices"
}

locals {
  routes = {
    health          = { resource_id = aws_api_gateway_resource.health.id, api_key = false }
    invoice         = { resource_id = aws_api_gateway_resource.invoice.id, api_key = true }
    issuer_invoices = { resource_id = aws_api_gateway_resource.issuer_invoices.id, api_key = true }
  }
}

resource "aws_api_gateway_method" "get" {
  for_each         = local.routes
  rest_api_id      = local.api_id
  resource_id      = each.value.resource_id
  http_method      = "GET"
  authorization    = "NONE" # callers authenticate with an API key (x-api-key header)
  api_key_required = each.value.api_key
}

resource "aws_api_gateway_integration" "get" {
  for_each                = local.routes
  rest_api_id             = local.api_id
  resource_id             = each.value.resource_id
  http_method             = aws_api_gateway_method.get[each.key].http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = var.lambda_invoke_arn
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = local.api_id
  # Redeploy whenever a route, method or integration changes.
  triggers = {
    redeployment = sha1(jsonencode([
      local.routes,
      [for m in aws_api_gateway_method.get : m.id],
      [for i in aws_api_gateway_integration.get : i.id],
    ]))
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id          = local.api_id
  deployment_id        = aws_api_gateway_deployment.this.id
  stage_name           = var.stage_name
  xray_tracing_enabled = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId = "$context.requestId"
      ip        = "$context.identity.sourceIp"
      apiKeyId  = "$context.identity.apiKeyId"
      method    = "$context.httpMethod"
      path      = "$context.resourcePath"
      status    = "$context.status"
      latencyMs = "$context.responseLatency"
    })
  }
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${var.name}/access"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = local.api_id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "*/*"
  settings {
    metrics_enabled        = true
    throttling_rate_limit  = var.rate_limit
    throttling_burst_limit = var.burst_limit
  }
}

resource "aws_api_gateway_usage_plan" "default" {
  name = "${var.name}-default"
  api_stages {
    api_id = local.api_id
    stage  = aws_api_gateway_stage.this.stage_name
  }
  throttle_settings {
    rate_limit  = var.rate_limit
    burst_limit = var.burst_limit
  }
  quota_settings {
    limit  = var.monthly_quota
    period = "MONTH"
  }
}

resource "aws_api_gateway_api_key" "clients" {
  for_each = toset(var.client_names)
  name     = "${var.name}-${each.key}"
}

resource "aws_api_gateway_usage_plan_key" "clients" {
  for_each      = aws_api_gateway_api_key.clients
  key_id        = each.value.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.default.id
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayGet"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  # Only GET requests on this API's stages may invoke the function.
  source_arn = "${aws_api_gateway_rest_api.this.execution_arn}/*/GET/*"
}
