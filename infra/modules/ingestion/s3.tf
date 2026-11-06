# Inbox bucket: suppliers' NF-e XML land under incoming/; invalid files are moved to rejected/.

resource "aws_s3_bucket" "inbox" {
  bucket_prefix = "${var.name}-inbox-"
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_ownership_controls" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  rule {
    object_ownership = "BucketOwnerEnforced" # ACLs disabled
  }
}

resource "aws_s3_bucket_public_access_block" "inbox" {
  bucket                  = aws_s3_bucket.inbox.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true # one KMS call per bucket key instead of per object
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "inbox" {
  bucket = aws_s3_bucket.inbox.id

  # NF-e XML must be kept for at least 5 years after the fiscal year (tax law).
  # Move to cheaper storage after 90 days, expire after var.retention_days.
  rule {
    id     = "archive-invoices"
    status = "Enabled"
    filter {
      prefix = "incoming/"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
    expiration {
      days = var.retention_days
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "expire-rejected"
    status = "Enabled"
    filter {
      prefix = "rejected/"
    }
    expiration {
      days = 180
    }
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 2
    }
  }
}

resource "aws_s3_bucket_policy" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.inbox.arn, "${aws_s3_bucket.inbox.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.inbox]
}

resource "aws_s3_bucket_notification" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  queue {
    queue_arn     = aws_sqs_queue.ingest.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "incoming/"
    filter_suffix = ".xml"
  }
  depends_on = [aws_sqs_queue_policy.ingest]
}
