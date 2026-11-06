# Values returned by the mocked AWS provider. Nothing here talks to AWS.

mock_data "aws_caller_identity" {
  defaults = {
    account_id = "123456789012"
  }
}

mock_resource "aws_kms_key" {
  defaults = {
    arn    = "arn:aws:kms:sa-east-1:123456789012:key/00000000-0000-0000-0000-000000000000"
    key_id = "00000000-0000-0000-0000-000000000000"
  }
}

mock_resource "aws_iam_role" {
  defaults = {
    arn = "arn:aws:iam::123456789012:role/mock"
  }
}

mock_resource "aws_lambda_function" {
  defaults = {
    arn        = "arn:aws:lambda:sa-east-1:123456789012:function:mock"
    invoke_arn = "arn:aws:apigateway:sa-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:sa-east-1:123456789012:function:mock/invocations"
  }
}

mock_resource "aws_api_gateway_rest_api" {
  defaults = {
    id               = "abc123"
    root_resource_id = "root123"
    execution_arn    = "arn:aws:execute-api:sa-east-1:123456789012:abc123"
  }
}

mock_resource "aws_s3_bucket" {
  defaults = {
    arn    = "arn:aws:s3:::nfe-test-inbox-mock"
    bucket = "nfe-test-inbox-mock"
  }
}

mock_resource "aws_sqs_queue" {
  defaults = {
    arn = "arn:aws:sqs:sa-east-1:123456789012:mock"
    id  = "https://sqs.sa-east-1.amazonaws.com/123456789012/mock"
  }
}

mock_resource "aws_dynamodb_table" {
  defaults = {
    arn = "arn:aws:dynamodb:sa-east-1:123456789012:table/mock"
  }
}

mock_resource "aws_cloudwatch_log_group" {
  defaults = {
    arn = "arn:aws:logs:sa-east-1:123456789012:log-group:mock"
  }
}

mock_resource "aws_sns_topic" {
  defaults = {
    arn = "arn:aws:sns:sa-east-1:123456789012:mock"
  }
}

mock_resource "aws_cloudwatch_event_bus" {
  defaults = {
    arn = "arn:aws:events:sa-east-1:123456789012:event-bus/mock"
  }
}
