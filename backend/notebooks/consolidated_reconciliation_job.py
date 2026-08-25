# Validata — Consolidated AWS Glue PySpark Job (PoC / Single-Run)
# Reads raw transaction CSVs from S3, reconciles them, and writes results to Snowflake.

import sys
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, when, abs, coalesce, current_timestamp, lit

glueContext = GlueContext(SparkContext.getOrCreate())
spark = glueContext.spark_session
job = Job(glueContext)

# 1. Read raw CSV transaction ledgers from S3 folders (automatically combines multiple CSV files inside)
legacy_df = spark.read.option("header", "true").option("inferSchema", "true").csv("s3://validata-datalake/raw/legacy_system/")
new_df = spark.read.option("header", "true").option("inferSchema", "true").csv("s3://validata-datalake/raw/new_system/")

# 2. Rename columns to avoid collisions on outer join
legacy_prep = legacy_df.select(
    col("txn_id"),
    col("customer_id").alias("leg_customer_id"),
    col("txn_date").alias("leg_txn_date"),
    col("amount").alias("leg_amount"),
    col("status").alias("leg_status"),
    col("currency").alias("leg_currency"),
    col("region").alias("leg_region"),
    col("channel").alias("leg_channel"),
    col("product_type").alias("leg_product_type")
)

new_prep = new_df.select(
    col("txn_id"),
    col("customer_id").alias("new_customer_id"),
    col("txn_date").alias("new_txn_date"),
    col("amount").alias("new_amount"),
    col("status").alias("new_status"),
    col("currency").alias("new_currency"),
    col("region").alias("new_region"),
    col("channel").alias("new_channel"),
    col("product_type").alias("new_product_type")
)

# 3. Full outer join on transaction identifier
reconciled = legacy_prep.join(new_prep, on="txn_id", how="full")

# 4. Calculate amount differences
reconciled = reconciled.withColumn("amount_diff", abs(coalesce(col("leg_amount"), col("new_amount")) - coalesce(col("new_amount"), col("leg_amount"))))
reconciled = reconciled.withColumn("amount_diff_pct", (col("amount_diff") / coalesce(col("leg_amount"), col("new_amount"))) * 100)

# 5. Classify validation anomaly status
reconciled = reconciled.withColumn(
    "validation_status",
    when(col("leg_amount").isNull(), "PHANTOM")
    .when(col("new_amount").isNull(), "MISSING")
    .when(col("leg_status") != col("new_status"), "STATUS_MISMATCH")
    .when(col("amount_diff_pct") > 0.1, "AMOUNT_MISMATCH")
    .otherwise("MATCH")
)

# 6. Format to target Snowflake table layout
final_results = reconciled.select(
    col("txn_id").alias("TXN_ID"),
    coalesce(col("leg_customer_id"), col("new_customer_id")).alias("CUSTOMER_ID"),
    coalesce(col("leg_txn_date"), col("new_txn_date")).alias("TXN_DATE"),
    coalesce(col("leg_currency"), col("new_currency")).alias("CURRENCY"),
    coalesce(col("leg_region"), col("new_region")).alias("REGION"),
    coalesce(col("leg_channel"), col("new_channel")).alias("CHANNEL"),
    coalesce(col("leg_product_type"), col("new_product_type")).alias("PRODUCT_TYPE"),
    col("leg_amount").alias("LEGACY_AMOUNT"),
    col("new_amount").alias("NEW_SYSTEM_AMOUNT"),
    col("amount_diff").alias("AMOUNT_DIFF"),
    col("amount_diff_pct").alias("AMOUNT_DIFF_PCT"),
    col("leg_status").alias("LEGACY_STATUS"),
    col("new_status").alias("NEW_SYSTEM_STATUS"),
    col("validation_status").alias("VALIDATION_STATUS"),
    current_timestamp().alias("VALIDATED_AT"),
    lit(None).cast("string").alias("AI_EXPLANATION"),
    lit(None).cast("timestamp").alias("AI_EXPLAINED_AT"),
    current_timestamp().alias("LOADED_AT")
)

# 7. Push data directly into Snowflake
sfOptions = {
    "sfURL": "ue74066.ap-southeast-7.aws.snowflakecomputing.com",
    "sfUser": "VALIDATA_SVC_USER",
    "sfPassword": "ValidataP!p3line2026",
    "sfDatabase": "ValiData_DB",
    "sfSchema": "CURATED_SCHEMA",
    "sfWarehouse": "COMPUTE_WH",
    "sfRole": "SYSADMIN",
    "dbtable": "VALIDATION_RESULTS"
}

final_results.write \
    .format("snowflake") \
    .options(**sfOptions) \
    .mode("overwrite") \
    .save()

job.commit()
print("Consolidated Glue Job Run Complete.")
