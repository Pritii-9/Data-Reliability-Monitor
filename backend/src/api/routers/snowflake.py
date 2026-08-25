import os
import time
import snowflake.connector
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from google import genai

router = APIRouter()

# --- Mock Connection Classes for Offline Development Fallback ---

class MockCursor:
    def __init__(self):
        self.description = []
        self.rows = []
        self.index = 0

    def execute(self, query: str, params=None):
        q = query.strip().upper()
        self.index = 0
        if "COUNT(*)" in q and "CASE WHEN" in q:
            # Summary stats mock
            self.description = [("total",), ("matched",), ("amount_mismatch",), ("status_mismatch",), ("missing",), ("phantom",), ("match_rate",)]
            self.rows = [(250, 210, 15, 10, 10, 5, 84.0)]
        elif "SELECT" in q and "CUSTOMER_ID" in q:
            # Paginated results mock
            self.description = [
                ("txn_id",), ("validation_status",), ("customer_id",), ("currency",), 
                ("region",), ("channel",), ("product_type",), ("legacy_amount",), 
                ("new_system_amount",), ("amount_diff",), ("amount_diff_pct",),
                ("legacy_status",), ("new_system_status",)
            ]
            self.rows = [
                ("TXN-101", "AMOUNT_MISMATCH", "CUST-01", "USD", "US", "WEB", "RETAIL", 1000.0, 1050.0, 50.0, 5.0, "SETTLED", "SETTLED"),
                ("TXN-102", "STATUS_MISMATCH", "CUST-02", "EUR", "EU", "MOBILE", "RETAIL", 200.0, 200.0, 0.0, 0.0, "PENDING", "FAILED"),
                ("TXN-103", "MISSING", "CUST-03", "GBP", "UK", "API", "RETAIL", 500.0, None, None, None, "SETTLED", None),
                ("TXN-104", "PHANTOM", "CUST-04", "JPY", "APAC", "API", "RETAIL", None, 300.0, None, None, None, "SETTLED")
            ]
            if params and len(params) > 0 and params[0] != "ALL":
                self.rows = [r for r in self.rows if r[1] == params[0]]
        elif "SELECT COUNT(*)" in q:
            # Count query mock
            self.description = [("count",)]
            self.rows = [(250,)]
        elif "VALIDATION_STATUS !=" in q:
            # Anomalies list mock
            self.description = [
                ("txn_id",), ("validation_status",), ("currency",), ("region",), ("channel",),
                ("legacy_amount",), ("new_system_amount",), ("amount_diff_pct",),
                ("legacy_status",), ("new_system_status",), ("ai_explanation",)
            ]
            self.rows = [
                ("TXN-101", "AMOUNT_MISMATCH", "USD", "US", "WEB", 1000.0, 1050.0, 5.0, "SETTLED", "SETTLED", "Gateway fee mismatch of $50. Mocked."),
                ("TXN-102", "STATUS_MISMATCH", "EUR", "EU", "MOBILE", 200.0, 200.0, 0.0, "PENDING", "FAILED", "Status mismatch: legacy Pending vs new Failed. Mocked."),
                ("TXN-103", "MISSING", "GBP", "UK", "API", 500.0, None, None, "SETTLED", None, "Transaction missing from new ledger system. Mocked."),
                ("TXN-104", "PHANTOM", "JPY", "APAC", "API", None, 300.0, None, None, "SETTLED", "Transaction exists in new database but missing in legacy ledger. Mocked.")
            ]
        elif "GROUP BY REGION" in q:
            # Region breakdown mock
            self.description = [("region",), ("validation_status",), ("count",)]
            self.rows = [
                ("US", "MATCH", 100), ("US", "AMOUNT_MISMATCH", 15),
                ("EU", "MATCH", 80), ("EU", "STATUS_MISMATCH", 10),
                ("UK", "MATCH", 30), ("UK", "MISSING", 10)
            ]
        elif "GROUP BY CHANNEL" in q:
            # Channel breakdown mock
            self.description = [("channel",), ("validation_status",), ("count",)]
            self.rows = [
                ("WEB", "MATCH", 110), ("WEB", "AMOUNT_MISMATCH", 10),
                ("MOBILE", "MATCH", 70), ("MOBILE", "STATUS_MISMATCH", 10),
                ("API", "MATCH", 30), ("API", "MISSING", 10)
            ]
        else:
            self.description = [("count",)]
            self.rows = [(0,)]

    def fetchone(self):
        if self.index < len(self.rows):
            row = self.rows[self.index]
            self.index += 1
            return row
        return None

    def fetchall(self):
        return self.rows

class MockConnection:
    def cursor(self):
        return MockCursor()
    def close(self):
        pass

# --- 60-Second TTL Cache Implementation ---

class TTLCache:
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self.cache = {}

    def get(self, key: str):
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            del self.cache[key]
        return None

    def set(self, key: str, value):
        self.cache[key] = (value, time.time() + self.ttl)

    def clear(self):
        self.cache.clear()

db_cache = TTLCache(ttl_seconds=60)

def get_conn():
    # Attempt Snowflake connection; fallback to mock connection if offline/credentials missing
    try:
        return snowflake.connector.connect(
            user=os.getenv("SF_USER", "VALIDATA_SVC_USER"),
            password=os.getenv("SF_PASSWORD", "ValidataP!p3line2026"),
            account=os.getenv("SF_ACCOUNT", "ue74066.ap-southeast-7.aws"),
            warehouse=os.getenv("SF_WAREHOUSE", "COMPUTE_WH"),
            database=os.getenv("SF_DATABASE", "ValiData_DB"),
            schema=os.getenv("SF_SCHEMA_CURATED", "CURATED_SCHEMA"),
            login_timeout=3,
        )
    except Exception as e:
        print(f"[WARNING] Snowflake offline ({e}). Running in Mock mode.")
        return MockConnection()

# --- API Endpoints ---

@router.post("/clear-cache")
def clear_cache():
    db_cache.clear()
    return {"status": "success", "message": "Cache cleared."}

@router.get("/summary")
def get_summary(refresh: bool = Query(False)):
    if not refresh:
        cached = db_cache.get("summary")
        if cached is not None:
            return cached

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

    result = dict(zip(cols, row))
    db_cache.set("summary", result)
    return result

@router.get("/results")
def get_results(
    status: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    refresh: bool = Query(False),
):
    cache_key = f"results_{status}_{limit}_{offset}"
    if not refresh:
        cached = db_cache.get(cache_key)
        if cached is not None:
            return cached

    conn = get_conn()
    cur = conn.cursor()

    if status and status.upper() != "ALL":
        query = """
            SELECT
                txn_id, validation_status, customer_id, currency, region, channel, product_type,
                legacy_amount, new_system_amount, amount_diff, amount_diff_pct,
                legacy_status, new_system_status
            FROM VALIDATION_RESULTS
            WHERE validation_status = %s
            ORDER BY validation_status, txn_id
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (status.upper(), limit, offset))
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        cur.execute("SELECT COUNT(*) FROM VALIDATION_RESULTS WHERE validation_status = %s", (status.upper(),))
        total = cur.fetchone()[0]
    else:
        query = """
            SELECT
                txn_id, validation_status, customer_id, currency, region, channel, product_type,
                legacy_amount, new_system_amount, amount_diff, amount_diff_pct,
                legacy_status, new_system_status
            FROM VALIDATION_RESULTS
            ORDER BY validation_status, txn_id
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (limit, offset))
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        cur.execute("SELECT COUNT(*) FROM VALIDATION_RESULTS")
        total = cur.fetchone()[0]

    conn.close()

    result = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(zip(cols, r)) for r in rows]
    }
    db_cache.set(cache_key, result)
    return result

@router.get("/anomalies")
def get_anomalies(refresh: bool = Query(False)):
    if not refresh:
        cached = db_cache.get("anomalies")
        if cached is not None:
            return cached

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

    result = [dict(zip(cols, r)) for r in rows]
    db_cache.set("anomalies", result)
    return result

@router.get("/breakdown")
def get_breakdown(refresh: bool = Query(False)):
    if not refresh:
        cached = db_cache.get("breakdown")
        if cached is not None:
            return cached

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT region, validation_status, COUNT(*) as count
        FROM VALIDATION_RESULTS
        GROUP BY region, validation_status
        ORDER BY region, validation_status
    """)
    region_rows = cur.fetchall()

    cur.execute("""
        SELECT channel, validation_status, COUNT(*) as count
        FROM VALIDATION_RESULTS
        GROUP BY channel, validation_status
        ORDER BY channel, validation_status
    """)
    channel_rows = cur.fetchall()
    conn.close()

    result = {
        "by_region": [{"region": r[0], "status": r[1], "count": r[2]} for r in region_rows],
        "by_channel": [{"channel": r[0], "status": r[1], "count": r[2]} for r in channel_rows],
    }
    db_cache.set("breakdown", result)
    return result

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

@router.post("/chat")
def ai_chat(req: ChatRequest):
    # Retrieve details to construct prompt context for Gemini
    try:
        conn = get_conn()
        cur = conn.cursor()
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
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    kpi_desc = f"Total: {kpis[0]}, Matches: {kpis[1]} ({round(kpis[1]*100.0/kpis[0], 2) if kpis[0] else 0}%), Mismatch: {kpis[2]}, Status: {kpis[3]}, Missing: {kpis[4]}, Phantom: {kpis[5]}."
    anom_list = []
    for r in anoms:
        diff_val = f"{round(r[6], 2)}%" if r[6] is not None else "0%"
        anom_list.append(
            f"TXN: {r[0]} | Status: {r[1]} | Region: {r[3]} | Legacy: {r[4]} | New: {r[5]} | Diff: {diff_val} | AI: {r[7] or 'Pending'}"
        )
    anom_desc = "\n".join(anom_list)

    system_context = f"KPIs:\n{kpi_desc}\n\nDiscrepancies:\n{anom_desc}"
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")

    client = genai.Client(api_key=api_key)

    system_instruction = f"""You are the senior data analyst AI Copilot for 'Validata' (Data Validation Engine).
You assist operators in troubleshooting migration anomalies between a legacy ledger and a new database.
All validation data is stored in a Snowflake Data Lake.

Context:
{system_context}

Guidelines:
1. Keep answers concise, highly professional, and direct (typically 2-4 sentences).
2. Answer based on the Snowflake records provided above.
3. If asked about a transaction ID not in this list, check if it matches the general format of txn IDs, and advise the user to search on the Results page or trigger validation for that record.
4. Recommend remediation steps (e.g. check gateways, fix ledgers, re-trigger ingestion) when analyzing anomalies.
5. When suggesting a data correction or database update, always provide the exact SQL script inside a markdown code block (e.g., ```sql\nUPDATE ...\n```) so the user can easily copy and execute it."""

    try:
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
        raise HTTPException(status_code=500, detail=f"Gemini error: {str(e)}")
