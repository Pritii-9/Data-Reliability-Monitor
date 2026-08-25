# Validata — Cross-Dataset Schema Enforcement (Silver Data)
# Enforces not-null checks, amount validation range checks, and date window verification.

from functools import reduce
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from datetime import datetime, timezone

spark = SparkSession.builder.appName("Validata-03-DeduplicateValidateSchema").getOrCreate()

# S3 configurations
BUCKET             = "s3://validata-datalake"
STAGING_LEGACY_IN  = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_IN     = f"{BUCKET}/staging/new_system/"
VALIDATED_LEGACY   = f"{BUCKET}/staging/validated/legacy_system/"
VALIDATED_NEW      = f"{BUCKET}/staging/validated/new_system/"
QUARANTINE_PATH    = f"{BUCKET}/data/quarantine/schema_violations/"
LOG_PATH           = f"{BUCKET}/logs/03_deduplicate_validate_schema/"

AMOUNT_MIN         = 0.01
AMOUNT_MAX         = 10_000_000.0
MIGRATION_DATE_MIN = "2026-01-01"
MIGRATION_DATE_MAX = "2026-12-31"

NOT_NULL_COLS = ["txn_id", "txn_date", "amount", "currency", "status"]

df_legacy  = spark.read.parquet(STAGING_LEGACY_IN)
df_new_sys = spark.read.parquet(STAGING_NEW_IN)

# Filter out rows with null in required columns
def check_not_nulls(df, label: str):
    null_conditions = [F.col(c).isNull() for c in NOT_NULL_COLS]
    any_null        = reduce(lambda a, b: a | b, null_conditions)
    null_rows     = df.filter(any_null)
    non_null_rows = df.filter(~any_null)
    return non_null_rows, null_rows

legacy_nonnull,  legacy_null_fail  = check_not_nulls(df_legacy,  "legacy_system")
new_sys_nonnull, new_sys_null_fail = check_not_nulls(df_new_sys, "new_system")

# Tag amount ranges (below min = FAIL, above max = WARN)
def validate_amount_range(df, label: str):
    return df.withColumn(
        "_amount_check",
        F.when(F.col("amount") < AMOUNT_MIN,  F.lit("FAIL_BELOW_MIN"))
         .when(F.col("amount") > AMOUNT_MAX,  F.lit("WARN_ABOVE_MAX"))
         .otherwise(                           F.lit("PASS"))
    )

legacy_amt  = validate_amount_range(legacy_nonnull,  "legacy_system")
new_sys_amt = validate_amount_range(new_sys_nonnull, "new_system")

# Tag transaction date ranges
DATE_MIN_COL = F.to_date(F.lit(MIGRATION_DATE_MIN), "yyyy-MM-dd")
DATE_MAX_COL = F.to_date(F.lit(MIGRATION_DATE_MAX), "yyyy-MM-dd")

def validate_date_range(df, label: str):
    return df.withColumn(
        "_date_check",
        F.when(F.datediff(F.col("txn_date"), DATE_MIN_COL) < 0, F.lit("FAIL_DATE_BEFORE_WINDOW"))
         .when(F.datediff(DATE_MAX_COL, F.col("txn_date")) < 0, F.lit("FAIL_DATE_AFTER_WINDOW"))
         .otherwise(F.lit("PASS"))
    )

legacy_dated  = validate_date_range(legacy_amt,  "legacy_system")
new_sys_dated = validate_date_range(new_sys_amt, "new_system")

# Combine validation checks to a master _row_status column
def assign_row_status(df, label: str):
    return df.withColumn(
        "_row_status",
        F.when(
            F.col("_amount_check").startsWith("FAIL") | F.col("_date_check").startsWith("FAIL"),
            F.lit("FAIL")
        ).when(
            F.col("_amount_check").startsWith("WARN") | F.col("_date_check").startsWith("WARN"),
            F.lit("WARN")
        ).otherwise(F.lit("PASS"))
    ).drop("_amount_check", "_date_check")

legacy_status  = assign_row_status(legacy_dated,  "legacy_system")
new_sys_status = assign_row_status(new_sys_dated, "new_system")

# Separate valid data (PASS/WARN) from invalid data (FAIL)
def split_by_status(df, label: str):
    proceed    = df.filter(F.col("_row_status") != "FAIL")
    quarantine = (
        df.filter(F.col("_row_status") == "FAIL")
          .withColumn("_quarantine_reason", F.lit("SCHEMA_RULE_VIOLATION"))
          .withColumn("_quarantine_source", F.lit(label))
    )
    return proceed, quarantine

legacy_proceed,  legacy_q   = split_by_status(legacy_status,  "legacy_system")
new_sys_proceed, new_sys_q  = split_by_status(new_sys_status, "new_system")

# Write quarantine files to S3 if any failures occurred
all_q = legacy_q.unionByName(new_sys_q, allowMissingColumns=True)
q_count = all_q.count()
if q_count > 0:
    all_q.write.mode("append").format("json").save(QUARANTINE_PATH)

# Save validated files to staging
for df, path, label in [
    (legacy_proceed,  VALIDATED_LEGACY, "legacy_system"),
    (new_sys_proceed, VALIDATED_NEW,    "new_system"),
]:
    df.write.mode("overwrite").partitionBy("txn_date").format("parquet").save(path)

# Log execution audit record
(
    spark.createDataFrame([{
        "notebook"            : "03_deduplicate_validate_schema",
        "run_timestamp"       : datetime.now(timezone.utc).isoformat(),
        "legacy_in"           : df_legacy.count(),
        "legacy_out"          : legacy_proceed.count(),
        "legacy_null_fail"    : legacy_null_fail.count(),
        "legacy_schema_fail"  : legacy_q.count(),
        "new_sys_in"          : df_new_sys.count(),
        "new_sys_out"         : new_sys_proceed.count(),
        "new_sys_null_fail"   : new_sys_null_fail.count(),
        "new_sys_schema_fail" : new_sys_q.count(),
        "status"              : "SUCCESS",
    }])
    .write.mode("append").format("json").save(LOG_PATH)
)
print("Notebook 03 Complete.")
