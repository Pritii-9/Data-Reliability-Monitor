import sys
import asyncio
import os
import io
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Fix Windows ProactorEventLoop ConnectionResetError [WinError 10054] issue
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Initialize FastAPI App
app = FastAPI(
    title="Data Reliability Control Center API",
    description="Decoupled backend engine for real-time data validation and AI-driven Root Cause Analysis (RCA).",
    version="1.0.0"
)

# Enable CORS for decoupled frontend communication
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
    s3_storage_path: Optional[str] = None

# --- AI ROOT CAUSE ANALYSIS ENGINE ---
from ai_engine import generate_ai_root_cause_analysis, generate_file_ai_summary

# --- API ENDPOINTS ---
@app.get("/")
async def root():
    return {"message": "Data Reliability Control Center API is active.", "docs": "/docs"}

@app.post("/ai-summarize-file")
async def ai_summarize_file(file: UploadFile = File(...)):
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
async def analyze_upload(file: UploadFile = File(...)):
    """
    Asynchronously accepts a CSV file upload, runs data quality checks,
    and returns AI-driven Root Cause Analysis if validation fails.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only CSV files are supported."
        )

    # Asynchronously read file bytes into memory (Modularized for future S3 multipart uploads)
    contents = await file.read()
    
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Corrupted CSV payload: {str(e)}"
        )

    checks: List[ValidationCheck] = []
    failed_checks: List[ValidationCheck] = []

    # 1. Schema Validation
    expected_schema = ["user_id", "email", "signup_date", "plan_type", "total_spent"]
    missing_cols = [col for col in expected_schema if col not in df.columns]
    
    if not missing_cols:
        checks.append(ValidationCheck(check_name="schema_validation", status="PASS", details=f"All {len(expected_schema)} required columns present."))
    else:
        fail_check = ValidationCheck(check_name="schema_validation", status="FAIL", details=f"Missing required columns: {missing_cols}")
        checks.append(fail_check)
        failed_checks.append(fail_check)

    # 2. Null Value Check
    required_non_nulls = [c for c in ["user_id", "email"] if c in df.columns]
    null_counts = {col: int(df[col].isnull().sum()) for col in required_non_nulls}
    total_nulls = sum(null_counts.values())
    
    if total_nulls == 0:
        checks.append(ValidationCheck(check_name="null_check", status="PASS", details="Zero null values found in primary key columns."))
    else:
        fail_check = ValidationCheck(check_name="null_check", status="FAIL", details=f"Detected null values: {null_counts}")
        checks.append(fail_check)
        failed_checks.append(fail_check)

    # 3. Data Type Validation Check
    if "total_spent" in df.columns:
        numeric_series = pd.to_numeric(df["total_spent"], errors="coerce")
        type_corruptions = int(numeric_series.isnull().sum() - df["total_spent"].isnull().sum())
        if type_corruptions == 0:
            checks.append(ValidationCheck(check_name="type_check", status="PASS", details="All values in 'total_spent' are valid numeric formats."))
        else:
            fail_check = ValidationCheck(check_name="type_check", status="FAIL", details=f"Found {type_corruptions} non-numeric string values in 'total_spent'.")
            checks.append(fail_check)
            failed_checks.append(fail_check)

    # 4. Duplicate Check
    if "user_id" in df.columns:
        duplicates = int(df.duplicated(subset=["user_id"]).sum())
        if duplicates == 0:
            checks.append(ValidationCheck(check_name="duplicate_check", status="PASS", details="All user_id entries are unique."))
        else:
            fail_check = ValidationCheck(check_name="duplicate_check", status="FAIL", details=f"Found {duplicates} duplicate user_id records.")
            checks.append(fail_check)
            failed_checks.append(fail_check)

    # 5. Row Count Bounds Check
    num_rows = len(df)
    if 1 <= num_rows <= 50000:
        checks.append(ValidationCheck(check_name="row_count", status="PASS", details=f"Batch size of {num_rows} rows is within bounds."))
    else:
        fail_check = ValidationCheck(check_name="row_count", status="FAIL", details=f"Row count {num_rows} is outside bounds (expected 1-50000).")
        checks.append(fail_check)
        failed_checks.append(fail_check)

    # Determine Pipeline Execution Status
    pipeline_status = "FAILURE" if failed_checks else "SUCCESS"
    
    # Generate AI Root Cause Analysis if pipeline failed
    rca_result = None
    if pipeline_status == "FAILURE":
        rca_result = generate_ai_root_cause_analysis(failed_checks, df)

    # Simulated S3 / Storage Path
    destination_prefix = "processed" if pipeline_status == "SUCCESS" else "quarantine"
    s3_path = f"s3://data-pipeline-bucket/{destination_prefix}/{file.filename}"

    return AnalysisResponse(
        filename=file.filename,
        status=pipeline_status,
        total_rows=len(df),
        total_columns=len(df.columns),
        checks=checks,
        root_cause_analysis=rca_result,
        s3_storage_path=s3_path
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
