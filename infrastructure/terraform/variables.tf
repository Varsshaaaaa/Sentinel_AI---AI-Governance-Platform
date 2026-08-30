variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "sentinelai"
}

variable "storage_backend" {
  description = "Storage backend (memory or dynamodb)"
  type        = string
  default     = "dynamodb"
}

variable "waf_websocket_stage" {
  description = "Stage name for WebSocket API"
  type        = string
  default     = "prod"
}

variable "cerebras_api_key" {
  description = "Cerebras API key for Policy Copilot (LiteLLM)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "litellm_model" {
  description = "LiteLLM model id (e.g. cerebras/llama-3.3-70b)"
  type        = string
  default     = "cerebras/gpt-oss-120b"
}

locals {
  prefix = "${var.project_name}-${var.environment}"
  dynamodb_table_prefix = local.prefix
  eventbridge_bus_name = "${local.prefix}-governance"
}
