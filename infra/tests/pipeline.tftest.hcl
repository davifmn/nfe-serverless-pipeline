# Whole stack against a mocked AWS provider: wiring and least privilege.
# Run from infra/:  terraform init -backend=false && terraform test

mock_provider "aws" {
  source = "./tests/mocks"
}

variables {
  environment = "test"
  region      = "sa-east-1"
}

run "ingest_is_wired_for_partial_batch_retries" {
  command = apply # applied to the mock: nothing is created in AWS

  assert {
    condition     = contains(aws_lambda_event_source_mapping.ingest.function_response_types, "ReportBatchItemFailures")
    error_message = "The ingest trigger must report individual failures, or one bad message retries the whole batch."
  }

  assert {
    condition     = one(aws_lambda_event_source_mapping.ingest.scaling_config).maximum_concurrency == 5
    error_message = "Ingest concurrency must be bounded."
  }

  assert {
    condition     = aws_kms_key.main.enable_key_rotation
    error_message = "The data key must rotate."
  }
}

run "roles_follow_least_privilege" {
  command = apply

  # No wildcard actions in either function's role.
  assert {
    condition = alltrue([
      for s in concat(jsondecode(module.ingest_function.policy).Statement, jsondecode(module.api_function.policy).Statement) :
      alltrue([for a in flatten([s.Action]) : !strcontains(a, "*")])
    ])
    error_message = "IAM actions must be listed explicitly (no wildcards)."
  }

  # The only statement allowed on Resource "*" is X-Ray, which has no resource-level permissions.
  assert {
    condition = alltrue([
      for s in jsondecode(module.ingest_function.policy).Statement : s.Resource != "*" || s.Sid == "Tracing"
    ])
    error_message = "Only X-Ray may use Resource \"*\"."
  }

  assert {
    condition = one([
      for s in jsondecode(module.ingest_function.policy).Statement : s.Action if s.Sid == "StoreInvoices"
    ]) == ["dynamodb:PutItem"]
    error_message = "The ingest function may only insert items (conditional PutItem)."
  }

  assert {
    condition = !anytrue([
      for s in jsondecode(module.api_function.policy).Statement :
      anytrue([for a in flatten([s.Action]) : contains(["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "s3:PutObject", "s3:DeleteObject"], a)])
    ])
    error_message = "The query API must be read-only."
  }

  assert {
    condition = one([
      for s in jsondecode(module.ingest_function.policy).Statement : s.Resource if s.Sid == "ReadIncoming"
    ]) == "${module.ingestion.bucket_arn}/incoming/*"
    error_message = "The ingest function may only read the incoming/ prefix."
  }
}

run "environment_name_is_validated" {
  command = plan

  variables {
    environment = "Production_1"
  }

  expect_failures = [var.environment]
}
