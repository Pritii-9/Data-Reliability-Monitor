# Runbook: Null Values in Required Fields (null_check)

## What this means
The pipeline monitor found empty or NULL values in columns that are strictly required (e.g., `user_id`, `email`). 

## How to investigate
1. **Identify the Scope:** Check the ticket details to see how many rows had nulls. Is it a handful of rows, or the entire dataset?
2. **Query the Upstream DB (if applicable):** If you have read access to the source database, query it to see if the records are actually missing email addresses there, or if the data was lost during the export process.
3. **Investigate the Ingestion Code:** Check `ingestion_simulator.py` to ensure it is correctly extracting all fields without accidental data drops.

## How to resolve
- **Data Bug:** If this is a bug in how users are registering (e.g., skipping a mandatory email field), alert the application team.
- **Tolerable Data Loss:** If it's a very small number of rows and acceptable for analytics, you might update the ETL process to automatically filter out those bad rows instead of failing the whole pipeline.
- For this project, fix the source data or adjust the `validate_nulls` logic, then re-run `pipeline_monitor.py` and resolve the ticket.
