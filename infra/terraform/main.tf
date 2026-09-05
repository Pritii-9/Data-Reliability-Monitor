terraform {
  required_version = ">= 1.5.0"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 0.87.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ─── AWS Provider ────────────────────────────────────────────
provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key_id
  secret_key = var.aws_secret_access_key
}

# ─── Snowflake Provider ───────────────────────────────────────
provider "snowflake" {
  account  = var.snowflake_account
  username = var.snowflake_username
  password = var.snowflake_password
  role     = "SYSADMIN"
}

# ═════════════════════════════════════════════════════════════
#  AWS — S3 Data Lake
# ═════════════════════════════════════════════════════════════

resource "aws_s3_bucket" "validata_datalake" {
  bucket        = "${var.s3_bucket_name}-${var.environment}"
  force_destroy = false

  tags = {
    Name        = "Validata Data Lake"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket_versioning" "validata_datalake_versioning" {
  bucket = aws_s3_bucket.validata_datalake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "validata_datalake_crypto" {
  bucket = aws_s3_bucket.validata_datalake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all public access to the data lake bucket
resource "aws_s3_bucket_public_access_block" "validata_datalake_public_block" {
  bucket                  = aws_s3_bucket.validata_datalake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ═════════════════════════════════════════════════════════════
#  Snowflake — Database & Warehouse
# ═════════════════════════════════════════════════════════════

resource "snowflake_database" "validata_db" {
  name    = var.database_name
  comment = "Primary Validata data validation database"
}

resource "snowflake_warehouse" "validata_wh" {
  name           = var.warehouse_name
  warehouse_size = "X-SMALL"
  auto_suspend   = 60
  auto_resume    = true
  comment        = "Validata compute warehouse — auto-suspends after 60s idle"
}

# ─── Schemas ─────────────────────────────────────────────────

resource "snowflake_schema" "raw_schema" {
  database = snowflake_database.validata_db.name
  name     = "RAW_SCHEMA"
  comment  = "Landing zone for raw transaction data ingested from S3"
}

resource "snowflake_schema" "curated_schema" {
  database = snowflake_database.validata_db.name
  name     = "CURATED_SCHEMA"
  comment  = "Validated and reconciled results written by the Glue ETL job"
}

# ─── Service User ─────────────────────────────────────────────

resource "snowflake_user" "validata_svc_user" {
  name         = var.service_user_name
  password     = var.service_user_password
  default_role = "SYSADMIN"
  comment      = "Dedicated service account used by the Glue PySpark ETL job"
  must_change_password = false
}

# ─── Role Grants ─────────────────────────────────────────────

resource "snowflake_grant_privileges_to_account_role" "svc_db_grant" {
  account_role_name = snowflake_user.validata_svc_user.default_role
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.validata_db.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "svc_wh_grant" {
  account_role_name = snowflake_user.validata_svc_user.default_role
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.validata_wh.name
  }
}

