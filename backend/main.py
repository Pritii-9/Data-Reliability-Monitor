from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel
from google import genai
import snowflake.connector
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Validata API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_conn():
    return snowflake.connector.connect(
        user="VALIDATA_SVC_USER",
        password="ValidataP!p3line2026",
        account="ue74066.ap-southeast-7.aws",
        warehouse="COMPUTE_WH",
        database="ValiData_DB",
        schema="CURATED_SCHEMA",
    )


@app.get("/api/summary")
def get_summary():
    """High-level pipeline KPIs for the dashboard header."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN validation_status = 'MATCH' THEN 1 ELSE 0 END) AS matched,
            SUM(CASE WHEN validation_status = 'AMOUNT_MISMATCH' THEN 1 ELSE 0 END) AS amount_mismatch,
            SUM(CASE WHEN validation_status = 'STATUS_MISMATCH' THEN 1 ELSE 0 END) AS status_mismatch,
            SUM(CASE WHEN validation_status = 'MISSING' THEN 1 ELSE 0 END) AS missing,
            SUM(CASE WHEN validation_status = 'PHANTOM' THEN 1 ELSE 0 END) AS phantom,
            ROUND(SUM(CASE WHEN validation_status = 'MATCH' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS match_rate
        FROM VALIDATION_RESULTS
    """)
    row = cur.fetchone()
    cols = [d[0].lower() for d in cur.description]
    conn.close()
    return dict(zip(cols, row))


@app.get("/api/results")
def get_results(
    status: Optional[str] = Query(None, description="Filter by validation_status"),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
):
    """Paginated validation results with optional status filter."""
    conn = get_conn()
    cur = conn.cursor()

    where = ""
    if status and status.upper() != "ALL":
        where = f"WHERE validation_status = '{status.upper()}'"

    cur.execute(f"""
        SELECT
            txn_id, validation_status, customer_id, currency, region, channel, product_type,
            legacy_amount, new_system_amount, amount_diff, amount_diff_pct,
            legacy_status, new_system_status
        FROM VALIDATION_RESULTS
        {where}
        ORDER BY validation_status, txn_id
        LIMIT {limit} OFFSET {offset}
    """)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]

    cur.execute(f"SELECT COUNT(*) FROM VALIDATION_RESULTS {where}")
    total = cur.fetchone()[0]
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(zip(cols, r)) for r in rows]
    }


@app.get("/api/anomalies")
def get_anomalies():
    """All non-MATCH rows with AI explanations for the audit report."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            txn_id, validation_status, currency, region, channel,
            legacy_amount, new_system_amount, amount_diff_pct,
            legacy_status, new_system_status,
            ai_explanation
        FROM VALIDATION_RESULTS
        WHERE validation_status != 'MATCH'
        ORDER BY validation_status, txn_id
    """)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


@app.get("/api/breakdown")
def get_breakdown():
    """Status breakdown by region and channel for charts."""
    conn = get_conn()
    cur = conn.cursor()

    # by region
    cur.execute("""
        SELECT region, validation_status, COUNT(*) as count
        FROM VALIDATION_RESULTS
        GROUP BY region, validation_status
        ORDER BY region, validation_status
    """)
    region_rows = cur.fetchall()

    # by channel
    cur.execute("""
        SELECT channel, validation_status, COUNT(*) as count
        FROM VALIDATION_RESULTS
        GROUP BY channel, validation_status
        ORDER BY channel, validation_status
    """)
    channel_rows = cur.fetchall()

    conn.close()
    return {
        "by_region": [{"region": r[0], "status": r[1], "count": r[2]} for r in region_rows],
        "by_channel": [{"channel": r[0], "status": r[1], "count": r[2]} for r in channel_rows],
    }


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []


@app.post("/api/chat")
def ai_chat(req: ChatRequest):
    """Query Snowflake results and get AI analytics via Gemini."""
    try:
        conn = get_conn()
        cur = conn.cursor()

        # Query high-level KPIs
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN validation_status = 'MATCH' THEN 1 ELSE 0 END) AS matched,
                SUM(CASE WHEN validation_status = 'AMOUNT_MISMATCH' THEN 1 ELSE 0 END) AS amount_mismatch,
                SUM(CASE WHEN validation_status = 'STATUS_MISMATCH' THEN 1 ELSE 0 END) AS status_mismatch,
                SUM(CASE WHEN validation_status = 'MISSING' THEN 1 ELSE 0 END) AS missing,
                SUM(CASE WHEN validation_status = 'PHANTOM' THEN 1 ELSE 0 END) AS phantom
            FROM VALIDATION_RESULTS
        """)
        kpis = cur.fetchone()

        # Query top discrepancies to inject into prompt context
        cur.execute("""
            SELECT txn_id, validation_status, currency, region, legacy_amount, new_system_amount, amount_diff_pct, ai_explanation
            FROM VALIDATION_RESULTS
            WHERE validation_status != 'MATCH'
            ORDER BY amount_diff_pct DESC NULLS LAST
            LIMIT 15
        """)
        anoms = cur.fetchall()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Snowflake query failed: {str(e)}")

    # Format data for LLM prompt context
    kpi_desc = f"Total transactions: {kpis[0]}, Matches: {kpis[1]} (Match Rate: {round(kpis[1]*100.0/kpis[0], 2) if kpis[0] else 0}%), Amount Mismatches: {kpis[2]}, Status Mismatches: {kpis[3]}, Missing Records: {kpis[4]}, Phantom Records: {kpis[5]}."
    
    anom_list = []
    for r in anoms:
        diff_val = f"{round(r[6], 2)}%" if r[6] is not None else "0%"
        anom_list.append(
            f"- TXN: {r[0]} | Status: {r[1]} | Region: {r[3]} | Currency: {r[2]} | Legacy: {r[4]} | New: {r[5]} | Diff %: {diff_val} | AI explanation: {r[7] or 'Pending'}"
        )
    anom_desc = "\n".join(anom_list)

    system_context = (
        f"SYSTEM OVERVIEW:\n{kpi_desc}\n\n"
        f"RECENT DISCREPANCIES / ANOMALIES (Top 15 by diff %):\n{anom_desc}"
    )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured in the server environment.")

    client = genai.Client(api_key=api_key)

    system_instruction = f"""You are the senior data analyst AI Copilot for 'Validata' (Data Validation Engine).
You assist operators in troubleshooting migration anomalies between a legacy ledger and a new database.
All validation data is stored in a Snowflake Data Lake.

Here is the current health status and anomaly details from Snowflake:
{system_context}

Guidelines:
1. Keep answers concise, highly professional, and direct (typically 2-4 sentences).
2. Answer based on the Snowflake records provided above.
3. If asked about a transaction ID not in this list, check if it matches the general format of txn IDs, and advise the user to search on the Results page or trigger validation for that record.
4. Recommend remediation steps (e.g. check gateways, fix ledgers, re-trigger ingestion) when analyzing anomalies."""

    try:
        # Build chat history prompt context
        prompts = []
        for item in (req.history or []):
            role = "User" if item.get("role") == "user" else "Assistant"
            prompts.append(f"{role}: {item.get('content')}")
        prompts.append(f"User: {req.message}")
        user_prompt = "\n".join(prompts)

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=user_prompt,
            config={"system_instruction": system_instruction}
        )
        return {"reply": response.text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini generation error: {str(e)}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "Validata API"}
