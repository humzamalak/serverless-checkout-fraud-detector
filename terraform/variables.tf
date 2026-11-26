variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "checkout-fraud"
}

variable "region" {
  description = "AWS region. Bedrock must offer the chosen model here."
  type        = string
  default     = "us-east-1"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID or cross-region inference profile ID. Check that model access is granted in the Bedrock console."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_enabled" {
  description = "Set to false to run with rules only (no Bedrock cost)."
  type        = bool
  default     = true
}

variable "approve_below" {
  description = "Rule score below this is approved without calling Bedrock."
  type        = number
  default     = 20
}

variable "decline_at" {
  description = "Rule score at or above this is declined without calling Bedrock."
  type        = number
  default     = 80
}

variable "api_authorization" {
  description = "AWS_IAM (callers sign requests with SigV4) or NONE (open, for a quick demo only)."
  type        = string
  default     = "AWS_IAM"

  validation {
    condition     = contains(["AWS_IAM", "NONE"], var.api_authorization)
    error_message = "api_authorization must be AWS_IAM or NONE."
  }
}

variable "throttle_rate_limit" {
  description = "Steady-state requests per second for the API stage."
  type        = number
  default     = 20
}

variable "throttle_burst_limit" {
  description = "Burst requests for the API stage."
  type        = number
  default     = 40
}

variable "alarm_email" {
  description = "E-mail for CloudWatch alarms. Leave empty to skip."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  type    = number
  default = 30
}
