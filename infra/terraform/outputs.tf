# =============================================================
#  Validata — Terraform Outputs
#  These values display after `terraform apply` completes.
#  Copy these into your backend/.env file.
# =============================================================

output "snowflake_database" {
  description = "Snowflake database name"
  value       = snowflake_database.validata.name
}

output "snowflake_warehouse" {
  description = "Snowflake warehouse name"
  value       = snowflake_warehouse.compute.name
}

output "snowflake_curated_schema" {
  description = "Curated schema name"
  value       = snowflake_schema.curated.name
}

output "service_user" {
  description = "Pipeline service account username"
  value       = snowflake_user.service_user.name
}

output "pipeline_role" {
  description = "Role assigned to the pipeline service user"
  value       = snowflake_account_role.pipeline_role.name
}

output "env_template" {
  description = "Copy this block into your backend/.env file"
  sensitive   = true
  value       = <<-EOT
    # === Paste into backend/.env ===
    SF_ACCOUNT=${var.snowflake_account}
    SF_USER=${var.service_user_name}
    SF_PASSWORD=<your_service_user_password>
    SF_DATABASE=${var.database_name}
    SF_WAREHOUSE=${var.warehouse_name}
    SF_SCHEMA_CURATED=CURATED_SCHEMA
    SF_SCHEMA_STAGING=STAGING_SCHEMA

    # AWS
    AWS_REGION=${var.aws_region}
    S3_BUCKET=s3://${var.s3_bucket_name}
  EOT
}

# =============================================================
#  AWS Outputs
# =============================================================

output "s3_bucket_name" {
  description = "S3 data lake bucket name"
  value       = aws_s3_bucket.datalake.bucket
}

output "s3_bucket_arn" {
  description = "S3 data lake bucket ARN"
  value       = aws_s3_bucket.datalake.arn
}

output "glue_role_arn" {
  description = "IAM role ARN assigned to all Glue jobs"
  value       = aws_iam_role.glue_execution.arn
}

output "glue_workflow_name" {
  description = "Glue Workflow name — trigger this to run the full pipeline"
  value       = aws_glue_workflow.pipeline.name
}

output "glue_jobs" {
  description = "All provisioned Glue job names in execution order"
  value = [
    aws_glue_job.extract_raw.name,
    aws_glue_job.clean_legacy.name,
    aws_glue_job.clean_new.name,
    aws_glue_job.validation_engine.name,
    aws_glue_job.load_to_snowflake.name,
    aws_glue_job.ai_anomaly.name,
  ]
}
