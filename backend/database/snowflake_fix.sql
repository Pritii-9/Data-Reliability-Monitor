-- =============================================================================
--  Validata — Snowflake FIX Script
--  Run this in Snowflake: Worksheets → paste ALL → Run All
--  This fixes the tables you already created to match what the notebooks expect
-- =============================================================================

USE ROLE SYSADMIN;
USE DATABASE ValiData_DB;
USE WAREHOUSE COMPUTE_WH;


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 1: legacy_transactions — add missing columns + rename keys
-- ─────────────────────────────────────────────────────────────────────────────

USE SCHEMA RAW_SCHEMA;

ALTER TABLE legacy_transactions RENAME COLUMN transaction_id   TO txn_id;
ALTER TABLE legacy_transactions RENAME COLUMN transaction_date TO txn_date;

ALTER TABLE legacy_transactions ADD COLUMN customer_id   VARCHAR(50);
ALTER TABLE legacy_transactions ADD COLUMN status        VARCHAR(20);
ALTER TABLE legacy_transactions ADD COLUMN region        VARCHAR(20);
ALTER TABLE legacy_transactions ADD COLUMN channel       VARCHAR(20);
ALTER TABLE legacy_transactions ADD COLUMN product_type  VARCHAR(50);
ALTER TABLE legacy_transactions ADD COLUMN reference_no  VARCHAR(50);
ALTER TABLE legacy_transactions ADD COLUMN _source_file  VARCHAR(500);
ALTER TABLE legacy_transactions ADD COLUMN _ingested_at  TIMESTAMP_NTZ;
ALTER TABLE legacy_transactions ADD COLUMN _source_label VARCHAR(50);
ALTER TABLE legacy_transactions ADD COLUMN _cleaned_at   TIMESTAMP_NTZ;
ALTER TABLE legacy_transactions ADD COLUMN _row_status   VARCHAR(10);


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 2: new_system_transactions — same fix
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE new_system_transactions RENAME COLUMN transaction_id   TO txn_id;
ALTER TABLE new_system_transactions RENAME COLUMN transaction_date TO txn_date;

ALTER TABLE new_system_transactions ADD COLUMN customer_id   VARCHAR(50);
ALTER TABLE new_system_transactions ADD COLUMN status        VARCHAR(20);
ALTER TABLE new_system_transactions ADD COLUMN region        VARCHAR(20);
ALTER TABLE new_system_transactions ADD COLUMN channel       VARCHAR(20);
ALTER TABLE new_system_transactions ADD COLUMN product_type  VARCHAR(50);
ALTER TABLE new_system_transactions ADD COLUMN reference_no  VARCHAR(50);
ALTER TABLE new_system_transactions ADD COLUMN _source_file  VARCHAR(500);
ALTER TABLE new_system_transactions ADD COLUMN _ingested_at  TIMESTAMP_NTZ;
ALTER TABLE new_system_transactions ADD COLUMN _source_label VARCHAR(50);
ALTER TABLE new_system_transactions ADD COLUMN _cleaned_at   TIMESTAMP_NTZ;
ALTER TABLE new_system_transactions ADD COLUMN _row_status   VARCHAR(10);


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 3: Drop old results + audit tables, create correct ones
-- ─────────────────────────────────────────────────────────────────────────────

USE SCHEMA CURATED_SCHEMA;

DROP TABLE IF EXISTS validata_results;
DROP TABLE IF EXISTS reconciliation_results;
DROP TABLE IF EXISTS audit_log;

-- Main validation results table (Notebook 05 writes here, Notebook 06 enriches)
CREATE TABLE VALIDATION_RESULTS (
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
    validation_status   VARCHAR(30)     NOT NULL,
    validated_at        TIMESTAMP_NTZ,
    ai_explanation      VARCHAR(4000),
    ai_explained_at     TIMESTAMP_NTZ,
    loaded_at           TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

-- Pipeline run history (all notebooks append here)
CREATE TABLE AUDIT_LOG (
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
-- FIX 4: Create service user for AWS Glue connection
-- ─────────────────────────────────────────────────────────────────────────────

CREATE USER IF NOT EXISTS VALIDATA_SVC_USER
    PASSWORD             = 'ValidataP!p3line2026'
    DEFAULT_ROLE         = SYSADMIN
    DEFAULT_WAREHOUSE    = COMPUTE_WH
    DEFAULT_NAMESPACE    = ValiData_DB.CURATED_SCHEMA
    MUST_CHANGE_PASSWORD = FALSE
    COMMENT              = 'Service account for Validata AWS Glue pipeline';

GRANT USAGE ON WAREHOUSE COMPUTE_WH TO USER VALIDATA_SVC_USER;
GRANT USAGE ON DATABASE  ValiData_DB TO USER VALIDATA_SVC_USER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE ValiData_DB TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ValiData_DB.RAW_SCHEMA     TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ValiData_DB.CURATED_SCHEMA TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA ValiData_DB.RAW_SCHEMA     TO USER VALIDATA_SVC_USER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA ValiData_DB.CURATED_SCHEMA TO USER VALIDATA_SVC_USER;


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFY — Run these last to confirm everything looks correct
-- ─────────────────────────────────────────────────────────────────────────────

SHOW TABLES IN SCHEMA ValiData_DB.RAW_SCHEMA;
SHOW TABLES IN SCHEMA ValiData_DB.CURATED_SCHEMA;
SHOW USERS  LIKE 'VALIDATA_SVC_USER';

-- Test Cortex AI (if this returns text, AI layer is ready)
SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', 'Say: Cortex is active') AS cortex_test;
