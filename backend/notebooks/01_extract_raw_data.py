# =============================================================================
#  Validata — Data Validation Engine
#  AWS Glue Notebook: 01_extract_raw_data
#  Layer  : Bronze / Raw Ingestion
#  Source : s3://validata-datalake/raw/
#  Dest   : s3://validata-datalake/staging/
#  Stack  : AWS S3 + AWS Glue (PySpark) + Snowflake + Google Gemini
# =============================================================================
#
# INSTRUCTIONS: Paste this into an AWS Glue Interactive Session Notebook.
# IAM Role Required: Validata-Glue-Role (with S3 and Glue permissions)
#
# PURPOSE
# ───────
# Reads raw CSV files from S3, enforces a strict schema, tags each row
# with its source file and ingestion timestamp, then writes clean
# Parquet files back to S3 for downstream processing.
# =============================================================================

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, DateType
)
from datetime import datetime, timezone

# AWS Glue automatically provides the SparkSession
spark = SparkSession.builder.getOrCreate()
print(f"Spark version: {spark.version}")

# --- S3 CONFIGURATION ---
BUCKET              = "s3://validata-datalake"
RAW_LEGACY_PATH     = f"{BUCKET}/raw/legacy_system/"
RAW_NEW_PATH        = f"{BUCKET}/raw/new_system/"
STAGING_LEGACY_PATH = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_PATH    = f"{BUCKET}/staging/new_system/"
LOG_PATH            = f"{BUCKET}/logs/01_extract_raw_data/"

print("=" * 60)
print("  Validata — 01 Extract Raw Data")
print("=" * 60)
print(f"  RAW LEGACY  : {RAW_LEGACY_PATH}")
print(f"  RAW NEW     : {RAW_NEW_PATH}")
print(f"  STG LEGACY  : {STAGING_LEGACY_PATH}")
print(f"  STG NEW     : {STAGING_NEW_PATH}")
print("=" * 60)

# --- SCHEMA ENFORCEMENT ---
TRANSACTION_SCHEMA = StructType([
    StructField("txn_id",       StringType(), nullable=False),  # primary key
    StructField("customer_id",  StringType(), nullable=True),   # nullable
    StructField("txn_date",     DateType(),   nullable=False),  # parsed as DATE
    StructField("amount",       DoubleType(), nullable=False),  # numeric
    StructField("currency",     StringType(), nullable=False),
    StructField("status",       StringType(), nullable=False),
    StructField("region",       StringType(), nullable=False),
    StructField("channel",      StringType(), nullable=False),
    StructField("product_type", StringType(), nullable=False),
    StructField("reference_no", StringType(), nullable=False),
])

def read_raw_csv(path: str, schema: StructType, source_label: str):
    """Read a CSV from S3, tag with source metadata."""
    print(f"\n→ Reading [{source_label}] from: {path}")
    return (
        spark.read.format("csv")
        .schema(schema)
        .option("header", "true")
        .option("dateFormat", "yyyy-MM-dd")
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .load(path)
        .withColumn("_source_file",  F.input_file_name())
        .withColumn("_ingested_at",  F.current_timestamp())
        .withColumn("_source_label", F.lit(source_label))
    )

# 1. Read from S3
df_legacy  = read_raw_csv(RAW_LEGACY_PATH,  TRANSACTION_SCHEMA, "legacy_system")
df_new_sys = read_raw_csv(RAW_NEW_PATH,     TRANSACTION_SCHEMA, "new_system")

# 2. Audit corrupt rows
def audit_bad_rows(df, label: str):
    corrupt = df.filter(F.col("_corrupt_record").isNotNull()).cache()
    no_key  = df.filter(F.col("txn_id").isNull()).cache()
    corrupt_count = corrupt.count()
    no_key_count  = no_key.count()
    print(f"\n  [{label}] Corrupt rows   : {corrupt_count}")
    print(f"  [{label}] Missing txn_id : {no_key_count}")
    corrupt.unpersist()
    no_key.unpersist()
    return corrupt_count, no_key_count

legacy_corrupt,  legacy_no_key  = audit_bad_rows(df_legacy,  "legacy_system")
new_sys_corrupt, new_sys_no_key = audit_bad_rows(df_new_sys, "new_system")

# 3. Drop corrupt metadata column before writing
df_legacy  = df_legacy.drop("_corrupt_record")
df_new_sys = df_new_sys.drop("_corrupt_record")

# 4. Write partitioned Parquet back to S3 staging
def write_staging_parquet(df, path: str, label: str) -> None:
    print(f"\n→ Writing [{label}] to staging: {path}")
    (
        df.write
        .mode("overwrite")
        .partitionBy("txn_date")
        .format("parquet")
        .save(path)
    )
    print(f"  ✔ [{label}] written successfully.")

write_staging_parquet(df_legacy,  STAGING_LEGACY_PATH, "legacy_system")
write_staging_parquet(df_new_sys, STAGING_NEW_PATH,    "new_system")

# 5. Audit log
audit_record = [{
    "notebook"        : "01_extract_raw_data",
    "run_timestamp"   : datetime.now(timezone.utc).isoformat(),
    "legacy_rows_read": df_legacy.count(),
    "new_sys_rows_read": df_new_sys.count(),
    "legacy_corrupt"  : legacy_corrupt,
    "legacy_no_key"   : legacy_no_key,
    "new_sys_corrupt" : new_sys_corrupt,
    "new_sys_no_key"  : new_sys_no_key,
    "staging_legacy"  : STAGING_LEGACY_PATH,
    "staging_new"     : STAGING_NEW_PATH,
    "status"          : "SUCCESS",
}]
spark.createDataFrame(audit_record).write.mode("append").format("json").save(LOG_PATH)

print("\n" + "=" * 60)
print("  NOTEBOOK 01 — COMPLETE")
print("=" * 60)
