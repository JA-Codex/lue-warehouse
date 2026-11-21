"""E7: the facts as data, in load order. One loader (etl/facts/load.py) reads this.

Per fact: its table in lue_dw, the columns of its grain (the natural key the loader matches on),
and one SQL query over staging and the dimensions that gives exactly one row per grain with every
fact column. Keys are resolved by etl/facts/keys.py: point in time for the SCD2 dimensions (the
version valid on the event date), the owner from the ownership register on that date, -1 for a key
that cannot be resolved (counted), -2 where a role does not apply (a milestone not reached yet).

`required` names columns that must have a value for a row to load (a measure the fact cannot hold
as NULL); a source row without one is counted as rejected and not loaded, never dropped silently.

`monthly` reconciles the loaded fact to staging by month (US-7.2): a label, then two queries giving
(month 'YYYY-MM', amount), one over the fact (its date through dim_date) and one over staging. The
loader writes one row per month to lue_audit.reconciliation; a month that differs is a Warning.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass, field

from etl.facts.keys import date_key, key, owner, plain, scd2


@dataclass
class Fact:
    name: str
    grain: list[str]  # fact columns that identify one row (matched on by the loader)
    source: str  # SQL: one row per grain, every column of cols, and source_system
    cols: list[str]  # fact columns written (keys, degenerate dimensions, measures)
    story: str
    required: list[str] = field(default_factory=list)  # a row without one of these is rejected
    staging: list[str] = field(default_factory=list)  # staging tables read (lineage)
    monthly: tuple[str, str, str] | None = None  # (label, fact query, staging query): month, amount

    @property
    def keys(self) -> list[str]:
        return [c for c in self.cols if c.endswith("_key")]


# The unit, lease and owner of an invoice line, the shared path of the invoice and payment facts.
UNIT_NK = "su.building_code || '-' || su.unit_no"


def by_month(table: str, date_key: str, amount: str) -> str:
    """A fact's amount per month of one of its role-playing dates (through dim_date)."""
    return (f"SELECT to_char(d.full_date, 'YYYY-MM') AS month, sum(f.{amount}) AS amount FROM lue_dw.{table} f "
            f"JOIN lue_dw.dim_date d ON d.date_key = f.{date_key} GROUP BY 1")  # fmt: skip


FACTS = [
    Fact("fact_rent_invoice_line", ["invoice_number", "invoice_line_no"], story="US-7.2",
         staging=["stg_invoice_line", "stg_invoice", "stg_lease", "stg_unit", "stg_ownership"],
         required=["billed_amount", "tax_amount", "discount_amount", "net_amount"],
         cols=["invoice_date_key", "due_date_key", "unit_key", "tenant_key", "lease_key", "owner_key",
               "charge_type_key", "invoice_number", "invoice_line_no", "billed_amount", "tax_amount",
               "discount_amount", "net_amount"],
         monthly=("net amount by invoice month",
                  by_month("fact_rent_invoice_line", "invoice_date_key", "net_amount"),
                  "SELECT to_char(i.invoice_date, 'YYYY-MM') AS month, sum(il.net_amount) AS amount "
                  "FROM lue_staging.stg_invoice_line il JOIN lue_staging.stg_invoice i USING (invoice_number) GROUP BY 1"),
         source=f"""
        SELECT {date_key('i.invoice_date')} AS invoice_date_key,
               {date_key('coalesce(il.due_date, i.due_date)')} AS due_date_key,
               {key('du', 'unit_key')} AS unit_key,
               {key('dt', 'tenant_key')} AS tenant_key,
               {key('dl', 'lease_key')} AS lease_key,
               {key('dw', 'owner_key')} AS owner_key,
               {key('dc', 'charge_type_key')} AS charge_type_key,
               il.invoice_number, il.line_no AS invoice_line_no,
               il.billed_amount, il.tax_amount, il.discount_amount, il.net_amount,
               'S1' AS source_system
        FROM lue_staging.stg_invoice_line il
        LEFT JOIN lue_staging.stg_invoice i ON i.invoice_number = il.invoice_number
        LEFT JOIN lue_staging.stg_lease sl ON sl.lease_number = i.lease_number
        LEFT JOIN lue_staging.stg_unit su ON su.unit_id = sl.unit_id
        {scd2('dim_unit', 'du', UNIT_NK, 'i.invoice_date')}
        {scd2('dim_tenant', 'dt', 'sl.tenant_code', 'i.invoice_date')}
        {plain('dim_lease', 'dl', 'i.lease_number')}
        {owner('dw', 'su.building_code', 'su.unit_no', 'i.invoice_date')}
        {plain('dim_charge_type', 'dc', 'il.charge_code')}"""),
    Fact("fact_payment", ["payment_reference", "invoice_number", "invoice_line_no"], story="US-7.1",
         staging=["stg_payment_allocation", "stg_payment", "stg_invoice_line", "stg_invoice", "stg_lease", "stg_unit", "stg_ownership"],
         required=["payment_amount", "days_past_due", "is_reversal"],
         monthly=("paid amount by paid month",
                  by_month("fact_payment", "paid_date_key", "payment_amount"),
                  "SELECT to_char(paid_at, 'YYYY-MM') AS month, sum(allocated_amount) AS amount "
                  "FROM lue_staging.stg_payment_allocation GROUP BY 1"),
         cols=["paid_date_key", "due_date_key", "unit_key", "tenant_key", "lease_key", "owner_key",
               "payment_method_key", "charge_type_key", "payment_reference", "invoice_number",
               "invoice_line_no", "payment_amount", "days_past_due", "settlement_lag_days", "is_reversal"],
         source=f"""
        SELECT {date_key('p.paid_at')} AS paid_date_key,
               {date_key('il.due_date')} AS due_date_key,
               {key('du', 'unit_key')} AS unit_key,
               {key('dt', 'tenant_key')} AS tenant_key,
               {key('dl', 'lease_key')} AS lease_key,
               {key('dw', 'owner_key')} AS owner_key,
               {key('dm', 'payment_method_key')} AS payment_method_key,
               {key('dc', 'charge_type_key')} AS charge_type_key,
               a.payment_reference, a.invoice_number, a.line_no AS invoice_line_no,
               a.allocated_amount AS payment_amount, a.days_past_due, p.settlement_lag_days,
               a.is_reversal, 'S1' AS source_system
        FROM lue_staging.stg_payment_allocation a
        JOIN lue_staging.stg_payment p USING (payment_reference)
        LEFT JOIN lue_staging.stg_invoice_line il ON il.invoice_number = a.invoice_number AND il.line_no = a.line_no
        LEFT JOIN lue_staging.stg_invoice i ON i.invoice_number = a.invoice_number
        LEFT JOIN lue_staging.stg_lease sl ON sl.lease_number = i.lease_number
        LEFT JOIN lue_staging.stg_unit su ON su.unit_id = sl.unit_id
        {scd2('dim_unit', 'du', UNIT_NK, 'p.paid_at')}
        {scd2('dim_tenant', 'dt', 'p.tenant_code', 'p.paid_at')}
        {plain('dim_lease', 'dl', 'i.lease_number')}
        {owner('dw', 'su.building_code', 'su.unit_no', 'p.paid_at')}
        {plain('dim_payment_method', 'dm', 'p.method_code')}
        {plain('dim_charge_type', 'dc', 'il.charge_code')}"""),
]  # fmt: skip
BY_NAME = {f.name: f for f in FACTS}
