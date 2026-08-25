# Validata — AI Anomaly Explanation
# Queries discrepancies from Snowflake and generates root cause explanations using Google Gemini.

import os, time
import pandas as pd
from google import genai
from datetime import datetime, timezone
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

# Snowflake & Gemini credentials
SF_ACCOUNT     = os.getenv("SF_ACCOUNT", "ue74066.ap-southeast-7.aws")
SF_PASSWORD    = os.getenv("SF_PASSWORD", "ValidataP!p3line2026")
SF_USER        = os.getenv("SF_USER", "VALIDATA_SVC_USER")
SF_DATABASE    = os.getenv("SF_DATABASE", "ValiData_DB")
SF_WAREHOUSE   = os.getenv("SF_WAREHOUSE", "COMPUTE_WH")
SF_SCHEMA      = os.getenv("SF_SCHEMA_CURATED", "CURATED_SCHEMA")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)
EXPLAIN_STATUSES = ["MISSING", "PHANTOM", "AMOUNT_MISMATCH", "STATUS_MISMATCH"]

conn = snowflake.connector.connect(
    user=SF_USER,
    password=SF_PASSWORD,
    account=SF_ACCOUNT,
    warehouse=SF_WAREHOUSE,
    database=SF_DATABASE,
    schema=SF_SCHEMA,
    role="SYSADMIN"
)

# Fetch unmatched transactions
cursor = conn.cursor()
statuses_sql = ", ".join([f"'{s}'" for s in EXPLAIN_STATUSES])
cursor.execute(f"""
    SELECT txn_id, validation_status, legacy_amount, new_system_amount,
           amount_diff_pct, legacy_status, new_system_status, currency
    FROM VALIDATION_RESULTS
    WHERE validation_status IN ({statuses_sql})
""")
rows = cursor.fetchall()
cols = [desc[0] for desc in cursor.description]
df_mismatches = pd.DataFrame(rows, columns=cols)
total_mismatches = len(df_mismatches)

def build_prompt(row) -> str:
    return f"""You are a senior data migration analyst writing an audit report.
A transaction was flagged during a validation between a legacy system and a new system.

Transaction details:
- Transaction ID     : {row['TXN_ID']}
- Flag Type          : {row['VALIDATION_STATUS']}
- Legacy Amount      : {row['LEGACY_AMOUNT']}
- New System Amount  : {row['NEW_SYSTEM_AMOUNT']}
- Amount Difference %: {row['AMOUNT_DIFF_PCT']}
- Legacy Status      : {row['LEGACY_STATUS']}
- New System Status  : {row['NEW_SYSTEM_STATUS']}
- Currency           : {row['CURRENCY']}

In exactly 2-3 sentences: explain the likely root cause of this anomaly and recommend one specific remediation action. Be professional and concise."""

# Generate explanation content via Gemini API and update Snowflake row-by-row
cursor2 = conn.cursor()
success_count = 0
for i, row in df_mismatches.iterrows():
    txn_id = row['TXN_ID']
    prompt = build_prompt(row)
    
    explanation = "Explanation unavailable."
    max_retries = 5
    backoff = 2.0
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt
            )
            explanation = response.text.strip()
            break
        except Exception as e:
            err_msg = str(e)
            print(f"  [WARNING] Attempt {attempt + 1} failed for {txn_id}: {err_msg}", flush=True)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("  [INFO] Rate limit hit. Sleeping 60s to reset quota window...", flush=True)
                time.sleep(60.0)
            elif attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"  [ERROR] Max retries reached for {txn_id}. Defaulting.", flush=True)
                
    # Update Snowflake row immediately
    try:
        safe_expl = explanation.replace("'", "''")
        cursor2.execute(f"""
            UPDATE VALIDATION_RESULTS
            SET AI_EXPLANATION = '{safe_expl}',
                AI_EXPLAINED_AT = CURRENT_TIMESTAMP()
            WHERE TXN_ID = '{txn_id}'
        """)
        success_count += 1
        print(f"  [OK] Saved AI explanation for {txn_id} ({success_count}/{len(df_mismatches)})", flush=True)
    except Exception as db_err:
        print(f"  [ERROR] Failed to save to Snowflake for {txn_id}: {db_err}", flush=True)
        
    time.sleep(3.5)

conn.close()
print(f"Notebook 06 Complete. Successfully updated {success_count} rows in Snowflake.", flush=True)
