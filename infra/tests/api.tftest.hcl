# Query API: authentication, throttling and invoke permission.

mock_provider "aws" {
  source = "./tests/mocks"
}

variables {
  name                 = "nfe-test-api"
  lambda_invoke_arn    = "arn:aws:apigateway:sa-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:sa-east-1:123456789012:function:api/invocations"
  lambda_function_name = "nfe-test-api"
  kms_key_arn          = "arn:aws:kms:sa-east-1:123456789012:key/test"
  client_names         = ["accounting", "erp"]
}

run "data_routes_require_an_api_key" {
  command = apply

  module {
    source = "./modules/api"
  }

  assert {
    condition     = aws_api_gateway_method.get["invoice"].api_key_required && aws_api_gateway_method.get["issuer_invoices"].api_key_required
    error_message = "Invoice data must require an API key."
  }

  assert {
    condition     = !aws_api_gateway_method.get["health"].api_key_required
    error_message = "/health stays open for load balancers and uptime checks."
  }

  assert {
    condition     = length(aws_api_gateway_api_key.clients) == 2 && length(aws_api_gateway_usage_plan_key.clients) == 2
    error_message = "Each client gets its own key on the usage plan."
  }

  assert {
    condition     = endswith(aws_lambda_permission.api.source_arn, "/*/GET/*")
    error_message = "API Gateway may only invoke the function for GET requests."
  }

  assert {
    condition     = one(aws_api_gateway_usage_plan.default.throttle_settings).rate_limit == 20
    error_message = "The usage plan must throttle clients."
  }
}
