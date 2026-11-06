# Generic Lambda function: package, least-privilege role, log group, alarms.

data "archive_file" "package" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.root}/.build/${var.name}.zip"
}

resource "aws_iam_role" "this" {
  name = var.name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "this" {
  name = "${var.name}-permissions"
  role = aws_iam_role.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid      = "WriteOwnLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "${aws_cloudwatch_log_group.this.arn}:*"
        },
        {
          # X-Ray has no resource-level permissions; "*" is the only valid resource.
          Sid      = "Tracing"
          Effect   = "Allow"
          Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
          Resource = "*"
        },
      ],
      var.policy_statements,
    )
  })
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
}

resource "aws_lambda_function" "this" {
  function_name                  = var.name
  description                    = var.description
  role                           = aws_iam_role.this.arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"] # Graviton: cheaper per GB-second than x86
  handler                        = var.handler
  filename                       = data.archive_file.package.output_path
  source_code_hash               = data.archive_file.package.output_base64sha256
  timeout                        = var.timeout_seconds
  memory_size                    = var.memory_mb
  reserved_concurrent_executions = var.reserved_concurrency
  kms_key_arn                    = var.kms_key_arn

  environment {
    variables = var.environment
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_iam_role_policy.this, aws_cloudwatch_log_group.this]
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.name}-errors"
  alarm_description   = "Unhandled errors in ${var.name}. See docs/runbook.md."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_topic_arn == null ? [] : [var.alarm_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name          = "${var.name}-throttles"
  alarm_description   = "${var.name} is being throttled (concurrency limit reached)."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_topic_arn == null ? [] : [var.alarm_topic_arn]
}
