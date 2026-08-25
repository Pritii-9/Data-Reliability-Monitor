# =============================================================================
#  Validata — Data Validation Engine
#  Local Reconciliation & Upload Pipeline
#  Usage: python scripts/run_reconciliation.py [--legacy PATH] [--new PATH] [--local-only]
# =============================================================================

import os
import sys
import argparse
import pandas as pd
import numpy as np
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from google import genai
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# --- PARSE COMMAND LINE ARGUMENTS ---
parser = argparse.ArgumentParser(description="Validata Local Reconciliation Tool")
parser.add_argument("--legacy", default="sample_data/test_legacy_transactions.csv", help="Path to legacy CSV source")
parser.add_argument("--new", default="sample_data/test_new_system_transactions.csv", help="Path to new system CSV source")
parser.add_argument("--local-only", action="store_true", help="Skip Snowflake and Gemini APIs, saving files locally instead")
args = parser.parse_args()

LEGACY_CSV_PATH = args.legacy
NEW_SYS_CSV_PATH = args.new
AMOUNT_TOLERANCE_PCT = 0.001  # 0.1%

# --- SNOWFLAKE CREDENTIALS ---
SF_ACCOUNT = os.getenv("SF_ACCOUNT")
SF_PASSWORD = os.getenv("SF_PASSWORD")
SF_USER = os.getenv("SF_USER")
SF_DATABASE = os.getenv("SF_DATABASE")
SF_WAREHOUSE = os.getenv("SF_WAREHOUSE")
SF_SCHEMA = os.getenv("SF_SCHEMA_CURATED")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not args.local_only and not all([SF_ACCOUNT, SF_PASSWORD, SF_USER, SF_DATABASE, SF_WAREHOUSE, SF_SCHEMA]):
    print("Error: Missing Snowflake connection credentials in environment variables.")
    sys.exit(1)

print("=" * 60)
print("  Validata — Local Reconciliation Engine")
if args.local_only:
    print("  [MODE: LOCAL MOCK / OFFLINE]")
print("=" * 60)

# 1. Read files
if not os.path.exists(LEGACY_CSV_PATH) or not os.path.exists(NEW_SYS_CSV_PATH):
    print(f"Error: Could not locate test CSV files at legacy path '{LEGACY_CSV_PATH}' or new system path '{NEW_SYS_CSV_PATH}'.")
    sys.exit(1)

print(f"Loading {LEGACY_CSV_PATH}...")
legacy_df = pd.read_csv(LEGACY_CSV_PATH)

print(f"Loading {NEW_SYS_CSV_PATH}...")
new_df = pd.read_csv(NEW_SYS_CSV_PATH)

# 2. Clean and Standardize (Trim spaces, uppercase enums, round amounts)
def clean_df(df, label):
    print(f"Cleaning [{label}] dataset...")
    df = df.copy()
    
    # Trim whitespaces
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()
        
    # Standardize columns
    df['currency'] = df['currency'].str.upper()
    df['status'] = df['status'].str.upper()
    df['region'] = df['region'].str.upper()
    df['channel'] = df['channel'].str.upper()
    df['product_type'] = df['product_type'].str.upper()
    
    # Round amount
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').round(2)
    
    # Replace empty with None
    df['customer_id'] = df['customer_id'].replace({"": None, "nan": None, "NaN": None})
    
    # Deduplicate on txn_id (keep first)
    before = len(df)
    df = df.drop_duplicates(subset=['txn_id'], keep='first')
    after = len(df)
    if before > after:
        print(f"  Dropped {before - after} duplicate txn_id rows.")
        
    return df

legacy_df = clean_df(legacy_df, "Legacy")
new_df = clean_df(new_df, "New System")

# 3. Join and Reconcile
print("\nReconciling datasets...")
# Prefix columns
leg_cols = {col: f"leg_{col}" for col in legacy_df.columns if col != 'txn_id'}
new_cols = {col: f"new_{col}" for col in new_df.columns if col != 'txn_id'}

legacy_prep = legacy_df.rename(columns=leg_cols)
new_prep = new_df.rename(columns=new_cols)

# Full outer join on txn_id
reconciled = pd.merge(legacy_prep, new_prep, on='txn_id', how='outer')

# Classify anomalies
def classify_row(row):
    leg_amt = row['leg_amount']
    new_amt = row['new_amount']
    leg_stat = row['leg_status']
    new_stat = row['new_status']
    
    if pd.isna(leg_amt):
        return 'PHANTOM'
    if pd.isna(new_amt):
        return 'MISSING'
    if leg_stat != new_stat:
        return 'STATUS_MISMATCH'
        
    # Calculate amount difference percent
    diff_pct = abs(leg_amt - new_amt) / (leg_amt if leg_amt != 0 else 1.0)
    if diff_pct > AMOUNT_TOLERANCE_PCT:
        return 'AMOUNT_MISMATCH'
        
    return 'MATCH'

reconciled['validation_status'] = reconciled.apply(classify_row, axis=1)

# Compute diff metrics
reconciled['amount_diff'] = np.abs(reconciled['leg_amount'] - reconciled['new_amount']).round(4)
reconciled['amount_diff_pct'] = (np.abs(reconciled['leg_amount'] - reconciled['new_amount']) / 
                                 reconciled['leg_amount'].replace(0, 1) * 100).round(4)

# Handle NaNs for sql upload
reconciled['amount_diff'] = reconciled['amount_diff'].fillna(0.0)
reconciled['amount_diff_pct'] = reconciled['amount_diff_pct'].fillna(0.0)

# Build unified fields
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

# Select final table columns
final_df = reconciled[[
    'txn_id', 'customer_id', 'txn_date', 'currency', 'region', 'channel', 'product_type',
    'legacy_amount', 'new_system_amount', 'amount_diff', 'amount_diff_pct',
    'legacy_status', 'new_system_status', 'validation_status'
]].copy()

final_df['validated_at'] = datetime.now(timezone.utc)
final_df['ai_explanation'] = None
final_df['ai_explained_at'] = None

# Ensure columns are uppercase for Snowflake write_pandas
final_df.columns = [col.upper() for col in final_df.columns]

# Replace float NaNs with None for Snowflake ingestion
final_df = final_df.replace({np.nan: None})

print("\nReconciliation Classification Summary:")
print(final_df['VALIDATION_STATUS'].value_counts())

# 4. Handle Mock Mode Local Output
if args.local_only:
    print("\n[LOCAL MOCK] Skipping Snowflake connection and Google Gemini API calls...")
    
    # Save the output DataFrame to local CSV
    local_out_csv = "sample_data/reconciliation_output_local.csv"
    final_df.to_csv(local_out_csv, index=False)
    print(f"[OK] Saved reconciliation output to: {local_out_csv}")
    
    # Generate local markdown report
    local_out_md = "sample_data/reconciliation_summary_local.md"
    
    mismatches = final_df[final_df['VALIDATION_STATUS'] != 'MATCH']
    mismatch_rows = []
    for idx, row in mismatches.iterrows():
        mismatch_rows.append(
            f"| {row['TXN_ID']} | {row['VALIDATION_STATUS']} | {row['LEGACY_AMOUNT']} | {row['NEW_SYSTEM_AMOUNT']} | {row['LEGACY_STATUS']} / {row['NEW_SYSTEM_STATUS']} |"
        )
    mismatch_table_content = "\n".join(mismatch_rows) if mismatch_rows else "| None | None | None | None | None |"

    summary_md = f"""# Local Reconciliation Audit Report

*Generated at: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}*
*Pipeline Mode: Local Mock (Offline)*

## 1. Summary Statistics
* **Total Transactions:** {len(final_df)}
* **Matches:** {len(final_df[final_df['VALIDATION_STATUS'] == 'MATCH'])}
* **Anomalies Detected:** {len(mismatches)}

### Status Count Breakdown:
{final_df['VALIDATION_STATUS'].value_counts().to_markdown()}

## 2. Identified Anomalies Table
| Transaction ID | Status | Legacy Amount | New System Amount | Legacy / New Status |
| :--- | :--- | :--- | :--- | :--- |
{mismatch_table_content}

*(AI Explanations and Snowflake updates skipped in local mock mode.)*
"""
    with open(local_out_md, "w") as f:
        f.write(summary_md)
    print(f"[OK] Generated local Markdown summary report: {local_out_md}")
    
    print("\nPipeline Complete! (Local Mode)")
    sys.exit(0)

# 5. Upload to Snowflake (Real Ingestion Flow)
print(f"\nConnecting to Snowflake account: {SF_ACCOUNT}...")
try:
    conn = snowflake.connector.connect(
        user=SF_USER,
        password=SF_PASSWORD,
        account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
        schema=SF_SCHEMA
    )
    cursor = conn.cursor()
    print("Truncating VALIDATION_RESULTS table...")
    cursor.execute("TRUNCATE TABLE VALIDATION_RESULTS")
    
    print("Uploading results via write_pandas...")
    success, nchunks, nrows, _ = write_pandas(
        conn=conn,
        df=final_df,
        table_name="VALIDATION_RESULTS",
        auto_create_table=False,
        quote_identifiers=False
    )
    print(f"Successfully uploaded {nrows} rows to Snowflake table: VALIDATION_RESULTS")
except Exception as e:
    print(f"Snowflake Connection/Upload Error: {e}")
    sys.exit(1)

# 6. Generate AI Explanations via Google Gemini (Real Ingestion Flow)
if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("your_"):
    print("\n[AI OBSERVABILITY] Gemini API key not found. Skipping explanations.")
    conn.close()
    sys.exit(0)

print("\nRunning Google Gemini AI Explanations...")
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Query anomaly rows that need explanation
    mismatches = final_df[final_df['VALIDATION_STATUS'] != 'MATCH'].copy()
    print(f"Found {len(mismatches)} anomalies to process with Gemini.")
    
    cursor_update = conn.cursor()
    for idx, row in mismatches.iterrows():
        txn_id = row['TXN_ID']
        status = row['VALIDATION_STATUS']
        
        prompt = f"""You are a senior data migration analyst writing an audit report.
A transaction was flagged during a validation between a legacy system and a new system.

Transaction details:
- Transaction ID     : {txn_id}
- Flag Type          : {status}
- Legacy Amount      : {row['LEGACY_AMOUNT']}
- New System Amount  : {row['NEW_SYSTEM_AMOUNT']}
- Amount Difference %: {row['AMOUNT_DIFF_PCT']}%
- Legacy Status      : {row['LEGACY_STATUS']}
- New System Status  : {row['NEW_SYSTEM_STATUS']}
- Currency           : {row['CURRENCY']}

In exactly 2-3 sentences: explain the likely root cause of this anomaly and recommend one specific remediation action. Be professional and concise."""

        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            explanation = response.text.strip()
            # Escape single quotes for SQL query
            safe_explanation = explanation.replace("'", "''")
            
            sql_update = f"""
                UPDATE VALIDATION_RESULTS
                SET AI_EXPLANATION = '{safe_explanation}',
                    AI_EXPLAINED_AT = CURRENT_TIMESTAMP()
                WHERE TXN_ID = '{txn_id}'
            """
            cursor_update.execute(sql_update)
            print(f"  [OK] Generated and saved explanation for {txn_id}")
        except Exception as gemini_err:
            print(f"  [ERROR] Error processing {txn_id}: {gemini_err}")
            
    print("\nAI Observability enrichment completed successfully.")
except Exception as e:
    print(f"AI Observability initialization error: {e}")
finally:
    conn.close()
    print("\nPipeline Complete!")
