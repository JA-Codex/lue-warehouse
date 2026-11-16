"""US-5.1: the staging contract as data. One place for every stg_ table: its bronze source, natural
key, survivorship order, and each column with its type, how it is cleaned and its NULL rule.

From this one spec come (etl/staging/ddl.py writes them, scripts/test_staging_contract.py checks
they are current):
  sql/20_staging/03_staging_functions.sql   clean_text, std and the vocabularies
  sql/20_staging/04_staging_tables.sql      the 20 stg_ tables
  docs/contracts/staging.md                 the contract E6 and E7 read
and the loader (etl/staging/load.py) builds its SQL from it.

Column expressions are SQL over the bronze row (alias b); every value in bronze is text exactly as
the source gave it, so the casts are the safe ones of E4 (lue_audit.try_*).
"""

# ruff: noqa: E501  (a table of column definitions and SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass, field

from etl import reference_data as ref


@dataclass
class Col:
    name: str
    type: str
    expr: str  # SQL over b; "" for a derived column (filled by etl/staging/business.py, US-5.2)
    doc: str
    null: str = "never NULL"  # the NULL rule, for the contract

    @property
    def derived(self) -> bool:
        return self.expr == ""


@dataclass
class Table:
    name: str
    bronze: str
    source_system: str
    key: list[str]
    cols: list[Col]
    doc: str
    updated: str = ""  # SQL for the source's own updated_at (D15), "" when the source has none
    where: str = ""  # extra SQL filter on b
    after: str = ""  # a staging table that must be loaded first
    extra_lineage: list[Col] = field(default_factory=list)

    @property
    def loaded(self) -> list[Col]:
        return [c for c in self.cols if not c.derived]

    @property
    def derived(self) -> list[Col]:
        return [c for c in self.cols if c.derived]


# ----------------------------------------------------------------------------- helpers
def text(c: str) -> str:
    """Trimmed, inner spaces collapsed, empty -> NULL."""
    return f"lue_staging.clean_text(b.{c})"


def code(c: str) -> str:
    """A business code: cleaned and upper case."""
    return f"upper(lue_staging.clean_text(b.{c}))"


def vocab(domain: str, c: str) -> str:
    """The canonical spelling from the vocabulary (NULL if the value is not in it)."""
    return f"lue_staging.std('{domain}', b.{c})"


def num(c: str, typ: str = "numeric") -> str:
    return f"lue_audit.try_numeric(b.{c})::{typ}"


def day(c: str) -> str:
    return f"lue_audit.try_date(b.{c})"


def stamp(c: str) -> str:
    return f"lue_audit.try_timestamp(b.{c})"


def boolean(c: str) -> str:
    return f"lower(lue_staging.clean_text(b.{c}))::boolean"


LINEAGE = [
    Col("source_system", "VARCHAR(20)", "b.source_system", "Source system of the surviving row"),
    Col("batch_id", "BIGINT", "b.batch_id", "Bronze batch of the surviving row"),
    Col("loaded_at", "TIMESTAMP", "b.loaded_at", "When that row was landed in bronze"),
    Col("src_row_id", "BIGINT", "b.row_id", "Bronze row_id of the surviving row (lineage)"),
    Col("src_updated_at", "TIMESTAMP", "", "The source's updated_at used by survivorship",
        null="NULL when the source has none"),  # fmt: skip
    Col("run_id", "BIGINT", "", "Pipeline run that last inserted or changed the row"),
    Col("staged_at", "TIMESTAMP", "", "When the row was last inserted or changed"),
]
LINEAGE_NAMES = [c.name for c in LINEAGE]

# ----------------------------------------------------------------------------- vocabularies
# domain -> canonical values. Matching ignores case and extra spaces (' lahore ' -> 'Lahore').
# Extra variants (other spellings and codes) map to a canonical value.
VOCABULARY = {
    "city": [c for c in ("Lahore", "Karachi", "Islamabad", "Faisalabad")],
    "unit_type": ["Apartment", "Office", "Shop"],
    "tenant_type": ["Individual", "Corporate"],
    "contact_channel": ["Phone", "WhatsApp", "Email"],
    "employer_sector": ["Banking", "Construction", "Education", "Energy", "Government",
                        "Healthcare", "Hospitality", "IT and Software", "Legal and Consulting",
                        "Logistics", "Manufacturing", "Media", "Retail", "Self-employed",
                        "Telecom"],  # fmt: skip
    "lease_type": ["Residential", "Commercial"],
    "rent_review_type": ["Fixed", "Annual escalation"],
    "lease_status": ["Active", "Renewed", "Terminated"],
    "invoice_status": ["Paid", "Partial", "Overdue"],
    "payment_status": ["Cleared", "Bounced"],
    "owner_type": ["Individual", "Company"],
    "trade": ["Plumbing", "Electrical", "HVAC", "Civil", "Pest control", "General maintenance"],
    "ticket_category": ["Plumbing", "Electrical", "HVAC", "Civil", "Pest control", "Other"],
    "priority": ["Emergency", "High", "Normal"],
    "reported_via": ["Tenant app", "Building staff"],
    "ticket_status": ["Raised", "Assigned", "Resolved", "Verified"],
    "offer_type": ["Rent-free days", "Discount", "Free maintenance"],
}
VARIANTS = {  # (domain, variant) -> canonical
    ("city", "LHE"): "Lahore", ("city", "KHI"): "Karachi", ("city", "ISB"): "Islamabad",
    ("city", "FSD"): "Faisalabad", ("city", "Lyallpur"): "Faisalabad",
    ("contact_channel", "E-mail"): "Email",
}  # fmt: skip
REGION = {"Lahore": "Punjab", "Faisalabad": "Punjab", "Karachi": "Sindh",
          "Islamabad": "Islamabad Capital Territory"}  # fmt: skip
CITY_CODE = {"Lahore": "LHE", "Karachi": "KHI", "Islamabad": "ISB", "Faisalabad": "FSD"}
# Payment methods: code -> (name, method_type, is_electronic). From etl/reference_data.py.
PAYMENT_METHODS = {m[0]: (m[1], m[2], m[2] not in ("Cash", "Cheque")) for m in ref.PAYMENT_METHODS}

RECURRING_DAYS = 30  # data dictionary: is_recurring = same subcategory on the same unit within 30 days

# ----------------------------------------------------------------------------- the tables
TABLES = [
    Table("stg_building", "brz_building", "S1", ["building_code"], doc="One row per building.", cols=[
        Col("building_code", "VARCHAR(8)", code("building_code"), "Building business code"),
        Col("building_name", "VARCHAR(80)", text("building_name"), "Building name"),
        Col("city", "VARCHAR(30)", vocab("city", "city"), "City, one spelling (vocabulary)",
            null="NULL only if the city is not in the vocabulary (then counted in the evidence)"),
        Col("city_code", "CHAR(3)", "lue_staging.city_code(" + vocab("city", "city") + ")",
            "City code: LHE, KHI, ISB, FSD"),
        Col("region", "VARCHAR(30)", "lue_staging.region_of(" + vocab("city", "city") + ")",
            "Province or territory, from the city"),
        Col("locality", "VARCHAR(40)", text("locality"), "Neighbourhood"),
        Col("building_class", "CHAR(1)", code("building_class"), "A, B or C"),
        Col("year_built", "SMALLINT", num("year_built", "smallint"), "Year built"),
    ]),  # fmt: skip
    Table("stg_unit", "brz_unit", "S1", ["unit_id"], updated=stamp("updated_at"),
          doc="One row per unit (the latest version by updated_at).", cols=[
        Col("unit_id", "INT", num("unit_id", "int"), "Unit id in PropertyHub"),
        Col("building_code", "VARCHAR(8)", code("building_code"), "Building of the unit"),
        Col("unit_no", "VARCHAR(10)", text("unit_no"), "Unit number inside the building"),
        Col("floor_no", "SMALLINT", num("floor_no", "smallint"), "Floor"),
        Col("unit_type", "VARCHAR(20)", vocab("unit_type", "unit_type"), "Apartment, Office or Shop"),
        Col("area_sqft", "NUMERIC(8,1)", num("area_sqft", "numeric(8,1)"), "Area in square feet"),
        Col("bedrooms", "SMALLINT", num("bedrooms", "smallint"), "Bedrooms (0 for offices and shops)"),
        Col("furnished", "BOOLEAN", boolean("furnished"), "Let furnished"),
    ]),  # fmt: skip
    Table("stg_tenant", "brz_tenant", "S1", ["tenant_code"], updated=stamp("updated_at"),
          doc="One row per tenant (the latest version by updated_at).", cols=[
        Col("tenant_code", "VARCHAR(12)", code("tenant_code"), "Tenant business key"),
        Col("tenant_name", "VARCHAR(100)", text("full_name"), "Tenant or company name"),
        Col("tenant_type", "VARCHAR(12)", vocab("tenant_type", "tenant_type"), "Individual or Corporate"),
        Col("employer_sector", "VARCHAR(30)",
            f"coalesce({vocab('employer_sector', 'employer_sector')}, {text('employer_sector')}, "
            "'Unknown')", "Employer sector", null="'Unknown' when missing (data dictionary)"),
        Col("phone", "VARCHAR(20)", text("phone"), "Phone", null="NULL when missing"),
        Col("contact_channel", "VARCHAR(12)", vocab("contact_channel", "contact_channel"),
            "Phone, WhatsApp or Email"),
    ]),  # fmt: skip
    Table("stg_lease", "brz_lease", "S1", ["lease_number"], doc="One row per lease.", cols=[
        Col("lease_number", "VARCHAR(14)", code("lease_number"), "Lease business key"),
        Col("unit_id", "INT", num("unit_id", "int"), "Unit let"),
        Col("tenant_code", "VARCHAR(12)", code("tenant_code"), "Tenant",
            null="never NULL; may name a tenant not staged yet (late arriving, US-6.5)"),
        Col("lease_type", "VARCHAR(12)", vocab("lease_type", "lease_type"), "Residential or Commercial"),
        Col("start_date", "DATE", day("start_date"), "Contract start"),
        Col("end_date", "DATE", day("end_date"), "Contract end"),
        Col("monthly_rent", "NUMERIC(12,2)", num("monthly_rent", "numeric(12,2)"),
            "Rent agreed at signing (PKR)"),
        Col("rent_review_type", "VARCHAR(20)", vocab("rent_review_type", "rent_review_type"),
            "Fixed or Annual escalation"),
        Col("previous_lease_number", "VARCHAR(14)", code("previous_lease_number"),
            "The lease this one renews", null="NULL for a first lease"),
        Col("status", "VARCHAR(12)", vocab("lease_status", "status"), "Active, Renewed or Terminated"),
        Col("term_months", "SMALLINT", "", "Contract length in whole months (US-5.2)"),
    ]),  # fmt: skip
    Table("stg_lease_event", "brz_lease_event", "S1", ["event_id"], doc="One row per lease event.",
          cols=[
        Col("event_id", "INT", num("event_id", "int"), "Event id"),
        Col("lease_number", "VARCHAR(14)", code("lease_number"), "Lease"),
        Col("event_code", "VARCHAR(8)", code("event_code"), "SIGN, RENEW, NOTICE or TERM"),
        Col("event_date", "DATE", day("event_date"), "Event date"),
    ]),  # fmt: skip
    Table("stg_invoice", "brz_invoice", "S1", ["invoice_number"], doc="One row per invoice.", cols=[
        Col("invoice_number", "VARCHAR(16)", code("invoice_number"), "Invoice number"),
        Col("lease_number", "VARCHAR(14)", code("lease_number"), "Lease billed"),
        Col("invoice_date", "DATE", day("invoice_date"), "Invoice date"),
        Col("due_date", "DATE", day("due_date"), "Due date"),
        Col("status", "VARCHAR(10)", vocab("invoice_status", "status"), "Paid, Partial or Overdue"),
    ]),  # fmt: skip
    Table("stg_invoice_line", "brz_invoice_line", "S1", ["invoice_number", "line_no"],
          doc="One row per invoice line.", cols=[
        Col("invoice_number", "VARCHAR(16)", code("invoice_number"), "Invoice"),
        Col("line_no", "SMALLINT", num("line_no", "smallint"), "Line number"),
        Col("charge_code", "VARCHAR(8)", code("charge_code"), "Charge type"),
        Col("billed_amount", "NUMERIC(12,2)", num("billed_amount", "numeric(12,2)"), "Billed (PKR)"),
        Col("tax_amount", "NUMERIC(12,2)", num("tax_amount", "numeric(12,2)"), "Tax (PKR)"),
        Col("discount_amount", "NUMERIC(12,2)", num("discount_amount", "numeric(12,2)"),
            "Discount (PKR)"),
        Col("net_amount", "NUMERIC(12,2)", num("net_amount", "numeric(12,2)"),
            "billed + tax - discount (PKR); negative for credits"),
        Col("due_date", "DATE", "", "Due date of the invoice (US-5.2)",
            null="NULL if the invoice is not staged"),
        Col("allocated_amount", "NUMERIC(12,2)", "", "Sum of the allocations to the line (US-5.2)"),
        Col("open_balance", "NUMERIC(12,2)", "", "net_amount - allocated_amount (US-5.2)"),
    ]),  # fmt: skip
    Table("stg_payment", "brz_payment", "S1", ["payment_reference"], doc="One row per payment.",
          cols=[
        Col("payment_reference", "VARCHAR(20)", code("payment_reference"), "Payment receipt number"),
        Col("tenant_code", "VARCHAR(12)", code("tenant_code"), "Tenant",
            null="never NULL; may name a tenant not staged yet (US-6.5)"),
        Col("paid_at", "TIMESTAMP", stamp("paid_at"), "When the money was received"),
        Col("method_code", "VARCHAR(10)", code("method_code"), "Payment method"),
        Col("amount", "NUMERIC(12,2)", num("amount", "numeric(12,2)"),
            "Amount (PKR); negative for a reversal"),
        Col("status", "VARCHAR(10)", vocab("payment_status", "status"), "Cleared or Bounced"),
        Col("reversal_of", "VARCHAR(20)", code("reversal_of"), "The payment this one reverses",
            null="NULL unless a reversal"),
        Col("is_reversal", "BOOLEAN", "", "status = 'Bounced' (data dictionary; US-5.2)"),
        Col("is_electronic", "BOOLEAN", "", "Bank, Raast, JazzCash or Easypaisa (US-5.2)"),
        Col("allocated_amount", "NUMERIC(12,2)", "", "Sum of the payment's allocations (US-5.2)"),
        Col("settlement_id", "VARCHAR(20)", "", "Matched S3 settlement line (US-5.2)",
            null="NULL if not matched"),
        Col("settlement_date", "DATE", "", "Date the bank settled it (US-5.2)",
            null="NULL if not matched"),
        Col("settlement_lag_days", "SMALLINT", "", "settlement_date - paid date (US-5.2)",
            null="NULL if not matched"),
        Col("is_unsettled", "BOOLEAN", "", "An electronic, cleared payment with no settlement line "
            "(US-5.2)"),
    ]),  # fmt: skip
    Table("stg_payment_allocation", "brz_payment_allocation", "S1",
          ["payment_reference", "invoice_number", "line_no"],
          doc="One row per payment and invoice line: S1's allocations, plus the allocations staging "
              "derives for a payment the source left (partly) unallocated (US-5.2).", cols=[
        Col("payment_reference", "VARCHAR(20)", code("payment_reference"), "Payment"),
        Col("invoice_number", "VARCHAR(16)", code("invoice_number"), "Invoice"),
        Col("line_no", "SMALLINT", num("line_no", "smallint"), "Invoice line"),
        Col("allocated_amount", "NUMERIC(12,2)", num("allocated_amount", "numeric(12,2)"),
            "Amount allocated (PKR); negative for a reversal"),
        Col("allocation_source", "VARCHAR(8)", "'S1'", "S1, or derived (by staging, US-5.2)"),
        Col("paid_at", "TIMESTAMP", "", "Paid time of the payment (US-5.2)"),
        Col("due_date", "DATE", "", "Due date of the line (US-5.2)"),
        Col("days_past_due", "SMALLINT", "", "Paid date - due date in days; negative = early "
            "(US-5.2)", null="NULL if the payment or the line is not staged"),
        Col("is_reversal", "BOOLEAN", "", "The payment is a reversal (US-5.2)"),
    ]),  # fmt: skip
    Table("stg_settlement", "brz_settlement", "S3", ["channel", "settlement_id"],
          doc="One row per settlement line of the banks and wallets.", cols=[
        Col("channel", "VARCHAR(12)",
            "split_part(split_part(b.source_file, '/', -1), '_', 2)",
            "bank, raast, jazzcash or easypaisa (from the file name)"),
        Col("settlement_id", "VARCHAR(20)", code("settlement_id"), "Line id in the channel"),
        Col("payment_reference", "VARCHAR(20)", code("payment_reference"), "Payment it settles"),
        Col("transaction_date", "DATE", day("transaction_date"), "Payment date per the bank"),
        Col("settlement_date", "DATE", day("settlement_date"), "Date settled"),
        Col("gross_amount", "NUMERIC(12,2)", num("gross_amount", "numeric(12,2)"), "Gross (PKR)"),
        Col("fee_amount", "NUMERIC(12,2)", num("fee_amount", "numeric(12,2)"), "Fee (PKR)"),
        Col("net_amount", "NUMERIC(12,2)", num("net_amount", "numeric(12,2)"), "Net (PKR)"),
        Col("is_matched", "BOOLEAN", "", "The payment is in stg_payment (US-5.2)"),
        Col("settlement_lag_days", "SMALLINT", "", "settlement_date - the payment's paid date "
            "(US-5.2)", null="NULL if not matched"),
    ]),  # fmt: skip
    Table("stg_owner", "brz_owner", "S2", ["owner_code"], doc="One row per owner.", cols=[
        Col("owner_code", "VARCHAR(10)", code("owner_code"), "Owner business key"),
        Col("owner_name", "VARCHAR(100)", text("owner_name"), "Owner name"),
        Col("owner_type", "VARCHAR(12)", vocab("owner_type", "owner_type"), "Individual or Company"),
    ]),  # fmt: skip
    Table("stg_ownership", "brz_ownership", "S2", ["building_code", "unit_no", "valid_from"],
          doc="One row per unit ownership period.", cols=[
        Col("building_code", "VARCHAR(8)", code("building_code"), "Building"),
        Col("unit_no", "VARCHAR(10)", text("unit_no"), "Unit number"),
        Col("owner_code", "VARCHAR(10)", code("owner_code"), "Owner"),
        Col("valid_from", "DATE", day("valid_from"), "First day of the ownership"),
        Col("valid_to", "DATE", day("valid_to"), "Last day", null="NULL while it lasts"),
    ]),  # fmt: skip
    Table("stg_vendor", "brz_vendor", "S2", ["vendor_code"], doc="One row per vendor.", cols=[
        Col("vendor_code", "VARCHAR(10)", code("vendor_code"), "Vendor business key"),
        Col("vendor_name", "VARCHAR(80)", text("vendor_name"), "Vendor name"),
        Col("trade", "VARCHAR(30)", vocab("trade", "trade"), "Main trade"),
        Col("rating", "CHAR(1)", code("rating"), "Current rating A, B or C"),
        Col("phone", "VARCHAR(20)", text("phone"), "Phone", null="NULL when missing"),
        Col("previous_rating", "CHAR(1)", code("previous_rating"), "Rating before the last change",
            null="NULL if never changed"),
        Col("rating_changed_on", "DATE", day("rating_changed_on"), "Date of the last change",
            null="NULL if never changed"),
    ]),  # fmt: skip
    Table("stg_maintenance_category", "brz_sla_policy", "S2", ["subcategory_code", "valid_from"],
          doc="One row per maintenance subcategory and SLA version (valid_from).", cols=[
        Col("subcategory_code", "VARCHAR(10)", code("subcategory_code"), "Subcategory key"),
        Col("subcategory_name", "VARCHAR(40)", text("subcategory_name"), "Subcategory"),
        Col("category_name", "VARCHAR(30)", vocab("ticket_category", "category_name"),
            "Plumbing, Electrical, HVAC, Civil, Pest control, Other"),
        Col("default_sla_hours", "SMALLINT", num("default_sla_hours", "smallint"), "SLA in hours"),
        Col("valid_from", "DATE", day("valid_from"), "First day of this SLA"),
    ]),  # fmt: skip
    Table("stg_holiday", "brz_holiday", "S2", ["holiday_date"], doc="One row per holiday or "
          "Ramadan day.", cols=[
        Col("holiday_date", "DATE", day("holiday_date"), "Day"),
        Col("holiday_name", "VARCHAR(40)", text("holiday_name"), "Holiday",
            null="NULL on a Ramadan day that is not a holiday"),
        Col("is_public_holiday", "BOOLEAN", boolean("is_public_holiday"), "Public holiday"),
        Col("is_ramadan", "BOOLEAN", boolean("is_ramadan"), "In Ramadan"),
    ]),  # fmt: skip
    Table("stg_ticket", "brz_ticket", "S4", ["ticket_id"],
          updated="(SELECT max(lue_audit.try_timestamp(s.status_at)) FROM "
                  "lue_staging.brz_ticket_status s WHERE s.loaded_at = b.loaded_at AND "
                  "s.source_file = b.source_file AND s.source_row = b.source_row)",
          where="EXISTS (SELECT 1 FROM lue_staging.brz_ticket_status s WHERE s.loaded_at = "
                "b.loaded_at AND s.source_file = b.source_file AND s.source_row = b.source_row AND "
                "lue_staging.std('ticket_status', s.status) = 'Raised' AND NOT EXISTS (SELECT 1 "
                "FROM lue_audit.dq_result r WHERE r.source_table = 'brz_ticket_status' AND "
                "r.row_id = s.row_id AND r.severity = 'reject'))",
          # A copy's status entries are the brz_ticket_status rows landed from the same file in
          # the same ingest step (same source_file, source_row and loaded_at; E3 lands the two
          # tables as two batches of one step).
          doc="One row per ticket: of two copies the one with the latest status time (D15). A "
              "ticket copy with no Raised entry that E4 accepted is not staged. The copy (src_file, "
              "src_row) is compared as a value: when another copy wins, the row is updated and "
              "its status history replaced.",
          extra_lineage=[Col("src_file", "VARCHAR(200)", "b.source_file", "File of the copy"),
                         Col("src_row", "INT", "b.source_row", "Position of the copy")],
          cols=[
        Col("ticket_id", "VARCHAR(14)", code("ticket_id"), "Ticket number"),
        Col("building_code", "VARCHAR(8)", code("building_code"), "Building"),
        Col("unit_no", "VARCHAR(10)", text("unit_no"), "Unit number"),
        Col("category", "VARCHAR(30)", vocab("ticket_category", "category"), "Category"),
        Col("subcategory_code", "VARCHAR(10)", code("subcategory_code"), "Subcategory"),
        Col("subcategory_name", "VARCHAR(40)", text("subcategory"), "Subcategory name"),
        Col("priority", "VARCHAR(10)", vocab("priority", "priority"), "Emergency, High or Normal"),
        Col("is_emergency", "BOOLEAN", "lue_staging.std('priority', b.priority) = 'Emergency'",
            "priority = Emergency (data dictionary)"),
        Col("source_is_recurring", "BOOLEAN", boolean("is_recurring"),
            "The app's own flag (90 days, US-2.5); see is_recurring"),
        Col("is_tenant_caused", "BOOLEAN", boolean("is_tenant_caused"), "Damage by the tenant"),
        Col("reported_via", "VARCHAR(20)", vocab("reported_via", "reported_via"), "Channel"),
        Col("description", "VARCHAR(200)", text("description"), "Description"),
        Col("vendor_code", "VARCHAR(10)", code("vendor_code"), "Vendor",
            null="NULL until assigned"),
        Col("estimated_cost", "NUMERIC(12,2)", num("estimate", "numeric(12,2)"), "Estimate (PKR)",
            null="NULL until assigned"),
        Col("actual_cost", "NUMERIC(12,2)", num("final_cost", "numeric(12,2)"), "Final cost (PKR)",
            null="NULL until resolved"),
        Col("status", "VARCHAR(12)", vocab("ticket_status", "status"), "Latest status"),
        Col("raised_at", "TIMESTAMP", "", "Raised (US-5.2)"),
        Col("assigned_at", "TIMESTAMP", "", "Assigned (US-5.2)", null="NULL until it happens"),
        Col("resolved_at", "TIMESTAMP", "", "Resolved (US-5.2)", null="NULL until it happens"),
        Col("verified_at", "TIMESTAMP", "", "Verified (US-5.2)", null="NULL until it happens"),
        Col("days_to_assign", "NUMERIC(6,2)", "", "assigned - raised in days (US-5.2)",
            null="NULL until assigned"),
        Col("days_to_resolve", "NUMERIC(6,2)", "", "resolved - raised in days (US-5.2)",
            null="NULL until resolved"),
        Col("days_to_verify", "NUMERIC(6,2)", "", "verified - resolved in days (US-5.2)",
            null="NULL until verified"),
        Col("hours_to_resolve", "NUMERIC(8,2)", "", "resolved - raised in hours (US-5.2)",
            null="NULL until resolved"),
        Col("sla_hours", "SMALLINT", "", "SLA in force on the raised date (US-5.2)",
            null="NULL if the subcategory has no SLA then"),
        Col("sla_breached", "BOOLEAN", "", "hours_to_resolve > sla_hours (US-5.2)",
            null="NULL until resolved"),
        Col("is_recurring", "BOOLEAN", "", f"Same unit and subcategory within {RECURRING_DAYS} "
            "days before (data dictionary; US-5.2)"),
    ]),  # fmt: skip
    Table("stg_ticket_status", "brz_ticket_status", "S4", ["ticket_id", "status_seq"],
          after="stg_ticket",
          doc="One row per status entry of the staged copy of each ticket.", cols=[
        Col("ticket_id", "VARCHAR(14)", code("ticket_id"), "Ticket"),
        Col("status_seq", "SMALLINT", "b.status_seq::smallint", "1 = first status"),
        Col("status", "VARCHAR(12)", vocab("ticket_status", "status"), "Status"),
        Col("status_at", "TIMESTAMP", stamp("status_at"), "When"),
        Col("vendor_code", "VARCHAR(10)", code("vendor_code"), "Vendor (on Assigned)",
            null="NULL except on Assigned"),
    ]),  # fmt: skip
    Table("stg_weather", "brz_weather", "S5", ["city", "weather_date"], doc="One row per city and "
          "day.", cols=[
        Col("city", "VARCHAR(30)", vocab("city", "city"), "City"),
        Col("weather_date", "DATE", day("weather_date"), "Day (Pakistan time)"),
        Col("max_temp_c", "NUMERIC(4,1)", num("max_temp_c", "numeric(4,1)"), "Maximum temperature",
            null="NULL when the API had no value"),
        Col("rainfall_mm", "NUMERIC(6,1)", num("rainfall_mm", "numeric(6,1)"), "Rainfall",
            null="NULL when the API had no value"),
    ]),  # fmt: skip
    Table("stg_incentive_offer", "brz_incentive_offer", "S6", ["offer_code"], doc="One row per "
          "offer in the catalogue.", cols=[
        Col("offer_code", "VARCHAR(10)", code("offer_code"), "Offer business key"),
        Col("offer_type", "VARCHAR(20)", vocab("offer_type", "offer_type"),
            "Rent-free days, Discount or Free maintenance"),
        Col("description", "VARCHAR(80)", text("description"), "Description"),
        Col("discount_pct", "NUMERIC(5,2)", f"coalesce({num('discount_pct', 'numeric(5,2)')}, 0)",
            "Discount, 0 if not a discount"),
        Col("rent_free_days", "SMALLINT", f"coalesce({num('rent_free_days', 'smallint')}, 0)",
            "Rent-free days, 0 if not rent-free"),
    ]),  # fmt: skip
    Table("stg_incentive_log", "brz_incentive_log", "S6",
          ["building_code", "unit_no", "offer_code", "start_date"],
          doc="One row per offer posted on a unit. A day-first date is read as such (repaired).",
          cols=[
        Col("building_code", "VARCHAR(8)", code("building_code"), "Building"),
        Col("unit_no", "VARCHAR(10)", text("unit_no"), "Unit number"),
        Col("offer_code", "VARCHAR(10)", code("offer_code"), "Offer"),
        Col("start_date", "DATE", day("start_date"), "First day posted"),
        Col("end_date", "DATE", day("end_date"), "Last day posted"),
    ]),  # fmt: skip
]
BY_NAME = {t.name: t for t in TABLES}
BY_BRONZE = {t.bronze: t for t in TABLES}
