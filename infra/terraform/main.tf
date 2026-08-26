# =============================================================
#  Validata — Infrastructure as Code (Terraform)
#  Manages: Snowflake Database, Schema, Warehouse, Tables,
#           Service User, Role Grants
#
#  Cost Management:
#    - Warehouse auto-suspends after 60s of inactivity
#    - Full teardown: `terraform destroy` (< 60 seconds)
#    - Compatible with Snowflake 30-day free trial
# =============================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 0.100"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# --- Providers ----------------------------------------------------------

provider "snowflake" {
  account  = var.snowflake_account
  username = var.snowflake_username
  password = var.snowflake_password
  role     = "SYSADMIN"
}

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key_id
  secret_key = var.aws_secret_access_key
}

# --- Database -----------------------------------------------------------

resource "snowflake_database" "validata" {
  name    = var.database_name
  comment = "Validata Data Validation Engine — curated warehouse"
}

# --- Schemas ------------------------------------------------------------

resource "snowflake_schema" "curated" {
  database = snowflake_database.validata.name
  name     = "CURATED_SCHEMA"
  comment  = "Holds final reconciled and AI-enriched validation results"
}

resource "snowflake_schema" "staging" {
  database = snowflake_database.validata.name
  name     = "STAGING_SCHEMA"
  comment  = "Intermediate staging zone for raw ingested data"
}

# --- Warehouse (auto-suspend to minimize cost) --------------------------

resource "snowflake_warehouse" "compute" {
  name                = var.warehouse_name
  warehouse_size      = "X-SMALL" # Smallest available = cheapest
  auto_suspend        = 60        # Suspends after 60s idle — key cost control
  auto_resume         = true
  initially_suspended = true # Starts suspended by default
  comment             = "Validata pipeline compute. Auto-suspends after 60s."
}

# --- Core Tables --------------------------------------------------------

resource "snowflake_table" "validation_results" {
  database = snowflake_database.validata.name
  schema   = snowflake_schema.curated.name
  name     = "VALIDATION_RESULTS"
  comment  = "Transaction-level reconciliation output with AI anomaly explanations"

  column {
    name     = "TXN_ID"
    type     = "VARCHAR(16777216)"
    nullable = false
    comment  = "Unique transaction identifier (primary key)"
  }
  column {
    name    = "CUSTOMER_ID"
    type    = "VARCHAR(16777216)"
    comment = "Customer identifier"
  }
  column {
    name    = "TXN_DATE"
    type    = "VARCHAR(16777216)"
    comment = "Transaction date (YYYY-MM-DD)"
  }
  column {
    name    = "CURRENCY"
    type    = "VARCHAR(16777216)"
    comment = "ISO 4217 currency code"
  }
  column {
    name    = "REGION"
    type    = "VARCHAR(16777216)"
    comment = "Geographic region"
  }
  column {
    name    = "CHANNEL"
    type    = "VARCHAR(16777216)"
    comment = "Transaction channel (WEB, MOBILE, API, etc.)"
  }
  column {
    name    = "PRODUCT_TYPE"
    type    = "VARCHAR(16777216)"
    comment = "Product category"
  }
  column {
    name    = "LEGACY_AMOUNT"
    type    = "VARCHAR(16777216)"
    comment = "Amount from legacy ledger system"
  }
  column {
    name    = "NEW_SYSTEM_AMOUNT"
    type    = "VARCHAR(16777216)"
    comment = "Amount from new system"
  }
  column {
    name    = "AMOUNT_DIFF"
    type    = "FLOAT"
    comment = "Absolute monetary difference"
  }
  column {
    name    = "AMOUNT_DIFF_PCT"
    type    = "FLOAT"
    comment = "Percentage difference between legacy and new amounts"
  }
  column {
    name    = "LEGACY_STATUS"
    type    = "VARCHAR(16777216)"
    comment = "Transaction status in legacy system"
  }
  column {
    name    = "NEW_SYSTEM_STATUS"
    type    = "VARCHAR(16777216)"
    comment = "Transaction status in new system"
  }
  column {
    name     = "VALIDATION_STATUS"
    type     = "VARCHAR(16777216)"
    nullable = false
    comment  = "Reconciliation result: MATCH | AMOUNT_MISMATCH | STATUS_MISMATCH | MISSING | PHANTOM"
  }
  column {
    name     = "VALIDATED_AT"
    type     = "TIMESTAMP_NTZ(9)"
    nullable = false
    comment  = "UTC timestamp of when this record was validated"
  }
  column {
    name    = "AI_EXPLANATION"
    type    = "VARCHAR(16777216)"
    comment = "Gemini AI root cause analysis for anomalies"
  }
  column {
    name    = "AI_EXPLAINED_AT"
    type    = "TIMESTAMP_NTZ(9)"
    comment = "UTC timestamp of AI enrichment"
  }
  column {
    name     = "LOADED_AT"
    type     = "TIMESTAMP_NTZ(9)"
    nullable = false
    comment  = "UTC timestamp of Snowflake ingestion"
  }
}

resource "snowflake_table" "audit_log" {
  database = snowflake_database.validata.name
  schema   = snowflake_schema.curated.name
  name     = "AUDIT_LOG"
  comment  = "Pipeline run audit trail — one row per pipeline execution"

  column {
    name     = "RUN_ID"
    type     = "VARCHAR(16777216)"
    nullable = false
    comment  = "Unique run identifier (UUID)"
  }
  column {
    name     = "RUN_TIMESTAMP"
    type     = "TIMESTAMP_NTZ(9)"
    nullable = false
    comment  = "UTC start time of the pipeline run"
  }
  column {
    name    = "LEGACY_FILE"
    type    = "VARCHAR(16777216)"
    comment = "Source legacy CSV file path"
  }
  column {
    name    = "NEW_FILE"
    type    = "VARCHAR(16777216)"
    comment = "Source new system CSV file path"
  }
  column {
    name    = "TOTAL_ROWS"
    type    = "NUMBER(18,0)"
    comment = "Total transactions processed"
  }
  column {
    name    = "MATCH_COUNT"
    type    = "NUMBER(18,0)"
    comment = "Transactions classified as MATCH"
  }
  column {
    name    = "MISMATCH_COUNT"
    type    = "NUMBER(18,0)"
    comment = "Total anomaly count (all non-MATCH rows)"
  }
  column {
    name    = "STATUS"
    type    = "VARCHAR(16777216)"
    comment = "Pipeline run status: SUCCESS | FAILED"
  }
  column {
    name    = "ERROR_MESSAGE"
    type    = "VARCHAR(16777216)"
    comment = "Error detail if STATUS = FAILED"
  }
  column {
    name    = "EXECUTION_ENVIRONMENT"
    type    = "VARCHAR(16777216)"
    comment = "Where this ran (e.g. AWS_GLUE_PROD vs LOCAL_SIMULATOR)"
  }
  column {
    name    = "PIPELINE_VERSION"
    type    = "VARCHAR(16777216)"
    comment = "Git commit hash or version tag of the ETL scripts used"
  }
}

# --- Service User & Role -----------------------------------------------

resource "snowflake_account_role" "pipeline_role" {
  name    = "VALIDATA_PIPELINE_ROLE"
  comment = "Least-privilege role for the Validata pipeline service account"
}

resource "snowflake_user" "service_user" {
  name                 = var.service_user_name
  password             = var.service_user_password
  default_role         = snowflake_account_role.pipeline_role.name
  comment              = "Validata pipeline service account — non-human user"
  must_change_password = false
}

# --- Privilege Grants --------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "warehouse_usage" {
  account_role_name = snowflake_account_role.pipeline_role.name
  privileges        = ["USAGE", "OPERATE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.compute.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "database_usage" {
  account_role_name = snowflake_account_role.pipeline_role.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.validata.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "schema_usage" {
  account_role_name = snowflake_account_role.pipeline_role.name
  privileges        = ["USAGE", "CREATE TABLE"]
  on_schema {
    schema_name = "\"${var.database_name}\".\"CURATED_SCHEMA\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "table_dml" {
  account_role_name = snowflake_account_role.pipeline_role.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "TRUNCATE"]
  on_schema_object {
    object_type = "TABLE"
    object_name = "\"${var.database_name}\".\"CURATED_SCHEMA\".\"VALIDATION_RESULTS\""
  }
}

resource "snowflake_grant_account_role" "assign_role_to_user" {
  role_name = snowflake_account_role.pipeline_role.name
  user_name = snowflake_user.service_user.name
}
