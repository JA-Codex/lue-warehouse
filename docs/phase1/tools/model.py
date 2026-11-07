"""Single source of truth for the LUE Phase 1 deliverables.

Every PDF, diagram, DDL file and the data dictionary is generated from this module,
so table names, column names, grain sentences and SCD types stay identical everywhere.
"""

PROJECT = "Lahore Urban Estates Analytics Warehouse"
SHORT = "LUE"
COURSE = "DL3004 Data Warehousing and Business Intelligence"
INSTITUTE = "FAST-NU Lahore · Fall 2026"
INSTRUCTOR = "Course Instructor: Mr. Muhammad Ishaq Raza · Lab Instructor: Mr. Shahzeb Mubashar"
AUTHORS = "Junaid Minhas (23L-2559), Ahmad Waqar (23L-2634), Hanan Tiwana (23L-2536) and Eesha Khurram (23L-2641)"
VERSION = "Phase 1 · Version 2.1"
DATE = "16 October 2026"


# ---------------------------------------------------------------- columns
def col(name, typ, desc, key="", ref=None, null=False, scd="", src="", ex="", rule="",
        tech=False, scd_reason=""):
    return dict(name=name, type=typ, desc=desc, key=key, ref=ref, null=null, scd=scd,
                src=src, ex=ex, rule=rule, tech=tech, scd_reason=scd_reason)


def tech_cols(scd2=False):
    cols = []
    if scd2:
        cols += [
            col("effective_from", "DATE", "First day this version is valid", src="ETL", ex="2025-06-01",
                rule="Set to load date when a new version is inserted"),
            col("effective_to", "DATE", "Last day (exclusive) this version is valid; 9999-12-31 while current",
                src="ETL", ex="9999-12-31", rule="Set to change date when the version is expired"),
            col("is_current", "BOOLEAN", "TRUE for the current version only", src="ETL", ex="TRUE",
                rule="Exactly one current row per natural key"),
        ]
    cols += [
        col("source_system", "VARCHAR(20)", "Source system that supplied the row (lineage)", src="ETL",
            ex="S1_PMS", tech=True),
        col("batch_id", "BIGINT", "Pipeline run that loaded or last changed the row (lineage)", src="ETL",
            ex="20260305001", tech=True),
        col("loaded_at", "TIMESTAMP", "When the row was loaded or last changed", src="ETL",
            ex="2026-03-05 02:10:44", tech=True),
    ]
    return cols


def sk(name, desc):
    return col(name, "INT", desc, key="PK", src="ETL (sequence)", ex="117",
               rule="Integer surrogate key; -1 = Unknown, -2 = Not applicable")


def fk(name, dim, desc, ex="117", rule=""):
    return col(name, "INT", desc, key="FK", ref=dim, src="ETL lookup", ex=ex,
               rule=rule or f"Must exist in {dim}; -1 if the reference is missing")


# ---------------------------------------------------------------- dimensions
DIMENSIONS = [
    dict(
        name="dim_date", grain="One row per calendar day from 2023-07-01 to 2027-06-30",
        nk="full_date", rows="1,461 + 2 special rows", source="Generated calendar + S2 holiday sheet",
        hierarchy="Day → Month → Quarter → Year; Day → Fiscal month → Fiscal quarter → Fiscal year",
        roles="invoice, due, paid, snapshot, raised, assigned, resolved, verified, event, coverage",
        cols=[
            col("date_key", "INT", "Surrogate key in YYYYMMDD form; analysis uses the attributes, never arithmetic on this key",
                key="PK", src="ETL", ex="20260305", rule="-1 = Unknown date, -2 = Not yet happened"),
            col("full_date", "DATE", "Calendar date (natural key)", src="Generated", ex="2026-03-05",
                rule="Unique", scd="0", scd_reason="A date never changes"),
            col("day_of_month", "SMALLINT", "Day number in the month", src="Derived", ex="5", scd="0"),
            col("day_name", "VARCHAR(10)", "Weekday name", src="Derived", ex="Thursday", scd="0"),
            col("is_weekend", "BOOLEAN", "Saturday or Sunday", src="Derived", ex="FALSE", scd="0"),
            col("week_of_year", "SMALLINT", "ISO week number", src="Derived", ex="10", scd="0"),
            col("month_no", "SMALLINT", "Calendar month number", src="Derived", ex="3", scd="0"),
            col("month_name", "VARCHAR(10)", "Calendar month name", src="Derived", ex="March", scd="0"),
            col("quarter_no", "SMALLINT", "Calendar quarter", src="Derived", ex="1", scd="0"),
            col("year_no", "SMALLINT", "Calendar year", src="Derived", ex="2026", scd="0"),
            col("fiscal_month_no", "SMALLINT", "Fiscal month (July = 1)", src="Derived", ex="9", scd="0"),
            col("fiscal_quarter_no", "SMALLINT", "Fiscal quarter (Jul–Sep = 1)", src="Derived", ex="3", scd="0"),
            col("fiscal_year_label", "VARCHAR(9)", "Fiscal year July–June", src="Derived", ex="FY2025-26", scd="0"),
            col("is_public_holiday", "BOOLEAN", "Pakistan public holiday", src="S2 holiday sheet", ex="FALSE",
                scd="1", scd_reason="Holiday dates are corrected when officially announced"),
            col("holiday_name", "VARCHAR(60)", "Name of the holiday, NULL otherwise", null=True,
                src="S2 holiday sheet", ex="Pakistan Day", scd="1"),
            col("is_ramadan", "BOOLEAN", "Day falls in Ramadan", src="S2 holiday sheet", ex="TRUE", scd="1"),
        ],
    ),
    dict(
        name="dim_unit", grain="One row per unit version (SCD Type 2)",
        nk="unit_nk (building_code + unit_no)", rows="≈ 1,900 versions for ≈ 1,800 units", source="S1 units + buildings",
        hierarchy="Unit → Floor → Building → Locality → City → Region",
        cols=[
            sk("unit_key", "Surrogate key of the unit version"),
            col("unit_nk", "VARCHAR(20)", "Natural key: building code + unit number", src="S1 buildings.building_code || units.unit_no",
                ex="GLB01-A101", rule="Unique per version set; resolves the A-101 collision across buildings", scd="0",
                scd_reason="Identity of the unit"),
            col("building_code", "VARCHAR(8)", "Building business code", src="S1 buildings.building_code", ex="GLB01", scd="0"),
            col("unit_no", "VARCHAR(10)", "Unit number inside the building", src="S1 units.unit_no", ex="A-101", scd="0"),
            col("unit_type", "VARCHAR(20)", "Apartment, Office or Shop", src="S1 units.unit_type", ex="Apartment",
                rule="Standardised to 3 values", scd="2",
                scd_reason="A converted unit must keep past rent and occupancy under its old type"),
            col("bedrooms", "SMALLINT", "Bedrooms (0 for offices and shops)", src="S1 units.bedrooms", ex="2", scd="1",
                scd_reason="Corrections only"),
            col("area_sqft", "NUMERIC(8,1)", "Covered area in square feet", src="S1 units.area_sqft", ex="1150.0",
                rule="> 0", scd="1", scd_reason="Corrections only"),
            col("furnished_flag", "BOOLEAN", "Unit is let furnished", src="S1 units.furnished", ex="TRUE", scd="2",
                scd_reason="Furnishing changes the rent level; history needed for rent analysis"),
            col("floor_no", "SMALLINT", "Floor number (hierarchy level 2)", src="S1 units.floor_no", ex="1", scd="0"),
            col("building_name", "VARCHAR(80)", "Building name (hierarchy level 3)", src="S1 buildings.building_name",
                ex="Gulberg Heights", scd="1", scd_reason="Renames and spelling fixes apply to all history"),
            col("building_class", "CHAR(1)", "Building class A, B or C", src="S1 buildings.building_class", ex="A", scd="1"),
            col("building_age_band", "VARCHAR(12)", "0–5, 6–15 or 16+ years", src="Derived from S1 buildings.year_built",
                ex="6–15 yrs", scd="1"),
            col("locality", "VARCHAR(40)", "Neighbourhood (hierarchy level 4)", src="S1 buildings.locality", ex="Gulberg III",
                rule="Trimmed and title-cased", scd="1"),
            col("city", "VARCHAR(30)", "City (hierarchy level 5)", src="S1 buildings.city", ex="Lahore",
                rule="One of Lahore, Karachi, Islamabad, Faisalabad", scd="1"),
            col("region", "VARCHAR(30)", "Province or territory (hierarchy level 6)", src="Derived from city",
                ex="Punjab", rule="Punjab, Sindh or Islamabad Capital Territory", scd="1"),
        ] + tech_cols(scd2=True),
    ),
    dict(
        name="dim_tenant", grain="One row per tenant version (SCD Type 2)",
        nk="tenant_code", rows="≈ 4,500 versions", source="S1 tenants",
        hierarchy="Tenant type → Tenant",
        cols=[
            sk("tenant_key", "Surrogate key of the tenant version"),
            col("tenant_code", "VARCHAR(12)", "Tenant business key", src="S1 tenants.tenant_code", ex="T-0912",
                scd="0", scd_reason="Identity"),
            col("tenant_name", "VARCHAR(100)", "Synthetic tenant or company name", src="S1 tenants.full_name",
                ex="Ayesha Khan", scd="1", scd_reason="Spelling corrections; no analytical history"),
            col("tenant_type", "VARCHAR(12)", "Individual or Corporate", src="S1 tenants.tenant_type", ex="Individual",
                scd="2", scd_reason="Q4 compares late payment by tenant type at the time of payment"),
            col("employer_sector", "VARCHAR(30)", "Employer sector, 'Unknown' if missing", src="S1 tenants.employer_sector",
                ex="Banking", rule="NULL → 'Unknown'", scd="2",
                scd_reason="Q4 analyses late payment by employer sector over time"),
            col("contact_channel", "VARCHAR(12)", "Phone, WhatsApp or Email", src="S1 tenants.contact_channel",
                ex="WhatsApp", scd="1", scd_reason="Current preference only"),
            col("is_inferred", "BOOLEAN", "Row was created as an inferred member before the real record arrived",
                src="ETL", ex="FALSE", rule="Set TRUE for late-arriving dimension members; cleared by deferred update"),
        ] + tech_cols(scd2=True),
    ),
    dict(
        name="dim_lease", grain="One row per lease contract",
        nk="lease_number", rows="≈ 5,500", source="S1 leases",
        hierarchy="—",
        cols=[
            sk("lease_key", "Surrogate key of the lease"),
            col("lease_number", "VARCHAR(14)", "Lease business key", src="S1 leases.lease_number", ex="L-2025-00831",
                scd="0", scd_reason="Identity"),
            col("lease_type", "VARCHAR(12)", "Residential or Commercial", src="S1 leases.lease_type", ex="Residential",
                scd="0", scd_reason="Signed contract term"),
            col("start_date", "DATE", "Contract start", src="S1 leases.start_date", ex="2025-06-01", scd="0",
                scd_reason="Signed contract term"),
            col("end_date", "DATE", "Contract end", src="S1 leases.end_date", ex="2026-04-30",
                rule="end_date > start_date", scd="0", scd_reason="Signed contract term; a renewal is a new lease"),
            col("term_months", "SMALLINT", "Contract length in months", src="Derived", ex="11", scd="0"),
            col("original_monthly_rent", "NUMERIC(12,2)", "Rent agreed at signing (PKR)", src="S1 leases.monthly_rent",
                ex="85000.00", rule="> 0", scd="0", scd_reason="Signed contract term"),
            col("rent_review_type", "VARCHAR(20)", "Fixed or Annual escalation", src="S1 leases.rent_review_type",
                ex="Fixed", scd="0"),
            col("previous_lease_number", "VARCHAR(14)", "Lease this one renewed, NULL for a first lease", null=True,
                src="S1 leases.previous_lease_number", ex="L-2024-00412", scd="0"),
        ] + tech_cols(),
    ),
    dict(
        name="dim_owner", grain="One row per owner",
        nk="owner_code", rows="≈ 900", source="S2 owner register (Excel)",
        hierarchy="Owner type → Owner",
        cols=[
            sk("owner_key", "Surrogate key of the owner"),
            col("owner_code", "VARCHAR(10)", "Owner business key", src="S2 owners.owner_code", ex="OW-0217", scd="0"),
            col("owner_name", "VARCHAR(100)", "Synthetic owner name", src="S2 owners.owner_name", ex="Malik Holdings",
                rule="Trimmed, title-cased", scd="1", scd_reason="Corrections only"),
            col("owner_type", "VARCHAR(12)", "Individual or Company", src="S2 owners.owner_type", ex="Company", scd="1"),
            col("portfolio_size_band", "VARCHAR(10)", "1 unit, 2–5 units or 6+ units", src="Derived from S2 ownership",
                ex="2–5", scd="1", scd_reason="Current band only; ownership history lives on the facts"),
        ] + tech_cols(),
    ),
    dict(
        name="dim_payment_method", grain="One row per payment method",
        nk="method_code", rows="6", source="S1 payment_methods",
        hierarchy="Method → Channel group",
        cols=[
            sk("payment_method_key", "Surrogate key of the payment method"),
            col("method_code", "VARCHAR(10)", "Method business key", src="S1 payment_methods.method_code", ex="JAZZ"),
            col("method_name", "VARCHAR(30)", "Cash, Cheque, Bank transfer, Raast, JazzCash, Easypaisa",
                src="S1 payment_methods.name", ex="JazzCash", scd="1"),
            col("channel_group", "VARCHAR(20)", "Cash, Cheque, Bank, Mobile wallet or Instant payment",
                src="Mapping table", ex="Mobile wallet", scd="1"),
            col("typical_settlement_days", "SMALLINT", "Expected days from payment to settlement",
                src="Mapping table", ex="1", scd="1"),
        ] + tech_cols(),
    ),
    dict(
        name="dim_charge_type", grain="One row per charge type",
        nk="charge_code", rows="6", source="S1 charge_types",
        hierarchy="Charge type → Charge category",
        cols=[
            sk("charge_type_key", "Surrogate key of the charge type"),
            col("charge_code", "VARCHAR(8)", "Charge business key", src="S1 charge_types.charge_code", ex="RENT"),
            col("charge_type_name", "VARCHAR(30)", "Rent, Service charge, Late fee, Utility, Credit note, Deposit adjustment",
                src="S1 charge_types.name", ex="Rent", scd="1"),
            col("charge_category", "VARCHAR(12)", "Rent, Ancillary, Penalty or Credit", src="S1 charge_types.category",
                ex="Rent", scd="1"),
        ] + tech_cols(),
    ),
    dict(
        name="dim_maintenance_category", grain="One row per maintenance subcategory version (SCD Type 2)",
        nk="subcategory_code", rows="≈ 30", source="S4 ticket categories + SLA policy sheet",
        hierarchy="Subcategory → Category",
        cols=[
            sk("maint_category_key", "Surrogate key of the subcategory version"),
            col("subcategory_code", "VARCHAR(10)", "Subcategory business key", src="S4 tickets.category_code",
                ex="PLB-LEAK", scd="0"),
            col("subcategory_name", "VARCHAR(40)", "Subcategory", src="S4 tickets.category_name", ex="Leak", scd="1"),
            col("category_name", "VARCHAR(30)", "Plumbing, Electrical, HVAC, Civil, Pest control, Other",
                src="Mapping table", ex="Plumbing", scd="1"),
            col("default_sla_hours", "SMALLINT", "Hours allowed to resolve", src="S2 SLA policy sheet", ex="48",
                rule="> 0", scd="2", scd_reason="A tighter SLA policy must not re-label past requests as breaches"),
        ] + tech_cols(scd2=True),
    ),
    dict(
        name="dim_vendor", grain="One row per vendor version (SCD Type 2)",
        nk="vendor_code", rows="≈ 160 versions", source="S2 vendor register (Excel)",
        hierarchy="Vendor → Trade",
        cols=[
            sk("vendor_key", "Surrogate key of the vendor version"),
            col("vendor_code", "VARCHAR(10)", "Vendor business key", src="S2 vendors.vendor_code", ex="V-044", scd="0"),
            col("vendor_name", "VARCHAR(80)", "Synthetic vendor name", src="S2 vendors.vendor_name", ex="Rehman Plumbing Works",
                scd="1"),
            col("trade", "VARCHAR(30)", "Main trade", src="S2 vendors.trade", ex="Plumbing", scd="1"),
            col("rating_band", "CHAR(1)", "Quality rating A, B or C", src="S2 vendors.rating", ex="B", scd="2",
                scd_reason="Q9 asks whether vendors were slow while rated low"),
            col("phone", "VARCHAR(20)", "Synthetic contact number", src="S2 vendors.phone", ex="0300-0000000",
                scd="1", scd_reason="Contact fix"),
        ] + tech_cols(scd2=True),
    ),
    dict(
        name="dim_lease_event_type", grain="One row per lease event type",
        nk="event_code", rows="4", source="S1 lease_events.event_code",
        hierarchy="—",
        cols=[
            sk("lease_event_type_key", "Surrogate key of the event type"),
            col("event_code", "VARCHAR(8)", "Event business key", src="S1 lease_events.event_code", ex="RENEW"),
            col("event_name", "VARCHAR(20)", "Signed, Renewed, Notice given, Terminated", src="Mapping table", ex="Renewed"),
            col("is_exit_event", "BOOLEAN", "Event ends occupancy (notice given, terminated)", src="Mapping table", ex="FALSE"),
        ] + tech_cols(),
    ),
    dict(
        name="dim_request_flags", grain="One row per combination of the three request flags (junk dimension, 8 rows)",
        nk="is_emergency + is_recurring + is_tenant_caused", rows="8", source="Generated (all combinations)",
        hierarchy="—",
        cols=[
            sk("request_flags_key", "Surrogate key of the flag combination"),
            col("is_emergency", "BOOLEAN", "Request marked emergency", src="S4 tickets.priority = 'Emergency'", ex="TRUE"),
            col("is_recurring", "BOOLEAN", "Same subcategory on the same unit within 30 days", src="Derived in Silver (lue_staging.stg_*)",
                ex="FALSE"),
            col("is_tenant_caused", "BOOLEAN", "Damage caused by the tenant (chargeable)", src="S4 tickets.tenant_caused",
                ex="FALSE"),
            col("flags_label", "VARCHAR(60)", "Readable label for reports", src="Derived",
                ex="Emergency · Not recurring · Not tenant-caused"),
        ],
    ),
    dict(
        name="dim_incentive", grain="One row per incentive offer type",
        nk="incentive_code", rows="≈ 8", source="S6 incentive log",
        hierarchy="Incentive type → Incentive",
        cols=[
            sk("incentive_key", "Surrogate key of the incentive"),
            col("incentive_code", "VARCHAR(10)", "Incentive business key", src="S6 offers.offer_code", ex="RF30"),
            col("incentive_type", "VARCHAR(20)", "Rent-free days, Discount or Free maintenance", src="S6 offers.offer_type",
                ex="Rent-free days", scd="1"),
            col("incentive_description", "VARCHAR(80)", "Readable description", src="S6 offers.description",
                ex="First month rent-free on an 11-month lease", scd="1"),
            col("discount_pct", "NUMERIC(5,2)", "Discount on monthly rent, 0 if not a discount", src="S6 offers.discount_pct",
                ex="0.00", rule="0–50", scd="1"),
            col("rent_free_days", "SMALLINT", "Rent-free days, 0 if not rent-free", src="S6 offers.rent_free_days",
                ex="30", rule="0–60", scd="1"),
        ] + tech_cols(),
    ),
    dict(
        name="dim_weather", grain="One row per city per calendar day",
        nk="city + weather_date", rows="≈ 4,380", source="S5 Open-Meteo REST API",
        hierarchy="—",
        cols=[
            sk("weather_key", "Surrogate key of the city-day"),
            col("city", "VARCHAR(30)", "City", src="S5 request parameter", ex="Lahore"),
            col("weather_date", "DATE", "Calendar date", src="S5 daily.time", ex="2025-07-14"),
            col("rainfall_mm", "NUMERIC(6,1)", "Total daily precipitation in mm", src="S5 daily.precipitation_sum",
                ex="38.4", rule=">= 0; NULL from API → quarantine", scd="1",
                scd_reason="Provider revisions overwrite the value"),
            col("rain_band", "VARCHAR(8)", "None (< 1 mm), Light (1–10 mm), Heavy (> 10 mm)", src="Derived", ex="Heavy", scd="1"),
            col("max_temp_c", "NUMERIC(4,1)", "Daily maximum temperature °C", src="S5 daily.temperature_2m_max",
                ex="36.2", scd="1"),
            col("heat_band", "VARCHAR(8)", "Mild (< 35 °C), Hot (35–40 °C), Extreme (> 40 °C)", src="Derived", ex="Hot", scd="1"),
        ] + tech_cols(),
    ),
]

# ---------------------------------------------------------------- facts
FACTS = [
    dict(
        name="fact_rent_invoice_line", type="Transaction", process="P1 Rent invoicing and payment",
        grain="One row represents one charge line (rent, service charge, late fee, utility or credit note) on one invoice issued to one lease.",
        load="Incremental insert by invoice date watermark; credit notes arrive as new negative lines",
        rows="≈ 130,000", pk="invoice_line_sk",
        cols=[
            col("invoice_line_sk", "BIGINT", "Surrogate fact key for traceability", key="PK", src="ETL (sequence)", ex="88123"),
            fk("invoice_date_key", "dim_date", "Role: invoice date", ex="20260301"),
            fk("due_date_key", "dim_date", "Role: due date", ex="20260310"),
            fk("unit_key", "dim_unit", "Unit version valid on the invoice date"),
            fk("tenant_key", "dim_tenant", "Tenant version valid on the invoice date", ex="402"),
            fk("lease_key", "dim_lease", "Lease billed", ex="2210"),
            fk("owner_key", "dim_owner", "Owner of the unit on the invoice date (ownership register)", ex="57"),
            fk("charge_type_key", "dim_charge_type", "Type of charge", ex="1"),
            col("invoice_number", "VARCHAR(16)", "Degenerate dimension: invoice number", src="S1 invoices.invoice_number",
                ex="INV-2026-03-00831"),
            col("invoice_line_no", "SMALLINT", "Degenerate dimension: line number on the invoice",
                src="S1 invoice_lines.line_no", ex="1", rule="(invoice_number, invoice_line_no) unique"),
            col("billed_amount", "NUMERIC(12,2)", "Gross charge before tax and discount (PKR) · additive",
                src="S1 invoice_lines.billed_amount", ex="85000.00"),
            col("tax_amount", "NUMERIC(12,2)", "Tax on the line (PKR) · additive", src="S1 invoice_lines.tax_amount", ex="0.00"),
            col("discount_amount", "NUMERIC(12,2)", "Discount on the line (PKR) · additive",
                src="S1 invoice_lines.discount_amount", ex="0.00"),
            col("net_amount", "NUMERIC(12,2)", "billed + tax − discount (PKR) · additive; negative for credit notes",
                src="S1 invoice_lines.net_amount", ex="85000.00", rule="Must equal billed_amount + tax_amount − discount_amount"),
        ] + tech_cols(),
    ),
    dict(
        name="fact_payment", type="Transaction", process="P1 Rent invoicing and payment",
        grain="One row represents one portion of one payment receipt allocated to one invoice line.",
        load="Incremental insert by paid date watermark; a bounced cheque adds a new negative row",
        rows="≈ 60,000", pk="payment_alloc_sk",
        cols=[
            col("payment_alloc_sk", "BIGINT", "Surrogate fact key for traceability", key="PK", src="ETL (sequence)", ex="40411"),
            fk("paid_date_key", "dim_date", "Role: date the money was received", ex="20260314"),
            fk("due_date_key", "dim_date", "Role: due date of the invoice line paid", ex="20260310"),
            fk("unit_key", "dim_unit", "Unit version valid on the paid date"),
            fk("tenant_key", "dim_tenant", "Tenant version valid on the paid date (point-in-time lookup)", ex="402"),
            fk("lease_key", "dim_lease", "Lease paid for", ex="2210"),
            fk("owner_key", "dim_owner", "Owner of the unit on the paid date", ex="57"),
            fk("payment_method_key", "dim_payment_method", "How the tenant paid", ex="5"),
            fk("charge_type_key", "dim_charge_type", "Type of the invoice line paid", ex="1"),
            col("payment_reference", "VARCHAR(20)", "Degenerate dimension: payment receipt number",
                src="S1 payments.payment_reference", ex="PAY-0098812"),
            col("invoice_number", "VARCHAR(16)", "Degenerate dimension: invoice paid", src="S1 payment_allocations",
                ex="INV-2026-03-00831"),
            col("invoice_line_no", "SMALLINT", "Degenerate dimension: invoice line paid", src="S1 payment_allocations",
                ex="1", rule="(payment_reference, invoice_number, invoice_line_no, is_reversal) unique"),
            col("payment_amount", "NUMERIC(12,2)", "Amount allocated to this line (PKR) · additive, signed",
                src="S1 payment_allocations.allocated_amount", ex="50000.00", rule="> 0 unless is_reversal"),
            col("days_past_due", "SMALLINT", "Paid date − due date in days (negative = early) · non-additive",
                src="Derived", ex="4", rule="Aggregate with an amount-weighted average"),
            col("settlement_lag_days", "SMALLINT", "Settlement date in S3 − paid date · non-additive; NULL if unmatched",
                null=True, src="Derived from S3 match", ex="1"),
            col("is_reversal", "BOOLEAN", "Row reverses an earlier payment (bounced cheque)", src="S1 payments.status = 'Bounced'",
                ex="FALSE"),
        ] + tech_cols(),
    ),
    dict(
        name="fact_unit_occupancy_daily", type="Periodic snapshot", process="P2 Unit occupancy",
        grain="One row represents one unit at the end of one calendar day, whether occupied or vacant.",
        load="Derived by the ETL from leases × dim_date; the last 35 days are re-derived on every run",
        rows="≈ 1.97 million", pk="(snapshot_date_key, unit_key)",
        cols=[
            col("snapshot_date_key", "INT", "Role: snapshot date (part of PK; partition key by month)", key="PK, FK",
                ref="dim_date", src="ETL", ex="20260305"),
            col("unit_key", "INT", "Unit version valid on the snapshot date (part of PK)", key="PK, FK", ref="dim_unit",
                src="ETL lookup", ex="117"),
            fk("tenant_key", "dim_tenant", "Tenant of the active lease; -2 when vacant", ex="402",
               rule="-2 = Not applicable (vacant)"),
            fk("lease_key", "dim_lease", "Active lease; -2 when vacant", ex="2210", rule="-2 = Not applicable (vacant)"),
            fk("owner_key", "dim_owner", "Owner of the unit on the snapshot date", ex="57"),
            col("is_occupied", "SMALLINT", "1 if a lease is active, 0 if vacant · semi-additive",
                src="Derived", ex="1", rule="SUM across units on one day; AVG across days"),
            col("contract_rent", "NUMERIC(12,2)", "Monthly rent of the active lease, 0 when vacant · semi-additive",
                src="Derived from S1 leases", ex="85000.00", rule="SUM across units on one day = rent roll; never SUM across days"),
            col("current_lease_arrears", "NUMERIC(12,2)",
                "Open overdue balance of the lease active that day, 0 when vacant · semi-additive",
                src="Derived from invoice and payment facts", ex="35000.00",
                rule="Use the period-end value; never SUM across days"),
        ] + tech_cols(),
    ),
    dict(
        name="fact_maintenance_request", type="Accumulating snapshot", process="P3 Maintenance",
        grain="One row represents one maintenance request across its whole lifecycle, updated as it is assigned, resolved and verified.",
        load="Insert when raised; UPDATE milestone date keys and measures as later statuses arrive",
        rows="≈ 6,000", pk="request_sk",
        cols=[
            col("request_sk", "BIGINT", "Surrogate fact key", key="PK", src="ETL (sequence)", ex="5120"),
            fk("raised_date_key", "dim_date", "Role: date raised", ex="20250714"),
            fk("assigned_date_key", "dim_date", "Role: date assigned to a vendor; -2 until it happens", ex="20250714",
               rule="-2 = Not yet happened"),
            fk("resolved_date_key", "dim_date", "Role: date resolved; -2 until it happens", ex="20250716",
               rule="-2 = Not yet happened"),
            fk("verified_date_key", "dim_date", "Role: date verified by the building manager; -2 until it happens",
               ex="20250717", rule="-2 = Not yet happened"),
            fk("unit_key", "dim_unit", "Unit version valid on the raised date"),
            fk("tenant_key", "dim_tenant", "Tenant who raised it; -2 if raised by staff on a vacant unit", ex="402"),
            fk("owner_key", "dim_owner", "Owner on the raised date (pays the cost)", ex="57"),
            fk("maint_category_key", "dim_maintenance_category", "Subcategory version valid on the raised date (SLA in force)",
               ex="12"),
            fk("vendor_key", "dim_vendor", "Vendor version valid on the assigned date; -2 until assigned", ex="31"),
            fk("request_flags_key", "dim_request_flags", "Junk dimension key", ex="3"),
            fk("weather_key", "dim_weather", "Weather in the unit's city on the raised date", ex="2911"),
            col("request_number", "VARCHAR(14)", "Degenerate dimension: ticket number", src="S4 tickets.ticket_id",
                ex="MR-2025-02211"),
            col("request_status", "VARCHAR(12)", "Raised, Assigned, Resolved or Verified", src="Latest S4 status",
                ex="Verified"),
            col("days_to_assign", "NUMERIC(6,2)", "Assigned − raised in days · non-additive", null=True, src="Derived",
                ex="0.40"),
            col("days_to_resolve", "NUMERIC(6,2)", "Resolved − raised in days · non-additive", null=True, src="Derived",
                ex="2.10"),
            col("days_to_verify", "NUMERIC(6,2)", "Verified − resolved in days · non-additive", null=True, src="Derived",
                ex="0.90"),
            col("estimated_cost", "NUMERIC(12,2)", "Vendor estimate (PKR) · additive", null=True,
                src="S4 tickets.estimate", ex="6500.00"),
            col("actual_cost", "NUMERIC(12,2)", "Final cost (PKR) · additive", null=True, src="S4 tickets.final_cost",
                ex="7200.00"),
            col("sla_breached_flag", "SMALLINT", "1 if hours to resolve > default_sla_hours in force · additive count",
                null=True, src="Derived", ex="0", rule="SUM / COUNT = breach rate"),
        ] + tech_cols(),
    ),
    dict(
        name="fact_lease_event", type="Factless (event tracking)", process="P4 Lease lifecycle",
        grain="One row represents one lifecycle event (signed, renewed, notice given or terminated) on one lease.",
        load="Incremental insert by event date watermark",
        rows="≈ 8,000", pk="lease_event_sk",
        cols=[
            col("lease_event_sk", "BIGINT", "Surrogate fact key", key="PK", src="ETL (sequence)", ex="7001"),
            fk("event_date_key", "dim_date", "Role: event date", ex="20260215"),
            fk("unit_key", "dim_unit", "Unit version valid on the event date"),
            fk("tenant_key", "dim_tenant", "Tenant version valid on the event date", ex="402"),
            fk("lease_key", "dim_lease", "Lease the event belongs to", ex="2210"),
            fk("owner_key", "dim_owner", "Owner on the event date", ex="57"),
            fk("lease_event_type_key", "dim_lease_event_type", "Signed, renewed, notice given, terminated", ex="2"),
            col("event_count", "SMALLINT", "Always 1; SUM = number of events", src="Constant", ex="1", rule="Always 1"),
        ] + tech_cols(),
    ),
    dict(
        name="fact_vacancy_incentive_coverage", type="Factless (coverage)", process="P5 Vacancy marketing",
        grain="One row represents one incentive offer being available on one vacant unit on one calendar day.",
        load="Derived from S6 offer date ranges × dim_date, restricted to vacant unit-days",
        rows="Set in Phase 2 (depends on generator settings)", pk="(coverage_date_key, unit_key, incentive_key)",
        cols=[
            col("coverage_date_key", "INT", "Role: day the offer was available (part of PK)", key="PK, FK", ref="dim_date",
                src="ETL", ex="20260110"),
            col("unit_key", "INT", "Vacant unit the offer applied to (part of PK)", key="PK, FK", ref="dim_unit",
                src="ETL lookup", ex="117"),
            col("incentive_key", "INT", "Offer type (part of PK)", key="PK, FK", ref="dim_incentive", src="ETL lookup", ex="2"),
            fk("owner_key", "dim_owner", "Owner who approved the offer (owner on that day)", ex="57"),
        ] + tech_cols(),
    ),
]

TABLES = {t["name"]: t for t in DIMENSIONS + FACTS}

# ---------------------------------------------------------------- schema names (US-0.1)
# One place for every physical schema name. Medallion layer names (Bronze, Silver, Gold) stay as concepts;
# the physical homes are below. Brief names (project_*) map to these in README.md (pending instructor confirmation, O4).
SCHEMA_SOURCE = "src_pms"            # inside database lue_source
SCHEMA_STAGING = "lue_staging"       # Bronze tables brz_*, Silver tables stg_*
SCHEMA_DW = "lue_dw"                 # dimensional warehouse
SCHEMA_REPORTING = "lue_reporting"   # Gold marts and views
SCHEMA_AUDIT = "lue_audit"           # audit, quarantine, reconciliation, lineage
SCHEMA_MAP = {"bronze": SCHEMA_STAGING, "silver": SCHEMA_STAGING, "dw": SCHEMA_DW,
              "gold": SCHEMA_REPORTING, "audit": SCHEMA_AUDIT}
BRONZE = f"{SCHEMA_STAGING}.brz_*"
SILVER = f"{SCHEMA_STAGING}.stg_*"

# ---------------------------------------------------------------- audit schema
AUDIT = [
    dict(name=f"{SCHEMA_AUDIT}.etl_run_log", grain="One row per pipeline step per run", cols=[
        col("run_id", "BIGINT", "Pipeline run identifier", key="PK", ex="20260305001"),
        col("step", "VARCHAR(40)", "Step name", key="PK", ex="load_fact_payment"),
        col("started_at", "TIMESTAMP", "Step start", ex="2026-03-05 02:00:05"),
        col("ended_at", "TIMESTAMP", "Step end", null=True, ex="2026-03-05 02:01:12"),
        col("rows_read", "INT", "Rows read from the input layer", ex="1240"),
        col("rows_inserted", "INT", "Rows inserted", ex="1228"),
        col("rows_updated", "INT", "Rows updated (SCD Type 1, accumulating snapshot)", ex="0"),
        col("rows_rejected", "INT", "Rows sent to quarantine", ex="12", rule="read = inserted + updated + rejected + unchanged"),
        col("status", "VARCHAR(10)", "Success, Failed or Warning", ex="Success"),
    ]),
    dict(name=f"{SCHEMA_AUDIT}.quarantine", grain="One row per rejected source row", cols=[
        col("quarantine_id", "BIGINT", "Surrogate key", key="PK", ex="9031"),
        col("run_id", "BIGINT", "Run that rejected the row", key="FK", ref=f"{SCHEMA_AUDIT}.etl_run_log", ex="20260305001"),
        col("source_system", "VARCHAR(20)", "Source system", ex="S1_PMS"),
        col("source_table", "VARCHAR(40)", "Source table or file", ex="payments"),
        col("batch_id", "BIGINT", "Ingestion batch", ex="20260305001"),
        col("record", "JSONB", "The rejected row exactly as received", ex='{"payment_reference": "PAY-0098812", ...}'),
        col("check_name", "VARCHAR(30)", "NULL, Data type, Duplicate, Business rule, Referential, Range", ex="Duplicate"),
        col("rejection_reason", "VARCHAR(200)", "Readable reason", ex="payment_reference already loaded in this batch"),
        col("rejected_at", "TIMESTAMP", "When rejected", ex="2026-03-05 02:00:41"),
    ]),
    dict(name=f"{SCHEMA_AUDIT}.reconciliation", grain="One row per reconciliation check per run", cols=[
        col("run_id", "BIGINT", "Run", key="PK", ex="20260305001"),
        col("check_name", "VARCHAR(60)", "Check performed", key="PK", ex="net_amount src_pms vs fact_rent_invoice_line"),
        col("source_value", "NUMERIC(16,2)", "Value measured at the source", ex="11250340.00"),
        col("warehouse_value", "NUMERIC(16,2)", "Value measured in the warehouse", ex="11250340.00"),
        col("difference", "NUMERIC(16,2)", "source − warehouse", ex="0.00"),
        col("passed", "BOOLEAN", "Difference within tolerance", ex="TRUE"),
    ]),
    dict(name=f"{SCHEMA_AUDIT}.lineage", grain="One row per target table per source table", cols=[
        col("target_table", "VARCHAR(60)", "Warehouse or reporting table", key="PK", ex="lue_dw.fact_payment"),
        col("source_table", "VARCHAR(60)", "Source or upstream table", key="PK", ex="lue_staging.stg_payment_allocations"),
        col("layer_path", "VARCHAR(80)", "Layers crossed", ex="S1 → Bronze → Silver → DW"),
        col("transformation", "VARCHAR(200)", "Short description of the transformation", ex="Point-in-time key lookup, days_past_due derived"),
    ]),
]

# ---------------------------------------------------------------- sources
SOURCES = [
    dict(id="S1", name="PropertyHub (property management system)", fmt="PostgreSQL schema src_pms", owner="Operations",
         content="Buildings, units, tenants, leases, lease events, invoices, invoice lines, charge types, payments, payment allocations, payment methods",
         ingest="SQL extract with psycopg2 → lue_staging.brz_*", defects="Duplicate payments, missing amounts, out-of-range dates, invoices before the tenant record"),
    dict(id="S2", name="Owner, vendor and policy registers", fmt="Excel workbook (.xlsx)", owner="Owner relations, operations",
         content="Owners, unit ownership periods, vendors, SLA policy, holiday calendar",
         ingest="pandas.read_excel → lue_staging.brz_*", defects="Inconsistent casing and spaces, typos, missing transfer dates"),
    dict(id="S3", name="Bank and wallet settlement files", fmt="CSV, one file per channel per day", owner="Finance",
         content="Settled transactions from bank transfer, Raast, JazzCash and Easypaisa",
         ingest="pandas.read_csv → lue_staging.brz_*", defects="Files arriving late, references that do not match PropertyHub"),
    dict(id="S4", name="Tenant app maintenance tickets", fmt="JSON export with nested status history", owner="Operations",
         content="Tickets, category, priority, vendor, estimate, final cost, status changes with timestamps",
         ingest="json + pandas.json_normalize → lue_staging.brz_*", defects="Missing resolve times, statuses out of order"),
    dict(id="S5", name="Weather", fmt="REST API (Open-Meteo historical, JSON)", owner="External",
         content="Daily rainfall and maximum temperature for Lahore, Karachi, Islamabad and Faisalabad",
         ingest="requests → lue_staging.brz_*", defects="Missing days returned as nulls"),
    dict(id="S6", name="Incentive log", fmt="CSV exported from per-building leasing spreadsheets", owner="Leasing",
         content="Incentive offers per unit with start and end dates",
         ingest="pandas.read_csv → lue_staging.brz_*", defects="Different date formats per building; unit codes without building prefix"),
]

SOURCE_TABLES = [
    ("S1", "src_pms.buildings", "One building", "building_code"),
    ("S1", "src_pms.units", "The current state of one unit", "unit_id (business key building_code + unit_no)"),
    ("S1", "src_pms.tenants", "The current state of one tenant (no history kept)", "tenant_code"),
    ("S1", "src_pms.leases", "One lease contract for one unit and one primary tenant", "lease_number"),
    ("S1", "src_pms.lease_events", "One lifecycle event on one lease", "event_id"),
    ("S1", "src_pms.invoices", "One invoice header issued to one lease for one month", "invoice_number"),
    ("S1", "src_pms.invoice_lines", "One charge line on one invoice", "invoice_number + line_no"),
    ("S1", "src_pms.charge_types", "One charge type", "charge_code"),
    ("S1", "src_pms.payments", "One payment receipt from a tenant", "payment_reference"),
    ("S1", "src_pms.payment_allocations", "One portion of one payment applied to one invoice line",
     "payment_reference + invoice_number + line_no"),
    ("S1", "src_pms.payment_methods", "One payment method", "method_code"),
    ("S2", "owners (sheet)", "One owner", "owner_code"),
    ("S2", "ownership (sheet)", "One period during which one owner held one unit", "unit + owner + valid_from"),
    ("S2", "vendors (sheet)", "The current state of one vendor", "vendor_code"),
    ("S2", "sla_policy (sheet)", "One SLA rule for one subcategory from a start date", "subcategory_code + valid_from"),
    ("S2", "holidays (sheet)", "One public holiday or Ramadan day", "date"),
    ("S3", "settlement_<channel>_<date>.csv", "One settled transaction on one channel on one day", "channel + settlement_id"),
    ("S4", "tickets.json", "One maintenance request with an array of status changes", "ticket_id"),
    ("S5", "Open-Meteo daily response", "One city on one day", "city + date"),
    ("S6", "incentive_log.csv", "One offer on one unit between a start and an end date", "building + unit + offer + start"),
]

# Normalised source ERD (Lab 03 style) for src_pms
SOURCE_ERD = {
    "buildings": [("VARCHAR(8)", "building_code", "PK"), ("VARCHAR(80)", "building_name", ""), ("VARCHAR(30)", "city", ""),
                  ("VARCHAR(40)", "locality", ""), ("CHAR(1)", "building_class", ""), ("SMALLINT", "year_built", "")],
    "units": [("INT", "unit_id", "PK"), ("VARCHAR(8)", "building_code", "FK"), ("VARCHAR(10)", "unit_no", ""),
              ("SMALLINT", "floor_no", ""), ("VARCHAR(20)", "unit_type", ""), ("NUMERIC(8,1)", "area_sqft", ""),
              ("SMALLINT", "bedrooms", ""), ("BOOLEAN", "furnished", ""), ("TIMESTAMP", "updated_at", "")],
    "tenants": [("VARCHAR(12)", "tenant_code", "PK"), ("VARCHAR(100)", "full_name", ""), ("VARCHAR(12)", "tenant_type", ""),
                ("VARCHAR(30)", "employer_sector", ""), ("VARCHAR(20)", "phone", ""), ("VARCHAR(12)", "contact_channel", ""),
                ("TIMESTAMP", "updated_at", "")],
    "leases": [("VARCHAR(14)", "lease_number", "PK"), ("INT", "unit_id", "FK"), ("VARCHAR(12)", "tenant_code", "FK"),
               ("VARCHAR(12)", "lease_type", ""), ("DATE", "start_date", ""), ("DATE", "end_date", ""),
               ("NUMERIC(12,2)", "monthly_rent", ""), ("VARCHAR(20)", "rent_review_type", ""),
               ("VARCHAR(14)", "previous_lease_number", "FK"), ("VARCHAR(12)", "status", "")],
    "lease_events": [("INT", "event_id", "PK"), ("VARCHAR(14)", "lease_number", "FK"), ("VARCHAR(8)", "event_code", ""),
                     ("DATE", "event_date", "")],
    "invoices": [("VARCHAR(16)", "invoice_number", "PK"), ("VARCHAR(14)", "lease_number", "FK"), ("DATE", "invoice_date", ""),
                 ("DATE", "due_date", ""), ("VARCHAR(12)", "status", "")],
    "invoice_lines": [("VARCHAR(16)", "invoice_number", "PK, FK"), ("SMALLINT", "line_no", "PK"),
                      ("VARCHAR(8)", "charge_code", "FK"), ("NUMERIC(12,2)", "billed_amount", ""),
                      ("NUMERIC(12,2)", "tax_amount", ""), ("NUMERIC(12,2)", "discount_amount", ""),
                      ("NUMERIC(12,2)", "net_amount", "")],
    "charge_types": [("VARCHAR(8)", "charge_code", "PK"), ("VARCHAR(30)", "name", ""), ("VARCHAR(12)", "category", "")],
    "payments": [("VARCHAR(20)", "payment_reference", "PK"), ("VARCHAR(12)", "tenant_code", "FK"), ("TIMESTAMP", "paid_at", ""),
                 ("VARCHAR(10)", "method_code", "FK"), ("NUMERIC(12,2)", "amount", ""), ("VARCHAR(10)", "status", ""),
                 ("VARCHAR(20)", "reversal_of", "FK")],
    "payment_allocations": [("VARCHAR(20)", "payment_reference", "PK, FK"), ("VARCHAR(16)", "invoice_number", "PK, FK"),
                            ("SMALLINT", "line_no", "PK, FK"), ("NUMERIC(12,2)", "allocated_amount", "")],
    "payment_methods": [("VARCHAR(10)", "method_code", "PK"), ("VARCHAR(30)", "name", "")],
}
SOURCE_RELS = [
    ("buildings", "||--o{", "units", "contains"),
    ("units", "||--o{", "leases", "let under"),
    ("tenants", "||--o{", "leases", "signs"),
    ("leases", "|o--o|", "leases", "renews"),
    ("leases", "||--o{", "lease_events", "records"),
    ("leases", "||--o{", "invoices", "billed by"),
    ("invoices", "||--|{", "invoice_lines", "contains"),
    ("charge_types", "||--o{", "invoice_lines", "classifies"),
    ("tenants", "||--o{", "payments", "makes"),
    ("payment_methods", "||--o{", "payments", "used by"),
    ("payments", "||--|{", "payment_allocations", "split into"),
    ("invoice_lines", "||--o{", "payment_allocations", "settled by"),
    ("payments", "|o--o|", "payments", "reverses"),
]

# ---------------------------------------------------------------- processes, bus matrix
PROCESSES = [
    ("P1", "Rent invoicing and payment", "Charges are billed to leases each month; tenants pay invoice lines, often in instalments",
     ["fact_rent_invoice_line", "fact_payment"], "Transaction (two facts)",
     "Billing and paying are separate events with different grains: one line can be paid in several instalments and one payment can cover several lines."),
    ("P2", "Unit occupancy", "Every unit is occupied or vacant on every day, at a contract rent",
     ["fact_unit_occupancy_daily"], "Periodic snapshot",
     "Management needs the state of every unit on every day, including days on which nothing happened."),
    ("P3", "Maintenance", "A request is raised, assigned to a vendor, resolved and verified",
     ["fact_maintenance_request"], "Accumulating snapshot",
     "A request has a fixed set of milestones; one row per request with a date per milestone gives lags directly."),
    ("P4", "Lease lifecycle", "Leases are signed, renewed, given notice and terminated",
     ["fact_lease_event"], "Factless (event tracking)",
     "The event itself is the fact; counting events by type answers renewal and churn questions."),
    ("P5", "Vacancy marketing", "Incentive offers are made available on vacant units",
     ["fact_vacancy_incentive_coverage"], "Factless (coverage)",
     "Records offers that existed even when no lease followed, which no transaction fact can show."),
]

BUS_DIMS = ["dim_date", "dim_unit", "dim_tenant", "dim_lease", "dim_owner", "dim_payment_method", "dim_charge_type",
            "dim_maintenance_category", "dim_vendor", "dim_lease_event_type", "dim_request_flags", "dim_incentive",
            "dim_weather"]


def bus_matrix():
    rows = []
    for f in FACTS:
        refs = {}
        for c in f["cols"]:
            if c["ref"] and c["ref"].startswith("dim_"):
                role = c["name"].replace("_key", "").replace("_date", "")
                refs.setdefault(c["ref"], []).append(role)
        row = []
        for d in BUS_DIMS:
            if d not in refs:
                row.append("")
            elif d == "dim_date":
                row.append("X (" + ", ".join(refs[d]) + ")")
            else:
                row.append("X")
        rows.append((f["name"], row))
    return rows


# ---------------------------------------------------------------- questions
QUESTIONS = [
    ("Q1", "What is the monthly collection rate by building?", "P1", "Finance head",
     "fact_rent_invoice_line + fact_payment", "dim_date (due), dim_unit", "net_amount, payment_amount",
     "Drill-across on due date; ROLLUP Region → City → Building with GROUPING() labels"),
    ("Q2", "Which buildings have the highest arrears ratio?", "P1", "CEO, finance head",
     "fact_rent_invoice_line + fact_payment", "dim_unit, dim_date (due)", "net_amount, payment_amount",
     "Aggregate first, then Top-N (RANK)"),
    ("Q3", "How are overdue balances distributed across ageing buckets (0–30, 31–60, 61–90, 90+ days)?", "P1",
     "Finance head", "fact_rent_invoice_line + fact_payment", "dim_date (due), dim_charge_type", "open balance",
     "Slice by bucket; drill bucket → building"),
    ("Q4", "Which tenants pay late repeatedly, and does late payment differ by employer sector at the time of payment?",
     "P1", "Finance head, building managers", "fact_payment", "dim_tenant (SCD2), dim_date (paid)",
     "days_past_due (weighted), payment_amount", "Window functions (late months per tenant); slice by sector version"),
    ("Q5", "Which payment methods settle fastest after the due date?", "P1", "Finance head",
     "fact_payment", "dim_payment_method", "days_past_due, settlement_lag_days", "Roll-up Method → Channel group"),
    ("Q6", "How do occupancy and vacancy trend by city and unit type?", "P2", "Operations head",
     "fact_unit_occupancy_daily", "dim_date (snapshot), dim_unit", "is_occupied",
     "CUBE City × Unit type; drill Year → Quarter → Month"),
    ("Q7", "Which unit types stay vacant longest?", "P2", "Leasing manager",
     "fact_unit_occupancy_daily", "dim_unit, dim_date", "is_occupied (vacancy spells)",
     "Window functions (LAG) to find vacancy spells"),
    ("Q8", "What is the lease renewal rate, and which buildings lose tenants at renewal?", "P4", "Leasing manager",
     "fact_lease_event + dim_lease", "dim_lease_event_type, dim_unit, dim_date (event)", "event_count",
     "Ratio of counts by building; ROLLUP City → Building"),
    ("Q9", "What is the average time to resolve a request by category and vendor, and were low-rated vendors slower?",
     "P3", "Operations head", "fact_maintenance_request", "dim_maintenance_category, dim_vendor (SCD2)",
     "days_to_resolve", "Drill Category → Subcategory; slice by rating band in force"),
    ("Q10", "Which buildings breach the maintenance SLA most often?", "P3", "Operations head, building managers",
     "fact_maintenance_request", "dim_unit, dim_maintenance_category", "sla_breached_flag",
     "ROLLUP City → Building with GROUPING() labels"),
    ("Q11", "What is the maintenance cost per unit per month by building?", "P3", "Owner relations lead",
     "fact_maintenance_request + dim_unit", "dim_date (resolved), dim_unit", "actual_cost",
     "Roll-up Month → Quarter → Fiscal year"),
    ("Q12", "What is the net operating income (rent collected − maintenance cost − LUE fee) per owner portfolio?", "P1, P3",
     "CEO, owner relations lead", "fact_payment + fact_maintenance_request", "dim_owner, dim_date",
     "payment_amount, actual_cost", "Drill-across on conformed Owner and Date"),
    ("Q13", "Do vacancy incentives shorten vacancy, and which offer type works best?", "P2, P5", "Leasing manager",
     "fact_vacancy_incentive_coverage + fact_unit_occupancy_daily", "dim_incentive, dim_unit, dim_date",
     "covered vs uncovered vacancy spell length", "Compare covered vs uncovered spells; slice by incentive type"),
    ("Q14", "Do leak and plumbing requests rise on heavy-rain days?", "P3", "Operations head",
     "fact_maintenance_request", "dim_weather, dim_maintenance_category", "request count",
     "Slice by rain band; drill Category → Subcategory"),
]

GRAIN_TESTS = [
    ("Q1–Q3", "Invoice line + payment facts",
     "The occupancy snapshot holds only the current lease's arrears, so a departed tenant's debt would be missed."),
    ("Q4", "fact_payment",
     "Only the payment fact knows when money arrived; invoice lines record what was billed, not when it was paid."),
    ("Q6–Q7", "fact_unit_occupancy_daily",
     "Lease events record changes, not the state of every unit on every day, so vacancy days cannot be counted from them."),
    ("Q8", "fact_lease_event",
     "The occupancy snapshot shows a unit stayed occupied but cannot tell a renewal from a new tenant."),
    ("Q9–Q11", "fact_maintenance_request",
     "Only the accumulating snapshot holds every milestone date of a request on one row."),
    ("Q12", "Two facts (drill-across)",
     "Rent and cost belong to different processes and meet only through conformed dim_owner and dim_date."),
    ("Q13", "fact_vacancy_incentive_coverage",
     "An offer that produced no lease leaves no row in any other fact; only the coverage fact records it."),
]

# ---------------------------------------------------------------- KPIs
KPIS = [
    ("Collection rate", "SUM(payment_amount allocated to lines due in the period) / SUM(net_amount of lines due in the period)",
     "fact_rent_invoice_line, fact_payment", "Q1"),
    ("Arrears ratio", "SUM(net_amount − allocated payments) for lines past due / SUM(net_amount billed)",
     "fact_rent_invoice_line, fact_payment", "Q2"),
    ("Arrears ageing", "Open balance grouped by days past due: 0–30, 31–60, 61–90, 90+", "fact_rent_invoice_line, fact_payment", "Q3"),
    ("DSO (rent)", "Open receivable at period end / net_amount billed in the period × days in the period",
     "fact_rent_invoice_line, fact_payment", "Q2"),
    ("Occupancy rate", "SUM(is_occupied) / COUNT(unit-days)", "fact_unit_occupancy_daily", "Q6"),
    ("Average vacancy duration", "Total vacant days / number of completed vacancy spells", "fact_unit_occupancy_daily", "Q7"),
    ("Renewal rate", "COUNT(renewed events) / COUNT(leases whose end_date falls in the period)", "fact_lease_event, dim_lease", "Q8"),
    ("Average days to resolve", "SUM(days_to_resolve) / COUNT(resolved requests)", "fact_maintenance_request", "Q9"),
    ("SLA breach rate", "SUM(sla_breached_flag) / COUNT(resolved requests)", "fact_maintenance_request", "Q10"),
    ("Maintenance cost per unit-month", "SUM(actual_cost) / (number of units × number of months)",
     "fact_maintenance_request, dim_unit", "Q11"),
    ("Net operating income per owner", "Rent collected − SUM(actual_cost) − LUE management fee",
     "fact_payment, fact_maintenance_request", "Q12"),
    ("Incentive effect", "Average vacancy spell length with an offer − without an offer",
     "fact_vacancy_incentive_coverage, fact_unit_occupancy_daily", "Q13"),
]

STAKEHOLDERS = [
    ("CEO", "Portfolio health, risk", "Which buildings underperform on collection and NOI?", "Owner portfolio"),
    ("Finance head", "Collections, arrears, cash flow", "What is this month's collection rate and arrears ageing?", "Collections"),
    ("Operations head", "Vacancy, maintenance performance", "Which vendors breach SLA most?", "Maintenance"),
    ("Building managers", "Their own building", "Who is overdue in my building? Which requests are aged?", "Collections, Maintenance (filtered)"),
    ("Leasing manager", "Renewals, vacancy, incentives", "Do incentives shorten vacancy?", "Occupancy and leasing"),
    ("Owner relations lead", "Owner reporting", "What is each owner's NOI this quarter?", "Owner portfolio"),
]

HIERARCHIES = [
    ("dim_date", "Calendar", "Day → Month → Quarter → Year"),
    ("dim_date", "Fiscal (July–June)", "Day → Fiscal month → Fiscal quarter → Fiscal year"),
    ("dim_unit", "Location", "Unit → Floor → Building → Locality → City → Region"),
    ("dim_payment_method", "Channel", "Method → Channel group"),
    ("dim_charge_type", "Charge", "Charge type → Charge category"),
    ("dim_maintenance_category", "Maintenance", "Subcategory → Category"),
    ("dim_vendor", "Trade", "Vendor → Trade"),
    ("dim_tenant", "Tenant type", "Tenant → Tenant type"),
    ("dim_owner", "Owner type", "Owner → Owner type"),
    ("dim_incentive", "Incentive", "Incentive → Incentive type"),
]

ADDITIVITY = [
    ("fact_rent_invoice_line", "billed_amount, tax_amount, discount_amount, net_amount", "Additive",
     "SUM across every dimension"),
    ("fact_payment", "payment_amount", "Additive (signed)", "SUM; reversals net out"),
    ("fact_payment", "days_past_due, settlement_lag_days", "Non-additive", "Amount-weighted average or median"),
    ("fact_unit_occupancy_daily", "is_occupied", "Semi-additive", "SUM across units on one day; AVG across days"),
    ("fact_unit_occupancy_daily", "contract_rent", "Semi-additive", "SUM across units on one day = rent roll; never SUM across days"),
    ("fact_unit_occupancy_daily", "current_lease_arrears", "Semi-additive", "Period-end value; never SUM across days"),
    ("fact_maintenance_request", "estimated_cost, actual_cost", "Additive", "SUM"),
    ("fact_maintenance_request", "sla_breached_flag", "Additive count", "SUM / COUNT for a rate"),
    ("fact_maintenance_request", "days_to_assign, days_to_resolve, days_to_verify", "Non-additive", "AVG or median"),
    ("fact_lease_event", "event_count", "Additive count", "SUM = COUNT(*)"),
    ("fact_vacancy_incentive_coverage", "(none)", "—", "COUNT(*) = offer-days"),
]
