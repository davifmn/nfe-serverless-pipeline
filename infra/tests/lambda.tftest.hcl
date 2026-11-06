# Generic Lambda module defaults.

mock_provider "aws" {
  source = "./tests/mocks"
}

variables {
  name        = "nfe-test-fn"
  handler     = "nfe_pipeline.handlers.api.handler"
  source_dir  = "../src"
  kms_key_arn = "arn:aws:kms:sa-east-1:123456789012:key/test"
  policy_statements = [{
    Sid      = "Custom"
    Effect   = "Allow"
    Action   = ["dynamodb:GetItem"]
    Resource = "arn:aws:dynamodb:sa-east-1:123456789012:table/t"
  }]
}

run "runtime_tracing_and_logs" {
  command = apply

  module {
    source = "./modules/lambda_function"
  }

  assert {
    condition     = aws_lambda_function.this.runtime == "python3.13" && aws_lambda_function.this.architectures == ["arm64"]
    error_message = "Functions run Python 3.13 on Graviton (arm64)."
  }

  assert {
    condition     = one(aws_lambda_function.this.tracing_config).mode == "Active"
    error_message = "X-Ray tracing must be on."
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 30 && aws_cloudwatch_log_group.this.kms_key_id == var.kms_key_arn
    error_message = "Logs must expire and be encrypted."
  }

  assert {
    condition     = contains([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s.Sid], "Custom")
    error_message = "Extra statements must be merged into the role policy."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.errors.alarm_actions) == 0
    error_message = "Without a topic the alarm has no actions."
  }
}
