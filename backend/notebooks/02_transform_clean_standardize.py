# =============================================================================
#  Validata — Data Validation Engine
#  Databricks Notebook: 02_transform_clean_standardize
#  Layer  : Silver / Cleaned Data
#  Source : s3://validata-datalake/staging/
#  Dest   : s3://validata-datalake/staging/  (overwrites with clean data)
#  Author : Senior Cloud Data Engineer
# =============================================================================
#
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
#
# KEY PYSPARK CONCEPTS INTRODUCED IN THIS NOTEBOOK
# ─────────────────────────────────────────────────
#   • F.trim()            — strip leading/trailing whitespace
#   • F.upper()           — uppercase a column
#   • F.round()           — round a numeric column
#   • F.when().otherwise()— conditional column logic (like SQL CASE WHEN)
#   • F.col().isin()      — membership check against a list
#   • DataFrame.dropDuplicates() — remove duplicate rows by key columns
#   • DataFrame.subtract()       — set difference between two DataFrames
#   • DataFrame.unionByName()    — stack two DataFrames by column name
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# CELL 1 — IMPORTS & SPARK SESSION
# ─────────────────────────────────────────────────────────────────────────────

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from datetime import datetime, timezone

spark = (
    SparkSession.builder
    .appName("Validata-02-TransformCleanStandardize")
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

# Input: what Notebook 01 wrote
STAGING_LEGACY_IN  = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_IN     = f"{BUCKET}/staging/new_system/"

# Output: we overwrite staging with the cleaned versions
STAGING_LEGACY_OUT = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_OUT    = f"{BUCKET}/staging/new_system/"

# Quarantine: rows that fail validation rules go here instead
QUARANTINE_PATH    = f"{BUCKET}/data/quarantine/"

LOG_PATH           = f"{BUCKET}/logs/02_transform_clean_standardize/"

# ── Allowed enum values — any row outside these sets is quarantined ──────────
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


# ─────────────────────────────────────────────────────────────────────────────
# CELL 3 — READ STAGING PARQUET
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# We read Parquet (not CSV) this time because Notebook 01 already wrote
# the data in Parquet format with the schema embedded.
#
# spark.read.parquet(path)
#   • No need to specify a schema — Parquet stores column names and types
#     inside the file itself. Spark reads them automatically.
#   • No format() call needed — .parquet() is shorthand for .format("parquet").
#   • Because we partitioned by txn_date in Notebook 01, Spark sees folders
#     like txn_date=2026-07-15/ and reconstructs txn_date as a column.
#     This is called "partition discovery" — Spark automatically adds the
#     partition key back as a column when reading.
# ─────────────────────────────────────────────────────────────────────────────

df_legacy  = spark.read.parquet(STAGING_LEGACY_IN)
df_new_sys = spark.read.parquet(STAGING_NEW_IN)

print(f"\nLegacy  rows loaded : {df_legacy.count():,}")
print(f"New sys rows loaded : {df_new_sys.count():,}")
print(f"Legacy  columns     : {df_legacy.columns}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 4 — CORE CLEANING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
#
# F.trim(F.col("col_name"))
#   Removes leading and trailing whitespace from a string column.
#   Source CSVs often have invisible spaces after commas — e.g. " USD " would
#   fail an equality check against "USD". trim() fixes this universally.
#
# F.upper(F.col("col_name"))
#   Converts all characters in the column to uppercase.
#   Reason: "completed" vs "COMPLETED" would be treated as two different
#   values in a group-by or join. Standardising to UPPER removes this risk.
#
# F.round(F.col("amount"), 2).cast(DecimalType(18, 2))
#   F.round(col, 2) rounds a double to 2 decimal places.
#   .cast(DecimalType(18, 2)) then converts the double to an exact fixed-point
#   Decimal type — 18 total digits, 2 after the decimal point.
#   Why two steps? round() alone keeps it as a Double (floating point),
#   which can still have tiny binary representation errors like 10.999999998.
#   Casting to DecimalType(18,2) forces exact precision — critical for
#   financial data where amounts must match to the cent.
#
# F.when(condition, value).otherwise(other_value)
#   This is PySpark's equivalent of SQL CASE WHEN ... THEN ... ELSE ... END.
#   Structure:
#       F.when(<condition>, <value_if_true>).otherwise(<value_if_false>)
#   It returns a Column expression, so it's used inside .withColumn().
#   In our case:
#       F.when(F.col("customer_id") == "", None).otherwise(F.col("customer_id"))
#   means: "If customer_id is an empty string, replace it with NULL;
#   otherwise keep the original value."
#   Why? Our simulator writes blank customer_ids as "" (empty string), not NULL.
#   Downstream SQL joins and IS NULL checks only work with real NULLs,
#   not empty strings. This converts the CSV artifact into proper SQL nulls.
#
# F.current_timestamp()
#   Returns the current timestamp at the moment Spark executes this action.
#   We store it as _cleaned_at to record exactly when each row was processed
#   by this notebook.
# ─────────────────────────────────────────────────────────────────────────────

def clean_and_standardize(df, label: str):
    """
    Apply all cleaning and standardization rules to a transaction DataFrame.

    Rules applied (in order):
      1. Trim all string columns
      2. UPPER-CASE all enum columns
      3. Round + cast amount to DecimalType(18,2)
      4. Convert empty customer_id to NULL
      5. Add _cleaned_at timestamp

    Parameters
    ----------
    df    : pyspark.sql.DataFrame — raw staging DataFrame
    label : str                   — source label for logging

    Returns
    -------
    pyspark.sql.DataFrame — cleaned DataFrame
    """
    print(f"\n[CLEAN] Processing [{label}]...")

    # ── String columns to trim (all of them) ──────────────────────────────
    string_cols = [
        "txn_id", "customer_id", "currency", "status",
        "region", "channel", "product_type", "reference_no",
    ]

    # ── Enum columns to UPPER-CASE (subset of string_cols) ────────────────
    upper_cols = ["currency", "status", "region", "channel", "product_type"]

    # Start the transformation chain
    cleaned = df

    # STEP 1 — Trim every string column
    # withColumn(name, expr) replaces a column in-place (or adds it if new).
    # We loop over all string columns so every one gets trimmed in one pass.
    for col_name in string_cols:
        cleaned = cleaned.withColumn(col_name, F.trim(F.col(col_name)))

    # STEP 2 — UPPER-CASE enum columns
    for col_name in upper_cols:
        cleaned = cleaned.withColumn(col_name, F.upper(F.col(col_name)))

    # STEP 3 — Standardise amount: round then cast to exact Decimal
    cleaned = cleaned.withColumn(
        "amount",
        F.round(F.col("amount"), 2).cast(DecimalType(18, 2))
    )

    # STEP 4 — Convert empty-string customer_id to real SQL NULL
    # F.when().otherwise() = SQL CASE WHEN
    cleaned = cleaned.withColumn(
        "customer_id",
        F.when(
            F.col("customer_id") == "",   # CONDITION: is it an empty string?
            None                          # TRUE branch: replace with NULL
        ).otherwise(
            F.col("customer_id")          # FALSE branch: keep original value
        )
    )

    # STEP 5 — Add processing timestamp for audit trail
    cleaned = cleaned.withColumn("_cleaned_at", F.current_timestamp())

    # Quick report
    null_cust = cleaned.filter(F.col("customer_id").isNull()).count()
    print(f"  Rows after cleaning  : {cleaned.count():,}")
    print(f"  NULL customer_id rows: {null_cust}")

    return cleaned


df_legacy_clean  = clean_and_standardize(df_legacy,  "legacy_system")
df_new_sys_clean = clean_and_standardize(df_new_sys, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 5 — DEDUPLICATE ON txn_id
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# df.dropDuplicates(["txn_id"])
#   Removes rows where the value of txn_id is NOT unique in the DataFrame.
#   It keeps the FIRST occurrence of each txn_id and drops all subsequent ones.
#   "First" here means whichever row appears first in the Spark partition —
#   in practice, for deterministic deduplication in production you would
#   combine this with an orderBy on a reliable tiebreaker column
#   (e.g. _ingested_at) before calling dropDuplicates.
#
#   Our simulator injected 5 duplicate txn_ids into legacy_transactions.csv,
#   so we expect the legacy count to drop by exactly 5 after this step.
#
# Why not df.distinct()?
#   distinct() checks ALL columns — a row must be completely identical to be
#   considered a duplicate. dropDuplicates(["txn_id"]) checks ONLY txn_id,
#   which is correct here: we want to remove same-key rows even if other
#   fields differ slightly.
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# CELL 6 — ENUM VALIDATION & QUARANTINE
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# F.col("status").isin(list(VALID_STATUSES))
#   Returns a boolean Column: True if the value is in the set, False otherwise.
#   ~  is Python's bitwise NOT — it NEGATES the boolean Column.
#   So ~F.col("status").isin(...) means "status is NOT in the allowed set."
#   We chain multiple such conditions with | (OR) to create one filter that
#   catches ANY column that has an invalid enum value.
#
# df.filter(condition)    → rows WHERE condition is TRUE
# df.subtract(other_df)   → set difference — rows in df that are NOT in other_df
#   We use subtract() instead of ~filter() here because it is more readable
#   when separating "good" from "bad" rows and works correctly across
#   DataFrames with the same schema.
#
# df.unionByName(other)
#   Stacks two DataFrames vertically, matching columns BY NAME (not position).
#   This is safer than union() which matches columns by position — if the
#   column order differs between the two DataFrames, union() silently puts
#   data in the wrong columns.
# ─────────────────────────────────────────────────────────────────────────────

def validate_enums_and_quarantine(df, label: str):
    """
    Split the DataFrame into:
      - valid   : rows where all enum columns contain allowed values
      - invalid : rows with at least one out-of-range enum value
    Returns (valid_df, invalid_df)
    """

    # Build a combined filter: True means AT LEAST ONE enum column is bad
    bad_enum_condition = (
        ~F.col("status").isin(list(VALID_STATUSES))       |
        ~F.col("currency").isin(list(VALID_CURRENCIES))   |
        ~F.col("region").isin(list(VALID_REGIONS))        |
        ~F.col("channel").isin(list(VALID_CHANNELS))      |
        ~F.col("product_type").isin(list(VALID_PRODUCTS))
    )

    # Rows that fail any enum check → quarantine
    invalid = (
        df.filter(bad_enum_condition)
          # Tag WHY the row was quarantined — important for ops debugging
          .withColumn("_quarantine_reason", F.lit("INVALID_ENUM_VALUE"))
          .withColumn("_quarantine_source", F.lit(label))
    )

    # Rows that pass ALL enum checks → proceed to next step
    valid   = df.subtract(df.filter(bad_enum_condition))

    inv_count = invalid.count()
    val_count = valid.count()

    print(f"\n[ENUM VALIDATE] [{label}]")
    print(f"  Valid rows   : {val_count:,}")
    print(f"  Invalid rows : {inv_count} --> quarantine")

    if inv_count > 0:
        invalid.select(
            "txn_id", "status", "currency", "region",
            "channel", "product_type", "_quarantine_reason"
        ).show(10, truncate=False)

    return valid, invalid


legacy_valid,  legacy_invalid  = validate_enums_and_quarantine(df_legacy_deduped,  "legacy_system")
new_sys_valid, new_sys_invalid = validate_enums_and_quarantine(df_new_sys_deduped, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 7 — WRITE QUARANTINED ROWS TO S3
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# We use unionByName() to stack both invalid DataFrames into a single
# quarantine table. Writing them together:
#   • keeps the quarantine zone in one place (easier to query in Snowflake)
#   • avoids two separate write jobs
#
# We write as JSON (not Parquet) here so that a data steward can easily
# open the file in any text editor or Athena and read the rejection reasons
# without needing a Parquet reader tool.
#
# .mode("append") — quarantine is a growing ledger, never overwritten.
# ─────────────────────────────────────────────────────────────────────────────

# Combine invalid rows from both sources (safe even if either is empty)
all_invalid = legacy_invalid.unionByName(new_sys_invalid, allowMissingColumns=True)
quarantine_count = all_invalid.count()

if quarantine_count > 0:
    (
        all_invalid.write
                   .mode("append")
                   .format("json")
                   .save(QUARANTINE_PATH)
    )
    print(f"\n[QUARANTINE] {quarantine_count} rows written to: {QUARANTINE_PATH}")
else:
    print("\n[QUARANTINE] No invalid rows — quarantine zone empty this run.")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 8 — FINAL SCHEMA PREVIEW & PROFILING
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# df.select([F.count(F.when(F.col(c).isNull(), c)).alias(c) for c in cols])
#   This is a list comprehension inside a .select() call.
#   For every column c, it counts the number of NULL values in that column.
#   F.when(F.col(c).isNull(), c) returns the column name if null, else null.
#   F.count() counts non-null values returned by F.when — so it counts nulls.
#   .alias(c) renames the resulting count column to the original column name.
#   The result is a single-row DataFrame showing null counts per column.
#   This is the fastest way to get a full null audit across all columns.
# ─────────────────────────────────────────────────────────────────────────────

def null_audit(df, label: str):
    """Print a null-count summary for every column in the DataFrame."""
    cols = [c for c in df.columns if not c.startswith("_")]
    null_counts = df.select([
        F.count(F.when(F.col(c).isNull(), c)).alias(c)
        for c in cols
    ])
    print(f"\n[NULL AUDIT] [{label}]")
    null_counts.show(truncate=False)


null_audit(legacy_valid,  "legacy_system  — after clean")
null_audit(new_sys_valid, "new_system     — after clean")

print("\nSchema after all transformations:")
legacy_valid.printSchema()


# ─────────────────────────────────────────────────────────────────────────────
# CELL 9 — WRITE CLEAN DATA BACK TO STAGING (OVERWRITE)
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# We overwrite the same staging path that Notebook 01 wrote.
# This is intentional: downstream notebooks (03, 04) always read from
# staging/, and they should always find clean data there — not raw data.
#
# An alternative architecture would write clean data to a separate path like
# staging/clean/legacy_system/ — valid choice for environments where you
# need to preserve the pre-clean state for reprocessing. We keep it simple
# here by overwriting.
#
# .partitionBy("txn_date") — preserved from Notebook 01.
# Partition pruning still applies for downstream date-range queries.
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# CELL 10 — AUDIT LOG ENTRY
# ─────────────────────────────────────────────────────────────────────────────

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

(
    spark.createDataFrame(audit_record)
         .write
         .mode("append")
         .format("json")
         .save(LOG_PATH)
)
print(f"\n[AUDIT LOG] Written to: {LOG_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 11 — NOTEBOOK SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("  NOTEBOOK 02 — COMPLETE")
print("=" * 60)
print(f"  Legacy  : {df_legacy.count():,} in  -->  {legacy_written:,} clean out")
print(f"  New sys : {df_new_sys.count():,} in  -->  {new_sys_written:,} clean out")
print(f"  Quarantined total : {quarantine_count}")
print()
print("  Transforms applied:")
print("    [x] Whitespace trimmed   (all string columns)")
print("    [x] Enum columns UPPER-CASED")
print("    [x] Amount rounded and cast to DecimalType(18,2)")
print("    [x] Empty customer_id converted to NULL")
print("    [x] Intra-file duplicates dropped (by txn_id)")
print("    [x] Invalid enum rows quarantined")
print()
print("  NEXT --> Run notebook 03_deduplicate_validate_schema")
print("=" * 60)
