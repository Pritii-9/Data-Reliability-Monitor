# Validata — Clean & Standardize (Silver Data)
# Cleans data formatting, removes duplicates, and quarantines invalid enums.

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from datetime import datetime, timezone

spark = SparkSession.builder.appName("Validata-02-TransformCleanStandardize").getOrCreate()

# S3 configurations
BUCKET             = "s3://validata-datalake"
STAGING_LEGACY_IN  = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_IN     = f"{BUCKET}/staging/new_system/"
STAGING_LEGACY_OUT = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_OUT    = f"{BUCKET}/staging/new_system/"
QUARANTINE_PATH    = f"{BUCKET}/data/quarantine/"
LOG_PATH           = f"{BUCKET}/logs/02_transform_clean_standardize/"

# Valid enum checks
VALID_STATUSES    = {"COMPLETED", "PENDING", "FAILED", "REVERSED"}
VALID_CURRENCIES  = {"USD", "EUR", "GBP", "INR", "AED"}
VALID_REGIONS     = {"APAC", "EMEA", "NA", "LATAM"}
VALID_CHANNELS    = {"ONLINE", "BRANCH", "ATM", "MOBILE"}
VALID_PRODUCTS    = {"LOAN_PAYMENT", "WIRE_TRANSFER", "BILL_PAY", "FX_CONVERSION", "DEPOSIT"}

df_legacy  = spark.read.parquet(STAGING_LEGACY_IN)
df_new_sys = spark.read.parquet(STAGING_NEW_IN)

# Clean, uppercase string enums, and round amounts
def clean_and_standardize(df, label: str):
    string_cols = ["txn_id", "customer_id", "currency", "status", "region", "channel", "product_type", "reference_no"]
    upper_cols = ["currency", "status", "region", "channel", "product_type"]

    cleaned = df
    for col in string_cols:
        cleaned = cleaned.withColumn(col, F.trim(F.col(col)))
    for col in upper_cols:
        cleaned = cleaned.withColumn(col, F.upper(F.col(col)))

    cleaned = cleaned.withColumn("amount", F.round(F.col("amount"), 2).cast(DecimalType(18, 2)))
    cleaned = cleaned.withColumn("customer_id", F.when(F.col("customer_id") == "", None).otherwise(F.col("customer_id")))
    cleaned = cleaned.withColumn("_cleaned_at", F.current_timestamp())
    return cleaned

df_legacy_clean  = clean_and_standardize(df_legacy,  "legacy_system")
df_new_sys_clean = clean_and_standardize(df_new_sys, "new_system")

# Remove transaction duplicates
def deduplicate(df, label: str):
    before = df.count()
    df_deduped = df.dropDuplicates(["txn_id"])
    dropped = before - df_deduped.count()
    print(f"[{label}] Dropped {dropped} duplicates.")
    return df_deduped

df_legacy_deduped  = deduplicate(df_legacy_clean,  "legacy_system")
df_new_sys_deduped = deduplicate(df_new_sys_clean, "new_system")

# Quarantine rows with invalid enum values
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
    return valid, invalid

legacy_valid,  legacy_invalid  = validate_enums_and_quarantine(df_legacy_deduped,  "legacy_system")
new_sys_valid, new_sys_invalid = validate_enums_and_quarantine(df_new_sys_deduped, "new_system")

# Save invalid records to quarantine path
all_invalid = legacy_invalid.unionByName(new_sys_invalid, allowMissingColumns=True)
quarantine_count = all_invalid.count()
if quarantine_count > 0:
    all_invalid.write.mode("append").format("json").save(QUARANTINE_PATH)

# Write output files to staging (overwrites)
def write_clean_parquet(df, path: str, label: str) -> int:
    row_count = df.count()
    df.write.mode("overwrite").partitionBy("txn_date").format("parquet").save(path)
    return row_count

legacy_written  = write_clean_parquet(legacy_valid,  STAGING_LEGACY_OUT, "legacy_system")
new_sys_written = write_clean_parquet(new_sys_valid, STAGING_NEW_OUT,    "new_system")

# Daily audit log entry
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
print("Notebook 02 Complete.")
