# =============================================================
#  Validata — AWS Infrastructure (S3 + Glue)
#
#  Resources:
#    S3  : validata-datalake bucket with raw/staging/curated/logs
#    IAM : Glue execution role + least-privilege S3/Snowflake policy
#    Glue: One job per notebook (01–06) + Workflow + Triggers
#
#  Cost Management:
#    - S3 Standard: ~$0.023/GB/month  (free tier: 5GB first 12 months)
#    - Glue DPU:    $0.44/DPU-hour    (only charged when job runs)
#    - `terraform destroy` removes ALL resources instantly
# =============================================================

# --- S3 Bucket ----------------------------------------------------------

resource "aws_s3_bucket" "datalake" {
  bucket        = var.s3_bucket_name
  force_destroy = true # Allows `terraform destroy` to wipe bucket contents
  tags = {
    Project     = "Validata"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Block all public access — internal pipeline only
resource "aws_s3_bucket_public_access_block" "datalake" {
  bucket                  = aws_s3_bucket.datalake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning for accidental-overwrite recovery
resource "aws_s3_bucket_versioning" "datalake" {
  bucket = aws_s3_bucket.datalake.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Lifecycle rule: auto-delete raw staging files after 30 days (cost control)
resource "aws_s3_bucket_lifecycle_configuration" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  rule {
    id     = "expire-raw-after-30d"
    status = "Enabled"
    filter { prefix = "raw/" }
    expiration { days = 30 }
  }

  rule {
    id     = "expire-staging-after-14d"
    status = "Enabled"
    filter { prefix = "staging/" }
    expiration { days = 14 }
  }
}

# Folder structure via empty prefix objects
resource "aws_s3_object" "folders" {
  for_each = toset([
    "raw/legacy_system/",
    "raw/new_system/",
    "staging/validated/legacy_system/",
    "staging/validated/new_system/",
    "curated/validation_results/",
    "logs/",
    "scripts/",
  ])
  bucket  = aws_s3_bucket.datalake.id
  key     = each.value
  content = ""
}

# Upload Glue scripts to S3/scripts/ automatically
resource "aws_s3_object" "glue_scripts" {
  for_each = fileset("${path.module}/../../backend/notebooks", "*.py")
  bucket   = aws_s3_bucket.datalake.id
  key      = "scripts/${each.value}"
  source   = "${path.module}/../../backend/notebooks/${each.value}"
  etag     = filemd5("${path.module}/../../backend/notebooks/${each.value}")
}

# --- IAM Role for Glue --------------------------------------------------

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_execution" {
  name               = "validata-glue-execution-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
  tags = {
    Project   = "Validata"
    ManagedBy = "Terraform"
  }
}

# Attach AWS managed Glue Service policy
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Inline least-privilege policy for S3 bucket access
resource "aws_iam_role_policy" "glue_s3_access" {
  name = "validata-glue-s3-policy"
  role = aws_iam_role.glue_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3BucketAccess"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.datalake.arn,
          "${aws_s3_bucket.datalake.arn}/*"
        ]
      },
      {
        Sid      = "CloudWatchLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:/aws-glue/*"
      }
    ]
  })
}

# --- Glue Data Catalog Database -----------------------------------------

resource "aws_glue_catalog_database" "validata" {
  name        = "validata_catalog"
  description = "Glue Data Catalog for Validata pipeline tables"
}

# --- Glue Jobs (one per notebook) ---------------------------------------

locals {
  glue_default_args = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--S3_BUCKET"                        = "s3://${var.s3_bucket_name}"
    "--SF_ACCOUNT"                       = var.snowflake_account
    "--SF_USER"                          = var.service_user_name
    "--SF_PASSWORD"                      = var.service_user_password
    "--SF_DATABASE"                      = var.database_name
    "--SF_WAREHOUSE"                     = var.warehouse_name
    "--GEMINI_API_KEY"                   = var.gemini_api_key
  }
}

resource "aws_glue_job" "extract_raw" {
  name         = "validata-01-extract-raw-data"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  description  = "Notebook 01 — Ingest raw CSV from S3 landing zone"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket_name}/scripts/01_extract_raw_data.py"
    python_version  = "3"
  }

  default_arguments = merge(local.glue_default_args, {
    "--job-bookmark-option" = "job-bookmark-enable"
  })

  execution_property {
    max_concurrent_runs = 1
  }

  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Project = "Validata", ManagedBy = "Terraform" }
}

resource "aws_glue_job" "clean_legacy" {
  name         = "validata-02-clean-legacy"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  description  = "Notebook 02 — Clean and standardize legacy system data"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket_name}/scripts/02_clean_legacy_data.py"
    python_version  = "3"
  }

  default_arguments = local.glue_default_args
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Project = "Validata", ManagedBy = "Terraform" }
}

resource "aws_glue_job" "clean_new" {
  name         = "validata-03-clean-new-system"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  description  = "Notebook 03 — Clean and standardize new system data"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket_name}/scripts/03_clean_new_system_data.py"
    python_version  = "3"
  }

  default_arguments = local.glue_default_args
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Project = "Validata", ManagedBy = "Terraform" }
}

resource "aws_glue_job" "validation_engine" {
  name         = "validata-04-validation-engine"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  description  = "Notebook 04 — Full-outer-join reconciliation and mismatch classification"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket_name}/scripts/04_validation_engine.py"
    python_version  = "3"
  }

  default_arguments = local.glue_default_args
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Project = "Validata", ManagedBy = "Terraform" }
}

resource "aws_glue_job" "load_to_snowflake" {
  name         = "validata-05-load-to-snowflake"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  description  = "Notebook 05 — Bulk load curated results from S3 into Snowflake"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket_name}/scripts/05_load_to_snowflake.py"
    python_version  = "3"
  }

  default_arguments = local.glue_default_args
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Project = "Validata", ManagedBy = "Terraform" }
}

resource "aws_glue_job" "ai_anomaly" {
  name         = "validata-06-ai-anomaly-explanation"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  description  = "Notebook 06 — Gemini AI root-cause enrichment for anomalies"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket_name}/scripts/06_ai_anomaly_explanation.py"
    python_version  = "3"
  }

  default_arguments = local.glue_default_args
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Project = "Validata", ManagedBy = "Terraform" }
}

# --- Glue Workflow + Sequential Triggers --------------------------------

resource "aws_glue_workflow" "pipeline" {
  name        = "validata-full-pipeline"
  description = "Orchestrates all 6 Validata notebooks end-to-end"
  tags        = { Project = "Validata", ManagedBy = "Terraform" }
}

# Trigger 1 — Start workflow on demand (or schedule)
resource "aws_glue_trigger" "start" {
  name          = "validata-trigger-start"
  workflow_name = aws_glue_workflow.pipeline.name
  type          = "ON_DEMAND" # Change to SCHEDULED for cron automation

  actions {
    job_name = aws_glue_job.extract_raw.name
  }
}

# Trigger 2 — Run clean-legacy after extract completes
resource "aws_glue_trigger" "after_extract" {
  name          = "validata-trigger-after-extract"
  workflow_name = aws_glue_workflow.pipeline.name
  type          = "CONDITIONAL"

  predicate {
    conditions {
      job_name = aws_glue_job.extract_raw.name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.clean_legacy.name
  }
}

# Trigger 3 — Run clean-new after clean-legacy completes
resource "aws_glue_trigger" "after_clean_legacy" {
  name          = "validata-trigger-after-clean-legacy"
  workflow_name = aws_glue_workflow.pipeline.name
  type          = "CONDITIONAL"

  predicate {
    conditions {
      job_name = aws_glue_job.clean_legacy.name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.clean_new.name
  }
}

# Trigger 4 — Run validation engine after both clean jobs complete
resource "aws_glue_trigger" "after_clean_new" {
  name          = "validata-trigger-after-clean-new"
  workflow_name = aws_glue_workflow.pipeline.name
  type          = "CONDITIONAL"

  predicate {
    logical = "AND"
    conditions {
      job_name = aws_glue_job.clean_legacy.name
      state    = "SUCCEEDED"
    }
    conditions {
      job_name = aws_glue_job.clean_new.name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.validation_engine.name
  }
}

# Trigger 5 — Load to Snowflake after validation engine
resource "aws_glue_trigger" "after_validation" {
  name          = "validata-trigger-after-validation"
  workflow_name = aws_glue_workflow.pipeline.name
  type          = "CONDITIONAL"

  predicate {
    conditions {
      job_name = aws_glue_job.validation_engine.name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.load_to_snowflake.name
  }
}

# Trigger 6 — AI enrichment after Snowflake load
resource "aws_glue_trigger" "after_snowflake_load" {
  name          = "validata-trigger-after-snowflake-load"
  workflow_name = aws_glue_workflow.pipeline.name
  type          = "CONDITIONAL"

  predicate {
    conditions {
      job_name = aws_glue_job.load_to_snowflake.name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.ai_anomaly.name
  }
}
