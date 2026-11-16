"""US-5.2: the derived business fields, computed once in staging after every load.

Every derived column of etl/staging/spec.py is set here, by one UPDATE per table that changes a
row only when a derived value differs (so an unchanged rerun changes nothing, US-5.3), and stamps
run_id and staged_at on the rows it changes.

1. Allocation (where the source did not). A cleared payment whose staged S1 allocations add up to
   less than its amount (the source left it unallocated, or E4 rejected an allocation row) gets
   derived allocations for the rest: the tenant's lines with an open balance, of invoices issued
   on or before the paid date, oldest due date first (then invoice, then line), except that the
   open lines of an invoice the payment already pays in S1 come first: the source pays the lines
   of one invoice in line order (US-2.4), so a payment that lost one allocation row to E4 is
   completed on its own invoice before it reaches an older unpaid one. Never more than
   the payment's rest, never more than a line's balance (net minus everything allocated to it,
   by S1 or derived), never on a line the payment already has. Payments in paid order.
   A reversal (a bounced cheque: negative, reversal_of the original) whose S1 allocations add up
   to less than its amount (E4 rejected one) reverses the rest on the original payment's lines,
   in line order, never more than the original allocated to a line, never on a line it already
   reverses. Without it the line would look paid twice once the tenant pays again. Payments and
   reversals are taken together in paid order, so a reversal reopens its lines in time for the
   tenant's next payment.
2. days_past_due = paid date - due date (negative = early), for every allocation, reversals too.
3. Settlement match: an S3 line matches the S1 payment with its payment_reference. A payment's
   settlement is its matched line with the earliest settlement date. Unmatched settlement lines
   and unsettled electronic payments (cleared, electronic, no line) are flagged.
4. Lease term in months, ticket lifecycle (times, durations, SLA, breach), the 30-day recurrence
   flag (the data dictionary's rule; the app's own 90-day flag is kept as source_is_recurring).
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from etl.staging import spec

ZERO = Decimal("0.00")


@dataclass
class Business:
    changed: dict[str, int] = field(default_factory=dict)  # table -> rows whose derived values changed
    derived_inserted: int = 0
    derived_updated: int = 0
    derived_deleted: int = 0
    payments_derived: int = 0  # payments that got at least one derived allocation

    @property
    def total(self) -> int:
        return sum(self.changed.values())


# ----------------------------------------------------------------------------- 1. allocation
Key = tuple[str, str, int]  # (payment_reference, invoice_number, line_no)


def plan(positives, reversals, lines, s1_pairs, s1_of) -> dict[Key, Decimal]:
    """The derived allocations. Pure Python, so it is tested without a database.

    positives: [(payment_reference, tenant_code, paid_at, rest, invoices)]: rest > 0 to allocate;
               invoices: the invoice numbers the payment already pays in S1
    reversals: [(payment_reference, reversal_of, paid_at, rest)]: rest < 0 to reverse
    lines:     {tenant_code: [[due_date, invoice_date, invoice_number, line_no, balance], ...]}
               in due date, invoice, line order; balance after every S1 allocation (changed here)
    s1_pairs:  {(payment_reference, invoice_number, line_no)} that S1 already allocates
    s1_of:     {payment_reference: [(invoice_number, line_no, amount), ...]} S1's allocations of
               each payment that a reversal reverses
    Payments and reversals are taken together in paid order (then reference): a reversal puts
    its lines' balance back before a later payment (the tenant paying again) looks for it.
    Returns {(payment_reference, invoice_number, line_no): amount (negative for a reversal)}.
    """
    out: dict[Key, Decimal] = {}
    derived_of: dict[str, list] = defaultdict(list)
    index = {(ln[2], ln[3]): ln for tenant_lines in lines.values() for ln in tenant_lines}
    events = [(p[2], p[0], 0, p) for p in positives] + [(r[2], r[0], 1, r) for r in reversals]
    for _at, _ref, kind, event in sorted(events, key=lambda e: (e[0], e[1])):
        if kind == 0:
            ref, tenant, paid, rest, invoices = event
            day = paid.date() if isinstance(paid, datetime) else paid
            # Its own invoices first, then oldest due (the list is in due, invoice, line order).
            for line in sorted(lines.get(tenant, []), key=lambda x: x[2] not in invoices):
                if rest <= 0:
                    break
                _due, issued, number, line_no, balance = line
                if balance <= 0 or issued > day or (ref, number, line_no) in s1_pairs:
                    continue
                take = min(rest, balance)
                out[(ref, number, line_no)] = take
                derived_of[ref].append((number, line_no, take))
                line[4] = balance - take
                rest -= take
        else:
            ref, original, _paid, rest = event
            need = -rest
            for number, line_no, allocated in sorted(s1_of.get(original, []) + derived_of[original],
                                                     key=lambda x: (x[0], x[1])):  # fmt: skip
                if need <= 0:
                    break
                if allocated <= 0 or (ref, number, line_no) in s1_pairs:
                    continue
                take = min(need, allocated)
                out[(ref, number, line_no)] = -take
                if (line := index.get((number, line_no))) is not None:
                    line[4] += take  # the line is open again
                need -= take
    return out


def derive_allocations(cur, run_id: int, now: datetime, result: Business) -> None:
    s1_sum = ("LEFT JOIN (SELECT payment_reference, sum(allocated_amount) AS s1 FROM "
              "lue_staging.stg_payment_allocation WHERE allocation_source = 'S1' GROUP BY 1) a "
              "USING (payment_reference)")  # fmt: skip
    cur.execute(
        f"SELECT p.payment_reference, p.tenant_code, p.paid_at, p.amount - coalesce(a.s1, 0) "
        f"FROM lue_staging.stg_payment p {s1_sum} WHERE p.status = 'Cleared' AND p.reversal_of "
        f"IS NULL AND p.amount > 0 AND p.paid_at IS NOT NULL AND p.amount - coalesce(a.s1, 0) > 0"
    )
    due_payments = cur.fetchall()
    cur.execute(
        f"SELECT p.payment_reference, p.reversal_of, p.paid_at, p.amount - coalesce(a.s1, 0) "
        f"FROM lue_staging.stg_payment p {s1_sum} WHERE p.reversal_of IS NOT NULL AND p.amount "
        f"< 0 AND p.paid_at IS NOT NULL AND p.amount - coalesce(a.s1, 0) < 0"
    )
    reversals = cur.fetchall()
    cur.execute("SELECT payment_reference, invoice_number, line_no, allocated_amount FROM "
                "lue_staging.stg_payment_allocation WHERE allocation_source = 'S1'")  # fmt: skip
    s1_pairs = set()
    paid_invoices: dict[str, set] = defaultdict(set)
    s1_of: dict[str, list] = defaultdict(list)
    reversed_refs = {r[1] for r in reversals}
    for ref, number, line_no, amount in cur.fetchall():
        s1_pairs.add((ref, number, line_no))
        paid_invoices[ref].add(number)
        if ref in reversed_refs:
            s1_of[ref].append((number, line_no, amount))
    positives = [(*p, paid_invoices.get(p[0], set())) for p in due_payments]
    cur.execute(
        "SELECT l.tenant_code, i.due_date, i.invoice_date, il.invoice_number, il.line_no, "
        "il.net_amount - coalesce(a.s1, 0) FROM lue_staging.stg_invoice_line il "
        "JOIN lue_staging.stg_invoice i USING (invoice_number) "
        "JOIN lue_staging.stg_lease l USING (lease_number) "
        "LEFT JOIN (SELECT invoice_number, line_no, sum(allocated_amount) AS s1 FROM "
        "lue_staging.stg_payment_allocation WHERE allocation_source = 'S1' GROUP BY 1, 2) a "
        "USING (invoice_number, line_no) WHERE i.due_date IS NOT NULL AND i.invoice_date IS NOT "
        "NULL AND il.net_amount > 0 ORDER BY l.tenant_code, i.due_date, il.invoice_number, il.line_no"
    )
    lines: dict[str, list[list]] = defaultdict(list)
    for tenant, due, issued, number, line_no, balance in cur.fetchall():
        lines[tenant].append([due, issued, number, line_no, balance])
    want = plan(positives, reversals, lines, s1_pairs, s1_of)
    result.payments_derived = len({k[0] for k in want})
    cur.execute("SELECT payment_reference, invoice_number, line_no, allocated_amount FROM "
                "lue_staging.stg_payment_allocation WHERE allocation_source = 'derived'")  # fmt: skip
    have = {(r, n, ln): amt for r, n, ln, amt in cur.fetchall()}
    gone = [k for k in have if k not in want]
    new = [(*k, v) for k, v in want.items() if k not in have]
    moved = [(*k, v) for k, v in want.items() if k in have and have[k] != v]
    if gone:
        cur.execute("DELETE FROM lue_staging.stg_payment_allocation WHERE allocation_source = "
                    "'derived' AND (payment_reference, invoice_number, line_no) IN (SELECT * FROM "
                    "unnest(%s::text[], %s::text[], %s::int[]))",
                    ([k[0] for k in gone], [k[1] for k in gone], [k[2] for k in gone]))  # fmt: skip
    if new:
        # Lineage of a derived row: no bronze row; source_system S1 (from S1's payment), the run.
        cur.execute(
            "INSERT INTO lue_staging.stg_payment_allocation (payment_reference, invoice_number, "
            "line_no, allocated_amount, allocation_source, source_system, batch_id, loaded_at, "
            "src_row_id, src_updated_at, run_id, staged_at) SELECT r, n, ln, a, 'derived', 'S1', "
            "NULL, NULL, NULL, NULL, %s, %s FROM unnest(%s::text[], %s::text[], %s::int[], "
            "%s::numeric[]) AS x(r, n, ln, a)",
            (run_id, now, [k[0] for k in new], [k[1] for k in new], [k[2] for k in new],
             [k[3] for k in new]),
        )  # fmt: skip
    if moved:
        cur.execute(
            "UPDATE lue_staging.stg_payment_allocation s SET allocated_amount = x.a, run_id = %s, "
            "staged_at = %s FROM unnest(%s::text[], %s::text[], %s::int[], %s::numeric[]) AS "
            "x(r, n, ln, a) WHERE s.allocation_source = 'derived' AND s.payment_reference = x.r "
            "AND s.invoice_number = x.n AND s.line_no = x.ln",
            (run_id, now, [k[0] for k in moved], [k[1] for k in moved], [k[2] for k in moved],
             [k[3] for k in moved]),
        )  # fmt: skip
    result.derived_inserted, result.derived_updated, result.derived_deleted = (
        len(new), len(moved), len(gone))  # fmt: skip


# ----------------------------------------------------------------------------- 2. to 4.
# table -> SQL of a SELECT giving the key columns and the derived values (named as the columns).
DERIVED = {
    "stg_lease": """
        SELECT lease_number,
               CASE WHEN start_date IS NOT NULL AND end_date >= start_date THEN
                    (date_part('year', age(end_date + 1, start_date)) * 12
                     + date_part('month', age(end_date + 1, start_date)))::smallint END AS term_months
        FROM lue_staging.stg_lease""",
    "stg_invoice_line": """
        SELECT il.invoice_number, il.line_no, i.due_date,
               coalesce(a.total, 0)::numeric(12,2) AS allocated_amount,
               (il.net_amount - coalesce(a.total, 0))::numeric(12,2) AS open_balance
        FROM lue_staging.stg_invoice_line il
        LEFT JOIN lue_staging.stg_invoice i USING (invoice_number)
        LEFT JOIN (SELECT invoice_number, line_no, sum(allocated_amount) AS total
                   FROM lue_staging.stg_payment_allocation GROUP BY 1, 2) a USING (invoice_number, line_no)""",
    "stg_payment": """
        SELECT p.payment_reference,
               coalesce(p.status = 'Bounced', false) AS is_reversal,
               coalesce(m.is_electronic, false) AS is_electronic,
               coalesce(a.total, 0)::numeric(12,2) AS allocated_amount,
               s.settlement_id, s.settlement_date,
               (s.settlement_date - p.paid_at::date)::smallint AS settlement_lag_days,
               (coalesce(m.is_electronic, false) AND p.status = 'Cleared'
                AND s.settlement_id IS NULL) AS is_unsettled
        FROM lue_staging.stg_payment p
        LEFT JOIN lue_staging.payment_method m USING (method_code)
        LEFT JOIN (SELECT payment_reference, sum(allocated_amount) AS total
                   FROM lue_staging.stg_payment_allocation GROUP BY 1) a USING (payment_reference)
        LEFT JOIN (SELECT DISTINCT ON (payment_reference) payment_reference, settlement_id,
                          settlement_date
                   FROM lue_staging.stg_settlement
                   ORDER BY payment_reference, settlement_date NULLS LAST, channel, settlement_id) s
               USING (payment_reference)""",
    "stg_payment_allocation": """
        SELECT a.payment_reference, a.invoice_number, a.line_no, p.paid_at, i.due_date,
               (p.paid_at::date - i.due_date)::smallint AS days_past_due,
               coalesce(p.status = 'Bounced', false) AS is_reversal
        FROM lue_staging.stg_payment_allocation a
        LEFT JOIN lue_staging.stg_payment p USING (payment_reference)
        LEFT JOIN lue_staging.stg_invoice i USING (invoice_number)""",
    "stg_settlement": """
        SELECT s.channel, s.settlement_id, p.payment_reference IS NOT NULL AS is_matched,
               (s.settlement_date - p.paid_at::date)::smallint AS settlement_lag_days
        FROM lue_staging.stg_settlement s
        LEFT JOIN lue_staging.stg_payment p USING (payment_reference)""",
    "stg_ticket": f"""
        WITH life AS (
            SELECT ticket_id,
                   min(status_at) FILTER (WHERE status = 'Raised') AS raised_at,
                   min(status_at) FILTER (WHERE status = 'Assigned') AS assigned_at,
                   min(status_at) FILTER (WHERE status = 'Resolved') AS resolved_at,
                   min(status_at) FILTER (WHERE status = 'Verified') AS verified_at
            FROM lue_staging.stg_ticket_status GROUP BY ticket_id),
        t AS (
            SELECT k.ticket_id, k.building_code, k.unit_no, k.subcategory_code, l.raised_at,
                   l.assigned_at, l.resolved_at, l.verified_at
            FROM lue_staging.stg_ticket k LEFT JOIN life l USING (ticket_id))
        SELECT t.ticket_id, t.raised_at, t.assigned_at, t.resolved_at, t.verified_at,
               round(extract(epoch FROM t.assigned_at - t.raised_at) / 86400, 2)::numeric(6,2) AS days_to_assign,
               round(extract(epoch FROM t.resolved_at - t.raised_at) / 86400, 2)::numeric(6,2) AS days_to_resolve,
               round(extract(epoch FROM t.verified_at - t.resolved_at) / 86400, 2)::numeric(6,2) AS days_to_verify,
               round(extract(epoch FROM t.resolved_at - t.raised_at) / 3600, 2)::numeric(8,2) AS hours_to_resolve,
               sla.default_sla_hours AS sla_hours,
               (extract(epoch FROM t.resolved_at - t.raised_at) / 3600 > sla.default_sla_hours) AS sla_breached,
               EXISTS (SELECT 1 FROM t o WHERE o.ticket_id <> t.ticket_id
                       AND o.building_code = t.building_code AND o.unit_no = t.unit_no
                       AND o.subcategory_code = t.subcategory_code
                       AND o.raised_at < t.raised_at
                       AND o.raised_at >= t.raised_at - interval '{spec.RECURRING_DAYS} days') AS is_recurring
        FROM t
        LEFT JOIN LATERAL (SELECT c.default_sla_hours FROM lue_staging.stg_maintenance_category c
                           WHERE c.subcategory_code = t.subcategory_code
                             AND c.valid_from <= t.raised_at::date
                           ORDER BY c.valid_from DESC LIMIT 1) sla ON true""",
}
# The order matters: allocations first (step 1), then lines and payments that sum them, then the
# matches and durations.
ORDER = ["stg_lease", "stg_payment_allocation", "stg_invoice_line", "stg_payment",
         "stg_settlement", "stg_ticket"]  # fmt: skip


def update_sql(table: str) -> str:
    t = spec.BY_NAME[table]
    derived = [c.name for c in t.derived]
    match = " AND ".join(f"s.{k} = d.{k}" for k in t.key)
    return (
        f"UPDATE lue_staging.{table} s SET "
        + ", ".join(f"{c} = d.{c}" for c in derived)
        + f", run_id = %(run)s, staged_at = %(now)s FROM ({DERIVED[table]}) d WHERE {match} AND "
        f"({', '.join('s.' + c for c in derived)}) IS DISTINCT FROM "
        f"({', '.join('d.' + c for c in derived)})"
    )


def apply(cur, run_id: int, now: datetime) -> Business:
    result = Business()
    derive_allocations(cur, run_id, now, result)
    for table in ORDER:
        cur.execute(update_sql(table), {"run": run_id, "now": now})
        result.changed[table] = cur.rowcount
    return result
