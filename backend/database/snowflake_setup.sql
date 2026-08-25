-- =============================================================================
--  Validata — Data Validation Engine
--  Snowflake Setup Script
--  Run this ONCE in Snowflake: Worksheets → paste → Run All
--  Author : Senior Cloud Data Engineer
-- =============================================================================
--  EXECUTION ORDER: Run each section top-to-bottom.
--  Estimated time : ~2 minutes
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1 — DATABASE & WAREHOUSE
-- ─────────────────────────────────────────────────────────────────────────────

USE ROLE SYSADMIN;

-- Create the virtual warehouse (compute engine for queries)
-- SIZE = X-SMALL is the smallest (and cheapest) — fine for our dataset size
CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH
    WAREHOUSE_SIZE   = 'X-SMALL'
    AUTO_SUSPEND     = 60           -- suspend after 60 seconds of inactivity
    AUTO_RESUME      = TRUE
    INITIALLY_SUSPENDED = TRUE      -- don't start billing until first query
    COMMENT = 'Validata pipeline compute warehouse';

USE WAREHOUSE COMPUTE_WH;

-- Create the main database
CREATE DATABASE IF NOT EXISTS VALIDATA_DB
    COMMENT = 'Validata — Data Validation Engine database';

USE DATABASE VALIDATA_DB;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2 — SCHEMAS
-- ─────────────────────────────────────────────────────────────────────────────

-- RAW_SCHEMA: holds data as received from source systems (minimal transforms)
CREATE SCHEMA IF NOT EXISTS VALIDATA_DB.RAW_SCHEMA
    COMMENT = 'Raw ingestion layer — source data as-is';

-- STAGING_SCHEMA: cleaned and validated data (Notebooks 02 and 03 output)
CREATE SCHEMA IF NOT EXISTS VALIDATA_DB.STAGING_SCHEMA
    COMMENT = 'Staging layer — cleaned and schema-validated data';

-- CURATED_SCHEMA: final validated output + AI explanations (Notebooks 04-06)
CREATE SCHEMA IF NOT EXISTS VALIDATA_DB.CURATED_SCHEMA
    COMMENT = 'Curated layer — validation results and audit reports';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3 — RAW SCHEMA TABLES
-- ─────────────────────────────────────────────────────────────────────────────

USE SCHEMA VALIDATA_DB.RAW_SCHEMA;

-- Mirrors the exact CSV structure from legacy_transactions.csv
CREATE TABLE IF NOT EXISTS LEGACY_TRANSACTIONS (
    txn_id          VARCHAR(50)     NOT NULL,
    customer_id     VARCHAR(50),
    txn_date        DATE,
    amount          NUMBER(18, 2),
    currency        VARCHAR(10),
    status          VARCHAR(20),
    region          VARCHAR(20),
    channel         VARCHAR(20),
    product_type    VARCHAR(50),
    reference_no    VARCHAR(50),
    _source_file    VARCHAR(500),
    _ingested_at    TIMESTAMP_NTZ,
    _source_label   VARCHAR(50)
);

-- Mirrors the exact CSV structure from new_system_transactions.csv
CREATE TABLE IF NOT EXISTS NEW_SYSTEM_TRANSACTIONS (
    txn_id          VARCHAR(50)     NOT NULL,
    customer_id     VARCHAR(50),
    txn_date        DATE,
    amount          NUMBER(18, 2),
    currency        VARCHAR(10),
    status          VARCHAR(20),
    region          VARCHAR(20),
    channel         VARCHAR(20),
    product_type    VARCHAR(50),
    reference_no    VARCHAR(50),
    _source_file    VARCHAR(500),
    _ingested_at    TIMESTAMP_NTZ,
    _source_label   VARCHAR(50)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4 — CURATED SCHEMA TABLES (most important)
-- ─────────────────────────────────────────────────────────────────────────────

USE SCHEMA VALIDATA_DB.CURATED_SCHEMA;

-- Main output table — one row per transaction, with validation result
-- This is what Notebook 05 writes to and Notebook 06 enriches
CREATE TABLE IF NOT EXISTS VALIDATION_RESULTS (
    txn_id              VARCHAR(50)     NOT NULL,
    customer_id         VARCHAR(50),
    txn_date            DATE,
    currency            VARCHAR(10),
    region              VARCHAR(20),
    channel             VARCHAR(20),
    product_type        VARCHAR(50),
    legacy_amount       NUMBER(18, 2),
    new_system_amount   NUMBER(18, 2),
    amount_diff         NUMBER(18, 4),
    amount_diff_pct     NUMBER(10, 4),
    legacy_status       VARCHAR(20),
    new_system_status   VARCHAR(20),
    validation_status   VARCHAR(30)     NOT NULL,   -- MATCH | MISSING | PHANTOM | AMOUNT_MISMATCH | STATUS_MISMATCH
    validated_at        TIMESTAMP_NTZ,
    ai_explanation      VARCHAR(4000),              -- populated by Notebook 06 (Cortex)
    ai_explained_at     TIMESTAMP_NTZ,
    loaded_at           TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

-- Pipeline run history — one row per notebook execution
CREATE TABLE IF NOT EXISTS AUDIT_LOG (
    notebook            VARCHAR(100),
    run_timestamp       TIMESTAMP_NTZ,
    rows_loaded         NUMBER,
    match_count         NUMBER,
    missing_count       NUMBER,
    phantom_count       NUMBER,
    amount_mismatch     NUMBER,
    status_mismatch     NUMBER,
    legacy_quarantined  NUMBER,
    new_sys_quarantined NUMBER,
    cortex_model        VARCHAR(50),
    source_path         VARCHAR(500),
    status              VARCHAR(20),    -- SUCCESS | FAILED
    notes               VARCHAR(1000)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5 — SERVICE USER & ROLE (for Databricks connection)
-- ─────────────────────────────────────────────────────────────────────────────

USE ROLE SYSADMIN;

-- Create a dedicated service user for the pipeline
-- IMPORTANT: Change the password below before running
CREATE USER IF NOT EXISTS VALIDATA_SVC_USER
    PASSWORD          = 'ValidataP!p3line2026'   -- CHANGE THIS
    DEFAULT_ROLE      = SYSADMIN
    DEFAULT_WAREHOUSE = COMPUTE_WH
    DEFAULT_NAMESPACE = VALIDATA_DB.CURATED_SCHEMA
    MUST_CHANGE_PASSWORD = FALSE
    COMMENT = 'Service account for Validata Databricks pipeline';

-- Grant the user access to the warehouse and database
GRANT USAGE ON WAREHOUSE COMPUTE_WH           TO USER VALIDATA_SVC_USER;
GRANT USAGE ON DATABASE  VALIDATA_DB          TO USER VALIDATA_SVC_USER;

GRANT USAGE  ON SCHEMA VALIDATA_DB.RAW_SCHEMA      TO USER VALIDATA_SVC_USER;
GRANT USAGE  ON SCHEMA VALIDATA_DB.STAGING_SCHEMA  TO USER VALIDATA_SVC_USER;
GRANT USAGE  ON SCHEMA VALIDATA_DB.CURATED_SCHEMA  TO USER VALIDATA_SVC_USER;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA VALIDATA_DB.RAW_SCHEMA      TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA VALIDATA_DB.STAGING_SCHEMA  TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA VALIDATA_DB.CURATED_SCHEMA  TO USER VALIDATA_SVC_USER;

-- Future tables will also be accessible
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA VALIDATA_DB.RAW_SCHEMA      TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA VALIDATA_DB.STAGING_SCHEMA  TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA VALIDATA_DB.CURATED_SCHEMA  TO USER VALIDATA_SVC_USER;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6 — VERIFY CORTEX IS AVAILABLE
-- ─────────────────────────────────────────────────────────────────────────────

-- Run this line alone to check if Cortex works on your account.
-- If it returns a text response → Cortex is active. You are ready.
-- If it errors → Cortex is not enabled. Raise a Snowflake support ticket.

SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', 'Say: Cortex is active') AS cortex_test;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 7 — VERIFY SETUP
-- ─────────────────────────────────────────────────────────────────────────────

-- Run these to confirm everything was created correctly
SHOW DATABASES   LIKE 'VALIDATA_DB';
SHOW SCHEMAS     IN DATABASE VALIDATA_DB;
SHOW TABLES      IN SCHEMA VALIDATA_DB.RAW_SCHEMA;
SHOW TABLES      IN SCHEMA VALIDATA_DB.CURATED_SCHEMA;
SHOW USERS       LIKE 'VALIDATA_SVC_USER';
SHOW WAREHOUSES  LIKE 'COMPUTE_WH';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 8 — USEFUL QUERIES (run anytime after pipeline executes)
-- ─────────────────────────────────────────────────────────────────────────────

-- Count of results by validation status
-- SELECT validation_status, COUNT(*) AS cnt
--   FROM VALIDATA_DB.CURATED_SCHEMA.VALIDATION_RESULTS
--  GROUP BY validation_status
--  ORDER BY cnt DESC;

-- View all AMOUNT_MISMATCH rows with AI explanation
-- SELECT txn_id, legacy_amount, new_system_amount,
--        amount_diff_pct, ai_explanation
--   FROM VALIDATA_DB.CURATED_SCHEMA.VALIDATION_RESULTS
--  WHERE validation_status = 'AMOUNT_MISMATCH'
--  ORDER BY amount_diff_pct DESC;

-- View pipeline run history
-- SELECT * FROM VALIDATA_DB.CURATED_SCHEMA.AUDIT_LOG
--  ORDER BY run_timestamp DESC;
