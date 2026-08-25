# Validata — Extract Raw Data (Bronze Ingestion)
# Reads raw CSV files from S3, enforces schema, and writes Parquet.

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType
from datetime import datetime, timezone

spark = SparkSession.builder.getOrCreate()

# S3 configurations
BUCKET              = "s3://validata-datalake"
RAW_LEGACY_PATH     = f"{BUCKET}/raw/legacy_system/"
RAW_NEW_PATH        = f"{BUCKET}/raw/new_system/"
STAGING_LEGACY_PATH = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_PATH    = f"{BUCKET}/staging/new_system/"
LOG_PATH            = f"{BUCKET}/logs/01_extract_raw_data/"

# Enforce schema structure
TRANSACTION_SCHEMA = StructType([
    StructField("txn_id",       StringType(), nullable=False),
    StructField("customer_id",  StringType(), nullable=True),
    StructField("txn_date",     DateType(),   nullable=False),
    StructField("amount",       DoubleType(), nullable=False),
    StructField("currency",     StringType(), nullable=False),
    StructField("status",       StringType(), nullable=False),
    StructField("region",       StringType(), nullable=False),
    StructField("channel",      StringType(), nullable=False),
    StructField("product_type", StringType(), nullable=False),
    StructField("reference_no", StringType(), nullable=False),
])

# Read raw CSV with permissive schema and metadata fields
def read_raw_csv(path: str, schema: StructType, source_label: str):
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

df_legacy  = read_raw_csv(RAW_LEGACY_PATH,  TRANSACTION_SCHEMA, "legacy_system")
df_new_sys = read_raw_csv(RAW_NEW_PATH,     TRANSACTION_SCHEMA, "new_system")

# Audit corrupt or invalid rows
def audit_bad_rows(df, label: str):
    corrupt = df.filter(F.col("_corrupt_record").isNotNull()).cache()
    no_key  = df.filter(F.col("txn_id").isNull()).cache()
    corrupt_count = corrupt.count()
    no_key_count  = no_key.count()
    print(f"[{label}] Corrupt: {corrupt_count}, Missing txn_id: {no_key_count}")
    corrupt.unpersist()
    no_key.unpersist()
    return corrupt_count, no_key_count

legacy_corrupt,  legacy_no_key  = audit_bad_rows(df_legacy,  "legacy_system")
new_sys_corrupt, new_sys_no_key = audit_bad_rows(df_new_sys, "new_system")

df_legacy  = df_legacy.drop("_corrupt_record")
df_new_sys = df_new_sys.drop("_corrupt_record")

# Save cleaned output files to partitioned S3 parquet
def write_staging_parquet(df, path: str, label: str) -> None:
    (
        df.write
        .mode("overwrite")
        .partitionBy("txn_date")
        .format("parquet")
        .save(path)
    )
    print(f"[{label}] Staging parquet write complete.")

write_staging_parquet(df_legacy,  STAGING_LEGACY_PATH, "legacy_system")
write_staging_parquet(df_new_sys, STAGING_NEW_PATH,    "new_system")

# Save daily audit execution log record
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
print("Notebook 01 Complete.")
