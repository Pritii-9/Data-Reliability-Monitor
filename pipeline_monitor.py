import os
import io
import csv
import boto3
from datetime import datetime, date
from collections import Counter
from database import SessionLocal, PipelineRun, CheckResult
from ticketing import create_ticket
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "data-pipeline-bucket")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# === Validation Logic (Unit Testable) ===

def check_file_arrival(files_list, expected_date_str):
    """Check if a file with the expected date string exists in the S3 bucket and return the newest."""
    matching_files = []
    for file in files_list:
        if expected_date_str in file['Key'] and file['Key'].endswith('.csv') and 'backup' not in file['Key']:
            matching_files.append(file)
            
    if matching_files:
        # Sort by LastModified (newest first)
        matching_files.sort(key=lambda x: x.get('LastModified', datetime.min), reverse=True)
        return True, matching_files[0]['Key']
        
    return False, None

def validate_schema(headers, expected_headers):
    """Check if the headers exactly match the expected schema."""
    if headers == expected_headers:
        return True, "Schema matches expected."
    return False, f"Expected {expected_headers}, but got {headers}"

def validate_row_count(num_rows, min_expected=10, max_expected=1000):
    """Check if the total row count falls within a reasonable range."""
    if min_expected <= num_rows <= max_expected:
        return True, f"Row count {num_rows} is within bounds."
    return False, f"Row count {num_rows} is out of bounds ({min_expected}-{max_expected})."

def validate_nulls(data, headers, required_columns):
    """Check for null or empty values in required columns."""
    if not data:
        return True, "No data to check for nulls."
        
    required_indices = []
    for col in required_columns:
        if col in headers:
            required_indices.append(headers.index(col))
            
    null_rows = 0
    for row in data:
        for idx in required_indices:
            if idx < len(row):
                val = str(row[idx]).strip()
                if not val or val.lower() == 'null' or val.lower() == 'none':
                    null_rows += 1
                    break # Only count the row once if multiple nulls exist
    
    if null_rows > 0:
        return False, f"Found {null_rows} rows with nulls in required columns ({required_columns})."
    return True, "No nulls found in required columns."

def validate_duplicates(data, headers, unique_column):
    """Check for duplicate values in a column that should be unique."""
    if not data or unique_column not in headers:
        return True, "Cannot check duplicates (no data or column missing)."
        
    idx = headers.index(unique_column)
    values = [row[idx] for row in data if idx < len(row)]
    
    counter = Counter(values)
    duplicates = {k: v for k, v in counter.items() if v > 1}
    
    if duplicates:
        return False, f"Found {len(duplicates)} duplicate(s) in unique column '{unique_column}'."
    return True, "No duplicates found."

# === Pipeline Monitor Core ===

def run_pipeline_monitor():
    """Main execution block for the pipeline monitor."""
    print(f"Starting pipeline monitor at {datetime.now()}...")
    session = SessionLocal()
    
    run_record = PipelineRun(status="IN_PROGRESS")
    session.add(run_record)
    session.commit()
    session.refresh(run_record)
    
    checks_passed = 0
    checks_failed = 0
    
    def log_check(name, passed, details, severity="MEDIUM"):
        nonlocal checks_passed, checks_failed
        if passed:
            checks_passed += 1
            status = "PASS"
        else:
            checks_failed += 1
            status = "FAIL"
            # Create a ticket on failure
            create_ticket(
                title=f"Check Failed: {name}",
                description=f"Pipeline Run ID: {run_record.id}\nDetails: {details}",
                severity=severity
            )
            
        check = CheckResult(
            run_id=run_record.id,
            check_name=name,
            status=status,
            details=details
        )
        session.add(check)
        session.commit()

    try:
        # 1. File Arrival Check
        today_str = datetime.now().strftime("%Y%m%d")
        try:
            response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME)
            files = response.get('Contents', [])
        except Exception as e:
            files = []
            print(f"Error accessing S3: {e}")
            
        arrived, file_key = check_file_arrival(files, today_str)
        
        if not arrived:
            log_check("file_arrival", False, f"Expected file for {today_str} not found.", "HIGH")
            raise Exception("Critical failure: File did not arrive. Halting further checks.")
        else:
            log_check("file_arrival", True, f"File {file_key} found.")
            
        # Download and read file
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_key)
        csv_string = obj['Body'].read().decode('utf-8')
        
        reader = csv.reader(io.StringIO(csv_string))
        rows = list(reader)
        
        if not rows:
            log_check("file_not_empty", False, "File is completely empty.", "HIGH")
            raise Exception("Critical failure: Empty file. Halting further checks.")
            
        headers = rows[0]
        data = rows[1:]
        
        # 2. Schema Validation
        expected_schema = ["user_id", "email", "signup_date", "plan_type", "total_spent"]
        schema_ok, schema_msg = validate_schema(headers, expected_schema)
        log_check("schema_validation", schema_ok, schema_msg, "HIGH")
        
        # 3. Row Count Check
        count_ok, count_msg = validate_row_count(len(data))
        log_check("row_count", count_ok, count_msg, "LOW")
        
        # 4. Nulls in Required Fields
        required = ["user_id", "email"]
        nulls_ok, nulls_msg = validate_nulls(data, headers, required)
        log_check("null_check", nulls_ok, nulls_msg, "MEDIUM")
        
        # 5. Duplicates Check
        dupes_ok, dupes_msg = validate_duplicates(data, headers, "user_id")
        log_check("duplicate_check", dupes_ok, dupes_msg, "MEDIUM")
        
        run_record.status = "SUCCESS" if checks_failed == 0 else "FAILURE"
        
    except Exception as e:
        print(f"Pipeline monitor aborted early: {e}")
        run_record.status = "FAILURE"
        
    finally:
        run_record.total_checks = checks_passed + checks_failed
        run_record.passed_checks = checks_passed
        run_record.failed_checks = checks_failed
        session.commit()
        session.close()
        
    print(f"Monitor run complete. Passed: {checks_passed}, Failed: {checks_failed}")

# === Unit Tests ===
def test_validations():
    """Simple unit tests for the validation logic."""
    print("Running unit tests...")
    
    # Test Schema
    assert validate_schema(["a", "b"], ["a", "b"])[0] == True
    assert validate_schema(["a", "c"], ["a", "b"])[0] == False
    
    # Test Row Count
    assert validate_row_count(50, 10, 100)[0] == True
    assert validate_row_count(5, 10, 100)[0] == False
    
    # Test Nulls
    headers = ["id", "name"]
    data_good = [[1, "Alice"], [2, "Bob"]]
    data_bad = [[1, "Alice"], [2, ""]]
    assert validate_nulls(data_good, headers, ["name"])[0] == True
    assert validate_nulls(data_bad, headers, ["name"])[0] == False
    
    print("All unit tests passed!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_validations()
    else:
        run_pipeline_monitor()
