variable "name" {
  type = string
}

variable "stage_name" {
  type    = string
  default = "v1"
}

variable "lambda_invoke_arn" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "client_names" {
  description = "One API key is created per client name."
  type        = list(string)
  default     = ["default"]
}

variable "rate_limit" {
  description = "Steady-state requests per second."
  type        = number
  default     = 20
}

variable "burst_limit" {
  type    = number
  default = 40
}

variable "monthly_quota" {
  type    = number
  default = 100000
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "kms_key_arn" {
  type = string
}
