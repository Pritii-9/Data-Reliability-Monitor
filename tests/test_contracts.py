import pytest
import pandas as pd
from src.engine.contract_validator import load_data_contract, evaluate_contract

def test_load_default_contract():
    contract = load_data_contract()
    assert "schema" in contract
    assert "required_columns" in contract["schema"]
    assert "user_id" in contract["schema"]["required_columns"]

def test_evaluate_contract_pass():
    df = pd.DataFrame([
        {"user_id": 1, "email": "test1@example.com", "signup_date": "2026-01-01", "plan_type": "Pro", "total_spent": 99.99},
        {"user_id": 2, "email": "test2@example.com", "signup_date": "2026-01-02", "plan_type": "Free", "total_spent": 0.0}
    ])
    
    checks, failed_checks = evaluate_contract(df)
    assert len(failed_checks) == 0
    assert all(c.status == "PASS" for c in checks)

def test_evaluate_contract_missing_schema():
    # Missing email column
    df = pd.DataFrame([
        {"user_id": 1, "signup_date": "2026-01-01", "plan_type": "Pro", "total_spent": 99.99}
    ])
    
    checks, failed_checks = evaluate_contract(df)
    assert len(failed_checks) > 0
    assert any(c.check_name == "schema_validation" and c.status == "FAIL" for c in failed_checks)

def test_evaluate_contract_type_and_null_failure():
    # Null email and string in numeric column
    df = pd.DataFrame([
        {"user_id": 1, "email": "", "signup_date": "2026-01-01", "plan_type": "Pro", "total_spent": "INVALID_NUMBER"}
    ])
    
    checks, failed_checks = evaluate_contract(df)
    failed_names = [c.check_name for c in failed_checks]
    assert "null_check" in failed_names
    assert "type_check" in failed_names

def test_custom_yaml_contract():
    custom_contract = {
        "dataset_name": "custom_test",
        "schema": {"required_columns": ["product_id", "price"]},
        "rules": {
            "null_check": {"required_non_null": ["product_id"]},
            "type_check": {"numeric_columns": ["price"]},
            "duplicate_check": {"unique_key": "product_id"},
            "row_count_bounds": {"min_rows": 1, "max_rows": 100}
        }
    }
    
    df_valid = pd.DataFrame([
        {"product_id": 101, "price": 49.99},
        {"product_id": 102, "price": 19.99}
    ])
    
    checks, failed = evaluate_contract(df_valid, custom_contract)
    assert len(failed) == 0
