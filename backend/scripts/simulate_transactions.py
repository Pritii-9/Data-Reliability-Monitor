"""
=============================================================================
  Validata — Data Validation Engine
  Transaction Simulator Script
  Author  : Senior Cloud Data Engineer (AI-assisted)
  Purpose : Generate two mock transaction CSV datasets —
              • legacy_transactions.csv   (Source A / legacy system)
              • new_system_transactions.csv (Source B / new system)
            with deliberately injected anomalies so the ETL pipeline
            has realistic data to catch:
              1. Duplicate records  (same txn_id appears more than once)
              2. Missing records    (records present in legacy but absent in new)
              3. Amount mismatches  (slight ± drift in transaction amounts)
              4. Status mismatches  (status field disagrees between systems)
              5. Null / blank fields (edge-case data quality issues)
=============================================================================
"""

import csv
import os
import random
import uuid
from copy import deepcopy
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# CONFIGURATION — tweak these numbers to scale your test dataset
# ---------------------------------------------------------------------------

NUM_CLEAN_RECORDS     = 200   # records that are identical in both systems
NUM_AMOUNT_MISMATCHES = 15    # records where the amount differs slightly
NUM_STATUS_MISMATCHES = 10    # records where status column disagrees
NUM_LEGACY_ONLY       = 12    # records that exist ONLY in the legacy system
NUM_NEW_ONLY          = 8     # records that exist ONLY in the new system
NUM_DUPLICATES        = 5     # records duplicated inside legacy_transactions
NUM_NULL_FIELDS       = 5     # records with blank / null customer_id

RANDOM_SEED           = 42    # keep results reproducible across runs
OUTPUT_DIR            = "sample_data"

# ---------------------------------------------------------------------------
# STATIC LOOKUP TABLES
# ---------------------------------------------------------------------------

CURRENCIES    = ["USD", "EUR", "GBP", "INR", "AED"]
STATUSES      = ["COMPLETED", "PENDING", "FAILED", "REVERSED"]
REGIONS       = ["APAC", "EMEA", "NA", "LATAM"]
CHANNELS      = ["ONLINE", "BRANCH", "ATM", "MOBILE"]
PRODUCT_TYPES = ["LOAN_PAYMENT", "WIRE_TRANSFER", "BILL_PAY", "FX_CONVERSION", "DEPOSIT"]

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def random_date(start_days_ago: int = 90) -> str:
    """Return a random ISO-8601 date string within the last N days."""
    base  = datetime(2026, 8, 1)
    delta = timedelta(days=random.randint(0, start_days_ago))
    return (base - delta).strftime("%Y-%m-%d")


def random_amount(low: float = 10.0, high: float = 50_000.0) -> float:
    """Return a rounded random float representing a transaction amount."""
    return round(random.uniform(low, high), 2)


def make_txn_id() -> str:
    """Generate a unique transaction ID in the format TXN-XXXXXXXX."""
    return f"TXN-{uuid.uuid4().hex[:8].upper()}"


def make_customer_id() -> str:
    """Generate a customer ID in the format CUST-NNNNNN."""
    return f"CUST-{random.randint(100000, 999999)}"


def build_clean_record(txn_id: str) -> dict:
    """Build one fully-populated, anomaly-free transaction row."""
    return {
        "txn_id"        : txn_id,
        "customer_id"   : make_customer_id(),
        "txn_date"      : random_date(),
        "amount"        : random_amount(),
        "currency"      : random.choice(CURRENCIES),
        "status"        : random.choice(STATUSES),
        "region"        : random.choice(REGIONS),
        "channel"       : random.choice(CHANNELS),
        "product_type"  : random.choice(PRODUCT_TYPES),
        "reference_no"  : f"REF-{random.randint(10000000, 99999999)}",
    }


def inject_amount_mismatch(record: dict, drift_pct: float = 0.05) -> dict:
    """
    Return a COPY of the record with the amount perturbed by ±drift_pct.
    This simulates rounding errors or FX conversion discrepancies between
    the legacy and new system.
    """
    new_rec = deepcopy(record)
    sign    = random.choice([-1, 1])
    drift   = round(record["amount"] * drift_pct * random.uniform(0.1, 1.0), 2)
    new_rec["amount"] = round(record["amount"] + sign * drift, 2)
    return new_rec


def inject_status_mismatch(record: dict) -> dict:
    """
    Return a COPY of the record with a DIFFERENT status value.
    Simulates a race condition or delayed propagation between systems.
    """
    new_rec = deepcopy(record)
    current = record["status"]
    options = [s for s in STATUSES if s != current]
    new_rec["status"] = random.choice(options)
    return new_rec


def inject_null_customer(record: dict) -> dict:
    """Return a COPY of the record with customer_id blanked out."""
    new_rec = deepcopy(record)
    new_rec["customer_id"] = ""   # Empty string = null-like in CSV
    return new_rec

# ---------------------------------------------------------------------------
# MAIN SIMULATION LOGIC
# ---------------------------------------------------------------------------

def simulate(output_dir: str = OUTPUT_DIR) -> None:
    random.seed(RANDOM_SEED)
    os.makedirs(output_dir, exist_ok=True)

    legacy_rows   = []   # rows written to legacy_transactions.csv
    new_sys_rows  = []   # rows written to new_system_transactions.csv

    print("=" * 60)
    print("  Validata — Transaction Simulator")
    print("=" * 60)

    # ------------------------------------------------------------------
    # PHASE 1 — CLEAN RECORDS (identical in both systems)
    # ------------------------------------------------------------------
    print(f"\n[1/6] Generating {NUM_CLEAN_RECORDS} clean matching records...")
    for _ in range(NUM_CLEAN_RECORDS):
        rec = build_clean_record(make_txn_id())
        legacy_rows.append(rec)
        new_sys_rows.append(deepcopy(rec))   # perfect copy in new system

    # ------------------------------------------------------------------
    # PHASE 2 — AMOUNT MISMATCHES
    # ------------------------------------------------------------------
    print(f"[2/6] Injecting {NUM_AMOUNT_MISMATCHES} amount-mismatch records...")
    for _ in range(NUM_AMOUNT_MISMATCHES):
        rec       = build_clean_record(make_txn_id())
        legacy_rows.append(rec)
        new_sys_rows.append(inject_amount_mismatch(rec))   # drifted amount

    # ------------------------------------------------------------------
    # PHASE 3 — STATUS MISMATCHES
    # ------------------------------------------------------------------
    print(f"[3/6] Injecting {NUM_STATUS_MISMATCHES} status-mismatch records...")
    for _ in range(NUM_STATUS_MISMATCHES):
        rec       = build_clean_record(make_txn_id())
        legacy_rows.append(rec)
        new_sys_rows.append(inject_status_mismatch(rec))   # wrong status

    # ------------------------------------------------------------------
    # PHASE 4 — LEGACY-ONLY RECORDS (missing from new system)
    # ------------------------------------------------------------------
    print(f"[4/6] Injecting {NUM_LEGACY_ONLY} legacy-only (missing) records...")
    for _ in range(NUM_LEGACY_ONLY):
        rec = build_clean_record(make_txn_id())
        legacy_rows.append(rec)
        # deliberately NOT adding to new_sys_rows

    # ------------------------------------------------------------------
    # PHASE 5 — NEW-SYSTEM-ONLY RECORDS (phantom records)
    # ------------------------------------------------------------------
    print(f"[5/6] Injecting {NUM_NEW_ONLY} new-system-only (phantom) records...")
    for _ in range(NUM_NEW_ONLY):
        rec = build_clean_record(make_txn_id())
        # deliberately NOT adding to legacy_rows
        new_sys_rows.append(rec)

    # ------------------------------------------------------------------
    # PHASE 6 — INTRA-FILE DUPLICATES (same txn_id twice in legacy)
    # ------------------------------------------------------------------
    print(f"[6/6] Injecting {NUM_DUPLICATES} intra-file duplicate records in legacy...")
    # Pick N existing legacy records at random and append them again
    duplicate_sources = random.sample(legacy_rows[:NUM_CLEAN_RECORDS], NUM_DUPLICATES)
    for dup in duplicate_sources:
        legacy_rows.append(deepcopy(dup))

    # ------------------------------------------------------------------
    # PHASE 6b — NULL CUSTOMER IDs scattered across legacy
    # ------------------------------------------------------------------
    null_targets = random.sample(range(len(legacy_rows)), NUM_NULL_FIELDS)
    for idx in null_targets:
        legacy_rows[idx] = inject_null_customer(legacy_rows[idx])
    print(f"       Also blanked customer_id on {NUM_NULL_FIELDS} legacy rows.")

    # ------------------------------------------------------------------
    # SHUFFLE both datasets — real exports are never sorted
    # ------------------------------------------------------------------
    random.shuffle(legacy_rows)
    random.shuffle(new_sys_rows)

    # ------------------------------------------------------------------
    # WRITE CSVs
    # ------------------------------------------------------------------
    fieldnames = [
        "txn_id", "customer_id", "txn_date", "amount",
        "currency", "status", "region", "channel",
        "product_type", "reference_no",
    ]

    legacy_path  = os.path.join(output_dir, "legacy_transactions.csv")
    new_sys_path = os.path.join(output_dir, "new_system_transactions.csv")

    for path, rows, label in [
        (legacy_path,  legacy_rows,  "legacy_transactions.csv"),
        (new_sys_path, new_sys_rows, "new_system_transactions.csv"),
    ]:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n[OK] Written: {path}  ({len(rows)} rows)")

    # ------------------------------------------------------------------
    # SUMMARY MANIFEST
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  SIMULATION SUMMARY")
    print("=" * 60)
    print(f"  Output directory       : {os.path.abspath(output_dir)}")
    print(f"  legacy_transactions    : {len(legacy_rows)} rows")
    print(f"  new_system_transactions: {len(new_sys_rows)} rows")
    print()
    print("  Injected Anomalies:")
    print(f"    Clean matching records   : {NUM_CLEAN_RECORDS}")
    print(f"    Amount mismatches        : {NUM_AMOUNT_MISMATCHES}")
    print(f"    Status mismatches        : {NUM_STATUS_MISMATCHES}")
    print(f"    Legacy-only (missing)    : {NUM_LEGACY_ONLY}")
    print(f"    New-system-only (phantom): {NUM_NEW_ONLY}")
    print(f"    Intra-file duplicates    : {NUM_DUPLICATES}  (in legacy)")
    print(f"    Null customer_id rows    : {NUM_NULL_FIELDS} (in legacy)")
    print()
    print("  Next Step >> Upload both CSVs to:")
    print("    s3://validata-datalake-priti/raw/legacy_system/")
    print("    s3://validata-datalake-priti/raw/new_system/")
    print("=" * 60)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    simulate()
