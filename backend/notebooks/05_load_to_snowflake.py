import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

import os
from dotenv import load_dotenv

load_dotenv()

# --- NATIVE AWS S3 PATHS ---
BUCKET = "s3://validata-datalake"
CURATED_RESULTS_PATH = f"{BUCKET}/curated/validation_results/"

# --- SNOWFLAKE CREDENTIALS ---
SF_ACCOUNT   = "ue74066.ap-southeast-7.aws"
SF_PASSWORD  = "ValidataP!p3line2026"

s3_options = {
    "key": os.getenv("AWS_ACCESS_KEY_ID"),
    "secret": os.getenv("AWS_SECRET_ACCESS_KEY")
}

print("1. Reading curated results directly from S3...")
# Pandas natively reads Parquet from S3! No PySpark needed.
pdf_results = pd.read_parquet(CURATED_RESULTS_PATH, storage_options=s3_options)

# Snowflake strictly expects UPPERCASE column names
pdf_results.columns = [col.upper() for col in pdf_results.columns]

print("2. Connecting to Snowflake...")
conn = snowflake.connector.connect(
    user="VALIDATA_SVC_USER",
    password=SF_PASSWORD,
    account=SF_ACCOUNT,
    warehouse="COMPUTE_WH",
    database="ValiData_DB",
    schema="CURATED_SCHEMA"
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
