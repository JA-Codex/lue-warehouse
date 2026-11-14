-- US-2.2: source system S1 (LUE-PMS), master and reference tables.
-- Run as lue_etl, connected to the lue_source database (scripts/db_load_source.py does this).
-- Safe to re-run: every statement is IF NOT EXISTS.
--
-- The tables follow the normalised source ERD of the frozen Phase 1 pack (diagrams/mermaid/05_source_erd.mmd):
-- same names, same column order, same types. Only the primary keys are enforced. The foreign keys in the
-- ERD (units.building_code, and later leases, invoices and payments) are NOT declared: PropertyHub is a
-- legacy system with loose integrity, and the defects US-2.6 plants (orphan references, invoices before
-- the tenant record, missing amounts) could not exist in a database that enforced them.
-- Later stories add the transaction tables (leases, invoices, payments) in 02_*.sql and 03_*.sql.

CREATE TABLE IF NOT EXISTS src_pms.buildings (
    building_code   VARCHAR(8)  PRIMARY KEY,
    building_name   VARCHAR(80),
    city            VARCHAR(30),
    locality        VARCHAR(40),
    building_class  CHAR(1),
    year_built      SMALLINT
);

CREATE TABLE IF NOT EXISTS src_pms.units (
    unit_id         INT         PRIMARY KEY,
    building_code   VARCHAR(8),
    unit_no         VARCHAR(10),
    floor_no        SMALLINT,
    unit_type       VARCHAR(20),
    area_sqft       NUMERIC(8,1),
    bedrooms        SMALLINT,
    furnished       BOOLEAN,
    updated_at      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS src_pms.tenants (
    tenant_code      VARCHAR(12) PRIMARY KEY,
    full_name        VARCHAR(100),
    tenant_type      VARCHAR(12),
    employer_sector  VARCHAR(30),
    phone            VARCHAR(20),
    contact_channel  VARCHAR(12),
    updated_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS src_pms.charge_types (
    charge_code  VARCHAR(8)  PRIMARY KEY,
    name         VARCHAR(30),
    category     VARCHAR(12)
);

CREATE TABLE IF NOT EXISTS src_pms.payment_methods (
    method_code  VARCHAR(10) PRIMARY KEY,
    name         VARCHAR(30)
);
