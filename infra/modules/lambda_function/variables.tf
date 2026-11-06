variable "name" {
  description = "Function name (also used for the role and log group)."
  type        = string
}

variable "description" {
  type    = string
  default = ""
}

variable "handler" {
  description = "Python handler, e.g. nfe_pipeline.handlers.ingest.handler."
  type        = string
}

variable "source_dir" {
  description = "Directory zipped as the deployment package."
  type        = string
}

variable "environment" {
  description = "Environment variables for the function."
  type        = map(string)
  default     = {}
}

variable "policy_statements" {
  description = "Extra IAM statements (objects with Sid, Effect, Action, Resource)."
  type        = any
  default     = []
}

variable "timeout_seconds" {
  type    = number
  default = 30
}

variable "memory_mb" {
  type    = number
  default = 256
}

variable "reserved_concurrency" {
  description = "Reserved concurrency; null leaves the function in the unreserved pool."
  type        = number
  default     = null
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "kms_key_arn" {
  description = "Customer managed key for environment variables and logs."
  type        = string
}

variable "alarm_topic_arn" {
  description = "SNS topic notified by the alarms (null: alarms without notification)."
  type        = string
  default     = null
}
