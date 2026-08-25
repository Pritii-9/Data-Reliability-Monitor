# =============================================================================
#  Validata — Data Validation Engine
#  AWS Glue Notebook: 04_validation_engine
#  Layer  : Gold / Validation Results
#  Source : s3://validata-datalake/staging/validated/
#  Dest   : s3://validata-datalake/curated/validation_results/
#  Stack  : AWS S3 + AWS Glue (PySpark) + Snowflake + Google Gemini
# =============================================================================
#
# PURPOSE
# ───────
# This is the CORE notebook — the validation engine itself.
# It joins legacy and new system data on txn_id and produces one output row
# per transaction, classifying it as one of:
#   MATCH          — identical in both systems
#   AMOUNT_MISMATCH — same txn_id, amounts differ beyond tolerance
#   STATUS_MISMATCH — same txn_id, status field disagrees
#   MISSING        — exists in legacy but NOT in new system
#   PHANTOM        — exists in new system but NOT in legacy
# =============================================================================

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from datetime import datetime, timezone

spark = (
    SparkSession.builder
    .appName("Validata-04-ValidationEngine")
    .getOrCreate()
)
print(f"Spark version: {spark.version}")

# --- S3 CONFIGURATION ---
BUCKET             = "s3://validata-datalake"
VALIDATED_LEGACY   = f"{BUCKET}/staging/validated/legacy_system/"
VALIDATED_NEW      = f"{BUCKET}/staging/validated/new_system/"
CURATED_OUTPUT     = f"{BUCKET}/curated/validation_results/"
LOG_PATH           = f"{BUCKET}/logs/04_validation_engine/"

# Amount mismatch tolerance: differences <= this % are considered MATCH.
AMOUNT_TOLERANCE_PCT = 0.001   # 0.1%

print("=" * 60)
print("  Validata — 04 Validation Engine")
print("=" * 60)
print(f"  TOLERANCE  : {AMOUNT_TOLERANCE_PCT * 100:.2f}%")

# 1. Read validated staging data
df_legacy  = spark.read.parquet(VALIDATED_LEGACY)
df_new_sys = spark.read.parquet(VALIDATED_NEW)

print(f"\nLegacy  rows : {df_legacy.count():,}")
print(f"New sys rows : {df_new_sys.count():,}")

# 2. Prepare DataFrames for join
BUSINESS_COLS = ["txn_id", "customer_id", "txn_date", "amount",
                 "currency", "status", "region", "channel",
                 "product_type", "reference_no"]

def prefix_columns(df, prefix: str, keep_join_key: bool = True):
    renamed = df.select(BUSINESS_COLS)
    for col in BUSINESS_COLS:
        if col == "txn_id" and keep_join_key:
            continue
        renamed = renamed.withColumnRenamed(col, f"{prefix}_{col}")
    return renamed

leg = prefix_columns(df_legacy,  "leg")
new = prefix_columns(df_new_sys, "new")

# 3. Full outer join
joined = leg.join(new, on="txn_id", how="full")

# 4. Classify each row
amount_diff_pct = (
    F.abs(F.col("leg_amount") - F.col("new_amount")) /
    F.coalesce(F.col("leg_amount"), F.lit(1.0))
)

classified = joined.withColumn(
    "validation_status",
    F.when(F.col("leg_amount").isNull(),                       F.lit("PHANTOM"))
     .when(F.col("new_amount").isNull(),                       F.lit("MISSING"))
     .when(F.col("leg_status") != F.col("new_status"),         F.lit("STATUS_MISMATCH"))
     .when(amount_diff_pct > AMOUNT_TOLERANCE_PCT,             F.lit("AMOUNT_MISMATCH"))
     .otherwise(                                               F.lit("MATCH"))
).withColumn(
    "amount_diff",
    F.round(F.abs(F.col("leg_amount") - F.col("new_amount")), 4)
).withColumn(
    "amount_diff_pct",
    F.round(amount_diff_pct * 100, 4)
).withColumn(
    "validated_at", F.current_timestamp()
)

print("\nValidation status distribution:")
classified.groupBy("validation_status").count().orderBy("validation_status").show()

# 5. Build final output schema
output = classified.select(
    "txn_id",
    F.coalesce(F.col("leg_customer_id"),  F.col("new_customer_id")) .alias("customer_id"),
    F.coalesce(F.col("leg_txn_date"),     F.col("new_txn_date"))    .alias("txn_date"),
    F.coalesce(F.col("leg_currency"),     F.col("new_currency"))    .alias("currency"),
    F.coalesce(F.col("leg_region"),       F.col("new_region"))      .alias("region"),
    F.coalesce(F.col("leg_channel"),      F.col("new_channel"))     .alias("channel"),
    F.coalesce(F.col("leg_product_type"), F.col("new_product_type")).alias("product_type"),
    F.col("leg_amount")        .alias("legacy_amount"),
    F.col("new_amount")        .alias("new_system_amount"),
    F.col("amount_diff"),
    F.col("amount_diff_pct"),
    F.col("leg_status")        .alias("legacy_status"),
    F.col("new_status")        .alias("new_system_status"),
    F.col("validation_status"),
    F.col("validated_at"),
)

# 6. Write curated validation results back to S3
(
    output.write
          .mode("overwrite")
          .partitionBy("validation_status")
          .format("parquet")
          .save(CURATED_OUTPUT)
)

print(f"\n[WRITE] Curated results --> {CURATED_OUTPUT}")

# 7. Audit log
status_counts = {
    row["validation_status"]: row["count"]
    for row in classified.groupBy("validation_status").count().collect()
}

(
    spark.createDataFrame([{
        "notebook"          : "04_validation_engine",
        "run_timestamp"     : datetime.now(timezone.utc).isoformat(),
        "total_rows"        : output.count(),
        "match_count"       : status_counts.get("MATCH", 0),
        "missing_count"     : status_counts.get("MISSING", 0),
        "phantom_count"     : status_counts.get("PHANTOM", 0),
        "amount_mismatch"   : status_counts.get("AMOUNT_MISMATCH", 0),
        "status_mismatch"   : status_counts.get("STATUS_MISMATCH", 0),
        "tolerance_pct"     : AMOUNT_TOLERANCE_PCT,
        "curated_path"      : CURATED_OUTPUT,
        "status"            : "SUCCESS",
    }])
    .write.mode("append").format("json").save(LOG_PATH)
)

print("\n" + "=" * 60)
print("  NOTEBOOK 04 — COMPLETE")
print("=" * 60)
