# Runbook: Schema Mismatch (schema_validation check)

## What this means
The data file arrived, but its column headers do not match the expected schema defined in the pipeline.

## How to investigate
1. **Compare Schemas:** Look at the incident ticket details in the dashboard to see what headers were expected versus what were actually received.
2. **Check for Upstream Changes:** Did the upstream engineering team release a new version of their application that changed the database schema or the CSV export format?
3. **Check for Corrupted Data:** Sometimes a delimiter issue (e.g., parsing a comma inside a text field) can cause the schema to shift or look incorrect.

## How to resolve
- If the upstream team intentionally changed the schema and it's a permanent change, update the `expected_schema` in `pipeline_monitor.py` to match the new format and deploy the update.
- If the schema change was accidental or a bug on the upstream side, file a bug report with that team. Wait for them to provide a corrected backfill file.
- Once fixed or adjusted, re-run `pipeline_monitor.py` and resolve the ticket.
