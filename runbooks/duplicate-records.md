# Runbook: Duplicate Records (duplicate_check)

## What this means
The data file contains multiple rows with the exact same value in a column that is supposed to be strictly unique (like `user_id` or `transaction_id`). 

## Common Causes
1. **Upstream API Retries:** A vendor's API failed to get a 200 OK response from our webhook and automatically re-sent the same payload.
2. **Bad SQL Joins:** The upstream engineering team modified a SQL query, resulting in a fan-out (Cartesian product) before exporting the CSV.

## How to investigate
1. Open the CSV file and sort by the unique column to identify the duplicates.
2. Check if the *entire row* is duplicated, or just the ID. 
   - If the entire row is duplicated, it is likely an API retry.
   - If the ID is the same but the data is different, it is a data corruption issue.

## Resolution Steps
1. Filter out the duplicates using Python/Pandas (`df.drop_duplicates(subset=['user_id'])`).
2. Upload the cleansed file to the `/processed` bucket.
3. Mark the Incident Ticket as RESOLVED in the Control Center.
4. Open a Jira ticket with the upstream vendor to notify them of the duplication bug.
