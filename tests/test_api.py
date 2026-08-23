import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_api_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Data Reliability Control Center API" in response.json()["message"]

def test_api_analyze_upload_success():
    csv_content = "user_id,email,signup_date,plan_type,total_spent\n101,test@example.com,2026-01-01,pro,99.99\n102,alice@example.com,2026-01-02,free,0.0"
    files = {"file": ("test_success.csv", csv_content.encode("utf-8"), "text/csv")}
    
    response = client.post("/analyze-upload", files=files)
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "SUCCESS"
    assert json_data["total_rows"] == 2
    assert json_data["root_cause_analysis"] is None

def test_api_analyze_upload_failure_ai_rca():
    # Type corruption & null value failure
    csv_content = "user_id,email,signup_date,plan_type,total_spent\n101,,2026-01-01,pro,INVALID_STRING\n102,alice@example.com,2026-01-02,free,0.0"
    files = {"file": ("test_corrupt.csv", csv_content.encode("utf-8"), "text/csv")}
    
    response = client.post("/analyze-upload", files=files)
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "FAILURE"
    assert json_data["root_cause_analysis"] is not None
    assert "Pipeline failed" in json_data["root_cause_analysis"]
