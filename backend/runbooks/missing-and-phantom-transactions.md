# Runbook: Missing and Phantom Transactions (MISSING / PHANTOM)

## What this means
- **MISSING:** A transaction exists in the legacy ledger but was never created in the new database.
- **PHANTOM:** A transaction exists in the new system database but has no record in the legacy ledger.

## Common Causes
1. **API/Queue Drops:** Network packet loss or message broker failure during the migration ingestion step.
2. **Double Posting:** The transaction was registered under a new transaction ID in the target system.

## How to investigate
1. Use the **AI Copilot** on the dashboard to ask: *"Find details for missing transaction <txn_id>"*.
2. Verify if the customer ID and reference number exist in both ledgers under different transaction IDs.

## Resolution Steps
1. For **MISSING** rows:
   - Export the legacy transaction details.
   - Insert/backfill the missing record into the new system ledger to sync the database.
2. For **PHANTOM** rows:
   - Trace the origin of the transaction in the new system to ensure it is not fraudulent or duplicate.
   - Delete/void the record if it is a duplicate.
