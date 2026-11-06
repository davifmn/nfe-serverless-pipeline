variable "environment" {
  description = "Short environment name, used in every resource name."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,11}$", var.environment))
    error_message = "Use 2-12 lowercase letters, digits or hyphens."
  }
}

variable "region" {
  type    = string
  default = "sa-east-1"
}

variable "alarm_email" {
  type    = string
  default = ""
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "ingest_max_concurrency" {
  description = "Upper bound of concurrent ingest invocations (protects downstream systems)."
  type        = number
  default     = 5
}

variable "api_clients" {
  description = "One API key per client."
  type        = list(string)
  default     = ["default"]
}

variable "api_rate_limit" {
  type    = number
  default = 20
}

variable "production" {
  description = "Turns on deletion protection and turns off force_destroy."
  type        = bool
  default     = false
}
