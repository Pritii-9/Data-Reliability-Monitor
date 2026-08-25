# =============================================================================
#  Validata — Data Validation Engine
#  Databricks Notebook: 01_extract_raw_data
#  Layer       : Bronze / Raw Ingestion
#  Source      : s3://validata-datalake/raw/
#  Destination : s3://validata-datalake/staging/
#  Author      : Senior Cloud Data Engineer
# =============================================================================
#
# PURPOSE OF THIS NOTEBOOK
# ─────────────────────────
# This is the FIRST notebook in the pipeline.  Its only job is to:
#   1. Read the raw CSV files that were uploaded to S3 by the source systems.
#   2. Perform the absolute minimum "safe landing" — no business logic yet.
#   3. Write the data out as Parquet into the staging zone.
#
# Think of this as the "intake desk" of an airport — passports are checked
# (schema inferred), bags are tagged (metadata added), but no customs
# inspection happens yet.
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# CELL 1 — IMPORTS & SPARK SESSION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • `from pyspark.sql import SparkSession`
#     PySpark is Python's API on top of Apache Spark.  SparkSession is the
#     single entry point into ALL Spark functionality — DataFrames, SQL,
#     streaming, etc.  Think of it as the "engine ignition key."
#
# • `from pyspark.sql import functions as F`
#     This imports Spark's built-in column-level functions under the alias F.
#     You will see things like F.col(), F.current_timestamp(), F.lit() later.
#     The alias avoids conflicts with Python's own built-in functions.
#
# • `from pyspark.sql.types import *`
#     Imports all Spark DataType classes (StructType, StructField, StringType,
#     DoubleType, DateType, etc.) so we can define an EXPLICIT schema.
#     Relying on Spark's automatic schema inference on CSVs is risky — it
#     reads sample rows and can mistype columns (e.g., read "amount" as
#     string if it sees a blank).  Defining it manually is a best practice.
#
# • In Databricks, a SparkSession is ALREADY created for you automatically
#     as the variable `spark`.  The `.getOrCreate()` pattern here is so this
#     same script also runs safely in a plain Python/local environment.
# ─────────────────────────────────────────────────────────────────────────────

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, DateType,
)

# In Databricks this just returns the pre-existing session.
# builder → configure → getOrCreate() is the standard idiom everywhere else.
spark = (
    SparkSession
    .builder
    .appName("Validata-01-ExtractRawData")   # visible in Spark UI
    .getOrCreate()
)

# Print the Spark version so the run log proves which runtime was used.
# This tiny line has saved hours of debugging version-mismatch issues.
print("Spark version: {spark.version}")

# --- SERVERLESS AUTHENTICATION (S3) ---
AWS_ACCESS_KEY = "YOUR_AWS_ACCESS_KEY_HERE"
AWS_SECRET_KEY = "YOUR_AWS_SECRET_KEY_HERE"
spark.conf.set("fs.s3a.access.key", AWS_ACCESS_KEY)
spark.conf.set("fs.s3a.secret.key", AWS_SECRET_KEY)
spark.conf.set("fs.s3a.endpoint", "s3.amazonaws.com")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 2 — CONFIGURATION (single source of truth for all paths)
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • Storing paths in Python variables at the top means every subsequent cell
#   references the SAME string.  If the bucket name ever changes, you change
#   it in ONE place.
#
# • In a real Databricks project you would pull these from Databricks Widgets
#   (dbutils.widgets) or a config YAML — but constants work perfectly for now.
#
# • Databricks clusters running on AWS natively resolve "s3://" paths via the
#   IAM role attached to the cluster or via a Databricks secret scope.
#   No additional boto3 import is needed.
# ─────────────────────────────────────────────────────────────────────────────

# ── S3 paths ──────────────────────────────────────────────────────────────────
BUCKET              = "s3://validata-datalake"

# Raw landing zone (Source CSVs uploaded by upstream systems)
RAW_LEGACY_PATH     = f"{BUCKET}/raw/legacy_system/"
RAW_NEW_PATH        = f"{BUCKET}/raw/new_system/"

# Staging zone (cleaned Parquet, written by THIS notebook)
STAGING_LEGACY_PATH = f"{BUCKET}/staging/legacy_system/"
STAGING_NEW_PATH    = f"{BUCKET}/staging/new_system/"

# Audit log path (we write a small JSON audit entry after every run)
LOG_PATH            = f"{BUCKET}/logs/01_extract_raw_data/"

# Print so the notebook output shows exactly which paths were used this run.
print("=" * 60)
print("  Validata — 01 Extract Raw Data")
print("=" * 60)
print(f"  RAW LEGACY  : {RAW_LEGACY_PATH}")
print(f"  RAW NEW     : {RAW_NEW_PATH}")
print(f"  STG LEGACY  : {STAGING_LEGACY_PATH}")
print(f"  STG NEW     : {STAGING_NEW_PATH}")
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CELL 3 — EXPLICIT SCHEMA DEFINITION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • `StructType([...])` defines the shape of the DataFrame — like CREATE TABLE
#   in SQL.  Each `StructField` is one column.
#
# • `StructField("column_name", DataType(), nullable)`
#     - column_name : must match the CSV header exactly (case-sensitive).
#     - DataType()  : the Spark type to cast this column to on read.
#     - nullable    : True means Spark allows NULL/empty in this column.
#                     We set customer_id to True because we know our test
#                     data has intentionally blank customer IDs.
#
# • Why DoubleType for amount instead of DecimalType?
#     DoubleType is faster for computation.  DecimalType is safer for exact
#     financial arithmetic.  For the ETL/comparison layer DoubleType is fine;
#     Snowflake will store it as NUMBER(18,2) after we load it.
#
# • Why DateType for txn_date?
#     Storing dates as real DATE objects (not strings) allows Spark to perform
#     date arithmetic later — e.g. "find transactions older than 30 days."
#     The dateFormat option in the reader below tells Spark the format of the
#     source string so it can parse it correctly.
# ─────────────────────────────────────────────────────────────────────────────

TRANSACTION_SCHEMA = StructType([
    StructField("txn_id",       StringType(), nullable=False),  # primary key
    StructField("customer_id",  StringType(), nullable=True),   # intentionally nullable
    StructField("txn_date",     DateType(),   nullable=False),  # parsed as real DATE
    StructField("amount",       DoubleType(), nullable=False),  # numeric for math later
    StructField("currency",     StringType(), nullable=False),
    StructField("status",       StringType(), nullable=False),
    StructField("region",       StringType(), nullable=False),
    StructField("channel",      StringType(), nullable=False),
    StructField("product_type", StringType(), nullable=False),
    StructField("reference_no", StringType(), nullable=False),
])

print("Schema defined successfully.")
print(f"  Columns : {len(TRANSACTION_SCHEMA.fields)}")
for field in TRANSACTION_SCHEMA.fields:
    print(f"    {field.name:<16} {str(field.dataType):<16} nullable={field.nullable}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 4 — GENERIC CSV READER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • We wrap the read logic in a Python function so it is REUSABLE.  We call
#   it twice below — once for legacy, once for new system — without repeating
#   the reader options.
#
# • `spark.read` returns a DataFrameReader object (a "builder").
#   Each chained method adds a configuration option:
#
#   .format("csv")
#       Tell Spark to use the CSV reader codec.
#
#   .schema(schema)
#       Provide our pre-defined schema.  Without this, Spark uses schema
#       inference, which requires an extra full scan of the file and can
#       produce wrong types.
#
#   .option("header", "true")
#       The first row of the CSV is the column header — don't treat it as data.
#
#   .option("dateFormat", "yyyy-MM-dd")
#       Tells the DateType parser the format of the source date strings.
#       "yyyy-MM-dd" is ISO-8601 — matches what our simulator wrote.
#
#   .option("mode", "PERMISSIVE")
#       When a row doesn't match the schema, Spark doesn't crash.  Instead
#       it sets all columns to NULL and records the bad row in a special
#       "_corrupt_record" column.  The alternative modes are DROPMALFORMED
#       (silently skip bad rows) and FAILFAST (throw exception immediately).
#       PERMISSIVE is the right choice for a validation pipeline — we WANT
#       to see and log bad rows rather than lose them.
#
#   .option("columnNameOfCorruptRecord", "_corrupt_record")
#       Names the column where malformed rows are stored.
#
#   .load(path)
#       The actual S3 path to read from.  Can be a specific file or a
#       directory prefix (Spark will read ALL files in the directory).
#
# • `df.withColumn("_source_file", F.input_file_name())`
#       Adds a new column called _source_file whose value is the full S3
#       path of the file each row came from.  Critical for audit trails when
#       a folder contains multiple CSV files.
#
# • `df.withColumn("_ingested_at", F.current_timestamp())`
#       Stamps each row with the exact UTC timestamp it was read.
#       This is a "technical metadata" column — it doesn't exist in the
#       source system, we're adding it for lineage tracking.
# ─────────────────────────────────────────────────────────────────────────────

def read_raw_csv(path: str, schema: StructType, source_label: str):
    """
    Read a CSV from S3 using an explicit schema and return an enriched
    Spark DataFrame with audit metadata columns appended.

    Parameters
    ----------
    path         : str         — S3 path (file or directory prefix)
    schema       : StructType  — pre-defined column schema
    source_label : str         — human-readable label for logging

    Returns
    -------
    pyspark.sql.DataFrame
    """
    print(f"\n→ Reading [{source_label}] from: {path}")

    df = (
        spark.read
        .format("csv")
        .schema(schema)
        .option("header",                    "true")
        .option("dateFormat",                "yyyy-MM-dd")
        .option("mode",                      "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .load(path)
    )

    # ── Append audit / lineage metadata columns ────────────────────────────
    df = (
        df
        # The S3 key (filename) the row was sourced from.
        .withColumn("_source_file",  F.input_file_name())
        # UTC timestamp this row was processed by Spark.
        .withColumn("_ingested_at",  F.current_timestamp())
        # Human-readable label passed in by the caller.
        .withColumn("_source_label", F.lit(source_label))
    )

    # ── Quick sanity metrics ───────────────────────────────────────────────
    row_count = df.count()
    print(f"  ✔ Rows read          : {row_count:,}")
    print(f"  ✔ Columns (incl meta): {len(df.columns)}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# CELL 5 — READ BOTH SOURCE FILES
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • We call our function twice, once per source.
# • The results are stored in two DataFrame variables:
#     df_legacy  → represents Source A (old system)
#     df_new_sys → represents Source B (new system)
# • DataFrames in Spark are LAZY — `.read.load()` doesn't actually read all
#   the data yet.  Spark builds a "query plan."  The plan only EXECUTES when
#   you call an action like .count(), .show(), or .write.
#   This is why `read_raw_csv` calls .count() — to force execution and give
#   us real row numbers for logging.
# ─────────────────────────────────────────────────────────────────────────────

df_legacy  = read_raw_csv(RAW_LEGACY_PATH,  TRANSACTION_SCHEMA, "legacy_system")
df_new_sys = read_raw_csv(RAW_NEW_PATH,     TRANSACTION_SCHEMA, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 6 — PREVIEW & QUICK PROFILING
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • `df.printSchema()`
#     Prints the tree-shaped schema to the notebook output.
#     Confirms Spark interpreted each column with the type we specified.
#
# • `df.show(n, truncate=False)`
#     Prints the first n rows as a table.
#     truncate=False means long strings aren't cut off — important for
#     seeing full UUIDs and S3 paths.
#
# • `df.describe("amount")`
#     Returns a mini-summary DataFrame with count, mean, stddev, min, max
#     for the "amount" column.  Calling .show() on it prints it.
#     This is the equivalent of pandas df["amount"].describe().
#
# • These cells are for notebook interactivity — in a production schedule
#   you would comment them out or gate them behind a DEBUG flag to save
#   compute time.
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─" * 50)
print("  LEGACY SYSTEM — Schema")
print("─" * 50)
df_legacy.printSchema()

print("  LEGACY SYSTEM — First 5 rows")
df_legacy.show(5, truncate=False)

print("  LEGACY SYSTEM — Amount distribution")
df_legacy.describe("amount").show()

print("\n" + "─" * 50)
print("  NEW SYSTEM — Schema")
print("─" * 50)
df_new_sys.printSchema()

print("  NEW SYSTEM — First 5 rows")
df_new_sys.show(5, truncate=False)

print("  NEW SYSTEM — Amount distribution")
df_new_sys.describe("amount").show()


# ─────────────────────────────────────────────────────────────────────────────
# CELL 7 — NULL / CORRUPT RECORD DETECTION
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • We check for two categories of data quality issues right at ingestion:
#
#   A) Corrupt records (PERMISSIVE mode captures these in _corrupt_record)
#      `F.col("_corrupt_record").isNotNull()` — filters rows where Spark
#      could NOT parse the row at all.  These are truly malformed rows.
#
#   B) Missing txn_id
#      A NULL txn_id means the row has no primary key.  It is unusable for
#      validation (we can't join on it).  We quarantine it immediately.
#
# • `filter()` and `where()` are interchangeable in PySpark — they both
#   create a new DataFrame containing only the rows that satisfy the condition.
#   The original df_legacy is NOT modified (DataFrames are immutable).
#
# • We cache the bad rows DataFrames with `.cache()` because we will call
#   .count() AND .show() on them — without caching, Spark would re-execute
#   the full read + filter twice.  `.cache()` stores the result in memory
#   after the first action.
# ─────────────────────────────────────────────────────────────────────────────

def audit_bad_rows(df, label: str):
    """Separate and report corrupt or key-less rows."""

    # A) Rows that Spark could not parse (PERMISSIVE mode captures these)
    corrupt = (
        df.filter(F.col("_corrupt_record").isNotNull())
          .cache()
    )

    # B) Rows missing the primary key entirely
    no_key = (
        df.filter(F.col("txn_id").isNull())
          .cache()
    )

    corrupt_count = corrupt.count()
    no_key_count  = no_key.count()

    print(f"\n  [{label}] Corrupt rows   : {corrupt_count}")
    print(f"  [{label}] Missing txn_id : {no_key_count}")

    if corrupt_count > 0:
        print(f"  Sample corrupt rows from [{label}]:")
        corrupt.select("_corrupt_record", "_source_file").show(5, truncate=False)

    # Free cached memory — good practice after using .cache()
    corrupt.unpersist()
    no_key.unpersist()

    return corrupt_count, no_key_count


legacy_corrupt,  legacy_no_key  = audit_bad_rows(df_legacy,  "legacy_system")
new_sys_corrupt, new_sys_no_key = audit_bad_rows(df_new_sys, "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 8 — DROP METADATA-ONLY COLUMNS BEFORE WRITING
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • The _corrupt_record column was only useful for the audit above.
#   We drop it before writing to staging so downstream notebooks don't
#   need to filter it out.  _source_file, _ingested_at, _source_label
#   are KEPT — they are genuine lineage metadata.
#
# • `df.drop("column_name")` returns a new DataFrame without that column.
#   Again, the original df is unchanged (immutable).
# ─────────────────────────────────────────────────────────────────────────────

df_legacy  = df_legacy.drop("_corrupt_record")
df_new_sys = df_new_sys.drop("_corrupt_record")

print("Dropped '_corrupt_record' column from both DataFrames.")
print(f"  legacy  columns remaining : {df_legacy.columns}")
print(f"  new_sys columns remaining : {df_new_sys.columns}")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 9 — WRITE TO STAGING AS PARQUET (PARTITIONED BY DATE)
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • WHY PARQUET?
#     Parquet is a columnar binary format — far more efficient than CSV for
#     big-data workloads.  It stores schema inline, compresses well, and
#     allows Spark to read ONLY the columns it needs (column pruning).
#     CSV requires reading every byte of every row even if you only want 2
#     columns.  For a dataset of millions of rows, this matters enormously.
#
# • `.write` returns a DataFrameWriter.
#   `.mode("overwrite")` — if the staging path already has data from a
#     previous run, overwrite it completely.  The alternatives are:
#       "append"       — add to existing data (risks duplicates on re-run)
#       "ignore"       — skip if data already exists (dangerous — silent skip)
#       "error" (default) — throw an error if data exists
#     "overwrite" is correct for idempotent ETL — running the notebook
#     twice gives the same result.
#
#   `.partitionBy("txn_date")` — physically splits the Parquet output into
#     sub-folders, one per date (e.g., txn_date=2026-07-15/).  This is
#     called "Hive-style partitioning."  The huge benefit: downstream
#     notebooks that only query a specific date range don't touch the
#     other partitions at all — called "partition pruning," it can reduce
#     I/O by 90%+.
#
#   `.format("parquet")` — use the Parquet codec.
#
#   `.save(path)` — execute the write.  This is an ACTION in Spark, so
#     all the lazy transformations defined above now execute.
# ─────────────────────────────────────────────────────────────────────────────

def write_staging_parquet(df, path: str, label: str) -> None:
    """Write a DataFrame to the staging zone as partitioned Parquet."""

    print(f"\n→ Writing [{label}] to staging: {path}")

    (
        df.write
          .mode("overwrite")
          .partitionBy("txn_date")       # enables partition pruning downstream
          .format("parquet")
          .save(path)
    )

    print(f"  ✔ [{label}] written successfully.")


write_staging_parquet(df_legacy,  STAGING_LEGACY_PATH, "legacy_system")
write_staging_parquet(df_new_sys, STAGING_NEW_PATH,    "new_system")


# ─────────────────────────────────────────────────────────────────────────────
# CELL 10 — WRITE PIPELINE AUDIT LOG ENTRY
# ─────────────────────────────────────────────────────────────────────────────
#
# LINE-BY-LINE EXPLANATION
# ─────────────────────────
# • After every run we write a small JSON record to the logs/ folder.
#   This gives ops teams a queryable history of every pipeline execution.
#
# • `spark.createDataFrame([dict], schema=None)` — creates a single-row
#   DataFrame from a Python list of dicts.  When schema=None, Spark infers
#   it automatically (acceptable for a small log record).
#
# • `.mode("append")` — we APPEND log entries, not overwrite.  The logs
#   folder grows over time and can be queried for trend analysis.
#
# • `.format("json")` — writes one JSON object per row.  Easy to read and
#   query with Athena, Snowflake external table, or just cat in the shell.
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timezone

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

audit_df = spark.createDataFrame(audit_record)

(
    audit_df.write
            .mode("append")
            .format("json")
            .save(LOG_PATH)
)

print("\n✔  Audit log written to:", LOG_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# CELL 11 — FINAL NOTEBOOK SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("  NOTEBOOK 01 — COMPLETE")
print("=" * 60)
print(f"  Legacy rows in staging  : {df_legacy.count():,}")
print(f"  New sys rows in staging : {df_new_sys.count():,}")
print()
print("  NEXT → Run notebook 02_transform_clean_standardize")
print("=" * 60)
