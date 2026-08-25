# Runbook: Amount Mismatch (AMOUNT_MISMATCH)

## What this means
A transaction exists in both the legacy ledger and the new database, but their amounts differ beyond the allowable percentage tolerance (default: 0.1%).

## Common Causes
1. **Currency/FX Conversion Lag:** Different exchange rates were applied when converting currencies.
2. **Transaction Fees:** The legacy or new system deducted payment gateway fees from the transaction amount before saving.

## How to investigate
1. Go to the **Results** page in the Validata dashboard and search for the transaction ID.
2. Compare `legacy_amount` vs `new_system_amount`.
3. Check the **AI Explanation** in the table to see Gemini's analysis.

## Resolution Steps
1. If the difference is a known processing fee:
   - Mark the difference as acceptable, or execute the AI Copilot's suggested correction script.
2. If the mismatch is an error:
   - Run the provided SQL remediation script in Snowflake to sync the correct ledger amount.
   - For example:
     ```sql
     UPDATE TRANSACTIONS SET AMOUNT = <legacy_amount> WHERE TXN_ID = '<txn_id>';
     ```
3. Re-run the validation engine to verify the mismatch is resolved.
