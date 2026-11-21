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

from etl.facts.keys import DATA_WINDOW, date_key, key, owner, plain, scd2


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
    # A periodic snapshot (US-7.3) is loaded month by month: `period` names its date key column and
    # the source takes %(first)s and %(last)s, the days of one month of keys.DATA_WINDOW.
    period: str | None = None
    refresh_days: int = 0  # the last n days of the window are deleted and re-derived every run (D14)
    prepare: list[str] = field(default_factory=list)  # SQL run once before the source (temp tables)
    resolved: list[str] = field(default_factory=list)  # keys in the primary key: -1 is refused

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
    # US-7.3: every unit on every day of the data window, occupied or vacant. The lease active that
    # day (start_date <= day <= end_date; end_date is the actual end, a termination included), and
    # its arrears from _occ_balance: per lease, a line's net counts from the day after it is due and
    # a payment against it from the later of that day and the paid date, summed with a window
    # function, so a day's balance is a range lookup (never a correlated subquery).
    Fact("fact_unit_occupancy_daily", ["snapshot_date_key", "unit_key"], story="US-7.3",
         staging=["stg_unit", "stg_lease", "stg_invoice_line", "stg_invoice", "stg_payment_allocation", "stg_ownership"],
         period="snapshot_date_key", refresh_days=35, resolved=["unit_key"], required=["contract_rent"],
         cols=["snapshot_date_key", "unit_key", "tenant_key", "lease_key", "owner_key", "is_occupied",
               "contract_rent", "current_lease_arrears"],
         monthly=("unit-days = units x days",
                  "SELECT to_char(d.full_date, 'YYYY-MM') AS month, count(*) AS amount FROM lue_dw.fact_unit_occupancy_daily f "
                  "JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key GROUP BY 1",
                  "SELECT to_char(d.full_date, 'YYYY-MM') AS month, count(*) * (SELECT count(*) FROM lue_staging.stg_unit) AS amount "
                  f"FROM lue_dw.dim_date d WHERE d.full_date BETWEEN DATE '{DATA_WINDOW[0]}' AND DATE '{DATA_WINDOW[1]}' GROUP BY 1"),
         prepare=[
             # 36 month-sized queries: JIT compilation costs more than it saves (about 0.8 s each)
             "SET LOCAL jit = off",
             "DROP TABLE IF EXISTS _occ_balance",
             """CREATE TEMP TABLE _occ_balance ON COMMIT DROP AS
             WITH line AS (SELECT il.invoice_number, il.line_no, i.lease_number, coalesce(il.due_date, i.due_date) AS due_date, il.net_amount
                           FROM lue_staging.stg_invoice_line il JOIN lue_staging.stg_invoice i USING (invoice_number)),
                  change AS (SELECT lease_number, due_date + 1 AS day, net_amount AS delta FROM line
                             UNION ALL
                             SELECT l.lease_number, greatest(l.due_date + 1, a.paid_at::date), -a.allocated_amount
                             FROM lue_staging.stg_payment_allocation a JOIN line l ON l.invoice_number = a.invoice_number AND l.line_no = a.line_no),
                  per_day AS (SELECT lease_number, day, sum(delta) AS delta FROM change GROUP BY 1, 2)
             SELECT lease_number, day AS from_day, coalesce(lead(day) OVER w, DATE '9999-12-31') AS to_day,
                    sum(delta) OVER w AS balance
             FROM per_day WINDOW w AS (PARTITION BY lease_number ORDER BY day)""",
             "ANALYZE _occ_balance",
         ],
         source=f"""
        SELECT {date_key('g.day')} AS snapshot_date_key,
               {key('du', 'unit_key')} AS unit_key,
               CASE WHEN sl.lease_number IS NULL THEN -2 ELSE {key('dt', 'tenant_key')} END AS tenant_key,
               CASE WHEN sl.lease_number IS NULL THEN -2 ELSE {key('dl', 'lease_key')} END AS lease_key,
               {key('dw', 'owner_key')} AS owner_key,
               (sl.lease_number IS NOT NULL)::int::smallint AS is_occupied,
               CASE WHEN sl.lease_number IS NULL THEN 0 ELSE sl.monthly_rent END AS contract_rent,
               CASE WHEN sl.lease_number IS NULL THEN 0 ELSE coalesce(b.balance, 0) END AS current_lease_arrears,
               'S1' AS source_system
        FROM lue_staging.stg_unit su
        CROSS JOIN LATERAL (SELECT s::date AS day FROM generate_series(%(first)s::date, %(last)s::date, interval '1 day') s) g
        LEFT JOIN lue_staging.stg_lease sl ON sl.unit_id = su.unit_id AND g.day BETWEEN sl.start_date AND sl.end_date
        LEFT JOIN _occ_balance b ON b.lease_number = sl.lease_number AND g.day >= b.from_day AND g.day < b.to_day
        {scd2('dim_unit', 'du', UNIT_NK, 'g.day')}
        {scd2('dim_tenant', 'dt', 'sl.tenant_code', 'g.day')}
        {plain('dim_lease', 'dl', 'sl.lease_number')}
        {owner('dw', 'su.building_code', 'su.unit_no', 'g.day')}"""),
]  # fmt: skip
BY_NAME = {f.name: f for f in FACTS}
