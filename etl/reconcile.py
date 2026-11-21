#!/usr/bin/env python3
"""Source-to-warehouse reconciliation, DQ-07 (US-8.2): python etl/reconcile.py

By month, for each measure: source = warehouse + quarantined. The quarantined rows are the
reconciling item: a row rejected by a quality rule (E4) explains a difference only when its key
never reached staging, so a rejected row that was loaded anyway cannot hide a gap. What is left,
source - warehouse - quarantined, is the unexplained variance; it must be 0 in every month.

  billed        net amount of the invoice lines by invoice month: src_pms against fact_rent_invoice_line
  paid          cash received by paid month: src_pms payments against fact_payment (staging allocates
                every payment, re-deriving the allocations E4 rejected, US-5.2)
  tickets       requests by raised month: the S4 file (as landed in bronze, which equals the file,
                US-3.4) against fact_maintenance_request; a ticket is one request number however many
                copies the file has, and its raised date is its "Raised" status entry
  lease events  events by event month: src_pms against fact_lease_event

The month is the source's own date (a date outside the window, as planted, keeps its month; a
missing date is 'none'). lue_audit.reconciliation (the frozen pack's table) gets one row per measure
and month: source_value = source, warehouse_value = warehouse + quarantined (accounted for),
difference = the unexplained variance, passed = 0 variance. In the pipeline this is the reconcile
step, after the facts; any unexplained variance fails it. Exit 1 then, 0 when all months pass.
"""

# ruff: noqa: E501  (SQL text and the result table: long lines read better)

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.ingest.base import IngestError, Run  # noqa: E402

STEP = "reconcile_dq07"
MONTH = "CASE WHEN {x} ~ '^\\d{{4}}-\\d{{2}}' THEN left({x}, 7) ELSE 'none' END"  # a raw text date's month
NUM = "CASE WHEN {x} ~ '^-?\\d+(\\.\\d+)?$' THEN ({x})::numeric ELSE 0 END"  # a raw text amount, or 0


def _rec(field: str) -> str:
    """A field of the quarantined row's JSON copy, as text."""
    return f"(q.record->>'{field}')"


def _fact_month(key: str) -> str:
    return f"CASE WHEN {key} > 0 THEN left({key}::text, 4) || '-' || substr({key}::text, 5, 2) ELSE 'none' END"


@dataclass(frozen=True)
class Measure:
    name: str
    label: str
    source_db: str  # "source" (lue_source) or "warehouse" (bronze, the landed copy of a file)
    source: str  # SQL: month, value
    warehouse: str  # SQL: month, value
    quarantined: str  # SQL: month, value (rejected rows whose key never reached staging)


MEASURES = [
    Measure("billed", "net amount by invoice month", "source",
            "SELECT coalesce(to_char(i.invoice_date, 'YYYY-MM'), 'none'), sum(il.net_amount) FROM src_pms.invoice_lines il "
            "LEFT JOIN src_pms.invoices i USING (invoice_number) GROUP BY 1",
            f"SELECT {_fact_month('invoice_date_key')}, sum(net_amount) FROM lue_dw.fact_rent_invoice_line GROUP BY 1",
            f"SELECT {MONTH.format(x='h.invoice_date')}, sum({NUM.format(x=_rec('net_amount'))}) "
            "FROM lue_audit.quarantine q "
            "LEFT JOIN (SELECT DISTINCT ON (invoice_number) invoice_number, invoice_date FROM lue_staging.brz_invoice ORDER BY invoice_number, row_id DESC) h "
            "ON h.invoice_number = q.record->>'invoice_number' "
            "WHERE q.source_table = 'brz_invoice_line' AND NOT EXISTS (SELECT 1 FROM lue_staging.stg_invoice_line s "
            "WHERE s.invoice_number = q.record->>'invoice_number' AND s.line_no::text = q.record->>'line_no') GROUP BY 1"),
    Measure("paid", "cash received by paid month", "source",
            "SELECT coalesce(to_char(paid_at, 'YYYY-MM'), 'none'), sum(amount) FROM src_pms.payments GROUP BY 1",
            f"SELECT {_fact_month('paid_date_key')}, sum(payment_amount) FROM lue_dw.fact_payment GROUP BY 1",
            f"SELECT {MONTH.format(x=_rec('paid_at'))}, sum({NUM.format(x=_rec('amount'))}) "
            "FROM lue_audit.quarantine q WHERE q.source_table = 'brz_payment' AND NOT EXISTS (SELECT 1 FROM lue_staging.stg_payment s "
            "WHERE s.payment_reference = q.record->>'payment_reference') GROUP BY 1"),
    Measure("tickets", "requests by raised month", "warehouse",
            "WITH r AS (SELECT ticket_id, min(status_at) AS raised FROM lue_staging.brz_ticket_status WHERE status = 'Raised' GROUP BY 1) "
            f"SELECT {MONTH.format(x='r.raised')}, count(*) FROM (SELECT DISTINCT ticket_id FROM lue_staging.brz_ticket) t "
            "LEFT JOIN r USING (ticket_id) GROUP BY 1",
            f"SELECT {_fact_month('raised_date_key')}, count(*) FROM lue_dw.fact_maintenance_request GROUP BY 1",
            "WITH r AS (SELECT ticket_id, min(status_at) AS raised FROM lue_staging.brz_ticket_status WHERE status = 'Raised' GROUP BY 1), "
            "q AS (SELECT DISTINCT q.record->>'ticket_id' AS ticket_id FROM lue_audit.quarantine q WHERE q.source_table IN ('brz_ticket', 'brz_ticket_status')) "
            f"SELECT {MONTH.format(x='r.raised')}, count(*) FROM (SELECT DISTINCT ticket_id FROM lue_staging.brz_ticket) t "
            "JOIN q USING (ticket_id) LEFT JOIN r USING (ticket_id) "
            "WHERE NOT EXISTS (SELECT 1 FROM lue_staging.stg_ticket s WHERE s.ticket_id = t.ticket_id) GROUP BY 1"),
    Measure("lease events", "events by event month", "source",
            "SELECT coalesce(to_char(event_date, 'YYYY-MM'), 'none'), count(*) FROM src_pms.lease_events GROUP BY 1",
            f"SELECT {_fact_month('event_date_key')}, sum(event_count) FROM lue_dw.fact_lease_event GROUP BY 1",
            f"SELECT {MONTH.format(x=_rec('event_date'))}, count(*) FROM lue_audit.quarantine q "
            "WHERE q.source_table = 'brz_lease_event' AND NOT EXISTS (SELECT 1 FROM lue_staging.stg_lease_event s "
            "WHERE s.event_id::text = q.record->>'event_id') GROUP BY 1"),
]  # fmt: skip
BY_NAME = {m.name: m for m in MEASURES}


@dataclass
class Line:
    measure: str
    month: str
    source: Decimal
    warehouse: Decimal
    quarantined: Decimal

    @property
    def variance(self) -> Decimal:
        """Unexplained: source - warehouse - quarantined (must be 0)."""
        return self.source - self.warehouse - self.quarantined

    @property
    def check_name(self) -> str:
        return f"DQ-07 {self.measure} {self.month}"


def _rows(cur, sql: str) -> dict[str, Decimal]:
    cur.execute(sql)
    return {m: Decimal(v or 0) for m, v in cur.fetchall()}


def reconcile(wh_cur, src_cur, measures: list[Measure] = MEASURES) -> list[Line]:
    """Every measure and month that either side has, ordered by measure, then month."""
    out = []
    for m in measures:
        source = _rows(src_cur if m.source_db == "source" else wh_cur, m.source)
        warehouse, quarantined = _rows(wh_cur, m.warehouse), _rows(wh_cur, m.quarantined)
        for month in sorted(set(source) | set(warehouse) | set(quarantined)):
            out.append(Line(m.name, month, source.get(month, Decimal(0)), warehouse.get(month, Decimal(0)),
                            quarantined.get(month, Decimal(0))))  # fmt: skip
    return out


def record(audit_cur, run_id: int, lines: list[Line]) -> None:
    """One row per measure and month in lue_audit.reconciliation (see the module docstring)."""
    audit_cur.executemany(
        "INSERT INTO lue_audit.reconciliation (run_id, check_name, source_value, warehouse_value, difference, passed) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        [(run_id, x.check_name[:60], x.source, x.warehouse + x.quarantined, -x.variance, x.variance == 0) for x in lines],
    )


class ReconciliationError(Exception):
    """Source and warehouse differ by more than the quarantined rows explain."""


def step(box: dict):
    """The pipeline's reconcile step: rows on the audit connection (they stay if the step fails)."""

    def run(s) -> None:
        src = s.run.source_connection()
        try:
            with src.cursor() as src_cur:
                lines = reconcile(s.cur, src_cur)
        finally:
            src.close()
        with s.run.audit.cursor() as audit:
            record(audit, s.run.run_id, lines)
        box[STEP] = lines
        s.result.rows_read = len(lines)
        off = [x for x in lines if x.variance]
        if off:
            raise ReconciliationError(f"unexplained variance in {len(off)} of {len(lines)} measure-months: "
                                      + "; ".join(f"{x.measure} {x.month} {x.variance:,}" for x in off[:5]))  # fmt: skip

    return run


def summary(lines: list[Line]) -> list[tuple]:
    """Per measure: months, source, warehouse, quarantined, unexplained, months off."""
    out = []
    for m in MEASURES:
        ls = [x for x in lines if x.measure == m.name]
        out.append((m.name, m.label, len(ls), sum(x.source for x in ls), sum(x.warehouse for x in ls),
                    sum(x.quarantined for x in ls), sum(x.variance for x in ls), sum(1 for x in ls if x.variance)))  # fmt: skip
    return out


def print_summary(lines: list[Line]) -> None:
    line = "=" * 118
    print(line)
    print(f"  {'measure':13} {'months':>6} {'source':>20} {'warehouse':>20} {'quarantined':>16} {'unexplained':>14} {'months off':>10}")
    for name, _label, n, s, w, q, v, off in summary(lines):
        print(f"  {name:13} {n:>6} {s:>20,.2f} {w:>20,.2f} {q:>16,.2f} {v:>14,.2f} {off:>10}")
    print(line)


def main(argv: list[str] | None = None) -> int:
    try:
        r = Run()
    except IngestError as exc:
        print(f"[FAIL] {exc}")
        return 2
    box: dict = {}
    try:
        result = r.step(STEP, "DW", step(box))
        print(f" Reconciliation run {r.run_id} (DQ-07: source = warehouse + quarantined, by month)")
        lines = box.get(STEP, [])
        print_summary(lines)
        for x in lines:
            if x.variance:
                print(f"  [FAIL] {x.measure} {x.month}: source {x.source:,} warehouse {x.warehouse:,} quarantined {x.quarantined:,} unexplained {x.variance:,}")
        print(f" RESULT: {result.status}: {sum(1 for x in lines if not x.variance)}/{len(lines)} measure-months reconcile")
        return 0 if result.status != "Failed" else 1
    finally:
        r.close()


if __name__ == "__main__":
    sys.exit(main())
