output "inbox_bucket" {
  description = "Upload NF-e XML to s3://<bucket>/incoming/"
  value       = module.ingestion.bucket_name
}

output "api_url" {
  value = module.api.invoke_url
}

output "api_key_ids" {
  value = module.api.api_key_ids
}

output "table_name" {
  value = module.ingestion.table_name
}

output "dlq_url" {
  value = module.ingestion.dlq_url
}

output "dashboard" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${module.monitoring.dashboard_name}"
}
