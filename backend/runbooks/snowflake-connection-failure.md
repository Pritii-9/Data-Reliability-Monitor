# Runbook: Snowflake Connection Failure

## What this means
The backend API cannot connect to the Snowflake Data Lake warehouse. The dashboard falls back to **Mock Mode** (indicated by warnings in the server logs).

## Common Causes
1. **Invalid Credentials:** The password or token in `.env` is expired or incorrect.
2. **Network Blockage:** Corporate VPN or local firewall is blocking the Snowflake connection port.
3. **Snowflake Account Suspend:** The Snowflake trial/account has been suspended due to credit exhaustion.

## How to investigate
1. Check the backend server logs for the specific Snowflake error code (e.g. `250001: Invalid connection credentials`).
2. Verify the `.env` settings:
   - `SF_ACCOUNT`, `SF_USER`, `SF_PASSWORD`, `SF_DATABASE`, `SF_WAREHOUSE`, `SF_SCHEMA`

## Resolution Steps
1. Verify if you can log in to the Snowflake console in the browser using the same credentials.
2. Update the credentials in your local `.env` file if they have expired.
3. If Snowflake is offline permanently, use the MockConnection fallback built into `backend/src/api/routers/snowflake.py` for offline development.
