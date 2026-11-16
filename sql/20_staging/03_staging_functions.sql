-- US-5.1: cleaning functions and vocabularies for staging. Written by etl/staging/ddl.py from
-- etl/staging/spec.py (do not edit by hand). Run as lue_etl by scripts/db_deploy.py. Safe to re-run:
-- the seeds use ON CONFLICT DO UPDATE, so a changed spelling in the spec reaches the database.
--
-- clean_text trims, collapses inner spaces and turns an empty text into NULL. It does not change
-- case: a blind Title Case would break values such as 'IT and Software', 'WhatsApp' or 'HVAC'.
-- Case and spelling are standardised by std(domain, value) through the vocabulary, which matches
-- ignoring case and spaces: std('city', ' lahore ') = std('city', 'LAHORE') = 'Lahore'. A value
-- that is not in the vocabulary gives NULL (counted in the cleaning evidence, US-5.4).
-- Dates and numbers use the safe casts of E4: lue_audit.try_date (YYYY-MM-DD or DD/MM/YYYY),
-- try_numeric and try_timestamp.

CREATE OR REPLACE FUNCTION lue_staging.clean_text(value text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT nullif(regexp_replace(regexp_replace(value, '^\s+|\s+$', '', 'g'), '\s+', ' ', 'g'), '')
$$;

CREATE TABLE IF NOT EXISTS lue_staging.vocabulary (
    domain               VARCHAR(30) NOT NULL,
    variant_key          VARCHAR(80) NOT NULL,
    canonical            VARCHAR(80) NOT NULL,
    CONSTRAINT pk_vocabulary PRIMARY KEY (domain, variant_key)
);

INSERT INTO lue_staging.vocabulary (domain, variant_key, canonical) VALUES
    ('city', 'lahore', 'Lahore'),
    ('city', 'karachi', 'Karachi'),
    ('city', 'islamabad', 'Islamabad'),
    ('city', 'faisalabad', 'Faisalabad'),
    ('unit_type', 'apartment', 'Apartment'),
    ('unit_type', 'office', 'Office'),
    ('unit_type', 'shop', 'Shop'),
    ('tenant_type', 'individual', 'Individual'),
    ('tenant_type', 'corporate', 'Corporate'),
    ('contact_channel', 'phone', 'Phone'),
    ('contact_channel', 'whatsapp', 'WhatsApp'),
    ('contact_channel', 'email', 'Email'),
    ('employer_sector', 'banking', 'Banking'),
    ('employer_sector', 'construction', 'Construction'),
    ('employer_sector', 'education', 'Education'),
    ('employer_sector', 'energy', 'Energy'),
    ('employer_sector', 'government', 'Government'),
    ('employer_sector', 'healthcare', 'Healthcare'),
    ('employer_sector', 'hospitality', 'Hospitality'),
    ('employer_sector', 'it and software', 'IT and Software'),
    ('employer_sector', 'legal and consulting', 'Legal and Consulting'),
    ('employer_sector', 'logistics', 'Logistics'),
    ('employer_sector', 'manufacturing', 'Manufacturing'),
    ('employer_sector', 'media', 'Media'),
    ('employer_sector', 'retail', 'Retail'),
    ('employer_sector', 'self-employed', 'Self-employed'),
    ('employer_sector', 'telecom', 'Telecom'),
    ('lease_type', 'residential', 'Residential'),
    ('lease_type', 'commercial', 'Commercial'),
    ('rent_review_type', 'fixed', 'Fixed'),
    ('rent_review_type', 'annual escalation', 'Annual escalation'),
    ('lease_status', 'active', 'Active'),
    ('lease_status', 'renewed', 'Renewed'),
    ('lease_status', 'terminated', 'Terminated'),
    ('invoice_status', 'paid', 'Paid'),
    ('invoice_status', 'partial', 'Partial'),
    ('invoice_status', 'overdue', 'Overdue'),
    ('payment_status', 'cleared', 'Cleared'),
    ('payment_status', 'bounced', 'Bounced'),
    ('owner_type', 'individual', 'Individual'),
    ('owner_type', 'company', 'Company'),
    ('trade', 'plumbing', 'Plumbing'),
    ('trade', 'electrical', 'Electrical'),
    ('trade', 'hvac', 'HVAC'),
    ('trade', 'civil', 'Civil'),
    ('trade', 'pest control', 'Pest control'),
    ('trade', 'general maintenance', 'General maintenance'),
    ('ticket_category', 'plumbing', 'Plumbing'),
    ('ticket_category', 'electrical', 'Electrical'),
    ('ticket_category', 'hvac', 'HVAC'),
    ('ticket_category', 'civil', 'Civil'),
    ('ticket_category', 'pest control', 'Pest control'),
    ('ticket_category', 'other', 'Other'),
    ('priority', 'emergency', 'Emergency'),
    ('priority', 'high', 'High'),
    ('priority', 'normal', 'Normal'),
    ('reported_via', 'tenant app', 'Tenant app'),
    ('reported_via', 'building staff', 'Building staff'),
    ('ticket_status', 'raised', 'Raised'),
    ('ticket_status', 'assigned', 'Assigned'),
    ('ticket_status', 'resolved', 'Resolved'),
    ('ticket_status', 'verified', 'Verified'),
    ('offer_type', 'rent-free days', 'Rent-free days'),
    ('offer_type', 'discount', 'Discount'),
    ('offer_type', 'free maintenance', 'Free maintenance'),
    ('city', 'lhe', 'Lahore'),
    ('city', 'khi', 'Karachi'),
    ('city', 'isb', 'Islamabad'),
    ('city', 'fsd', 'Faisalabad'),
    ('city', 'lyallpur', 'Faisalabad'),
    ('contact_channel', 'e-mail', 'Email')
ON CONFLICT (domain, variant_key) DO UPDATE SET canonical = EXCLUDED.canonical;

CREATE OR REPLACE FUNCTION lue_staging.std(domain text, value text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT v.canonical FROM lue_staging.vocabulary v
    WHERE v.domain = std.domain AND v.variant_key = lower(lue_staging.clean_text(std.value))
$$;

CREATE TABLE IF NOT EXISTS lue_staging.city (
    city                 VARCHAR(30) NOT NULL,
    city_code            CHAR(3) NOT NULL,
    region               VARCHAR(30) NOT NULL,
    CONSTRAINT pk_city PRIMARY KEY (city)
);

INSERT INTO lue_staging.city (city, city_code, region) VALUES
    ('Lahore', 'LHE', 'Punjab'),
    ('Faisalabad', 'FSD', 'Punjab'),
    ('Karachi', 'KHI', 'Sindh'),
    ('Islamabad', 'ISB', 'Islamabad Capital Territory')
ON CONFLICT (city) DO UPDATE SET city_code = EXCLUDED.city_code, region = EXCLUDED.region;

CREATE OR REPLACE FUNCTION lue_staging.region_of(city text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT c.region FROM lue_staging.city c WHERE c.city = region_of.city
$$;

CREATE OR REPLACE FUNCTION lue_staging.city_code(city text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT c.city_code FROM lue_staging.city c WHERE c.city = city_code.city
$$;

CREATE TABLE IF NOT EXISTS lue_staging.payment_method (
    method_code          VARCHAR(10) NOT NULL,
    method_name          VARCHAR(30) NOT NULL,
    method_type          VARCHAR(20) NOT NULL,
    is_electronic        BOOLEAN NOT NULL,
    CONSTRAINT pk_payment_method PRIMARY KEY (method_code)
);

INSERT INTO lue_staging.payment_method (method_code, method_name, method_type, is_electronic) VALUES
    ('CASH', 'Cash', 'Cash', FALSE),
    ('CHEQUE', 'Cheque', 'Cheque', FALSE),
    ('BANK', 'Bank transfer', 'Bank', TRUE),
    ('RAAST', 'Raast', 'Instant payment', TRUE),
    ('JAZZ', 'JazzCash', 'Mobile wallet', TRUE),
    ('EASY', 'Easypaisa', 'Mobile wallet', TRUE)
ON CONFLICT (method_code) DO UPDATE SET method_name = EXCLUDED.method_name,
    method_type = EXCLUDED.method_type, is_electronic = EXCLUDED.is_electronic;
