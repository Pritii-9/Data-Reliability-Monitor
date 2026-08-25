# Runbook: Low Row Count (row_count)

## What this means
The pipeline received a file, but the total number of rows is below the expected minimum threshold.

## Common Causes
1. **Empty File:** A vendor's script ran but failed to extract any data from their database, resulting in a CSV with only headers (0 rows).
2. **Partial Export:** A database timeout caused the upstream system to prematurely abort the CSV generation.

## How to investigate
1. Check the Incident Ticket to see how many rows were received vs expected.
2. Open the file to see if it is completely empty or just smaller than usual.

## Resolution Steps
1. If the file is completely empty, delete it from the S3 bucket to prevent downstream processes from failing.
2. Contact the upstream data provider and request a backfill / re-export of today's data.
3. Wait for the backfill file to arrive, verify it passes the pipeline monitor, and then mark the ticket as RESOLVED.
