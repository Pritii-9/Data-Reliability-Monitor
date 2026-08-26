import os
import pandas as pd
import numpy as np
import snowflake.connector
from dotenv import load_dotenv

# Load env
load_dotenv('.env')

SF_ACCOUNT = os.getenv("SF_ACCOUNT")
SF_PASSWORD = os.getenv("SF_PASSWORD")
SF_USER = os.getenv("SF_USER")
SF_DATABASE = os.getenv("SF_DATABASE")
SF_WAREHOUSE = os.getenv("SF_WAREHOUSE")
SF_SCHEMA = os.getenv("SF_SCHEMA_CURATED")

# 1. Connect and describe table
print("Connecting to Snowflake...")
conn = snowflake.connector.connect(
    user=SF_USER,
    password=SF_PASSWORD,
    account=SF_ACCOUNT,
    warehouse=SF_WAREHOUSE,
    database=SF_DATABASE,
    schema=SF_SCHEMA
)

cursor = conn.cursor()
cursor.execute("DESCRIBE TABLE VALIDATION_RESULTS")
desc_cols = cursor.fetchall()
print("\n--- SNOWFLAKE TABLE SCHEMA (VALIDATION_RESULTS) ---")
for col in desc_cols:
    name, col_type, nullable = col[0], col[1], col[3]
    print(f"Column: {name:<20} Type: {col_type:<20} Nullable: {nullable}")

# 2. Inspect DataFrame from run_reconciliation logic
print("\n--- RUNNING RECONCILIATION DATAFRAME BUILD ---")
legacy_df = pd.read_csv('backend/sample_data/test_legacy_transactions.csv')
new_df = pd.read_csv('backend/sample_data/test_new_system_transactions.csv')

# Clean
for df in [legacy_df, new_df]:
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()
    df['currency'] = df['currency'].str.upper()
    df['status'] = df['status'].str.upper()
    df['region'] = df['region'].str.upper()
    df['channel'] = df['channel'].str.upper()
    df['product_type'] = df['product_type'].str.upper()
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').round(2)
    df['customer_id'] = df['customer_id'].replace({"": None, "nan": None, "NaN": None})

legacy_df = legacy_df.drop_duplicates(subset=['txn_id'], keep='first')
new_df = new_df.drop_duplicates(subset=['txn_id'], keep='first')

leg_cols = {col: f"leg_{col}" for col in legacy_df.columns if col != 'txn_id'}
new_cols = {col: f"new_{col}" for col in new_df.columns if col != 'txn_id'}
reconciled = pd.merge(legacy_df.rename(columns=leg_cols), new_df.rename(columns=new_cols), on='txn_id', how='outer')

reconciled['validation_status'] = 'MATCH' # Dummy
reconciled['amount_diff'] = 0.0
reconciled['amount_diff_pct'] = 0.0
reconciled['customer_id'] = reconciled['leg_customer_id'].combine_first(reconciled['new_customer_id'])
reconciled['txn_date'] = reconciled['leg_txn_date'].combine_first(reconciled['new_txn_date'])
reconciled['currency'] = reconciled['leg_currency'].combine_first(reconciled['new_currency'])
reconciled['region'] = reconciled['leg_region'].combine_first(reconciled['new_region'])
reconciled['channel'] = reconciled['leg_channel'].combine_first(reconciled['new_channel'])
reconciled['product_type'] = reconciled['leg_product_type'].combine_first(reconciled['new_product_type'])
reconciled['legacy_amount'] = reconciled['leg_amount']
reconciled['new_system_amount'] = reconciled['new_amount']
reconciled['legacy_status'] = reconciled['leg_status']
reconciled['new_system_status'] = reconciled['new_status']

from datetime import datetime, timezone
final_df = reconciled[[
    'txn_id', 'customer_id', 'txn_date', 'currency', 'region', 'channel', 'product_type',
    'legacy_amount', 'new_system_amount', 'amount_diff', 'amount_diff_pct',
    'legacy_status', 'new_system_status', 'validation_status'
]].copy()

final_df['validated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
final_df['ai_explanation'] = None
final_df['ai_explained_at'] = None
final_df.columns = [col.upper() for col in final_df.columns]
final_df = final_df.replace({np.nan: None})

print("\n--- DATAFRAME ROW INSPECTION ---")
for col in final_df.columns:
    nulls = final_df[col].isna().sum()
    print(f"DF Column: {col:<20} Nulls: {nulls:<5} Dtype: {final_df[col].dtype}")

conn.close()
