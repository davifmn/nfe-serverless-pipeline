# S3 → SQS decouples uploads from processing: bursts are absorbed by the queue, failures
# are retried, and poison messages end in the dead-letter queue instead of looping forever.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-ingest-dlq"
  message_retention_seconds = 1209600 # 14 days to investigate and redrive
  kms_master_key_id         = var.kms_key_arn
}

resource "aws_sqs_queue" "ingest" {
  name = "${var.name}-ingest"
  # AWS guidance: at least 6x the consumer's timeout, so a slow batch isn't redelivered
  # while it is still being processed.
  visibility_timeout_seconds = 6 * var.consumer_timeout_seconds
  receive_wait_time_seconds  = 20 # long polling
  message_retention_seconds  = 345600
  kms_master_key_id          = var.kms_key_arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.ingest.arn]
  })
}

resource "aws_sqs_queue_policy" "ingest" {
  queue_url = aws_sqs_queue.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowInboxNotifications"
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.ingest.arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = aws_s3_bucket.inbox.arn }
        StringEquals = { "aws:SourceAccount" = var.account_id }
      }
    }]
  })
}
