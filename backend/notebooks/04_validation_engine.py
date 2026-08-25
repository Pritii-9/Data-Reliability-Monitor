# =============================================================================
#  Validata — Data Validation Engine
#  Databricks Notebook: 04_validation_engine
#  Layer  : Gold / Validation Results
#  Source : s3://validata-datalake/staging/validated/
#  Dest   : s3://validata-datalake/curated/validation_results/
#  Author : Senior Cloud Data Engineer
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
#
# KEY PYSPARK CONCEPTS INTRODUCED
# ────────────────────────────────
#   • Full outer join                   — join keeping ALL rows from both sides
#   • Column aliasing with .alias()     — rename columns after join
#   • F.abs() / F.when()               — absolute value + conditional logic
#   • F.coalesce()                      — return first non-NULL from a list
#   • df.withColumnRenamed()            — rename a column
#   • Writing partitioned curated data  — final Gold-layer write
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# CELL 1 — IMPORTS & SESSION
# ─────────────────────────────────────────────────────────────────────────────

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from datetime import datetime, timezone

spark = (
    SparkSession.builder
    .appName("Validata-04-ValidationEngine")
    .getOrCreate()
)
print("Spark version: {spark.version}")

# --- SERVERLESS AUTHENTICATION (S3) ---
AWS_ACCESS_KEY = "YOUR_AWS_ACCESS_KEY_HERE"
AWS_SECRET_KEY = "YOUR_AWS_SECRET_KEY_HERE"
spark.conf.set("fs.s3a.access.key", AWS_ACCESS_KEY)
spark.conf.set("fs.s3a.secret.key", AWS_SECRET_KEY)
spark.conf.set("fs.s3a.endpoint", "s3.amazonaws.com")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 2 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

BUCKET = "s3://validata-datalake"

VALIDATED_LEGACY   = f"{BUCKET}/staging/validated/legacy_system/"
VALIDATED_NEW      = f"{BUCKET}/staging/validated/new_system/"
CURATED_OUTPUT     = f"{BUCKET}/curated/validation_results/"
LOG_PATH           = f"{BUCKET}/logs/04_validation_engine/"

# Amount mismatch tolerance: differences <= this % are considered MATCH.
# Set to 0.0 for exact matching, 0.01 for 1% tolerance.
AMOUNT_TOLERANCE_PCT = 0.001   # 0.1% — catches our simulated 5% drifts easily

print("=" * 60)
print("  Validata — 04 Validation Engine")
print("=" * 60)
print(f"  TOLERANCE  : {AMOUNT_TOLERANCE_PCT * 100:.2f}%")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 3 — READ VALIDATED STAGING DATA
# ─────────────────────────────────────────────────────────────────────────────

df_legacy  = spark.read.parquet(VALIDATED_LEGACY)
df_new_sys = spark.read.parquet(VALIDATED_NEW)

print(f"\nLegacy  rows : {df_legacy.count():,}")
print(f"New sys rows : {df_new_sys.count():,}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 4 — PREPARE DATAFRAMES FOR JOIN
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# Before joining, we rename all business columns in each DataFrame with a
# prefix (leg_ and new_) so that after the join we can clearly tell which
# value came from which system. Without this, a full outer join on txn_id
# would create two columns called "amount" — Spark resolves ambiguity by
# requiring you to reference them with the original DataFrame name, which
# is messy and error-prone.
#
# We keep only the columns needed for validation — the metadata columns
# (_source_file, etc.) are not needed for the comparison logic.
#
# .alias("l") on the join line creates a DataFrame alias, allowing us to
# reference columns as l.txn_id / r.txn_id when Spark needs disambiguation.
# ─────────────────────────────────────────────────────────────────────────────

BUSINESS_COLS = ["txn_id", "customer_id", "txn_date", "amount",
                 "currency", "status", "region", "channel",
                 "product_type", "reference_no"]

def prefix_columns(df, prefix: str, keep_join_key: bool = True):
    """
    Rename all business columns with a prefix.
    Keep txn_id unprefixed so it can be the join key, unless keep_join_key=False.
    """
    renamed = df.select(BUSINESS_COLS)
    for col in BUSINESS_COLS:
        if col == "txn_id" and keep_join_key:
            continue  # txn_id stays unprefixed — it's our join key
        renamed = renamed.withColumnRenamed(col, f"{prefix}_{col}")
    return renamed


leg = prefix_columns(df_legacy,  "leg")
new = prefix_columns(df_new_sys, "new")

print("\nLegacy columns after prefix  :", leg.columns)
print("New sys columns after prefix :", new.columns)


# ─────────────────────────────────────────────────────────────────────────────
# CELL 5 — FULL OUTER JOIN
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# leg.join(new, on="txn_id", how="full")
#   A FULL OUTER JOIN returns ALL rows from both DataFrames:
#     - Rows where txn_id matches in both → one combined row
#     - Rows in leg with NO match in new  → row with NULLs in new_* columns
#     - Rows in new with NO match in leg  → row with NULLs in leg_* columns
#
#   This is exactly what we need:
#     - Matched rows     → compare amounts, statuses
#     - leg-only rows    → MISSING from new system
#     - new-only rows    → PHANTOM in new system
#
#   how="full" is identical to how="outer" — both work, "full" is clearer.
#
#   on="txn_id" — when both DataFrames have a column with the same name,
#   Spark can use it directly as the join key. The result has ONE txn_id
#   column (not two), which is the correct behavior for equi-joins.
# ─────────────────────────────────────────────────────────────────────────────

joined = leg.join(new, on="txn_id", how="full")

print(f"\nJoined DataFrame rows : {joined.count():,}")
print(f"Joined columns        : {joined.columns}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 6 — CLASSIFY EACH ROW
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# F.abs(F.col("leg_amount") - F.col("new_amount"))
#   F.abs() returns the absolute value of a Column expression.
#   We subtract amounts and take the absolute value to get the raw difference
#   regardless of which system reported a higher number.
#
# amount_diff / F.coalesce(F.col("leg_amount"), F.lit(1.0))
#   We divide the raw difference by the legacy amount to get a % difference.
#   F.coalesce(col, default) returns the first non-NULL argument.
#   If leg_amount is NULL (PHANTOM row), we fall back to 1.0 to avoid
#   dividing by NULL (which would produce NULL, breaking the comparison).
#
# Classification logic (applied top-to-bottom — first match wins):
#   1. leg_amount IS NULL → PHANTOM  (row only in new system)
#   2. new_amount IS NULL → MISSING  (row only in legacy)
#   3. status disagrees   → STATUS_MISMATCH
#   4. % amount diff > tolerance → AMOUNT_MISMATCH
#   5. Everything else    → MATCH
# ─────────────────────────────────────────────────────────────────────────────

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
    F.round(amount_diff_pct * 100, 4)   # store as a percentage for readability
).withColumn(
    "validated_at", F.current_timestamp()
)

print("\nValidation status distribution:")
classified.groupBy("validation_status").count().orderBy("validation_status").show()


# ─────────────────────────────────────────────────────────────────────────────
# CELL 7 — BUILD FINAL OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# F.coalesce(F.col("leg_customer_id"), F.col("new_customer_id"))
#   For MISSING rows, leg_customer_id is populated but new_customer_id is NULL.
#   For PHANTOM rows, the opposite is true.
#   coalesce() picks whichever is non-NULL, giving us a single customer_id
#   column in the output regardless of which system had the record.
#
# This select() call defines the EXACT schema that Notebook 05 will load
# into Snowflake. Column order and naming should match the Snowflake
# DDL for ValiData_DB.CURATED_SCHEMA.validation_results.
# ─────────────────────────────────────────────────────────────────────────────

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

print("\nFinal output schema:")
output.printSchema()
print(f"Total output rows: {output.count():,}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 8 — SHOW MISMATCH SAMPLES
# ─────────────────────────────────────────────────────────────────────────────

for status in ["MISSING", "PHANTOM", "AMOUNT_MISMATCH", "STATUS_MISMATCH"]:
    sample = output.filter(F.col("validation_status") == status)
    count  = sample.count()
    print(f"\n[{status}] — {count} rows found")
    if count > 0:
        sample.show(5, truncate=True)


# ─────────────────────────────────────────────────────────────────────────────
# CELL 9 — WRITE CURATED VALIDATION RESULTS
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# We partition by validation_status, not txn_date this time.
# Why? Notebook 05 (Snowflake load) and Notebook 06 (AI explanations) both
# query by validation_status — e.g. "give me all AMOUNT_MISMATCH rows."
# Partitioning by validation_status means those queries skip irrelevant
# partitions (e.g. the huge MATCH partition) and only read what they need.
# ─────────────────────────────────────────────────────────────────────────────

(
    output.write
          .mode("overwrite")
          .partitionBy("validation_status")
          .format("parquet")
          .save(CURATED_OUTPUT)
)

print(f"\n[WRITE] Curated results --> {CURATED_OUTPUT}")
print("        Partitioned by: validation_status")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 10 — AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

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
print(f"[AUDIT LOG] Written to: {LOG_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 11 — SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("  NOTEBOOK 04 — COMPLETE")
print("=" * 60)
print(f"  Total transactions compared : {output.count():,}")
for k, v in sorted(status_counts.items()):
    print(f"    {k:<20} : {v}")
print()
print(f"  Curated output : {CURATED_OUTPUT}")
print()
print("  NEXT --> Run notebook 05_load_to_snowflake")
print("=" * 60)
