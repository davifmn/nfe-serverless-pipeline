variable "name" {
  description = "Resource name prefix, e.g. nfe-dev."
  type        = string
}

variable "account_id" {
  description = "AWS account ID, used to scope the queue policy to this account's bucket."
  type        = string
}

variable "kms_key_arn" {
  description = "Customer managed key used by S3, SQS and DynamoDB."
  type        = string
}

variable "consumer_timeout_seconds" {
  description = "Timeout of the Lambda that consumes the queue."
  type        = number
}

variable "max_receive_count" {
  description = "Deliveries before a message goes to the dead-letter queue."
  type        = number
  default     = 5
}

variable "retention_days" {
  description = "Days to keep invoice XML (legal minimum is about 5 years plus the fiscal year)."
  type        = number
  default     = 2190
  validation {
    condition     = var.retention_days >= 1826
    error_message = "NF-e XML must be kept for at least 5 years (1826 days)."
  }
}

variable "event_archive_days" {
  type    = number
  default = 30
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "force_destroy" {
  description = "Allow destroying the bucket with objects inside (dev only)."
  type        = bool
  default     = false
}
