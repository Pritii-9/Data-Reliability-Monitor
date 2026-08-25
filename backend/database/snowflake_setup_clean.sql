-- =============================================================================
--  Validata — Data Validation Engine
--  CLEAN SETUP SCRIPT  (paste ALL into Snowflake Worksheet → Run All)
--  Step 1: Drops everything you created before
--  Step 2: Rebuilds everything correctly from scratch
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- PART 1 — WIPE EVERYTHING PREVIOUSLY CREATED
-- ─────────────────────────────────────────────────────────────────────────────

USE ROLE SYSADMIN;

-- Drops the entire database and ALL schemas/tables inside it in one shot
DROP DATABASE IF EXISTS ValiData_DB;

-- Drop the old service user if it exists (requires ACCOUNTADMIN)
USE ROLE ACCOUNTADMIN;
DROP USER IF EXISTS VALIDATA_SVC_USER;
USE ROLE SYSADMIN;

-- Drop warehouse if it exists (we will recreate it)
DROP WAREHOUSE IF EXISTS COMPUTE_WH;


-- ─────────────────────────────────────────────────────────────────────────────
-- PART 2 — REBUILD WAREHOUSE
-- ─────────────────────────────────────────────────────────────────────────────

CREATE WAREHOUSE COMPUTE_WH
    WAREHOUSE_SIZE      = 'X-SMALL'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Validata pipeline compute warehouse';

USE WAREHOUSE COMPUTE_WH;


-- ─────────────────────────────────────────────────────────────────────────────
-- PART 3 — REBUILD DATABASE & SCHEMAS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE DATABASE ValiData_DB
    COMMENT = 'Validata — Data Validation Engine';

USE DATABASE ValiData_DB;

CREATE SCHEMA RAW_SCHEMA      COMMENT = 'Raw source data';
CREATE SCHEMA STAGING_SCHEMA  COMMENT = 'Cleaned and validated data';
CREATE SCHEMA CURATED_SCHEMA  COMMENT = 'Final validation results + AI explanations';


-- ─────────────────────────────────────────────────────────────────────────────
-- PART 4 — RAW SCHEMA TABLES
-- ─────────────────────────────────────────────────────────────────────────────

USE SCHEMA RAW_SCHEMA;

CREATE TABLE legacy_transactions (
    txn_id          VARCHAR(50),
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

CREATE TABLE new_system_transactions (
    txn_id          VARCHAR(50),
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
-- PART 5 — CURATED SCHEMA TABLES
-- ─────────────────────────────────────────────────────────────────────────────

USE SCHEMA CURATED_SCHEMA;

-- Main output — Notebook 05 writes here, Notebook 06 adds AI explanation
CREATE TABLE validation_results (
    txn_id              VARCHAR(50)   NOT NULL,
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
    validation_status   VARCHAR(30)   NOT NULL,
    validated_at        TIMESTAMP_NTZ,
    ai_explanation      VARCHAR(4000),
    ai_explained_at     TIMESTAMP_NTZ,
    loaded_at           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Pipeline run history — every notebook appends one row here
CREATE TABLE audit_log (
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
    status              VARCHAR(20),
    notes               VARCHAR(1000)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- PART 6 — SERVICE USER FOR DATABRICKS
-- ─────────────────────────────────────────────────────────────────────────────
-- IMPORTANT: Change the password before running this section

-- CREATE USER requires ACCOUNTADMIN role in Snowflake
USE ROLE ACCOUNTADMIN;

CREATE USER VALIDATA_SVC_USER
    PASSWORD             = 'ValidataP!p3line2026'
    DEFAULT_ROLE         = SYSADMIN
    DEFAULT_WAREHOUSE    = COMPUTE_WH
    DEFAULT_NAMESPACE    = ValiData_DB.CURATED_SCHEMA
    MUST_CHANGE_PASSWORD = FALSE
    COMMENT              = 'Databricks pipeline service account';

-- Switch back to SYSADMIN for grants
USE ROLE SYSADMIN;

GRANT USAGE ON WAREHOUSE COMPUTE_WH TO USER VALIDATA_SVC_USER;
GRANT USAGE ON DATABASE  ValiData_DB TO USER VALIDATA_SVC_USER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE ValiData_DB             TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ValiData_DB.RAW_SCHEMA     TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ValiData_DB.CURATED_SCHEMA TO USER VALIDATA_SVC_USER;
-- Note: FUTURE TABLES cannot be granted directly to a USER in Snowflake.
-- The ALL TABLES grants above cover all existing tables (already created in this script).


-- ─────────────────────────────────────────────────────────────────────────────
-- PART 7 — VERIFY EVERYTHING
-- ─────────────────────────────────────────────────────────────────────────────

SHOW DATABASES   LIKE 'ValiData_DB';
SHOW SCHEMAS     IN DATABASE ValiData_DB;
SHOW TABLES      IN SCHEMA ValiData_DB.RAW_SCHEMA;
SHOW TABLES      IN SCHEMA ValiData_DB.CURATED_SCHEMA;
SHOW USERS       LIKE 'VALIDATA_SVC_USER';
SHOW WAREHOUSES  LIKE 'COMPUTE_WH';

-- Test Cortex AI — if this returns text, Notebook 06 AI layer is ready
-- (Skipping Cortex test because we are using Gemini API instead on trial accounts)
