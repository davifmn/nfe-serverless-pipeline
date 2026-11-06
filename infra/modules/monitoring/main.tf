# Alarm notifications and the queue/API alarms. Lambda alarms live in the lambda module.

resource "aws_sns_topic" "alarms" {
  name              = "${var.name}-alarms"
  kms_master_key_id = var.kms_key_arn
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.name}-dlq-not-empty"
  alarm_description   = "Messages failed every retry and are in the DLQ. See docs/runbook.md#dlq-not-empty."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "queue_backlog" {
  alarm_name          = "${var.name}-ingest-backlog"
  alarm_description   = "Oldest message waits more than ${var.max_message_age_seconds}s: ingestion is falling behind."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = var.queue_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.max_message_age_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  alarm_description   = "The query API is returning server errors."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5XXError"
  dimensions          = { ApiName = var.api_name, Stage = var.api_stage }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = var.name
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Ingest queue"
          region = var.region
          stat   = "Maximum"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.queue_name],
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", var.queue_name, { yAxis = "right" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda"
          region = var.region
          stat   = "Sum"
          metrics = [
            for fn in var.function_names : ["AWS/Lambda", "Errors", "FunctionName", fn]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "API latency (p99) and requests"
          region = var.region
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiName", var.api_name, "Stage", var.api_stage, { stat = "p99" }],
            ["AWS/ApiGateway", "Count", "ApiName", var.api_name, "Stage", var.api_stage, { stat = "Sum", yAxis = "right" }],
          ]
        }
      },
    ]
  })
}
