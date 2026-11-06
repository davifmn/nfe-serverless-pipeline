output "invoke_url" {
  value = aws_api_gateway_stage.this.invoke_url
}

output "rest_api_name" {
  value = aws_api_gateway_rest_api.this.name
}

output "stage_name" {
  value = aws_api_gateway_stage.this.stage_name
}

output "api_key_ids" {
  description = "Read a key with: aws apigateway get-api-key --api-key <id> --include-value"
  value       = { for name, key in aws_api_gateway_api_key.clients : name => key.id }
}
