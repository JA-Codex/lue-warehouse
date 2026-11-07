-- Lahore Urban Estates Analytics Warehouse · physical model (PostgreSQL 16+)
-- Phase 1 · Version 2.1. Generated from the same model as the data dictionary and diagrams.
-- Run in psql: \i physical_model.sql

DROP SCHEMA IF EXISTS lue_dw CASCADE;
DROP SCHEMA IF EXISTS lue_audit CASCADE;
CREATE SCHEMA lue_dw;
CREATE SCHEMA lue_audit;

-- helper used by a CHECK constraint so special members (-1, -2) pass
CREATE OR REPLACE FUNCTION key_is_special(k INT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE AS $$ SELECT k < 0 $$;

-- ============================== DIMENSIONS ==============================

-- dim_date: One row per calendar day from 2023-07-01 to 2027-06-30
CREATE TABLE lue_dw.dim_date (
    date_key                   INT NOT NULL,
    full_date                  DATE NOT NULL,
    day_of_month               SMALLINT NOT NULL,
    day_name                   VARCHAR(10) NOT NULL,
    is_weekend                 BOOLEAN NOT NULL,
    week_of_year               SMALLINT NOT NULL,
    month_no                   SMALLINT NOT NULL,
    month_name                 VARCHAR(10) NOT NULL,
    quarter_no                 SMALLINT NOT NULL,
    year_no                    SMALLINT NOT NULL,
    fiscal_month_no            SMALLINT NOT NULL,
    fiscal_quarter_no          SMALLINT NOT NULL,
    fiscal_year_label          VARCHAR(9) NOT NULL,
    is_public_holiday          BOOLEAN NOT NULL,
    holiday_name               VARCHAR(60),
    is_ramadan                 BOOLEAN NOT NULL,
    CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    CONSTRAINT uq_dim_date_nk UNIQUE (full_date)
);
INSERT INTO lue_dw.dim_date (date_key, full_date, day_of_month, day_name, is_weekend, week_of_year, month_no, month_name, quarter_no, year_no, fiscal_month_no, fiscal_quarter_no, fiscal_year_label, is_public_holiday, holiday_name, is_ramadan)
  VALUES (-1, '1900-01-01', 0, 'Unknown', FALSE, 0, 0, 'Unknown', 0, 0, 0, 0, 'Unknown', FALSE, 'Unknown', FALSE);
INSERT INTO lue_dw.dim_date (date_key, full_date, day_of_month, day_name, is_weekend, week_of_year, month_no, month_name, quarter_no, year_no, fiscal_month_no, fiscal_quarter_no, fiscal_year_label, is_public_holiday, holiday_name, is_ramadan)
  VALUES (-2, '1900-01-02', 0, 'N/A', FALSE, 0, 0, 'N/A', 0, 0, 0, 0, 'N/A', FALSE, 'Not applicable', FALSE);

-- dim_unit: One row per unit version (SCD Type 2)
CREATE TABLE lue_dw.dim_unit (
    unit_key                   INT NOT NULL,
    unit_nk                    VARCHAR(20) NOT NULL,
    building_code              VARCHAR(8) NOT NULL,
    unit_no                    VARCHAR(10) NOT NULL,
    unit_type                  VARCHAR(20) NOT NULL,
    bedrooms                   SMALLINT NOT NULL,
    area_sqft                  NUMERIC(8,1) NOT NULL,
    furnished_flag             BOOLEAN NOT NULL,
    floor_no                   SMALLINT NOT NULL,
    building_name              VARCHAR(80) NOT NULL,
    building_class             CHAR(1) NOT NULL,
    building_age_band          VARCHAR(12) NOT NULL,
    locality                   VARCHAR(40) NOT NULL,
    city                       VARCHAR(30) NOT NULL,
    region                     VARCHAR(30) NOT NULL,
    effective_from             DATE NOT NULL,
    effective_to               DATE NOT NULL,
    is_current                 BOOLEAN NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_unit PRIMARY KEY (unit_key),
    CONSTRAINT uq_dim_unit_version UNIQUE (unit_nk, effective_from)
);
INSERT INTO lue_dw.dim_unit (unit_key, unit_nk, building_code, unit_no, unit_type, bedrooms, area_sqft, furnished_flag, floor_no, building_name, building_class, building_age_band, locality, city, region, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 'Unknown', 0, 0, FALSE, 0, 'Unknown', '?', 'Unknown', 'Unknown', 'Unknown', 'Unknown', '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_unit (unit_key, unit_nk, building_code, unit_no, unit_type, bedrooms, area_sqft, furnished_flag, floor_no, building_name, building_class, building_age_band, locality, city, region, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-2, 'Not applicable', 'N/A', 'N/A', 'Not applicable', 0, 0, FALSE, 0, 'Not applicable', '?', 'N/A', 'Not applicable', 'Not applicable', 'Not applicable', '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_tenant: One row per tenant version (SCD Type 2)
CREATE TABLE lue_dw.dim_tenant (
    tenant_key                 INT NOT NULL,
    tenant_code                VARCHAR(12) NOT NULL,
    tenant_name                VARCHAR(100) NOT NULL,
    tenant_type                VARCHAR(12) NOT NULL,
    employer_sector            VARCHAR(30) NOT NULL,
    contact_channel            VARCHAR(12) NOT NULL,
    is_inferred                BOOLEAN NOT NULL,
    effective_from             DATE NOT NULL,
    effective_to               DATE NOT NULL,
    is_current                 BOOLEAN NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_tenant PRIMARY KEY (tenant_key),
    CONSTRAINT uq_dim_tenant_version UNIQUE (tenant_code, effective_from)
);
INSERT INTO lue_dw.dim_tenant (tenant_key, tenant_code, tenant_name, tenant_type, employer_sector, contact_channel, is_inferred, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'Unknown', FALSE, '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_tenant (tenant_key, tenant_code, tenant_name, tenant_type, employer_sector, contact_channel, is_inferred, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'N/A', 'Not applicable', 'N/A', FALSE, '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_lease: One row per lease contract
CREATE TABLE lue_dw.dim_lease (
    lease_key                  INT NOT NULL,
    lease_number               VARCHAR(14) NOT NULL,
    lease_type                 VARCHAR(12) NOT NULL,
    start_date                 DATE NOT NULL,
    end_date                   DATE NOT NULL,
    term_months                SMALLINT NOT NULL,
    original_monthly_rent      NUMERIC(12,2) NOT NULL,
    rent_review_type           VARCHAR(20) NOT NULL,
    previous_lease_number      VARCHAR(14),
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_lease PRIMARY KEY (lease_key),
    CONSTRAINT uq_dim_lease_nk UNIQUE (lease_number),
    CONSTRAINT ck_lease_dates CHECK (key_is_special(lease_key) OR end_date > start_date)
);
INSERT INTO lue_dw.dim_lease (lease_key, lease_number, lease_type, start_date, end_date, term_months, original_monthly_rent, rent_review_type, previous_lease_number, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', '1900-01-01', '1900-01-01', 0, 0, 'Unknown', 'Unknown', 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_lease (lease_key, lease_number, lease_type, start_date, end_date, term_months, original_monthly_rent, rent_review_type, previous_lease_number, source_system, batch_id, loaded_at)
  VALUES (-2, 'Not applicable', 'N/A', '1900-01-01', '1900-01-01', 0, 0, 'Not applicable', 'Not applicable', 'ETL', 0, '1900-01-01 00:00:00');

-- dim_owner: One row per owner
CREATE TABLE lue_dw.dim_owner (
    owner_key                  INT NOT NULL,
    owner_code                 VARCHAR(10) NOT NULL,
    owner_name                 VARCHAR(100) NOT NULL,
    owner_type                 VARCHAR(12) NOT NULL,
    portfolio_size_band        VARCHAR(10) NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_owner PRIMARY KEY (owner_key),
    CONSTRAINT uq_dim_owner_nk UNIQUE (owner_code)
);
INSERT INTO lue_dw.dim_owner (owner_key, owner_code, owner_name, owner_type, portfolio_size_band, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_owner (owner_key, owner_code, owner_name, owner_type, portfolio_size_band, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'N/A', 'N/A', 'ETL', 0, '1900-01-01 00:00:00');

-- dim_payment_method: One row per payment method
CREATE TABLE lue_dw.dim_payment_method (
    payment_method_key         INT NOT NULL,
    method_code                VARCHAR(10) NOT NULL,
    method_name                VARCHAR(30) NOT NULL,
    channel_group              VARCHAR(20) NOT NULL,
    typical_settlement_days    SMALLINT NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_payment_method PRIMARY KEY (payment_method_key),
    CONSTRAINT uq_dim_payment_method_nk UNIQUE (method_code)
);
INSERT INTO lue_dw.dim_payment_method (payment_method_key, method_code, method_name, channel_group, typical_settlement_days, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 0, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_payment_method (payment_method_key, method_code, method_name, channel_group, typical_settlement_days, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'Not applicable', 0, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_charge_type: One row per charge type
CREATE TABLE lue_dw.dim_charge_type (
    charge_type_key            INT NOT NULL,
    charge_code                VARCHAR(8) NOT NULL,
    charge_type_name           VARCHAR(30) NOT NULL,
    charge_category            VARCHAR(12) NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_charge_type PRIMARY KEY (charge_type_key),
    CONSTRAINT uq_dim_charge_type_nk UNIQUE (charge_code)
);
INSERT INTO lue_dw.dim_charge_type (charge_type_key, charge_code, charge_type_name, charge_category, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_charge_type (charge_type_key, charge_code, charge_type_name, charge_category, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'N/A', 'ETL', 0, '1900-01-01 00:00:00');

-- dim_maintenance_category: One row per maintenance subcategory version (SCD Type 2)
CREATE TABLE lue_dw.dim_maintenance_category (
    maint_category_key         INT NOT NULL,
    subcategory_code           VARCHAR(10) NOT NULL,
    subcategory_name           VARCHAR(40) NOT NULL,
    category_name              VARCHAR(30) NOT NULL,
    default_sla_hours          SMALLINT NOT NULL,
    effective_from             DATE NOT NULL,
    effective_to               DATE NOT NULL,
    is_current                 BOOLEAN NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_maintenance_category PRIMARY KEY (maint_category_key),
    CONSTRAINT uq_dim_maintenance_category_version UNIQUE (subcategory_code, effective_from)
);
INSERT INTO lue_dw.dim_maintenance_category (maint_category_key, subcategory_code, subcategory_name, category_name, default_sla_hours, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 0, '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_maintenance_category (maint_category_key, subcategory_code, subcategory_name, category_name, default_sla_hours, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'Not applicable', 0, '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_vendor: One row per vendor version (SCD Type 2)
CREATE TABLE lue_dw.dim_vendor (
    vendor_key                 INT NOT NULL,
    vendor_code                VARCHAR(10) NOT NULL,
    vendor_name                VARCHAR(80) NOT NULL,
    trade                      VARCHAR(30) NOT NULL,
    rating_band                CHAR(1) NOT NULL,
    phone                      VARCHAR(20) NOT NULL,
    effective_from             DATE NOT NULL,
    effective_to               DATE NOT NULL,
    is_current                 BOOLEAN NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_vendor PRIMARY KEY (vendor_key),
    CONSTRAINT uq_dim_vendor_version UNIQUE (vendor_code, effective_from)
);
INSERT INTO lue_dw.dim_vendor (vendor_key, vendor_code, vendor_name, trade, rating_band, phone, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', '?', 'Unknown', '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_vendor (vendor_key, vendor_code, vendor_name, trade, rating_band, phone, effective_from, effective_to, is_current, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'Not applicable', '?', 'Not applicable', '1900-01-01', '9999-12-31', TRUE, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_lease_event_type: One row per lease event type
CREATE TABLE lue_dw.dim_lease_event_type (
    lease_event_type_key       INT NOT NULL,
    event_code                 VARCHAR(8) NOT NULL,
    event_name                 VARCHAR(20) NOT NULL,
    is_exit_event              BOOLEAN NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_lease_event_type PRIMARY KEY (lease_event_type_key),
    CONSTRAINT uq_dim_lease_event_type_nk UNIQUE (event_code)
);
INSERT INTO lue_dw.dim_lease_event_type (lease_event_type_key, event_code, event_name, is_exit_event, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', FALSE, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_lease_event_type (lease_event_type_key, event_code, event_name, is_exit_event, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', FALSE, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_request_flags: One row per combination of the three request flags (junk dimension, 8 rows)
CREATE TABLE lue_dw.dim_request_flags (
    request_flags_key          INT NOT NULL,
    is_emergency               BOOLEAN NOT NULL,
    is_recurring               BOOLEAN NOT NULL,
    is_tenant_caused           BOOLEAN NOT NULL,
    flags_label                VARCHAR(60) NOT NULL,
    CONSTRAINT pk_dim_request_flags PRIMARY KEY (request_flags_key),
    CONSTRAINT uq_dim_request_flags_nk UNIQUE (is_emergency, is_recurring, is_tenant_caused)
);

-- dim_incentive: One row per incentive offer type
CREATE TABLE lue_dw.dim_incentive (
    incentive_key              INT NOT NULL,
    incentive_code             VARCHAR(10) NOT NULL,
    incentive_type             VARCHAR(20) NOT NULL,
    incentive_description      VARCHAR(80) NOT NULL,
    discount_pct               NUMERIC(5,2) NOT NULL,
    rent_free_days             SMALLINT NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_incentive PRIMARY KEY (incentive_key),
    CONSTRAINT uq_dim_incentive_nk UNIQUE (incentive_code)
);
INSERT INTO lue_dw.dim_incentive (incentive_key, incentive_code, incentive_type, incentive_description, discount_pct, rent_free_days, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 0, 0, 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_incentive (incentive_key, incentive_code, incentive_type, incentive_description, discount_pct, rent_free_days, source_system, batch_id, loaded_at)
  VALUES (-2, 'N/A', 'Not applicable', 'Not applicable', 0, 0, 'ETL', 0, '1900-01-01 00:00:00');

-- dim_weather: One row per city per calendar day
CREATE TABLE lue_dw.dim_weather (
    weather_key                INT NOT NULL,
    city                       VARCHAR(30) NOT NULL,
    weather_date               DATE NOT NULL,
    rainfall_mm                NUMERIC(6,1) NOT NULL,
    rain_band                  VARCHAR(8) NOT NULL,
    max_temp_c                 NUMERIC(4,1) NOT NULL,
    heat_band                  VARCHAR(8) NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_dim_weather PRIMARY KEY (weather_key),
    CONSTRAINT uq_dim_weather_nk UNIQUE (city, weather_date)
);
INSERT INTO lue_dw.dim_weather (weather_key, city, weather_date, rainfall_mm, rain_band, max_temp_c, heat_band, source_system, batch_id, loaded_at)
  VALUES (-1, 'Unknown', '1900-01-01', 0, 'Unknown', 0, 'Unknown', 'ETL', 0, '1900-01-01 00:00:00');
INSERT INTO lue_dw.dim_weather (weather_key, city, weather_date, rainfall_mm, rain_band, max_temp_c, heat_band, source_system, batch_id, loaded_at)
  VALUES (-2, 'Not applicable', '1900-01-02', 0, 'N/A', 0, 'N/A', 'ETL', 0, '1900-01-01 00:00:00');

-- ================================ FACTS =================================

-- fact_rent_invoice_line (Transaction): One row represents one charge line (rent, service charge, late fee, utility or credit note) on one invoice issued to one lease.
CREATE TABLE lue_dw.fact_rent_invoice_line (
    invoice_line_sk            BIGINT NOT NULL,
    invoice_date_key           INT NOT NULL,
    due_date_key               INT NOT NULL,
    unit_key                   INT NOT NULL,
    tenant_key                 INT NOT NULL,
    lease_key                  INT NOT NULL,
    owner_key                  INT NOT NULL,
    charge_type_key            INT NOT NULL,
    invoice_number             VARCHAR(16) NOT NULL,
    invoice_line_no            SMALLINT NOT NULL,
    billed_amount              NUMERIC(12,2) NOT NULL,
    tax_amount                 NUMERIC(12,2) NOT NULL,
    discount_amount            NUMERIC(12,2) NOT NULL,
    net_amount                 NUMERIC(12,2) NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_fact_rent_invoice_line PRIMARY KEY (invoice_line_sk),
    CONSTRAINT fk_fact_rent_invoice_li_invoice_date FOREIGN KEY (invoice_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_rent_invoice_li_due_date FOREIGN KEY (due_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_rent_invoice_li_unit FOREIGN KEY (unit_key) REFERENCES lue_dw.dim_unit (unit_key),
    CONSTRAINT fk_fact_rent_invoice_li_tenant FOREIGN KEY (tenant_key) REFERENCES lue_dw.dim_tenant (tenant_key),
    CONSTRAINT fk_fact_rent_invoice_li_lease FOREIGN KEY (lease_key) REFERENCES lue_dw.dim_lease (lease_key),
    CONSTRAINT fk_fact_rent_invoice_li_owner FOREIGN KEY (owner_key) REFERENCES lue_dw.dim_owner (owner_key),
    CONSTRAINT fk_fact_rent_invoice_li_charge_type FOREIGN KEY (charge_type_key) REFERENCES lue_dw.dim_charge_type (charge_type_key),
    CONSTRAINT uq_invoice_line UNIQUE (invoice_number, invoice_line_no),
    CONSTRAINT ck_net_amount CHECK (net_amount = billed_amount + tax_amount - discount_amount)
);
CREATE INDEX ix_fact_rent_invoice_line_invoice_date ON lue_dw.fact_rent_invoice_line (invoice_date_key);
CREATE INDEX ix_fact_rent_invoice_line_due_date ON lue_dw.fact_rent_invoice_line (due_date_key);
CREATE INDEX ix_fact_rent_invoice_line_unit ON lue_dw.fact_rent_invoice_line (unit_key);
CREATE INDEX ix_fact_rent_invoice_line_tenant ON lue_dw.fact_rent_invoice_line (tenant_key);
CREATE INDEX ix_fact_rent_invoice_line_lease ON lue_dw.fact_rent_invoice_line (lease_key);
CREATE INDEX ix_fact_rent_invoice_line_owner ON lue_dw.fact_rent_invoice_line (owner_key);
CREATE INDEX ix_fact_rent_invoice_line_charge_type ON lue_dw.fact_rent_invoice_line (charge_type_key);

-- fact_payment (Transaction): One row represents one portion of one payment receipt allocated to one invoice line.
CREATE TABLE lue_dw.fact_payment (
    payment_alloc_sk           BIGINT NOT NULL,
    paid_date_key              INT NOT NULL,
    due_date_key               INT NOT NULL,
    unit_key                   INT NOT NULL,
    tenant_key                 INT NOT NULL,
    lease_key                  INT NOT NULL,
    owner_key                  INT NOT NULL,
    payment_method_key         INT NOT NULL,
    charge_type_key            INT NOT NULL,
    payment_reference          VARCHAR(20) NOT NULL,
    invoice_number             VARCHAR(16) NOT NULL,
    invoice_line_no            SMALLINT NOT NULL,
    payment_amount             NUMERIC(12,2) NOT NULL,
    days_past_due              SMALLINT NOT NULL,
    settlement_lag_days        SMALLINT,
    is_reversal                BOOLEAN NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_fact_payment PRIMARY KEY (payment_alloc_sk),
    CONSTRAINT fk_fact_payment_paid_date FOREIGN KEY (paid_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_payment_due_date FOREIGN KEY (due_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_payment_unit FOREIGN KEY (unit_key) REFERENCES lue_dw.dim_unit (unit_key),
    CONSTRAINT fk_fact_payment_tenant FOREIGN KEY (tenant_key) REFERENCES lue_dw.dim_tenant (tenant_key),
    CONSTRAINT fk_fact_payment_lease FOREIGN KEY (lease_key) REFERENCES lue_dw.dim_lease (lease_key),
    CONSTRAINT fk_fact_payment_owner FOREIGN KEY (owner_key) REFERENCES lue_dw.dim_owner (owner_key),
    CONSTRAINT fk_fact_payment_payment_method FOREIGN KEY (payment_method_key) REFERENCES lue_dw.dim_payment_method (payment_method_key),
    CONSTRAINT fk_fact_payment_charge_type FOREIGN KEY (charge_type_key) REFERENCES lue_dw.dim_charge_type (charge_type_key)
);
CREATE INDEX ix_fact_payment_paid_date ON lue_dw.fact_payment (paid_date_key);
CREATE INDEX ix_fact_payment_due_date ON lue_dw.fact_payment (due_date_key);
CREATE INDEX ix_fact_payment_unit ON lue_dw.fact_payment (unit_key);
CREATE INDEX ix_fact_payment_tenant ON lue_dw.fact_payment (tenant_key);
CREATE INDEX ix_fact_payment_lease ON lue_dw.fact_payment (lease_key);
CREATE INDEX ix_fact_payment_owner ON lue_dw.fact_payment (owner_key);
CREATE INDEX ix_fact_payment_payment_method ON lue_dw.fact_payment (payment_method_key);
CREATE INDEX ix_fact_payment_charge_type ON lue_dw.fact_payment (charge_type_key);

-- fact_unit_occupancy_daily (Periodic snapshot): One row represents one unit at the end of one calendar day, whether occupied or vacant.
CREATE TABLE lue_dw.fact_unit_occupancy_daily (
    snapshot_date_key          INT NOT NULL,
    unit_key                   INT NOT NULL,
    tenant_key                 INT NOT NULL,
    lease_key                  INT NOT NULL,
    owner_key                  INT NOT NULL,
    is_occupied                SMALLINT NOT NULL,
    contract_rent              NUMERIC(12,2) NOT NULL,
    current_lease_arrears      NUMERIC(12,2) NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_fact_unit_occupancy_daily PRIMARY KEY (snapshot_date_key, unit_key),
    CONSTRAINT fk_fact_unit_occupancy__snapshot_date FOREIGN KEY (snapshot_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_unit_occupancy__unit FOREIGN KEY (unit_key) REFERENCES lue_dw.dim_unit (unit_key),
    CONSTRAINT fk_fact_unit_occupancy__tenant FOREIGN KEY (tenant_key) REFERENCES lue_dw.dim_tenant (tenant_key),
    CONSTRAINT fk_fact_unit_occupancy__lease FOREIGN KEY (lease_key) REFERENCES lue_dw.dim_lease (lease_key),
    CONSTRAINT fk_fact_unit_occupancy__owner FOREIGN KEY (owner_key) REFERENCES lue_dw.dim_owner (owner_key)
) PARTITION BY RANGE (snapshot_date_key);
-- one partition per month, Jul 2023 – Jun 2027
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2023_07 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20230701) TO (20230801);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2023_08 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20230801) TO (20230901);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2023_09 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20230901) TO (20231001);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2023_10 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20231001) TO (20231101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2023_11 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20231101) TO (20231201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2023_12 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20231201) TO (20240101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_01 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240101) TO (20240201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_02 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240201) TO (20240301);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_03 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240301) TO (20240401);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_04 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240401) TO (20240501);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_05 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240501) TO (20240601);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_06 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240601) TO (20240701);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_07 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240701) TO (20240801);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_08 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240801) TO (20240901);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_09 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20240901) TO (20241001);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_10 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20241001) TO (20241101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_11 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20241101) TO (20241201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2024_12 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20241201) TO (20250101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_01 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250101) TO (20250201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_02 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250201) TO (20250301);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_03 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250301) TO (20250401);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_04 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250401) TO (20250501);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_05 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250501) TO (20250601);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_06 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250601) TO (20250701);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_07 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250701) TO (20250801);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_08 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250801) TO (20250901);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_09 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20250901) TO (20251001);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_10 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20251001) TO (20251101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_11 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20251101) TO (20251201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2025_12 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20251201) TO (20260101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_01 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260101) TO (20260201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_02 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260201) TO (20260301);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_03 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260301) TO (20260401);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_04 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260401) TO (20260501);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_05 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260501) TO (20260601);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_06 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260601) TO (20260701);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_07 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260701) TO (20260801);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_08 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260801) TO (20260901);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_09 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20260901) TO (20261001);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_10 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20261001) TO (20261101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_11 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20261101) TO (20261201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2026_12 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20261201) TO (20270101);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2027_01 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20270101) TO (20270201);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2027_02 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20270201) TO (20270301);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2027_03 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20270301) TO (20270401);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2027_04 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20270401) TO (20270501);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2027_05 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20270501) TO (20270601);
CREATE TABLE lue_dw.fact_unit_occupancy_daily_2027_06 PARTITION OF lue_dw.fact_unit_occupancy_daily FOR VALUES FROM (20270601) TO (20270701);
CREATE INDEX ix_fact_unit_occupancy_da_tenant ON lue_dw.fact_unit_occupancy_daily (tenant_key);
CREATE INDEX ix_fact_unit_occupancy_da_lease ON lue_dw.fact_unit_occupancy_daily (lease_key);
CREATE INDEX ix_fact_unit_occupancy_da_owner ON lue_dw.fact_unit_occupancy_daily (owner_key);
CREATE INDEX ix_occupancy_unit_date ON lue_dw.fact_unit_occupancy_daily (unit_key, snapshot_date_key);

-- fact_maintenance_request (Accumulating snapshot): One row represents one maintenance request across its whole lifecycle, updated as it is assigned, resolved and verified.
CREATE TABLE lue_dw.fact_maintenance_request (
    request_sk                 BIGINT NOT NULL,
    raised_date_key            INT NOT NULL,
    assigned_date_key          INT NOT NULL,
    resolved_date_key          INT NOT NULL,
    verified_date_key          INT NOT NULL,
    unit_key                   INT NOT NULL,
    tenant_key                 INT NOT NULL,
    owner_key                  INT NOT NULL,
    maint_category_key         INT NOT NULL,
    vendor_key                 INT NOT NULL,
    request_flags_key          INT NOT NULL,
    weather_key                INT NOT NULL,
    request_number             VARCHAR(14) NOT NULL,
    request_status             VARCHAR(12) NOT NULL,
    days_to_assign             NUMERIC(6,2),
    days_to_resolve            NUMERIC(6,2),
    days_to_verify             NUMERIC(6,2),
    estimated_cost             NUMERIC(12,2),
    actual_cost                NUMERIC(12,2),
    sla_breached_flag          SMALLINT,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_fact_maintenance_request PRIMARY KEY (request_sk),
    CONSTRAINT fk_fact_maintenance_req_raised_date FOREIGN KEY (raised_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_maintenance_req_assigned_date FOREIGN KEY (assigned_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_maintenance_req_resolved_date FOREIGN KEY (resolved_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_maintenance_req_verified_date FOREIGN KEY (verified_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_maintenance_req_unit FOREIGN KEY (unit_key) REFERENCES lue_dw.dim_unit (unit_key),
    CONSTRAINT fk_fact_maintenance_req_tenant FOREIGN KEY (tenant_key) REFERENCES lue_dw.dim_tenant (tenant_key),
    CONSTRAINT fk_fact_maintenance_req_owner FOREIGN KEY (owner_key) REFERENCES lue_dw.dim_owner (owner_key),
    CONSTRAINT fk_fact_maintenance_req_maint_category FOREIGN KEY (maint_category_key) REFERENCES lue_dw.dim_maintenance_category (maint_category_key),
    CONSTRAINT fk_fact_maintenance_req_vendor FOREIGN KEY (vendor_key) REFERENCES lue_dw.dim_vendor (vendor_key),
    CONSTRAINT fk_fact_maintenance_req_request_flags FOREIGN KEY (request_flags_key) REFERENCES lue_dw.dim_request_flags (request_flags_key),
    CONSTRAINT fk_fact_maintenance_req_weather FOREIGN KEY (weather_key) REFERENCES lue_dw.dim_weather (weather_key)
);
CREATE INDEX ix_fact_maintenance_reque_raised_date ON lue_dw.fact_maintenance_request (raised_date_key);
CREATE INDEX ix_fact_maintenance_reque_assigned_date ON lue_dw.fact_maintenance_request (assigned_date_key);
CREATE INDEX ix_fact_maintenance_reque_resolved_date ON lue_dw.fact_maintenance_request (resolved_date_key);
CREATE INDEX ix_fact_maintenance_reque_verified_date ON lue_dw.fact_maintenance_request (verified_date_key);
CREATE INDEX ix_fact_maintenance_reque_unit ON lue_dw.fact_maintenance_request (unit_key);
CREATE INDEX ix_fact_maintenance_reque_tenant ON lue_dw.fact_maintenance_request (tenant_key);
CREATE INDEX ix_fact_maintenance_reque_owner ON lue_dw.fact_maintenance_request (owner_key);
CREATE INDEX ix_fact_maintenance_reque_maint_category ON lue_dw.fact_maintenance_request (maint_category_key);
CREATE INDEX ix_fact_maintenance_reque_vendor ON lue_dw.fact_maintenance_request (vendor_key);
CREATE INDEX ix_fact_maintenance_reque_request_flags ON lue_dw.fact_maintenance_request (request_flags_key);
CREATE INDEX ix_fact_maintenance_reque_weather ON lue_dw.fact_maintenance_request (weather_key);
CREATE INDEX ix_maint_open ON lue_dw.fact_maintenance_request (raised_date_key) WHERE resolved_date_key = -2;

-- fact_lease_event (Factless (event tracking)): One row represents one lifecycle event (signed, renewed, notice given or terminated) on one lease.
CREATE TABLE lue_dw.fact_lease_event (
    lease_event_sk             BIGINT NOT NULL,
    event_date_key             INT NOT NULL,
    unit_key                   INT NOT NULL,
    tenant_key                 INT NOT NULL,
    lease_key                  INT NOT NULL,
    owner_key                  INT NOT NULL,
    lease_event_type_key       INT NOT NULL,
    event_count                SMALLINT NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_fact_lease_event PRIMARY KEY (lease_event_sk),
    CONSTRAINT fk_fact_lease_event_event_date FOREIGN KEY (event_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_lease_event_unit FOREIGN KEY (unit_key) REFERENCES lue_dw.dim_unit (unit_key),
    CONSTRAINT fk_fact_lease_event_tenant FOREIGN KEY (tenant_key) REFERENCES lue_dw.dim_tenant (tenant_key),
    CONSTRAINT fk_fact_lease_event_lease FOREIGN KEY (lease_key) REFERENCES lue_dw.dim_lease (lease_key),
    CONSTRAINT fk_fact_lease_event_owner FOREIGN KEY (owner_key) REFERENCES lue_dw.dim_owner (owner_key),
    CONSTRAINT fk_fact_lease_event_lease_event_type FOREIGN KEY (lease_event_type_key) REFERENCES lue_dw.dim_lease_event_type (lease_event_type_key),
    CONSTRAINT ck_event_count CHECK (event_count = 1)
);
CREATE INDEX ix_fact_lease_event_event_date ON lue_dw.fact_lease_event (event_date_key);
CREATE INDEX ix_fact_lease_event_unit ON lue_dw.fact_lease_event (unit_key);
CREATE INDEX ix_fact_lease_event_tenant ON lue_dw.fact_lease_event (tenant_key);
CREATE INDEX ix_fact_lease_event_lease ON lue_dw.fact_lease_event (lease_key);
CREATE INDEX ix_fact_lease_event_owner ON lue_dw.fact_lease_event (owner_key);
CREATE INDEX ix_fact_lease_event_lease_event_type ON lue_dw.fact_lease_event (lease_event_type_key);

-- fact_vacancy_incentive_coverage (Factless (coverage)): One row represents one incentive offer being available on one vacant unit on one calendar day.
CREATE TABLE lue_dw.fact_vacancy_incentive_coverage (
    coverage_date_key          INT NOT NULL,
    unit_key                   INT NOT NULL,
    incentive_key              INT NOT NULL,
    owner_key                  INT NOT NULL,
    source_system              VARCHAR(20) NOT NULL,
    batch_id                   BIGINT NOT NULL,
    loaded_at                  TIMESTAMP NOT NULL,
    CONSTRAINT pk_fact_vacancy_incentive_coverage PRIMARY KEY (coverage_date_key, unit_key, incentive_key),
    CONSTRAINT fk_fact_vacancy_incenti_coverage_date FOREIGN KEY (coverage_date_key) REFERENCES lue_dw.dim_date (date_key),
    CONSTRAINT fk_fact_vacancy_incenti_unit FOREIGN KEY (unit_key) REFERENCES lue_dw.dim_unit (unit_key),
    CONSTRAINT fk_fact_vacancy_incenti_incentive FOREIGN KEY (incentive_key) REFERENCES lue_dw.dim_incentive (incentive_key),
    CONSTRAINT fk_fact_vacancy_incenti_owner FOREIGN KEY (owner_key) REFERENCES lue_dw.dim_owner (owner_key)
);
CREATE INDEX ix_fact_vacancy_incentive_owner ON lue_dw.fact_vacancy_incentive_coverage (owner_key);

-- ================================ AUDIT =================================

-- lue_audit.etl_run_log: One row per pipeline step per run
CREATE TABLE lue_audit.etl_run_log (
    run_id               BIGINT NOT NULL,
    step                 VARCHAR(40) NOT NULL,
    started_at           TIMESTAMP NOT NULL,
    ended_at             TIMESTAMP,
    rows_read            INT NOT NULL,
    rows_inserted        INT NOT NULL,
    rows_updated         INT NOT NULL,
    rows_rejected        INT NOT NULL,
    status               VARCHAR(10) NOT NULL,
    CONSTRAINT pk_etl_run_log PRIMARY KEY (run_id, step)
);

-- lue_audit.quarantine: One row per rejected source row
CREATE TABLE lue_audit.quarantine (
    quarantine_id        BIGINT NOT NULL,
    run_id               BIGINT NOT NULL,
    source_system        VARCHAR(20) NOT NULL,
    source_table         VARCHAR(40) NOT NULL,
    batch_id             BIGINT NOT NULL,
    record               JSONB NOT NULL,
    check_name           VARCHAR(30) NOT NULL,
    rejection_reason     VARCHAR(200) NOT NULL,
    rejected_at          TIMESTAMP NOT NULL,
    CONSTRAINT pk_quarantine PRIMARY KEY (quarantine_id)
);

-- lue_audit.reconciliation: One row per reconciliation check per run
CREATE TABLE lue_audit.reconciliation (
    run_id               BIGINT NOT NULL,
    check_name           VARCHAR(60) NOT NULL,
    source_value         NUMERIC(16,2) NOT NULL,
    warehouse_value      NUMERIC(16,2) NOT NULL,
    difference           NUMERIC(16,2) NOT NULL,
    passed               BOOLEAN NOT NULL,
    CONSTRAINT pk_reconciliation PRIMARY KEY (run_id, check_name)
);

-- lue_audit.lineage: One row per target table per source table
CREATE TABLE lue_audit.lineage (
    target_table         VARCHAR(60) NOT NULL,
    source_table         VARCHAR(60) NOT NULL,
    layer_path           VARCHAR(80) NOT NULL,
    transformation       VARCHAR(200) NOT NULL,
    CONSTRAINT pk_lineage PRIMARY KEY (target_table, source_table)
);
