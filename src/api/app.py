import sys
import asyncio
import os
import io
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
import json
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.db.database import SessionLocal, PipelineRun, CheckResult, Ticket
from src.engine.ai_engine import generate_ai_root_cause_analysis, generate_file_ai_summary
from src.engine.contract_validator import evaluate_contract

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("api_engine")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Data Reliability Control Center API",
    description="Decoupled backend engine for real-time data validation and AI-driven Root Cause Analysis (RCA).",
    version="1.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: str = Depends(api_key_header)):
    expected_key = os.getenv("API_SECRET_KEY", "DRM_DEFAULT_DEV_KEY")
    if api_key != expected_key and expected_key != "DRM_DEFAULT_DEV_KEY":
        logger.warning(f"Failed authentication attempt with key: {api_key}")
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PYDANTIC SCHEMAS ---
class ValidationCheck(BaseModel):
    check_name: str
    status: str  # 'PASS' or 'FAIL'
    details: str

class AnalysisResponse(BaseModel):
    filename: str
    status: str  # 'SUCCESS' or 'FAILURE'
    total_rows: int
    total_columns: int
    checks: List[ValidationCheck]
    root_cause_analysis: Optional[str] = None
    storage_path: Optional[str] = None

# --- API ENDPOINTS ---
@app.get("/")
@limiter.limit("30/minute")
async def root(request: Request):
    return {"message": "Data Reliability Control Center API is active.", "docs": "/docs"}

@app.post("/ai-summarize-file")
@limiter.limit("10/minute")
async def ai_summarize_file(request: Request, file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    """
    RAG-style AI Document & Data Intelligence endpoint.
    Accepts PDF, CSV, or TXT files and returns structured Google Gemini AI Analysis
    (Overview, Successes, Issues, Root Cause Action Plan).
    """
    filename = file.filename.lower()
    if not (filename.endswith(".csv") or filename.endswith(".pdf") or filename.endswith(".txt")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported format. Upload CSV, PDF, or TXT files."
        )
    contents = await file.read()
    summary_result = generate_file_ai_summary(file.filename, contents)
    return summary_result

@app.post("/analyze-upload", response_model=AnalysisResponse)
@limiter.limit("10/minute")
async def analyze_upload(
    request: Request,
    file: UploadFile = File(...),
    schema_json: Optional[str] = Form(None),
    api_key: str = Depends(verify_api_key)
):
    """
    Asynchronously accepts a CSV file upload, runs data quality checks,
    and returns AI-driven Root Cause Analysis if validation fails.
    """
    logger.info(f"Received file upload for analysis: {file.filename}")
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only CSV files are supported."
        )

    contents = await file.read()
    
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        logger.error(f"Failed to parse CSV {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Corrupted CSV payload: {str(e)}"
        )

    contract_source = None
    if schema_json:
        try:
            parsed = json.loads(schema_json)
            if isinstance(parsed, list):
                contract_source = {"schema": {"required_columns": parsed}}
            elif isinstance(parsed, dict):
                contract_source = parsed
            else:
                contract_source = schema_json
        except Exception:
            contract_source = schema_json

    raw_checks, raw_failed = evaluate_contract(df, contract_source)
    checks = [ValidationCheck(check_name=c.check_name, status=c.status, details=c.details) for c in raw_checks]
    failed_checks = [ValidationCheck(check_name=c.check_name, status=c.status, details=c.details) for c in raw_failed]

    pipeline_status = "FAILURE" if failed_checks else "SUCCESS"
    
    rca_result = None
    if pipeline_status == "FAILURE":
        rca_result = generate_ai_root_cause_analysis(failed_checks, df)

    destination_prefix = "processed" if pipeline_status == "SUCCESS" else "quarantine"
    file_path = f"{destination_prefix}/{file.filename}"
    
    if supabase:
        try:
            supabase.storage.from_("data-pipeline").upload(
                file=contents,
                path=file_path,
                file_options={"content-type": "text/csv"}
            )
            final_storage_path = f"supabase://storage/data-pipeline/{file_path}"
        except Exception as e:
            print(f"Supabase upload failed, falling back to local: {e}")
            os.makedirs(f"./data/{destination_prefix}", exist_ok=True)
            local_path = f"./data/{file_path}"
            with open(local_path, "wb") as f:
                f.write(contents)
            final_storage_path = local_path
    else:
        os.makedirs(f"./data/{destination_prefix}", exist_ok=True)
        local_path = f"./data/{file_path}"
        with open(local_path, "wb") as f:
            f.write(contents)
        final_storage_path = local_path

    response_data = AnalysisResponse(
        filename=file.filename,
        status=pipeline_status,
        total_rows=len(df),
        total_columns=len(df.columns),
        checks=checks,
        root_cause_analysis=rca_result,
        storage_path=final_storage_path
    )
    
    db = SessionLocal()
    try:
        new_run = PipelineRun(
            file_name=file.filename,
            storage_location=final_storage_path,
            status=pipeline_status,
            total_checks=len(checks),
            passed_checks=len(checks) - len(failed_checks),
            failed_checks=len(failed_checks)
        )
        db.add(new_run)
        db.commit()
        db.refresh(new_run)

        for chk in checks:
            db.add(CheckResult(run_id=new_run.id, check_name=chk.check_name, status=chk.status, details=chk.details))
            
        if failed_checks:
            desc = f"**File Name:** `{file.filename}`\n**Pipeline Run ID:** `{new_run.id}`\n\n### AI Root Cause Analysis\n{rca_result}"
            db.add(Ticket(title=f"Validation Failure: {file.filename}", description=desc, severity="HIGH"))
            
        db.commit()
        logger.info(f"Analysis saved to database. Run ID: {new_run.id}")
    except Exception as e:
        logger.error(f"Database persist error: {e}")
        db.rollback()
    finally:
        db.close()

    return response_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
