-- US-2.4: source system S1 (LUE-PMS), payment tables.
-- Run as lue_etl, connected to the lue_source database (scripts/db_load_source.py does this).
-- Safe to re-run: every statement is IF NOT EXISTS.
--
-- Same rules as the other S1 files: names, column order and types follow the normalised source ERD of the
-- frozen Phase 1 pack, and only the primary keys are enforced. The foreign keys of the ERD
-- (payments.tenant_code, payments.method_code, payments.reversal_of, payment_allocations.payment_reference,
-- payment_allocations.invoice_number and line_no) are NOT declared: US-2.6 plants duplicate payments and
-- orphan references that a database with foreign keys would refuse.
-- A bounced cheque is a NEGATIVE payment (status 'Bounced', reversal_of = the original receipt).

CREATE TABLE IF NOT EXISTS src_pms.payments (
    payment_reference  VARCHAR(20)   PRIMARY KEY,
    tenant_code        VARCHAR(12),
    paid_at            TIMESTAMP,
    method_code        VARCHAR(10),
    amount             NUMERIC(12,2),
    status             VARCHAR(10),
    reversal_of        VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS src_pms.payment_allocations (
    payment_reference  VARCHAR(20),
    invoice_number     VARCHAR(16),
    line_no            SMALLINT,
    allocated_amount   NUMERIC(12,2),
    PRIMARY KEY (payment_reference, invoice_number, line_no)
);
