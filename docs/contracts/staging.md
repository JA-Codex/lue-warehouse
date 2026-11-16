# Staging contract (lue_staging.stg_*)

Written by `etl/staging/ddl.py` from `etl/staging/spec.py` (US-5.1): do not edit by hand.
The dimension (E6) and fact (E7) loaders read only these tables.

## Rules for every table

- **One row per natural key** (the primary key). The surviving bronze row is the latest by
  the source's `updated_at` (where the source has one), then `loaded_at`, then `batch_id`,
  then the row's position (decision D15).
- **Only rows E4 did not reject** take part (`lue_audit.dq_result`), and only from bronze
  batches E4 has validated (`lue_audit.dq_batch`); staging refuses to run otherwise.
- **Values are cleaned and typed:** text trimmed with inner spaces collapsed and empty as
  NULL (`clean_text`); codes in upper case; vocabulary values in one spelling (`std`, which
  ignores case and spaces); dates `YYYY-MM-DD` or day-first `DD/MM/YYYY` (repaired); numbers
  and timestamps by the safe casts of E4.
- **Lineage on every row:** `source_system`, `batch_id`, `loaded_at` and `src_row_id` of the
  surviving bronze row, `src_updated_at`, and `run_id` and `staged_at` of the last change.
- **Incremental (US-5.3):** a run reads the bronze rows landed since the table's watermark
  (`lue_audit.etl_watermark`, source_system `STG`) and merges by the key, changing a row only
  when a value differs and never with an older version.
- **Derived columns** (marked) are computed by US-5.2 after every load.

## Vocabularies

| Domain | Values |
|---|---|
| city | Lahore, Karachi, Islamabad, Faisalabad |
| unit_type | Apartment, Office, Shop |
| tenant_type | Individual, Corporate |
| contact_channel | Phone, WhatsApp, Email |
| employer_sector | Banking, Construction, Education, Energy, Government, Healthcare, Hospitality, IT and Software, Legal and Consulting, Logistics, Manufacturing, Media, Retail, Self-employed, Telecom |
| lease_type | Residential, Commercial |
| rent_review_type | Fixed, Annual escalation |
| lease_status | Active, Renewed, Terminated |
| invoice_status | Paid, Partial, Overdue |
| payment_status | Cleared, Bounced |
| owner_type | Individual, Company |
| trade | Plumbing, Electrical, HVAC, Civil, Pest control, General maintenance |
| ticket_category | Plumbing, Electrical, HVAC, Civil, Pest control, Other |
| priority | Emergency, High, Normal |
| reported_via | Tenant app, Building staff |
| ticket_status | Raised, Assigned, Resolved, Verified |
| offer_type | Rent-free days, Discount, Free maintenance |

Other spellings accepted: LHE -> Lahore, KHI -> Karachi, ISB -> Islamabad, FSD -> Faisalabad, Lyallpur -> Faisalabad, E-mail -> Email.

Regions: Lahore LHE (Punjab), Faisalabad FSD (Punjab), Karachi KHI (Sindh), Islamabad ISB (Islamabad Capital Territory).

## stg_building

One row per building. From `lue_staging.brz_building` (S1). Key: `building_code`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `building_code` | VARCHAR(8) | Building business code | key |
| `building_name` | VARCHAR(80) | Building name | never NULL |
| `city` | VARCHAR(30) | City, one spelling (vocabulary) | NULL only if the city is not in the vocabulary (then counted in the evidence) |
| `city_code` | CHAR(3) | City code: LHE, KHI, ISB, FSD | never NULL |
| `region` | VARCHAR(30) | Province or territory, from the city | never NULL |
| `locality` | VARCHAR(40) | Neighbourhood | never NULL |
| `building_class` | CHAR(1) | A, B or C | never NULL |
| `year_built` | SMALLINT | Year built | never NULL |

## stg_unit

One row per unit (the latest version by updated_at). From `lue_staging.brz_unit` (S1). Key: `unit_id`. Survivorship uses the source's `updated_at`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `unit_id` | INT | Unit id in PropertyHub | key |
| `building_code` | VARCHAR(8) | Building of the unit | never NULL |
| `unit_no` | VARCHAR(10) | Unit number inside the building | never NULL |
| `floor_no` | SMALLINT | Floor | never NULL |
| `unit_type` | VARCHAR(20) | Apartment, Office or Shop | never NULL |
| `area_sqft` | NUMERIC(8,1) | Area in square feet | never NULL |
| `bedrooms` | SMALLINT | Bedrooms (0 for offices and shops) | never NULL |
| `furnished` | BOOLEAN | Let furnished | never NULL |

## stg_tenant

One row per tenant (the latest version by updated_at). From `lue_staging.brz_tenant` (S1). Key: `tenant_code`. Survivorship uses the source's `updated_at`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `tenant_code` | VARCHAR(12) | Tenant business key | key |
| `tenant_name` | VARCHAR(100) | Tenant or company name | never NULL |
| `tenant_type` | VARCHAR(12) | Individual or Corporate | never NULL |
| `employer_sector` | VARCHAR(30) | Employer sector | 'Unknown' when missing (data dictionary) |
| `phone` | VARCHAR(20) | Phone | NULL when missing |
| `contact_channel` | VARCHAR(12) | Phone, WhatsApp or Email | never NULL |

## stg_lease

One row per lease. From `lue_staging.brz_lease` (S1). Key: `lease_number`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `lease_number` | VARCHAR(14) | Lease business key | key |
| `unit_id` | INT | Unit let | never NULL |
| `tenant_code` | VARCHAR(12) | Tenant | never NULL; may name a tenant not staged yet (late arriving, US-6.5) |
| `lease_type` | VARCHAR(12) | Residential or Commercial | never NULL |
| `start_date` | DATE | Contract start | never NULL |
| `end_date` | DATE | Contract end | never NULL |
| `monthly_rent` | NUMERIC(12,2) | Rent agreed at signing (PKR) | never NULL |
| `rent_review_type` | VARCHAR(20) | Fixed or Annual escalation | never NULL |
| `previous_lease_number` | VARCHAR(14) | The lease this one renews | NULL for a first lease |
| `status` | VARCHAR(12) | Active, Renewed or Terminated | never NULL |
| `term_months` | SMALLINT | Contract length in whole months (US-5.2) (derived) | never NULL |

## stg_lease_event

One row per lease event. From `lue_staging.brz_lease_event` (S1). Key: `event_id`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `event_id` | INT | Event id | key |
| `lease_number` | VARCHAR(14) | Lease | never NULL |
| `event_code` | VARCHAR(8) | SIGN, RENEW, NOTICE or TERM | never NULL |
| `event_date` | DATE | Event date | never NULL |

## stg_invoice

One row per invoice. From `lue_staging.brz_invoice` (S1). Key: `invoice_number`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `invoice_number` | VARCHAR(16) | Invoice number | key |
| `lease_number` | VARCHAR(14) | Lease billed | never NULL |
| `invoice_date` | DATE | Invoice date | never NULL |
| `due_date` | DATE | Due date | never NULL |
| `status` | VARCHAR(10) | Paid, Partial or Overdue | never NULL |

## stg_invoice_line

One row per invoice line. From `lue_staging.brz_invoice_line` (S1). Key: `invoice_number, line_no`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `invoice_number` | VARCHAR(16) | Invoice | key |
| `line_no` | SMALLINT | Line number | key |
| `charge_code` | VARCHAR(8) | Charge type | never NULL |
| `billed_amount` | NUMERIC(12,2) | Billed (PKR) | never NULL |
| `tax_amount` | NUMERIC(12,2) | Tax (PKR) | never NULL |
| `discount_amount` | NUMERIC(12,2) | Discount (PKR) | never NULL |
| `net_amount` | NUMERIC(12,2) | billed + tax - discount (PKR); negative for credits | never NULL |
| `due_date` | DATE | Due date of the invoice (US-5.2) (derived) | NULL if the invoice is not staged |
| `allocated_amount` | NUMERIC(12,2) | Sum of the allocations to the line (US-5.2) (derived) | never NULL |
| `open_balance` | NUMERIC(12,2) | net_amount - allocated_amount (US-5.2) (derived) | never NULL |

## stg_payment

One row per payment. From `lue_staging.brz_payment` (S1). Key: `payment_reference`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `payment_reference` | VARCHAR(20) | Payment receipt number | key |
| `tenant_code` | VARCHAR(12) | Tenant | never NULL; may name a tenant not staged yet (US-6.5) |
| `paid_at` | TIMESTAMP | When the money was received | never NULL |
| `method_code` | VARCHAR(10) | Payment method | never NULL |
| `amount` | NUMERIC(12,2) | Amount (PKR); negative for a reversal | never NULL |
| `status` | VARCHAR(10) | Cleared or Bounced | never NULL |
| `reversal_of` | VARCHAR(20) | The payment this one reverses | NULL unless a reversal |
| `is_reversal` | BOOLEAN | status = 'Bounced' (data dictionary; US-5.2) (derived) | never NULL |
| `is_electronic` | BOOLEAN | Bank, Raast, JazzCash or Easypaisa (US-5.2) (derived) | never NULL |
| `allocated_amount` | NUMERIC(12,2) | Sum of the payment's allocations (US-5.2) (derived) | never NULL |
| `settlement_id` | VARCHAR(20) | Matched S3 settlement line (US-5.2) (derived) | NULL if not matched |
| `settlement_date` | DATE | Date the bank settled it (US-5.2) (derived) | NULL if not matched |
| `settlement_lag_days` | SMALLINT | settlement_date - paid date (US-5.2) (derived) | NULL if not matched |
| `is_unsettled` | BOOLEAN | An electronic, cleared payment with no settlement line (US-5.2) (derived) | never NULL |

## stg_payment_allocation

One row per payment and invoice line: S1's allocations, plus the allocations staging derives for a payment the source left (partly) unallocated (US-5.2). From `lue_staging.brz_payment_allocation` (S1). Key: `payment_reference, invoice_number, line_no`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `payment_reference` | VARCHAR(20) | Payment | key |
| `invoice_number` | VARCHAR(16) | Invoice | key |
| `line_no` | SMALLINT | Invoice line | key |
| `allocated_amount` | NUMERIC(12,2) | Amount allocated (PKR); negative for a reversal | never NULL |
| `allocation_source` | VARCHAR(8) | S1, or derived (by staging, US-5.2) | never NULL |
| `paid_at` | TIMESTAMP | Paid time of the payment (US-5.2) (derived) | never NULL |
| `due_date` | DATE | Due date of the line (US-5.2) (derived) | never NULL |
| `days_past_due` | SMALLINT | Paid date - due date in days; negative = early (US-5.2) (derived) | NULL if the payment or the line is not staged |
| `is_reversal` | BOOLEAN | The payment is a reversal (US-5.2) (derived) | never NULL |

## stg_settlement

One row per settlement line of the banks and wallets. From `lue_staging.brz_settlement` (S3). Key: `channel, settlement_id`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `channel` | VARCHAR(12) | bank, raast, jazzcash or easypaisa (from the file name) | key |
| `settlement_id` | VARCHAR(20) | Line id in the channel | key |
| `payment_reference` | VARCHAR(20) | Payment it settles | never NULL |
| `transaction_date` | DATE | Payment date per the bank | never NULL |
| `settlement_date` | DATE | Date settled | never NULL |
| `gross_amount` | NUMERIC(12,2) | Gross (PKR) | never NULL |
| `fee_amount` | NUMERIC(12,2) | Fee (PKR) | never NULL |
| `net_amount` | NUMERIC(12,2) | Net (PKR) | never NULL |
| `is_matched` | BOOLEAN | The payment is in stg_payment (US-5.2) (derived) | never NULL |
| `settlement_lag_days` | SMALLINT | settlement_date - the payment's paid date (US-5.2) (derived) | NULL if not matched |

## stg_owner

One row per owner. From `lue_staging.brz_owner` (S2). Key: `owner_code`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `owner_code` | VARCHAR(10) | Owner business key | key |
| `owner_name` | VARCHAR(100) | Owner name | never NULL |
| `owner_type` | VARCHAR(12) | Individual or Company | never NULL |

## stg_ownership

One row per unit ownership period. From `lue_staging.brz_ownership` (S2). Key: `building_code, unit_no, valid_from`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `building_code` | VARCHAR(8) | Building | key |
| `unit_no` | VARCHAR(10) | Unit number | key |
| `owner_code` | VARCHAR(10) | Owner | never NULL |
| `valid_from` | DATE | First day of the ownership | key |
| `valid_to` | DATE | Last day | NULL while it lasts |

## stg_vendor

One row per vendor. From `lue_staging.brz_vendor` (S2). Key: `vendor_code`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `vendor_code` | VARCHAR(10) | Vendor business key | key |
| `vendor_name` | VARCHAR(80) | Vendor name | never NULL |
| `trade` | VARCHAR(30) | Main trade | never NULL |
| `rating` | CHAR(1) | Current rating A, B or C | never NULL |
| `phone` | VARCHAR(20) | Phone | NULL when missing |
| `previous_rating` | CHAR(1) | Rating before the last change | NULL if never changed |
| `rating_changed_on` | DATE | Date of the last change | NULL if never changed |

## stg_maintenance_category

One row per maintenance subcategory and SLA version (valid_from). From `lue_staging.brz_sla_policy` (S2). Key: `subcategory_code, valid_from`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `subcategory_code` | VARCHAR(10) | Subcategory key | key |
| `subcategory_name` | VARCHAR(40) | Subcategory | never NULL |
| `category_name` | VARCHAR(30) | Plumbing, Electrical, HVAC, Civil, Pest control, Other | never NULL |
| `default_sla_hours` | SMALLINT | SLA in hours | never NULL |
| `valid_from` | DATE | First day of this SLA | key |

## stg_holiday

One row per holiday or Ramadan day. From `lue_staging.brz_holiday` (S2). Key: `holiday_date`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `holiday_date` | DATE | Day | key |
| `holiday_name` | VARCHAR(40) | Holiday | NULL on a Ramadan day that is not a holiday |
| `is_public_holiday` | BOOLEAN | Public holiday | never NULL |
| `is_ramadan` | BOOLEAN | In Ramadan | never NULL |

## stg_ticket

One row per ticket: of two copies the one with the latest status time (D15). A ticket copy with no Raised entry that E4 accepted is not staged. The copy (src_file, src_row) is compared as a value: when another copy wins, the row is updated and its status history replaced. From `lue_staging.brz_ticket` (S4). Key: `ticket_id`. Survivorship uses the source's `updated_at`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `ticket_id` | VARCHAR(14) | Ticket number | key |
| `building_code` | VARCHAR(8) | Building | never NULL |
| `unit_no` | VARCHAR(10) | Unit number | never NULL |
| `category` | VARCHAR(30) | Category | never NULL |
| `subcategory_code` | VARCHAR(10) | Subcategory | never NULL |
| `subcategory_name` | VARCHAR(40) | Subcategory name | never NULL |
| `priority` | VARCHAR(10) | Emergency, High or Normal | never NULL |
| `is_emergency` | BOOLEAN | priority = Emergency (data dictionary) | never NULL |
| `source_is_recurring` | BOOLEAN | The app's own flag (90 days, US-2.5); see is_recurring | never NULL |
| `is_tenant_caused` | BOOLEAN | Damage by the tenant | never NULL |
| `reported_via` | VARCHAR(20) | Channel | never NULL |
| `description` | VARCHAR(200) | Description | never NULL |
| `vendor_code` | VARCHAR(10) | Vendor | NULL until assigned |
| `estimated_cost` | NUMERIC(12,2) | Estimate (PKR) | NULL until assigned |
| `actual_cost` | NUMERIC(12,2) | Final cost (PKR) | NULL until resolved |
| `status` | VARCHAR(12) | Latest status | never NULL |
| `raised_at` | TIMESTAMP | Raised (US-5.2) (derived) | never NULL |
| `assigned_at` | TIMESTAMP | Assigned (US-5.2) (derived) | NULL until it happens |
| `resolved_at` | TIMESTAMP | Resolved (US-5.2) (derived) | NULL until it happens |
| `verified_at` | TIMESTAMP | Verified (US-5.2) (derived) | NULL until it happens |
| `days_to_assign` | NUMERIC(6,2) | assigned - raised in days (US-5.2) (derived) | NULL until assigned |
| `days_to_resolve` | NUMERIC(6,2) | resolved - raised in days (US-5.2) (derived) | NULL until resolved |
| `days_to_verify` | NUMERIC(6,2) | verified - resolved in days (US-5.2) (derived) | NULL until verified |
| `hours_to_resolve` | NUMERIC(8,2) | resolved - raised in hours (US-5.2) (derived) | NULL until resolved |
| `sla_hours` | SMALLINT | SLA in force on the raised date (US-5.2) (derived) | NULL if the subcategory has no SLA then |
| `sla_breached` | BOOLEAN | hours_to_resolve > sla_hours (US-5.2) (derived) | NULL until resolved |
| `is_recurring` | BOOLEAN | Same unit and subcategory within 30 days before (data dictionary; US-5.2) (derived) | never NULL |
| `src_file` | VARCHAR(200) | File of the copy (lineage) | |
| `src_row` | INT | Position of the copy (lineage) | |

## stg_ticket_status

One row per status entry of the staged copy of each ticket. From `lue_staging.brz_ticket_status` (S4). Key: `ticket_id, status_seq`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `ticket_id` | VARCHAR(14) | Ticket | key |
| `status_seq` | SMALLINT | 1 = first status | key |
| `status` | VARCHAR(12) | Status | never NULL |
| `status_at` | TIMESTAMP | When | never NULL |
| `vendor_code` | VARCHAR(10) | Vendor (on Assigned) | NULL except on Assigned |

## stg_weather

One row per city and day. From `lue_staging.brz_weather` (S5). Key: `city, weather_date`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `city` | VARCHAR(30) | City | key |
| `weather_date` | DATE | Day (Pakistan time) | key |
| `max_temp_c` | NUMERIC(4,1) | Maximum temperature | NULL when the API had no value |
| `rainfall_mm` | NUMERIC(6,1) | Rainfall | NULL when the API had no value |

## stg_incentive_offer

One row per offer in the catalogue. From `lue_staging.brz_incentive_offer` (S6). Key: `offer_code`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `offer_code` | VARCHAR(10) | Offer business key | key |
| `offer_type` | VARCHAR(20) | Rent-free days, Discount or Free maintenance | never NULL |
| `description` | VARCHAR(80) | Description | never NULL |
| `discount_pct` | NUMERIC(5,2) | Discount, 0 if not a discount | never NULL |
| `rent_free_days` | SMALLINT | Rent-free days, 0 if not rent-free | never NULL |

## stg_incentive_log

One row per offer posted on a unit. A day-first date is read as such (repaired). From `lue_staging.brz_incentive_log` (S6). Key: `building_code, unit_no, offer_code, start_date`.

| Column | Type | Meaning | NULL |
|---|---|---|---|
| `building_code` | VARCHAR(8) | Building | key |
| `unit_no` | VARCHAR(10) | Unit number | key |
| `offer_code` | VARCHAR(10) | Offer | key |
| `start_date` | DATE | First day posted | key |
| `end_date` | DATE | Last day posted | never NULL |
