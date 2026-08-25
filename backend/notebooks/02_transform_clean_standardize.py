#  Validata — Data Validation Engine
#  AWS Glue Notebook: 02_transform_clean_standardize
#  Layer  : Silver / Cleaned Data
#  Source : s3://validata-datalake/staging/
#  Dest   : s3://validata-datalake/staging/  (overwrites with clean data)
#  Stack  : AWS S3 + AWS Glue (PySpark) + Snowflake + Google Gemini

# PURPOSE
# ───────
# Notebook 01 was a "safe landing" — minimum changes, raw data preserved.
# THIS notebook is the cleaning crew. It applies ALL business-level fixes:
#   1. Trim whitespace from every string column
#   2. UPPER-CASE all enum columns (status, currency, region, channel)
#   3. Standardise amount to exactly 2 decimal places
#   4. Replace blank customer_id ("") with a proper SQL NULL
#   5. Drop intra-file duplicate txn_ids (keep first occurrence)
#   6. Validate enum values — flag rows with illegal values
#   7. Add a _cleaned_at audit timestamp
#   8. Write clean Parquet back to staging (overwrite)
#   9. Quarantine rejected rows to S3 quarantine path
#  10. Write audit log entry


from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from datetime import datetime, timezone

spark = (
    SparkSession.builder
    .appName("Validata-02-TransformCleanStandardize")
    .getOrCreate()
)
print(f"Spark version: {spark.version}")

# --- S3 CONFIGURATION ---
BUCKET             = "s3://validata-datalake"
STAGING_LEGACY_IN  = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_IN     = f"{BUCKET}/staging/new_system/"
STAGING_LEGACY_OUT = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_OUT    = f"{BUCKET}/staging/new_system/"
QUARANTINE_PATH    = f"{BUCKET}/data/quarantine/"
LOG_PATH           = f"{BUCKET}/logs/02_transform_clean_standardize/"

# Allowed enum values — any row outside these sets is quarantined
VALID_STATUSES    = {"COMPLETED", "PENDING", "FAILED", "REVERSED"}
VALID_CURRENCIES  = {"USD", "EUR", "GBP", "INR", "AED"}
VALID_REGIONS     = {"APAC", "EMEA", "NA", "LATAM"}
VALID_CHANNELS    = {"ONLINE", "BRANCH", "ATM", "MOBILE"}
VALID_PRODUCTS    = {"LOAN_PAYMENT", "WIRE_TRANSFER", "BILL_PAY",
                     "FX_CONVERSION", "DEPOSIT"}

print("=" * 60)
print("  Validata — 02 Transform Clean Standardize")
print("=" * 60)
print(f"  LEGACY  IN  : {STAGING_LEGACY_IN}")
print(f"  NEW SYS IN  : {STAGING_NEW_IN}")
print(f"  QUARANTINE  : {QUARANTINE_PATH}")
print("=" * 60)

# 1. Read staging parquet
df_legacy  = spark.read.parquet(STAGING_LEGACY_IN)
df_new_sys = spark.read.parquet(STAGING_NEW_IN)

print(f"\nLegacy  rows loaded : {df_legacy.count():,}")
print(f"New sys rows loaded : {df_new_sys.count():,}")

# 2. Core cleaning function
def clean_and_standardize(df, label: str):
    print(f"\n[CLEAN] Processing [{label}]...")
    string_cols = [
        "txn_id", "customer_id", "currency", "status",
        "region", "channel", "product_type", "reference_no",
    ]
    upper_cols = ["currency", "status", "region", "channel", "product_type"]

    cleaned = df
    for col_name in string_cols:
        cleaned = cleaned.withColumn(col_name, F.trim(F.col(col_name)))
    for col_name in upper_cols:
        cleaned = cleaned.withColumn(col_name, F.upper(F.col(col_name)))

    cleaned = cleaned.withColumn(
        "amount",
        F.round(F.col("amount"), 2).cast(DecimalType(18, 2))
    )
    cleaned = cleaned.withColumn(
        "customer_id",
        F.when(F.col("customer_id") == "", None).otherwise(F.col("customer_id"))
    )
    cleaned = cleaned.withColumn("_cleaned_at", F.current_timestamp())

    print(f"  Rows after cleaning  : {cleaned.count():,}")
    return cleaned

df_legacy_clean  = clean_and_standardize(df_legacy,  "legacy_system")
df_new_sys_clean = clean_and_standardize(df_new_sys, "new_system")

# 3. Deduplicate on txn_id
def deduplicate(df, label: str):
    before = df.count()
    df_deduped = df.dropDuplicates(["txn_id"])
    after  = df_deduped.count()
    dropped = before - after
    print(f"\n[DEDUP] [{label}]")
    print(f"  Before : {before:,} rows")
    print(f"  After  : {after:,} rows")
    print(f"  Dropped: {dropped} duplicate txn_id rows")
    return df_deduped

df_legacy_deduped  = deduplicate(df_legacy_clean,  "legacy_system")
df_new_sys_deduped = deduplicate(df_new_sys_clean, "new_system")

# 4. Enum validation and quarantine
def validate_enums_and_quarantine(df, label: str):
    bad_enum_condition = (
        ~F.col("status").isin(list(VALID_STATUSES))       |
        ~F.col("currency").isin(list(VALID_CURRENCIES))   |
        ~F.col("region").isin(list(VALID_REGIONS))        |
        ~F.col("channel").isin(list(VALID_CHANNELS))      |
        ~F.col("product_type").isin(list(VALID_PRODUCTS))
    )

    invalid = (
        df.filter(bad_enum_condition)
        .withColumn("_quarantine_reason", F.lit("INVALID_ENUM_VALUE"))
        .withColumn("_quarantine_source", F.lit(label))
    )

    valid = df.subtract(df.filter(bad_enum_condition))
    print(f"\n[ENUM VALIDATE] [{label}]")
    print(f"  Valid rows   : {valid.count():,}")
    print(f"  Invalid rows : {invalid.count()} --> quarantine")
    return valid, invalid

legacy_valid,  legacy_invalid  = validate_enums_and_quarantine(df_legacy_deduped,  "legacy_system")
new_sys_valid, new_sys_invalid = validate_enums_and_quarantine(df_new_sys_deduped, "new_system")

# 5. Write quarantine to S3
all_invalid = legacy_invalid.unionByName(new_sys_invalid, allowMissingColumns=True)
quarantine_count = all_invalid.count()

if quarantine_count > 0:
    all_invalid.write.mode("append").format("json").save(QUARANTINE_PATH)
    print(f"\n[QUARANTINE] {quarantine_count} rows written to: {QUARANTINE_PATH}")

# 6. Write clean data back to staging (overwrite)
def write_clean_parquet(df, path: str, label: str) -> int:
    row_count = df.count()
    (
        df.write
        .mode("overwrite")
        .partitionBy("txn_date")
        .format("parquet")
        .save(path)
    )
    print(f"\n[WRITE] [{label}] {row_count:,} clean rows --> {path}")
    return row_count

legacy_written  = write_clean_parquet(legacy_valid,  STAGING_LEGACY_OUT, "legacy_system")
new_sys_written = write_clean_parquet(new_sys_valid, STAGING_NEW_OUT,    "new_system")

# 7. Audit log
audit_record = [{
    "notebook"           : "02_transform_clean_standardize",
    "run_timestamp"      : datetime.now(timezone.utc).isoformat(),
    "legacy_in_rows"     : df_legacy.count(),
    "legacy_out_rows"    : legacy_written,
    "legacy_quarantined" : legacy_invalid.count(),
    "new_sys_in_rows"    : df_new_sys.count(),
    "new_sys_out_rows"   : new_sys_written,
    "new_sys_quarantined": new_sys_invalid.count(),
    "quarantine_path"    : QUARANTINE_PATH,
    "status"             : "SUCCESS",
}]
spark.createDataFrame(audit_record).write.mode("append").format("json").save(LOG_PATH)

print("\n" + "=" * 60)
print("  NOTEBOOK 02 — COMPLETE")
print("=" * 60)
