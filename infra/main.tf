data "aws_caller_identity" "current" {}

locals {
  name       = "nfe-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id
  source_dir = "${path.root}/../src"

  ingest_timeout = 60

  function_names = {
    ingest = "${local.name}-ingest"
    api    = "${local.name}-api"
  }
  api_name   = "${local.name}-api"
  api_stage  = "v1"
  log_region = "logs.${var.region}.amazonaws.com"
}

# --- Encryption: one customer managed key for every data store ------------------------

resource "aws_kms_key" "main" {
  description             = "${local.name}: invoices at rest (S3, SQS, DynamoDB, logs, SNS)"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Delegate to IAM: roles get key access through their own policies.
        Sid       = "AccountAdministration"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        # S3 must encrypt the event notifications it sends to the encrypted queue.
        Sid       = "S3Notifications"
        Effect    = "Allow"
        Principal = { Service = "s3.amazonaws.com" }
        Action    = ["kms:GenerateDataKey", "kms:Decrypt"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
      },
      {
        # CloudWatch alarms publish to the encrypted SNS topic.
        Sid       = "CloudWatchAlarms"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = ["kms:GenerateDataKey*", "kms:Decrypt"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
      },
      {
        Sid       = "CloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = local.log_region }
        Action    = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
        Resource  = "*"
        Condition = {
          ArnLike = { "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.region}:${local.account_id}:*" }
        }
      },
    ]
  })
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.main.key_id
}

# --- Data plane --------------------------------------------------------------------------

module "ingestion" {
  source                   = "./modules/ingestion"
  name                     = local.name
  account_id               = local.account_id
  kms_key_arn              = aws_kms_key.main.arn
  consumer_timeout_seconds = local.ingest_timeout
  deletion_protection      = var.production
  force_destroy            = !var.production
}

module "monitoring" {
  source         = "./modules/monitoring"
  name           = local.name
  region         = var.region
  kms_key_arn    = aws_kms_key.main.arn
  alarm_email    = var.alarm_email
  queue_name     = module.ingestion.queue_name
  dlq_name       = module.ingestion.dlq_name
  api_name       = local.api_name
  api_stage      = local.api_stage
  function_names = values(local.function_names)
}

locals {
  kms_use = {
    Sid      = "UseDataKey"
    Effect   = "Allow"
    Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
    Resource = aws_kms_key.main.arn
  }
}

module "ingest_function" {
  source          = "./modules/lambda_function"
  name            = local.function_names.ingest
  description     = "Validates NF-e XML from the inbox and stores it in DynamoDB"
  handler         = "nfe_pipeline.handlers.ingest.handler"
  source_dir      = local.source_dir
  timeout_seconds = local.ingest_timeout
  memory_mb       = 512
  kms_key_arn     = aws_kms_key.main.arn
  alarm_topic_arn = module.monitoring.alarm_topic_arn

  log_retention_days = var.log_retention_days
  environment = {
    TABLE_NAME     = module.ingestion.table_name
    BUCKET_NAME    = module.ingestion.bucket_name
    EVENT_BUS_NAME = module.ingestion.event_bus_name
  }

  policy_statements = [
    {
      Sid      = "ConsumeIngestQueue"
      Effect   = "Allow"
      Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
      Resource = module.ingestion.queue_arn
    },
    {
      Sid      = "ReadIncoming"
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:DeleteObject"]
      Resource = "${module.ingestion.bucket_arn}/incoming/*"
    },
    {
      Sid      = "WriteRejected"
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${module.ingestion.bucket_arn}/rejected/*"
    },
    {
      Sid      = "StoreInvoices"
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem"]
      Resource = module.ingestion.table_arn
    },
    {
      Sid      = "PublishEvents"
      Effect   = "Allow"
      Action   = ["events:PutEvents"]
      Resource = module.ingestion.event_bus_arn
    },
    local.kms_use,
  ]
}

resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn                   = module.ingestion.queue_arn
  function_name                      = module.ingest_function.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  # Only failed messages of a batch are retried (the handler reports them individually).
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.ingest_max_concurrency
  }
}

module "api_function" {
  source          = "./modules/lambda_function"
  name            = local.function_names.api
  description     = "Read-only NF-e query API"
  handler         = "nfe_pipeline.handlers.api.handler"
  source_dir      = local.source_dir
  timeout_seconds = 10
  memory_mb       = 256
  kms_key_arn     = aws_kms_key.main.arn
  alarm_topic_arn = module.monitoring.alarm_topic_arn

  log_retention_days = var.log_retention_days
  environment = {
    TABLE_NAME  = module.ingestion.table_name
    BUCKET_NAME = module.ingestion.bucket_name
  }

  policy_statements = [
    {
      Sid      = "ReadInvoices"
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:Query"]
      Resource = [module.ingestion.table_arn, "${module.ingestion.table_arn}/index/GSI1"]
    },
    local.kms_use,
  ]
}

module "api" {
  source               = "./modules/api"
  name                 = local.api_name
  stage_name           = local.api_stage
  lambda_invoke_arn    = module.api_function.invoke_arn
  lambda_function_name = module.api_function.function_name
  client_names         = var.api_clients
  rate_limit           = var.api_rate_limit
  burst_limit          = var.api_rate_limit * 2
  log_retention_days   = var.log_retention_days
  kms_key_arn          = aws_kms_key.main.arn
}
