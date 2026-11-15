-- US-2.3: source system S1 (LUE-PMS), lease and billing tables.
-- Run as lue_etl, connected to the lue_source database (scripts/db_load_source.py does this).
-- Safe to re-run: every statement is IF NOT EXISTS.
--
-- Same rules as 01_src_pms_master.sql: the tables follow the normalised source ERD of the frozen Phase 1 pack
-- (diagrams/mermaid/05_source_erd.mmd), same names, column order and types, and only the primary keys are
-- enforced. The foreign keys of the ERD (leases.unit_id, leases.tenant_code, lease_events.lease_number,
-- invoices.lease_number, invoice_lines.invoice_number and charge_code) are NOT declared: US-2.6 plants orphan
-- references and invoices that precede their tenant record, which a database with foreign keys would refuse.

CREATE TABLE IF NOT EXISTS src_pms.leases (
    lease_number           VARCHAR(14)   PRIMARY KEY,
    unit_id                INT,
    tenant_code            VARCHAR(12),
    lease_type             VARCHAR(12),
    start_date             DATE,
    end_date               DATE,
    monthly_rent           NUMERIC(12,2),
    rent_review_type       VARCHAR(20),
    previous_lease_number  VARCHAR(14),
    status                 VARCHAR(12)
);

CREATE TABLE IF NOT EXISTS src_pms.lease_events (
    event_id      INT         PRIMARY KEY,
    lease_number  VARCHAR(14),
    event_code    VARCHAR(8),
    event_date    DATE
);

CREATE TABLE IF NOT EXISTS src_pms.invoices (
    invoice_number  VARCHAR(16) PRIMARY KEY,
    lease_number    VARCHAR(14),
    invoice_date    DATE,
    due_date        DATE,
    status          VARCHAR(12)
);

CREATE TABLE IF NOT EXISTS src_pms.invoice_lines (
    invoice_number   VARCHAR(16),
    line_no          SMALLINT,
    charge_code      VARCHAR(8),
    billed_amount    NUMERIC(12,2),
    tax_amount       NUMERIC(12,2),
    discount_amount  NUMERIC(12,2),
    net_amount       NUMERIC(12,2),
    PRIMARY KEY (invoice_number, line_no)
);
