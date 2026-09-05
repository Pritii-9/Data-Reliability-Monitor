variable "snowflake_account" {
  description = "Snowflake account identifier"
  type        = string
}

variable "snowflake_username" {
  description = "Snowflake admin username"
  type        = string
}

variable "snowflake_password" {
  description = "Snowflake admin password"
  type        = string
  sensitive   = true
}

variable "database_name" {
  description = "Primary Snowflake database name"
  type        = string
  default     = "ValiData_DB"
}

variable "warehouse_name" {
  description = "Snowflake warehouse name"
  type        = string
  default     = "COMPUTE_WH"
}

variable "service_user_name" {
  description = "Dedicated service account username"
  type        = string
  default     = "VALIDATA_SVC_USER"
}

variable "service_user_password" {
  description = "Service account password"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region for S3 data lake storage"
  type        = string
  default     = "ap-southeast-1"
}

variable "aws_access_key_id" {
  description = "AWS access key"
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS secret access key"
  type        = string
  sensitive   = true
}

variable "s3_bucket_name" {
  description = "S3 bucket for staging raw transaction data"
  type        = string
  default     = "validata-datalake"
}

variable "environment" {
  description = "Target deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "gemini_api_key" {
  description = "Google Gemini API Key for AI anomaly explanations"
  type        = string
  sensitive   = true
}
