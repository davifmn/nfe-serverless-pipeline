output "bucket_name" {
  value = aws_s3_bucket.inbox.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.inbox.arn
}

output "queue_arn" {
  value = aws_sqs_queue.ingest.arn
}

output "queue_name" {
  value = aws_sqs_queue.ingest.name
}

output "dlq_name" {
  value = aws_sqs_queue.dlq.name
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.id
}

output "table_name" {
  value = aws_dynamodb_table.invoices.name
}

output "table_arn" {
  value = aws_dynamodb_table.invoices.arn
}

output "event_bus_name" {
  value = aws_cloudwatch_event_bus.events.name
}

output "event_bus_arn" {
  value = aws_cloudwatch_event_bus.events.arn
}
