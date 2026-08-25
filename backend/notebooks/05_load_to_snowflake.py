# =============================================================================
#  Validata — Data Validation Engine
#  AWS Integration Notebook: 05_load_to_snowflake
#  Layer  : Curated Integration
#  Source : s3://validata-datalake/curated/validation_results/
#  Dest   : Snowflake (ValiData_DB.CURATED_SCHEMA.VALIDATION_RESULTS)
#  Stack  : AWS S3 + AWS Glue (PySpark) + Snowflake + Google Gemini
# =============================================================================

import os
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv

load_dotenv()

# --- S3 CONFIGURATION ---
BUCKET = "s3://validata-datalake"
CURATED_RESULTS_PATH = f"{BUCKET}/curated/validation_results/"

# --- SNOWFLAKE CREDENTIALS ---
SF_ACCOUNT   = os.getenv("SF_ACCOUNT", "ue74066.ap-southeast-7.aws")
SF_PASSWORD  = os.getenv("SF_PASSWORD", "ValidataP!p3line2026")
SF_USER      = os.getenv("SF_USER", "VALIDATA_SVC_USER")
SF_DATABASE  = os.getenv("SF_DATABASE", "ValiData_DB")
SF_WAREHOUSE = os.getenv("SF_WAREHOUSE", "COMPUTE_WH")
SF_SCHEMA    = os.getenv("SF_SCHEMA_CURATED", "CURATED_SCHEMA")

s3_options = {
    "key": os.getenv("AWS_ACCESS_KEY_ID"),
    "secret": os.getenv("AWS_SECRET_ACCESS_KEY")
}

print("1. Reading curated results directly from S3...")
pdf_results = pd.read_parquet(CURATED_RESULTS_PATH, storage_options=s3_options)

# Snowflake strictly expects UPPERCASE column names
pdf_results.columns = [col.upper() for col in pdf_results.columns]

print("2. Connecting to Snowflake...")
conn = snowflake.connector.connect(
    user=SF_USER,
    password=SF_PASSWORD,
    account=SF_ACCOUNT,
    warehouse=SF_WAREHOUSE,
    database=SF_DATABASE,
    schema=SF_SCHEMA
)

cursor = conn.cursor()
cursor.execute("TRUNCATE TABLE VALIDATION_RESULTS")

print("3. Writing data to Snowflake...")
success, nchunks, nrows, _ = write_pandas(
    conn=conn, 
    df=pdf_results, 
    table_name="VALIDATION_RESULTS", 
    auto_create_table=False,
    quote_identifiers=False
)

print(f"Notebook 05 Complete! Successfully wrote {nrows} rows directly into Snowflake!")
conn.close()
