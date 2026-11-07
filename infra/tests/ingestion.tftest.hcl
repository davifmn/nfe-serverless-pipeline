# Storage, queue and table settings of the ingestion module.

mock_provider "aws" {
  source = "./tests/mocks"
}

variables {
  name                     = "nfe-test"
  account_id               = "123456789012"
  kms_key_arn              = "arn:aws:kms:sa-east-1:123456789012:key/test"
  consumer_timeout_seconds = 60
}

run "bucket_is_private_encrypted_and_tls_only" {
  command = apply

  module {
    source = "./modules/ingestion"
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.inbox.block_public_acls,
      aws_s3_bucket_public_access_block.inbox.block_public_policy,
      aws_s3_bucket_public_access_block.inbox.ignore_public_acls,
      aws_s3_bucket_public_access_block.inbox.restrict_public_buckets,
    ])
    error_message = "All public access must be blocked."
  }

  assert {
    condition = anytrue([
      for r in aws_s3_bucket_server_side_encryption_configuration.inbox.rule :
      anytrue([for d in r.apply_server_side_encryption_by_default : d.sse_algorithm == "aws:kms" && d.kms_master_key_id == var.kms_key_arn])
    ])
    error_message = "Objects must be encrypted with the customer managed key."
  }

  assert {
    condition     = jsondecode(aws_s3_bucket_policy.inbox.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Requests without TLS must be denied."
  }

  assert {
    condition     = one(aws_s3_bucket_versioning.inbox.versioning_configuration).status == "Enabled"
    error_message = "Versioning protects invoices from accidental overwrites."
  }
}

run "invoices_are_kept_for_the_legal_period" {
  command = apply

  module {
    source = "./modules/ingestion"
  }

  assert {
    condition = anytrue([
      for r in aws_s3_bucket_lifecycle_configuration.inbox.rule :
      anytrue([for e in r.expiration : e.days >= 1826]) if r.id == "archive-invoices"
    ])
    error_message = "Invoice XML must be retained for at least 5 years."
  }
}

run "retention_below_the_legal_minimum_is_rejected" {
  command = plan

  module {
    source = "./modules/ingestion"
  }

  variables {
    retention_days = 365
  }

  expect_failures = [var.retention_days]
}

run "queue_has_dlq_and_safe_visibility_timeout" {
  command = apply

  module {
    source = "./modules/ingestion"
  }

  assert {
    condition     = jsondecode(aws_sqs_queue.ingest.redrive_policy).maxReceiveCount == 5
    error_message = "Messages must go to the DLQ after 5 failed deliveries."
  }

  assert {
    condition     = aws_sqs_queue.ingest.visibility_timeout_seconds == 6 * var.consumer_timeout_seconds
    error_message = "Visibility timeout must be 6x the consumer timeout."
  }

  assert {
    condition = anytrue([
      for q in aws_s3_bucket_notification.inbox.queue : q.filter_prefix == "incoming/" && q.filter_suffix == ".xml"
    ])
    error_message = "Only .xml files under incoming/ trigger ingestion."
  }

  assert {
    condition     = jsondecode(aws_sqs_queue_policy.ingest.policy).Statement[0].Condition.ArnEquals["aws:SourceArn"] == aws_s3_bucket.inbox.arn
    error_message = "Only the inbox bucket may send to the queue."
  }
}

run "table_matches_the_application_access_patterns" {
  command = apply

  module {
    source = "./modules/ingestion"
  }

  assert {
    condition     = aws_dynamodb_table.invoices.hash_key == "PK" && aws_dynamodb_table.invoices.range_key == "SK"
    error_message = "Keys must match src/nfe_pipeline/repository.py."
  }

  assert {
    condition = anytrue([
      for g in aws_dynamodb_table.invoices.global_secondary_index :
      g.name == "GSI1" && contains([for k in g.key_schema : "${k.key_type}:${k.attribute_name}"], "HASH:GSI1PK") && contains([for k in g.key_schema : "${k.key_type}:${k.attribute_name}"], "RANGE:GSI1SK")
    ])
    error_message = "GSI1 (issuer + date) is required by the issuer query."
  }

  assert {
    condition     = one(aws_dynamodb_table.invoices.point_in_time_recovery).enabled
    error_message = "Point-in-time recovery must be on."
  }
}
