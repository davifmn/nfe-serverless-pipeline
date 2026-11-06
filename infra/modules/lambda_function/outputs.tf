output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "arn" {
  value = aws_lambda_function.this.arn
}

output "invoke_arn" {
  value = aws_lambda_function.this.invoke_arn
}

output "role_name" {
  value = aws_iam_role.this.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.this.name
}

output "policy" {
  description = "IAM policy document of the role (JSON), exposed for tests and audits."
  value       = aws_iam_role_policy.this.policy
}
