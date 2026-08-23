# Runbook: Missing Data File (file_arrival check)

## What this means
The `pipeline_monitor.py` expected a data file to arrive in the Supabase storage bucket for the current date, but no matching file was found.

## How to investigate
1. **Check Supabase Storage:** Log into the Supabase Dashboard, navigate to Storage, and list the bucket contents. Check if a file arrived with the wrong name or date format.
2. **Check the Upstream Source:** The upstream system (simulated by `ingestion_simulator.py`) might have failed to run. Check the logs for the ingestion service.
3. **Check Network/Permissions:** Ensure that the upstream system has the correct Supabase API credentials to upload to the bucket.

## How to resolve
- If the upstream system failed, trigger a manual re-run of the ingestion process.
- If the file was uploaded with the wrong naming convention, rename the object in Supabase Storage and re-run the monitor.
- Once the file is present in the bucket, execute `python pipeline_monitor.py` to process the file and clear the incident. Mark the ticket as `RESOLVED`.
