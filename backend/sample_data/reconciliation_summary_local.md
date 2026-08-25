# Local Reconciliation Audit Report

*Generated at: 2026-08-25 08:42:36 UTC*
*Pipeline Mode: Local Mock (Offline)*

## 1. Summary Statistics
* **Total Transactions:** 11
* **Matches:** 7
* **Anomalies Detected:** 4

### Status Count Breakdown:
| VALIDATION_STATUS   |   count |
|:--------------------|--------:|
| MATCH               |       7 |
| MISSING             |       2 |
| STATUS_MISMATCH     |       1 |
| PHANTOM             |       1 |

## 2. Identified Anomalies Table
| Transaction ID | Status | Legacy Amount | New System Amount | Legacy / New Status |
| :--- | :--- | :--- | :--- | :--- |
| TXN-1004 | STATUS_MISMATCH | 15.75 | 15.75 | COMPLETED / FAILED |
| TXN-1005 | MISSING | 250.0 | None | PENDING / None |
| TXN-1009 | MISSING | 30.0 | None | COMPLETED / None |
| TXN-1011 | PHANTOM | None | 95.0 | None / COMPLETED |

*(AI Explanations and Snowflake updates skipped in local mock mode.)*
