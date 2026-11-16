-- US-3.2 to US-3.4: the bronze tables (lue_staging.brz_*). Run as lue_etl by scripts/db_deploy.py,
-- after sql/10_ddl. Safe to re-run.
--
-- Bronze is a faithful copy: every source value is kept as TEXT exactly as the source gave it
-- (NULL for a missing value), so nothing can fail to land and DQ-02 (data type) can judge the raw
-- value later. Every row carries batch_id, source_system and loaded_at (US-3.1). File sources also
-- keep the file name and the row's position in it; S1 rows keep an MD5 of the row (row_hash), which
-- is how the incremental extract (US-3.2) recognises a row it already has. Loads only append:
-- nothing is updated or deleted here, duplicates included (cleaning is staging's job, E5).
-- No secondary indexes (D20). Bronze is not part of the Phase 1 physical model (only the brz_*
-- name pattern is), so these tables are not compared by scripts/check_contract.py.


-- S1 src_pms.buildings
CREATE TABLE IF NOT EXISTS lue_staging.brz_building (
    building_code            TEXT,
    building_name            TEXT,
    city                     TEXT,
    locality                 TEXT,
    building_class           TEXT,
    year_built               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.units
CREATE TABLE IF NOT EXISTS lue_staging.brz_unit (
    unit_id                  TEXT,
    building_code            TEXT,
    unit_no                  TEXT,
    floor_no                 TEXT,
    unit_type                TEXT,
    area_sqft                TEXT,
    bedrooms                 TEXT,
    furnished                TEXT,
    updated_at               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.tenants
CREATE TABLE IF NOT EXISTS lue_staging.brz_tenant (
    tenant_code              TEXT,
    full_name                TEXT,
    tenant_type              TEXT,
    employer_sector          TEXT,
    phone                    TEXT,
    contact_channel          TEXT,
    updated_at               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.leases
CREATE TABLE IF NOT EXISTS lue_staging.brz_lease (
    lease_number             TEXT,
    unit_id                  TEXT,
    tenant_code              TEXT,
    lease_type               TEXT,
    start_date               TEXT,
    end_date                 TEXT,
    monthly_rent             TEXT,
    rent_review_type         TEXT,
    previous_lease_number    TEXT,
    status                   TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.lease_events
CREATE TABLE IF NOT EXISTS lue_staging.brz_lease_event (
    event_id                 TEXT,
    lease_number             TEXT,
    event_code               TEXT,
    event_date               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.invoices
CREATE TABLE IF NOT EXISTS lue_staging.brz_invoice (
    invoice_number           TEXT,
    lease_number             TEXT,
    invoice_date             TEXT,
    due_date                 TEXT,
    status                   TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.invoice_lines
CREATE TABLE IF NOT EXISTS lue_staging.brz_invoice_line (
    invoice_number           TEXT,
    line_no                  TEXT,
    charge_code              TEXT,
    billed_amount            TEXT,
    tax_amount               TEXT,
    discount_amount          TEXT,
    net_amount               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.payments
CREATE TABLE IF NOT EXISTS lue_staging.brz_payment (
    payment_reference        TEXT,
    tenant_code              TEXT,
    paid_at                  TEXT,
    method_code              TEXT,
    amount                   TEXT,
    status                   TEXT,
    reversal_of              TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S1 src_pms.payment_allocations
CREATE TABLE IF NOT EXISTS lue_staging.brz_payment_allocation (
    payment_reference        TEXT,
    invoice_number           TEXT,
    line_no                  TEXT,
    allocated_amount         TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    row_hash                 CHAR(32) NOT NULL
);

-- S2 registers.xlsx sheet owners
CREATE TABLE IF NOT EXISTS lue_staging.brz_owner (
    owner_code               TEXT,
    owner_name               TEXT,
    owner_type               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S2 registers.xlsx sheet ownership
CREATE TABLE IF NOT EXISTS lue_staging.brz_ownership (
    building_code            TEXT,
    unit_no                  TEXT,
    owner_code               TEXT,
    valid_from               TEXT,
    valid_to                 TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S2 registers.xlsx sheet vendors
CREATE TABLE IF NOT EXISTS lue_staging.brz_vendor (
    vendor_code              TEXT,
    vendor_name              TEXT,
    trade                    TEXT,
    rating                   TEXT,
    phone                    TEXT,
    previous_rating          TEXT,
    rating_changed_on        TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S2 registers.xlsx sheet sla_policy
CREATE TABLE IF NOT EXISTS lue_staging.brz_sla_policy (
    subcategory_code         TEXT,
    subcategory_name         TEXT,
    category_name            TEXT,
    default_sla_hours        TEXT,
    valid_from               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S2 registers.xlsx sheet holidays
CREATE TABLE IF NOT EXISTS lue_staging.brz_holiday (
    holiday_date             TEXT,
    holiday_name             TEXT,
    is_public_holiday        TEXT,
    is_ramadan               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S3 s3/settlement_<channel>_<date>.csv
CREATE TABLE IF NOT EXISTS lue_staging.brz_settlement (
    settlement_id            TEXT,
    payment_reference        TEXT,
    transaction_date         TEXT,
    settlement_date          TEXT,
    gross_amount             TEXT,
    fee_amount               TEXT,
    net_amount               TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S6 s6/offers.csv
CREATE TABLE IF NOT EXISTS lue_staging.brz_incentive_offer (
    offer_code               TEXT,
    offer_type               TEXT,
    description              TEXT,
    discount_pct             TEXT,
    rent_free_days           TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S6 s6/incentive_log.csv
CREATE TABLE IF NOT EXISTS lue_staging.brz_incentive_log (
    building_code            TEXT,
    unit_no                  TEXT,
    offer_code               TEXT,
    start_date               TEXT,
    end_date                 TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S4 s4/tickets.json: one row per ticket object (source_row = its position, 1 first)
CREATE TABLE IF NOT EXISTS lue_staging.brz_ticket (
    ticket_id                TEXT,
    building_code            TEXT,
    unit_no                  TEXT,
    category                 TEXT,
    subcategory_code         TEXT,
    subcategory              TEXT,
    priority                 TEXT,
    is_emergency             TEXT,
    is_recurring             TEXT,
    is_tenant_caused         TEXT,
    reported_via             TEXT,
    description              TEXT,
    vendor_code              TEXT,
    estimate                 TEXT,
    final_cost               TEXT,
    status                   TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S4 the status_history array, one row per entry; (source_file, source_row) is the ticket object it
-- came from, so the two copies of a duplicated ticket keep their own histories
CREATE TABLE IF NOT EXISTS lue_staging.brz_ticket_status (
    ticket_id                TEXT,
    status_seq               INT NOT NULL,
    status                   TEXT,
    status_at                TEXT,
    vendor_code              TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);

-- S5 data/weather_cache.json: one row per city and day
CREATE TABLE IF NOT EXISTS lue_staging.brz_weather (
    city                     TEXT,
    weather_date             TEXT,
    max_temp_c               TEXT,
    rainfall_mm              TEXT,
    batch_id                 BIGINT NOT NULL,
    source_system            VARCHAR(20) NOT NULL,
    loaded_at                TIMESTAMP NOT NULL,
    source_file              VARCHAR(200) NOT NULL,
    source_row               INT NOT NULL
);
