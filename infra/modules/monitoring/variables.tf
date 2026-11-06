variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "alarm_email" {
  description = "Address subscribed to alarms (empty: no subscription)."
  type        = string
  default     = ""
}

variable "queue_name" {
  type = string
}

variable "dlq_name" {
  type = string
}

variable "max_message_age_seconds" {
  type    = number
  default = 900
}

variable "api_name" {
  type = string
}

variable "api_stage" {
  type = string
}

variable "function_names" {
  type = list(string)
}
