import sys
import os
import pytest

# Add parent directory to path so we can import the pipeline_monitor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline_monitor import validate_schema, validate_row_count, validate_nulls, validate_duplicates

def test_validate_schema():
    expected = ["user_id", "email", "total_spent"]
    
    # Pass
    ok, msg = validate_schema(["user_id", "email", "total_spent"], expected)
    assert ok is True
    
    # Fail (missing column)
    ok, msg = validate_schema(["user_id", "total_spent"], expected)
    assert ok is False

def test_validate_row_count():
    # Pass
    ok, msg = validate_row_count(50, min_expected=10, max_expected=100)
    assert ok is True
    
    # Fail (too low)
    ok, msg = validate_row_count(5, min_expected=10, max_expected=100)
    assert ok is False
    
    # Fail (too high)
    ok, msg = validate_row_count(150, min_expected=10, max_expected=100)
    assert ok is False

def test_validate_nulls():
    headers = ["user_id", "email", "plan_type"]
    required = ["user_id", "email"]
    
    # Pass
    data_good = [
        [1, "alice@test.com", "Pro"],
        [2, "bob@test.com", ""] # plan_type is empty, but it's not required!
    ]
    ok, msg = validate_nulls(data_good, headers, required)
    assert ok is True
    
    # Fail
    data_bad = [
        [1, "", "Pro"], # Missing email
        [2, "bob@test.com", "Basic"]
    ]
    ok, msg = validate_nulls(data_bad, headers, required)
    assert ok is False
    assert "1 rows with nulls" in msg

def test_validate_duplicates():
    headers = ["user_id", "email"]
    
    # Pass
    data_good = [
        [1, "alice@test.com"],
        [2, "bob@test.com"]
    ]
    ok, msg = validate_duplicates(data_good, headers, "user_id")
    assert ok is True
    
    # Fail
    data_bad = [
        [1, "alice@test.com"],
        [1, "bob@test.com"] # Duplicate user_id!
    ]
    ok, msg = validate_duplicates(data_bad, headers, "user_id")
    assert ok is False
    assert "1 duplicate(s)" in msg
