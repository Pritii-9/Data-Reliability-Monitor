# =============================================================================
#  Validata — Data Validation Engine
#  Notebook: 06_ai_anomaly_explanation
#  AI Layer : Google Gemini 2.0 Flash
#  Source   : ValiData_DB.CURATED_SCHEMA.VALIDATION_RESULTS
# =============================================================================

import os, time
import pandas as pd
from google import genai
from datetime import datetime, timezone
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

# --- CREDENTIALS ---
SF_ACCOUNT     = "ue74066.ap-southeast-7.aws"
SF_PASSWORD    = "ValidataP!p3line2026"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print(f"Using Gemini API key: {GEMINI_API_KEY[:10]}...")
client = genai.Client(api_key=GEMINI_API_KEY)
EXPLAIN_STATUSES = ["MISSING", "PHANTOM", "AMOUNT_MISMATCH", "STATUS_MISMATCH"]

print("=" * 60)
print("  Validata — 06 AI Anomaly Explanation (Gemini 2.0 Flash)")
print("=" * 60)

# 1. Connect to Snowflake
conn = snowflake.connector.connect(
    user="VALIDATA_SVC_USER",
    password=SF_PASSWORD,
    account=SF_ACCOUNT,
    warehouse="COMPUTE_WH",
    database="ValiData_DB",
    schema="CURATED_SCHEMA"
)

# 2. Fetch mismatch rows using native cursor (avoids Pandas timestamp bug)
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
print(f"Mismatch rows to explain : {total_mismatches}\n")

# 3. Build Prompt
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

# 4. Generate Explanations
explanations = []
for i, row in df_mismatches.iterrows():
    txn_id = row['TXN_ID']
    prompt = build_prompt(row)
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        explanation = response.text.strip()
        explanations.append(explanation)
        print(f"  [{i+1}/{total_mismatches}] {txn_id} --> OK")
    except Exception as e:
        explanations.append("Explanation unavailable.")
        print(f"  [{i+1}/{total_mismatches}] {txn_id} --> ERROR: {e}")
    time.sleep(0.5)

# 5. Write explanations back to Snowflake
df_mismatches['AI_EXPLANATION'] = explanations
print("\nUpdating Snowflake VALIDATION_RESULTS with AI explanations...")
cursor2 = conn.cursor()
success_count = 0
for i, row in df_mismatches.iterrows():
    safe_expl = row['AI_EXPLANATION'].replace("'", "''")
    cursor2.execute(f"""
        UPDATE VALIDATION_RESULTS
        SET AI_EXPLANATION = '{safe_expl}',
            AI_EXPLAINED_AT = CURRENT_TIMESTAMP()
        WHERE TXN_ID = '{row['TXN_ID']}'
    """)
    success_count += 1

conn.close()
print(f"[OK] Updated {success_count} rows in Snowflake!")
print("\nRun this in Snowflake to verify:")
print("SELECT TXN_ID, VALIDATION_STATUS, AI_EXPLANATION FROM VALIDATION_RESULTS WHERE VALIDATION_STATUS != 'MATCH';")
