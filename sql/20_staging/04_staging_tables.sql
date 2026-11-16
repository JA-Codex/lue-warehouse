-- US-5.1: the staging tables (lue_staging.stg_*), the clean contract the dimension and fact
-- loaders read (docs/contracts/staging.md). Written by etl/staging/ddl.py from etl/staging/spec.py
-- (do not edit by hand). Run as lue_etl by scripts/db_deploy.py. Safe to re-run.
-- One row per natural key (the primary key): the surviving version (D15). Typed and cleaned.
-- Lineage columns at the end name the bronze row that survived. Columns marked "derived" are
-- computed by etl/staging/business.py (US-5.2). No secondary indexes (D20).

-- One row per building.
CREATE TABLE IF NOT EXISTS lue_staging.stg_building (
    building_code            VARCHAR(8) NOT NULL,
    building_name            VARCHAR(80),
    city                     VARCHAR(30),
    city_code                CHAR(3),
    region                   VARCHAR(30),
    locality                 VARCHAR(40),
    building_class           CHAR(1),
    year_built               SMALLINT,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_building PRIMARY KEY (building_code)
);

-- One row per unit (the latest version by updated_at).
CREATE TABLE IF NOT EXISTS lue_staging.stg_unit (
    unit_id                  INT NOT NULL,
    building_code            VARCHAR(8),
    unit_no                  VARCHAR(10),
    floor_no                 SMALLINT,
    unit_type                VARCHAR(20),
    area_sqft                NUMERIC(8,1),
    bedrooms                 SMALLINT,
    furnished                BOOLEAN,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_unit PRIMARY KEY (unit_id)
);

-- One row per tenant (the latest version by updated_at).
CREATE TABLE IF NOT EXISTS lue_staging.stg_tenant (
    tenant_code              VARCHAR(12) NOT NULL,
    tenant_name              VARCHAR(100),
    tenant_type              VARCHAR(12),
    employer_sector          VARCHAR(30),
    phone                    VARCHAR(20),
    contact_channel          VARCHAR(12),
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_tenant PRIMARY KEY (tenant_code)
);

-- One row per lease.
CREATE TABLE IF NOT EXISTS lue_staging.stg_lease (
    lease_number             VARCHAR(14) NOT NULL,
    unit_id                  INT,
    tenant_code              VARCHAR(12),
    lease_type               VARCHAR(12),
    start_date               DATE,
    end_date                 DATE,
    monthly_rent             NUMERIC(12,2),
    rent_review_type         VARCHAR(20),
    previous_lease_number    VARCHAR(14),
    status                   VARCHAR(12),
    term_months              SMALLINT,  -- derived (US-5.2)
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_lease PRIMARY KEY (lease_number)
);

-- One row per lease event.
CREATE TABLE IF NOT EXISTS lue_staging.stg_lease_event (
    event_id                 INT NOT NULL,
    lease_number             VARCHAR(14),
    event_code               VARCHAR(8),
    event_date               DATE,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_lease_event PRIMARY KEY (event_id)
);

-- One row per invoice.
CREATE TABLE IF NOT EXISTS lue_staging.stg_invoice (
    invoice_number           VARCHAR(16) NOT NULL,
    lease_number             VARCHAR(14),
    invoice_date             DATE,
    due_date                 DATE,
    status                   VARCHAR(10),
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_invoice PRIMARY KEY (invoice_number)
);

-- One row per invoice line.
CREATE TABLE IF NOT EXISTS lue_staging.stg_invoice_line (
    invoice_number           VARCHAR(16) NOT NULL,
    line_no                  SMALLINT NOT NULL,
    charge_code              VARCHAR(8),
    billed_amount            NUMERIC(12,2),
    tax_amount               NUMERIC(12,2),
    discount_amount          NUMERIC(12,2),
    net_amount               NUMERIC(12,2),
    due_date                 DATE,  -- derived (US-5.2)
    allocated_amount         NUMERIC(12,2),  -- derived (US-5.2)
    open_balance             NUMERIC(12,2),  -- derived (US-5.2)
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_invoice_line PRIMARY KEY (invoice_number, line_no)
);

-- One row per payment.
CREATE TABLE IF NOT EXISTS lue_staging.stg_payment (
    payment_reference        VARCHAR(20) NOT NULL,
    tenant_code              VARCHAR(12),
    paid_at                  TIMESTAMP,
    method_code              VARCHAR(10),
    amount                   NUMERIC(12,2),
    status                   VARCHAR(10),
    reversal_of              VARCHAR(20),
    is_reversal              BOOLEAN,  -- derived (US-5.2)
    is_electronic            BOOLEAN,  -- derived (US-5.2)
    allocated_amount         NUMERIC(12,2),  -- derived (US-5.2)
    settlement_id            VARCHAR(20),  -- derived (US-5.2)
    settlement_date          DATE,  -- derived (US-5.2)
    settlement_lag_days      SMALLINT,  -- derived (US-5.2)
    is_unsettled             BOOLEAN,  -- derived (US-5.2)
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_payment PRIMARY KEY (payment_reference)
);

-- One row per payment and invoice line: S1's allocations, plus the allocations staging derives for a payment the source left (partly) unallocated (US-5.2).
CREATE TABLE IF NOT EXISTS lue_staging.stg_payment_allocation (
    payment_reference        VARCHAR(20) NOT NULL,
    invoice_number           VARCHAR(16) NOT NULL,
    line_no                  SMALLINT NOT NULL,
    allocated_amount         NUMERIC(12,2),
    allocation_source        VARCHAR(8),
    paid_at                  TIMESTAMP,  -- derived (US-5.2)
    due_date                 DATE,  -- derived (US-5.2)
    days_past_due            SMALLINT,  -- derived (US-5.2)
    is_reversal              BOOLEAN,  -- derived (US-5.2)
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_payment_allocation PRIMARY KEY (payment_reference, invoice_number, line_no)
);

-- One row per settlement line of the banks and wallets.
CREATE TABLE IF NOT EXISTS lue_staging.stg_settlement (
    channel                  VARCHAR(12) NOT NULL,
    settlement_id            VARCHAR(20) NOT NULL,
    payment_reference        VARCHAR(20),
    transaction_date         DATE,
    settlement_date          DATE,
    gross_amount             NUMERIC(12,2),
    fee_amount               NUMERIC(12,2),
    net_amount               NUMERIC(12,2),
    is_matched               BOOLEAN,  -- derived (US-5.2)
    settlement_lag_days      SMALLINT,  -- derived (US-5.2)
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_settlement PRIMARY KEY (channel, settlement_id)
);

-- One row per owner.
CREATE TABLE IF NOT EXISTS lue_staging.stg_owner (
    owner_code               VARCHAR(10) NOT NULL,
    owner_name               VARCHAR(100),
    owner_type               VARCHAR(12),
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_owner PRIMARY KEY (owner_code)
);

-- One row per unit ownership period.
CREATE TABLE IF NOT EXISTS lue_staging.stg_ownership (
    building_code            VARCHAR(8) NOT NULL,
    unit_no                  VARCHAR(10) NOT NULL,
    owner_code               VARCHAR(10),
    valid_from               DATE NOT NULL,
    valid_to                 DATE,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_ownership PRIMARY KEY (building_code, unit_no, valid_from)
);

-- One row per vendor.
CREATE TABLE IF NOT EXISTS lue_staging.stg_vendor (
    vendor_code              VARCHAR(10) NOT NULL,
    vendor_name              VARCHAR(80),
    trade                    VARCHAR(30),
    rating                   CHAR(1),
    phone                    VARCHAR(20),
    previous_rating          CHAR(1),
    rating_changed_on        DATE,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_vendor PRIMARY KEY (vendor_code)
);

-- One row per maintenance subcategory and SLA version (valid_from).
CREATE TABLE IF NOT EXISTS lue_staging.stg_maintenance_category (
    subcategory_code         VARCHAR(10) NOT NULL,
    subcategory_name         VARCHAR(40),
    category_name            VARCHAR(30),
    default_sla_hours        SMALLINT,
    valid_from               DATE NOT NULL,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_maintenance_category PRIMARY KEY (subcategory_code, valid_from)
);

-- One row per holiday or Ramadan day.
CREATE TABLE IF NOT EXISTS lue_staging.stg_holiday (
    holiday_date             DATE NOT NULL,
    holiday_name             VARCHAR(40),
    is_public_holiday        BOOLEAN,
    is_ramadan               BOOLEAN,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_holiday PRIMARY KEY (holiday_date)
);

-- One row per ticket: of two copies the one with the latest status time (D15). A ticket copy with no Raised entry that E4 accepted is not staged. The copy (src_file, src_row) is compared as a value: when another copy wins, the row is updated and its status history replaced.
CREATE TABLE IF NOT EXISTS lue_staging.stg_ticket (
    ticket_id                VARCHAR(14) NOT NULL,
    building_code            VARCHAR(8),
    unit_no                  VARCHAR(10),
    category                 VARCHAR(30),
    subcategory_code         VARCHAR(10),
    subcategory_name         VARCHAR(40),
    priority                 VARCHAR(10),
    is_emergency             BOOLEAN,
    source_is_recurring      BOOLEAN,
    is_tenant_caused         BOOLEAN,
    reported_via             VARCHAR(20),
    description              VARCHAR(200),
    vendor_code              VARCHAR(10),
    estimated_cost           NUMERIC(12,2),
    actual_cost              NUMERIC(12,2),
    status                   VARCHAR(12),
    raised_at                TIMESTAMP,  -- derived (US-5.2)
    assigned_at              TIMESTAMP,  -- derived (US-5.2)
    resolved_at              TIMESTAMP,  -- derived (US-5.2)
    verified_at              TIMESTAMP,  -- derived (US-5.2)
    days_to_assign           NUMERIC(6,2),  -- derived (US-5.2)
    days_to_resolve          NUMERIC(6,2),  -- derived (US-5.2)
    days_to_verify           NUMERIC(6,2),  -- derived (US-5.2)
    hours_to_resolve         NUMERIC(8,2),  -- derived (US-5.2)
    sla_hours                SMALLINT,  -- derived (US-5.2)
    sla_breached             BOOLEAN,  -- derived (US-5.2)
    is_recurring             BOOLEAN,  -- derived (US-5.2)
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    src_file                 VARCHAR(200),
    src_row                  INT,
    CONSTRAINT pk_stg_ticket PRIMARY KEY (ticket_id)
);

-- One row per status entry of the staged copy of each ticket.
CREATE TABLE IF NOT EXISTS lue_staging.stg_ticket_status (
    ticket_id                VARCHAR(14) NOT NULL,
    status_seq               SMALLINT NOT NULL,
    status                   VARCHAR(12),
    status_at                TIMESTAMP,
    vendor_code              VARCHAR(10),
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_ticket_status PRIMARY KEY (ticket_id, status_seq)
);

-- One row per city and day.
CREATE TABLE IF NOT EXISTS lue_staging.stg_weather (
    city                     VARCHAR(30) NOT NULL,
    weather_date             DATE NOT NULL,
    max_temp_c               NUMERIC(4,1),
    rainfall_mm              NUMERIC(6,1),
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_weather PRIMARY KEY (city, weather_date)
);

-- One row per offer in the catalogue.
CREATE TABLE IF NOT EXISTS lue_staging.stg_incentive_offer (
    offer_code               VARCHAR(10) NOT NULL,
    offer_type               VARCHAR(20),
    description              VARCHAR(80),
    discount_pct             NUMERIC(5,2),
    rent_free_days           SMALLINT,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_incentive_offer PRIMARY KEY (offer_code)
);

-- One row per offer posted on a unit. A day-first date is read as such (repaired).
CREATE TABLE IF NOT EXISTS lue_staging.stg_incentive_log (
    building_code            VARCHAR(8) NOT NULL,
    unit_no                  VARCHAR(10) NOT NULL,
    offer_code               VARCHAR(10) NOT NULL,
    start_date               DATE NOT NULL,
    end_date                 DATE,
    source_system            VARCHAR(20),
    batch_id                 BIGINT,
    loaded_at                TIMESTAMP,
    src_row_id               BIGINT,
    src_updated_at           TIMESTAMP,
    run_id                   BIGINT,
    staged_at                TIMESTAMP,
    CONSTRAINT pk_stg_incentive_log PRIMARY KEY (building_code, unit_no, offer_code, start_date)
);
