# =============================================================================
#  Validata — Data Validation Engine
#  Databricks Notebook: 03_deduplicate_validate_schema
#  Layer  : Silver / Schema Enforcement
#  Source : s3://validata-datalake/staging/  (clean Parquet from NB 02)
#  Dest   : s3://validata-datalake/staging/validated/
#  Author : Senior Cloud Data Engineer
# =============================================================================
#
# PURPOSE
# ───────
# Notebook 02 cleaned individual files in isolation.
# THIS notebook enforces CROSS-DATASET business rules:
#   1. NOT-NULL check on required business columns
#   2. Amount range validation (> 0 and <= 10M)
#   3. Date range check — txn_date must be within migration window
#   4. Assign a _row_status (PASS / WARN / FAIL) per row
#   5. Route FAILs to quarantine; route PASS + WARN to staging/validated/
#
# KEY PYSPARK CONCEPTS INTRODUCED
# ────────────────────────────────
#   • functools.reduce()              — chain OR conditions dynamically
#   • F.col().isNull()                — NULL detection on a Column
#   • F.datediff() / F.to_date()      — date arithmetic in Spark
#   • F.col().startsWith()            — string prefix check on a Column
#   • Chained .when().when().otherwise() — multi-branch CASE WHEN
#   • df.subtract()                   — set difference between two DataFrames
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# CELL 1 — IMPORTS & SESSION
# ─────────────────────────────────────────────────────────────────────────────

from functools import reduce
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from datetime import datetime, timezone

spark = (
    SparkSession.builder
    .appName("Validata-03-DeduplicateValidateSchema")
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

# NOT-NULLABLE business columns — NULL in any of these = FAIL row
NOT_NULL_COLS = ["txn_id", "txn_date", "amount", "currency", "status"]

print("=" * 60)
print("  Validata — 03 Deduplicate Validate Schema")
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CELL 3 — READ CLEAN STAGING PARQUET
# ─────────────────────────────────────────────────────────────────────────────

df_legacy  = spark.read.parquet(STAGING_LEGACY_IN)
df_new_sys = spark.read.parquet(STAGING_NEW_IN)

print(f"\nLegacy  rows : {df_legacy.count():,}")
print(f"New sys rows : {df_new_sys.count():,}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 4 — NOT-NULL ENFORCEMENT
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# reduce(lambda a, b: a | b, conditions)
#   Python's reduce() applies a binary function (lambda a, b: a | b) to a
#   list of items cumulatively:
#     reduce(f, [c1, c2, c3]) == f(f(c1, c2), c3) == c1 | c2 | c3
#   Here each item is a Spark Column expression (F.col(c).isNull()).
#   The | operator on two Spark Columns creates a logical OR Column.
#   The result is a single Column that is True when ANY required column is NULL.
#
# ~any_null
#   The ~ operator on a Spark Column is logical NOT.
#   So df.filter(~any_null) keeps rows where NO required column is NULL.
# ─────────────────────────────────────────────────────────────────────────────

def check_not_nulls(df, label: str):
    null_conditions = [F.col(c).isNull() for c in NOT_NULL_COLS]
    any_null        = reduce(lambda a, b: a | b, null_conditions)

    null_rows     = df.filter(any_null)
    non_null_rows = df.filter(~any_null)

    print(f"\n[NOT-NULL CHECK] [{label}]")
    print(f"  Passing  : {non_null_rows.count():,}")
    print(f"  Failing  : {null_rows.count()} (missing required field)")

    if null_rows.count() > 0:
        null_rows.select(*NOT_NULL_COLS).show(5, truncate=False)

    return non_null_rows, null_rows


legacy_nonnull,  legacy_null_fail  = check_not_nulls(df_legacy,  "legacy_system")
new_sys_nonnull, new_sys_null_fail = check_not_nulls(df_new_sys, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 5 — AMOUNT RANGE VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# Chained F.when().when().otherwise() = SQL CASE WHEN ... WHEN ... ELSE
# Spark evaluates each .when() from top to bottom — first match wins.
#
# F.lit("FAIL_BELOW_MIN")
#   Creates a constant string Column. F.lit() is required because .when()
#   expects a Column object on both sides — a plain Python string "FAIL..."
#   is not a Column and will raise a TypeError.
# ─────────────────────────────────────────────────────────────────────────────

def validate_amount_range(df, label: str):
    df_tagged = df.withColumn(
        "_amount_check",
        F.when(F.col("amount") < AMOUNT_MIN,  F.lit("FAIL_BELOW_MIN"))
         .when(F.col("amount") > AMOUNT_MAX,  F.lit("WARN_ABOVE_MAX"))
         .otherwise(                           F.lit("PASS"))
    )
    print(f"\n[AMOUNT CHECK] [{label}]")
    df_tagged.groupBy("_amount_check").count().orderBy("_amount_check").show()
    return df_tagged


legacy_amt  = validate_amount_range(legacy_nonnull,  "legacy_system")
new_sys_amt = validate_amount_range(new_sys_nonnull, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 6 — DATE RANGE VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# F.to_date(F.lit("2026-01-01"), "yyyy-MM-dd")
#   Converts a Python string literal into a Spark DATE Column.
#   We must wrap the string in F.lit() first to make it a Column, then
#   F.to_date() parses it according to the provided format pattern.
#   This date Column is reusable across all rows without re-parsing.
#
# F.datediff(end_col, start_col)
#   Returns (end - start) in whole days as an integer Column.
#   If end < start, the result is negative.
#   We check for negative datediff to detect out-of-window dates.
# ─────────────────────────────────────────────────────────────────────────────

DATE_MIN_COL = F.to_date(F.lit(MIGRATION_DATE_MIN), "yyyy-MM-dd")
DATE_MAX_COL = F.to_date(F.lit(MIGRATION_DATE_MAX), "yyyy-MM-dd")

def validate_date_range(df, label: str):
    df_tagged = df.withColumn(
        "_date_check",
        F.when(F.datediff(F.col("txn_date"), DATE_MIN_COL) < 0,
               F.lit("FAIL_DATE_BEFORE_WINDOW"))
         .when(F.datediff(DATE_MAX_COL, F.col("txn_date")) < 0,
               F.lit("FAIL_DATE_AFTER_WINDOW"))
         .otherwise(F.lit("PASS"))
    )
    print(f"\n[DATE CHECK] [{label}]")
    df_tagged.groupBy("_date_check").count().orderBy("_date_check").show()
    return df_tagged


legacy_dated  = validate_date_range(legacy_amt,  "legacy_system")
new_sys_dated = validate_date_range(new_sys_amt, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 7 — COMBINE FLAGS INTO MASTER _row_status
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# F.col("_amount_check").startsWith("FAIL")
#   Returns True if _amount_check begins with "FAIL" — matches both
#   "FAIL_BELOW_MIN" and any other FAIL_ variants we might add later.
#   This is more robust than an exact equality check and scales as
#   we add more validation rules.
#
# Priority: FAIL > WARN > PASS
#   A single FAIL in any check makes the entire row a FAIL.
#   WARN only applies when no FAIL exists.
#   PASS only when everything is clean.
# ─────────────────────────────────────────────────────────────────────────────

def assign_row_status(df, label: str):
    df_status = df.withColumn(
        "_row_status",
        F.when(
            F.col("_amount_check").startsWith("FAIL") |
            F.col("_date_check").startsWith("FAIL"),
            F.lit("FAIL")
        ).when(
            F.col("_amount_check").startsWith("WARN") |
            F.col("_date_check").startsWith("WARN"),
            F.lit("WARN")
        ).otherwise(F.lit("PASS"))
    ).drop("_amount_check", "_date_check")

    print(f"\n[ROW STATUS] [{label}]")
    df_status.groupBy("_row_status").count().show()
    return df_status


legacy_status  = assign_row_status(legacy_dated,  "legacy_system")
new_sys_status = assign_row_status(new_sys_dated, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 8 — SPLIT PASS/WARN FROM FAIL
# ─────────────────────────────────────────────────────────────────────────────

def split_by_status(df, label: str):
    proceed    = df.filter(F.col("_row_status") != "FAIL")
    quarantine = (
        df.filter(F.col("_row_status") == "FAIL")
          .withColumn("_quarantine_reason", F.lit("SCHEMA_RULE_VIOLATION"))
          .withColumn("_quarantine_source", F.lit(label))
    )
    print(f"\n[SPLIT] [{label}]")
    print(f"  Proceeding  : {proceed.count():,}")
    print(f"  Quarantined : {quarantine.count()}")
    return proceed, quarantine


legacy_proceed,  legacy_q   = split_by_status(legacy_status,  "legacy_system")
new_sys_proceed, new_sys_q  = split_by_status(new_sys_status, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 9 — WRITE QUARANTINE & VALIDATED DATA
# ─────────────────────────────────────────────────────────────────────────────

all_q = legacy_q.unionByName(new_sys_q, allowMissingColumns=True)
q_count = all_q.count()

if q_count > 0:
    all_q.write.mode("append").format("json").save(QUARANTINE_PATH)
    print(f"\n[QUARANTINE] {q_count} rows written to: {QUARANTINE_PATH}")
else:
    print("\n[QUARANTINE] No schema violations this run.")

for df, path, label in [
    (legacy_proceed,  VALIDATED_LEGACY, "legacy_system"),
    (new_sys_proceed, VALIDATED_NEW,    "new_system"),
]:
    df.write.mode("overwrite").partitionBy("txn_date").format("parquet").save(path)
    print(f"[WRITE] [{label}] {df.count():,} rows --> {path}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 10 — AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

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
print(f"\n[AUDIT LOG] Written to: {LOG_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 11 — SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("  NOTEBOOK 03 — COMPLETE")
print("=" * 60)
print(f"  Legacy  : {df_legacy.count():,} in  -->  {legacy_proceed.count():,} validated")
print(f"  New sys : {df_new_sys.count():,} in  -->  {new_sys_proceed.count():,} validated")
print(f"  Total quarantined this run : {q_count}")
print()
print("  Rules enforced:")
print("    [x] NOT NULL on txn_id, txn_date, amount, currency, status")
print("    [x] Amount range : 0.01 to 10,000,000")
print("    [x] Date range   : 2026-01-01 to 2026-12-31")
print("    [x] _row_status  : PASS / WARN / FAIL per row")
print()
print("  NEXT --> Run notebook 04_validation_engine")
print("=" * 60)
