#  Validata — Terraform Input Variables

variable "snowflake_account" {
  description = "Snowflake account identifier (e.g. ue74066.ap-southeast-7.aws)"
  type        = string
  sensitive   = true
}

variable "snowflake_username" {
  description = "Snowflake admin username used for provisioning"
  type        = string
  sensitive   = true
}

variable "snowflake_password" {
  description = "Snowflake admin password"
  type        = string
  sensitive   = true
}

variable "database_name" {
  description = "Snowflake database name for Validata"
  type        = string
  default     = "ValiData_DB"
}

variable "warehouse_name" {
  description = "Snowflake virtual warehouse name"
  type        = string
  default     = "COMPUTE_WH"
}

variable "service_user_name" {
  description = "Pipeline service account username"
  type        = string
  default     = "VALIDATA_SVC_USER"
}

variable "service_user_password" {
  description = "Pipeline service account password"
  type        = string
  sensitive   = true
}

# =============================================================
#  AWS Variables
# =============================================================

variable "aws_region" {
  description = "AWS region to deploy S3 and Glue resources"
  type        = string
  default     = "ap-southeast-1" # Singapore — closest to ap-southeast-7 Snowflake
}

variable "aws_access_key_id" {
  description = "AWS access key ID for the pipeline IAM user"
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS secret access key for the pipeline IAM user"
  type        = string
  sensitive   = true
}

variable "s3_bucket_name" {
  description = "Globally unique S3 bucket name for the Validata data lake"
  type        = string
  default     = "validata-datalake"
}

variable "environment" {
  description = "Deployment environment tag (dev | staging | prod)"
  type        = string
  default     = "dev"
}

variable "gemini_api_key" {
  description = "Google Gemini API key passed as a Glue job argument"
  type        = string
  sensitive   = true
}
