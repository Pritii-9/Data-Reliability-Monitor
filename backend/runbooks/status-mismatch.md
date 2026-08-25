# Runbook: Status Mismatch (STATUS_MISMATCH)

## What this means
The legacy ledger and the new database disagree on the final status of a transaction (e.g., `PENDING` in Legacy but `FAILED` in the New System).

## Common Causes
1. **Asynchronous Settlement Delays:** The new system has not yet received the settlement webhook confirmation.
2. **Reversals:** A transaction was reversed/refunded in one system but the state did not sync to the other.

## How to investigate
1. Open the Validata dashboard, locate the transaction under **Results**, and check the status fields.
2. Check the transaction's reference number (`reference_no`) in payment gateway logs (e.g., Stripe, Adyen) to find the true status.

## Resolution Steps
1. Determine the source of truth (typically the payment gateway or legacy core).
2. Run an update script in Snowflake to align the statuses:
   ```sql
   UPDATE TRANSACTIONS SET STATUS = 'COMPLETED' WHERE TXN_ID = '<txn_id>';
   ```
3. Trigger a manual sync on the dashboard.
