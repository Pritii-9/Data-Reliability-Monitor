import os
import yaml
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel

class ValidationCheckResult(BaseModel):
    check_name: str
    status: str  # 'PASS' or 'FAIL'
    details: str

DEFAULT_CONTRACT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../config/contracts/default_user_schema.yaml")
)

def load_data_contract(contract_source: Optional[Any] = None) -> Dict[str, Any]:
    """
    Loads a Data Contract configuration from a YAML file path, raw YAML string, dictionary, or default file.
    """
    if isinstance(contract_source, dict):
        return contract_source

    if isinstance(contract_source, str):
        if os.path.exists(contract_source):
            with open(contract_source, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        try:
            parsed = yaml.safe_load(contract_source)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # Fallback to default contract file
    if os.path.exists(DEFAULT_CONTRACT_PATH):
        with open(DEFAULT_CONTRACT_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Fallback default dict structure if file not found
    return {
        "dataset_name": "default_fallback",
        "schema": {"required_columns": ["user_id", "email", "signup_date", "plan_type", "total_spent"]},
        "rules": {
            "null_check": {"required_non_null": ["user_id", "email"]},
            "type_check": {"numeric_columns": ["total_spent"]},
            "duplicate_check": {"unique_key": "user_id"},
            "row_count_bounds": {"min_rows": 1, "max_rows": 50000}
        }
    }

def evaluate_contract(df: pd.DataFrame, contract_source: Optional[Any] = None) -> Tuple[List[ValidationCheckResult], List[ValidationCheckResult]]:
    """
    Evaluates a pandas DataFrame against a dynamic YAML Data Contract specification.
    Returns: (all_checks, failed_checks)
    """
    contract = load_data_contract(contract_source)
    checks: List[ValidationCheckResult] = []
    failed_checks: List[ValidationCheckResult] = []

    schema_config = contract.get("schema", {})
    rules_config = contract.get("rules", {})

    # 1. Dynamic Schema Validation
    required_cols = schema_config.get("required_columns", [])
    if required_cols:
        missing_cols = [col for col in required_cols if col not in df.columns]
        if not missing_cols:
            chk = ValidationCheckResult(
                check_name="schema_validation",
                status="PASS",
                details=f"All {len(required_cols)} required columns present ({', '.join(required_cols)})."
            )
            checks.append(chk)
        else:
            chk = ValidationCheckResult(
                check_name="schema_validation",
                status="FAIL",
                details=f"Missing required columns: {missing_cols}"
            )
            checks.append(chk)
            failed_checks.append(chk)

    # 2. Null Value Check
    null_rule = rules_config.get("null_check", {})
    non_null_cols = [col for col in null_rule.get("required_non_null", []) if col in df.columns]
    if non_null_cols:
        null_counts = {}
        for col in non_null_cols:
            # Check for pandas NaN / None as well as empty strings
            null_mask = df[col].isnull() | (df[col].astype(str).str.strip().str.lower().isin(["", "null", "none", "nan"]))
            cnt = int(null_mask.sum())
            if cnt > 0:
                null_counts[col] = cnt

        if not null_counts:
            chk = ValidationCheckResult(
                check_name="null_check",
                status="PASS",
                details=f"Zero null values found in primary identifier columns ({', '.join(non_null_cols)})."
            )
            checks.append(chk)
        else:
            chk = ValidationCheckResult(
                check_name="null_check",
                status="FAIL",
                details=f"Detected null values in required columns: {null_counts}"
            )
            checks.append(chk)
            failed_checks.append(chk)

    # 3. Data Type Consistency Check
    type_rule = rules_config.get("type_check", {})
    numeric_cols = [col for col in type_rule.get("numeric_columns", []) if col in df.columns]
    if numeric_cols:
        type_errors = {}
        for col in numeric_cols:
            numeric_series = pd.to_numeric(df[col], errors="coerce")
            corruptions = int(numeric_series.isnull().sum() - df[col].isnull().sum())
            if corruptions > 0:
                type_errors[col] = corruptions

        if not type_errors:
            chk = ValidationCheckResult(
                check_name="type_check",
                status="PASS",
                details=f"All values in numeric columns ({', '.join(numeric_cols)}) match valid numeric formats."
            )
            checks.append(chk)
        else:
            chk = ValidationCheckResult(
                check_name="type_check",
                status="FAIL",
                details=f"Type corruption detected in numeric columns: {type_errors}"
            )
            checks.append(chk)
            failed_checks.append(chk)

    # 4. Duplicate Check
    dup_rule = rules_config.get("duplicate_check", {})
    unique_key = dup_rule.get("unique_key")
    if unique_key and unique_key in df.columns:
        duplicates = int(df.duplicated(subset=[unique_key]).sum())
        if duplicates == 0:
            chk = ValidationCheckResult(
                check_name="duplicate_check",
                status="PASS",
                details=f"All '{unique_key}' primary key entries are unique."
            )
            checks.append(chk)
        else:
            chk = ValidationCheckResult(
                check_name="duplicate_check",
                status="FAIL",
                details=f"Found {duplicates} duplicate records for primary key '{unique_key}'."
            )
            checks.append(chk)
            failed_checks.append(chk)

    # 5. Row Count Bounds Check
    row_rule = rules_config.get("row_count_bounds", {})
    min_rows = row_rule.get("min_rows", 1)
    max_rows = row_rule.get("max_rows", 1000000)
    num_rows = len(df)
    if min_rows <= num_rows <= max_rows:
        chk = ValidationCheckResult(
            check_name="row_count",
            status="PASS",
            details=f"Batch size of {num_rows:,} rows is within expected bounds ({min_rows:,} - {max_rows:,})."
        )
        checks.append(chk)
    else:
        chk = ValidationCheckResult(
            check_name="row_count",
            status="FAIL",
            details=f"Row count {num_rows:,} is outside expected contract bounds ({min_rows:,} - {max_rows:,})."
        )
        checks.append(chk)
        failed_checks.append(chk)

    return checks, failed_checks
