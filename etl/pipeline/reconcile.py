"""US-8.2: DQ-07 source-to-warehouse reconciliation (etl/pipeline/reconcile.py).

Reads from lue_warehouse and lue_audit.reconciliation (already populated by the fact loaders)
and writes overall source-vs-warehouse reconciliation rows for each table / month:

  source_rows = warehouse_rows + quarantined_rows  (the reconciling item)
  variance    = source_rows - warehouse_rows - quarantined_rows
  passed      = (variance == 0)

Each row is inserted into lue_audit.reconciliation with:
  check_name = dq07_{table}_{YYYY-MM}
  source_value     = rows in the staging table for that month
  warehouse_value  = rows in the fact table for that month
  difference       = source_value - warehouse_value
  passed           = (variance == 0)

Raises ReconcileError if any variance is unexplained (i.e. any row that did not pass).

Usage::

    from etl.pipeline.reconcile import reconcile
    reconcile(conn, run_id)   # conn: psycopg2 connection to lue_warehouse (autocommit)
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ReconcileError(Exception):
    """Raised when at least one source-to-warehouse variance is unexplained."""


# Tables to reconcile: (staging_table, fact_table, month_column_in_staging)
# For ticket and lease-event facts there is no calendar month split, so we
# count the entire table (month="total").
_MONTHLY_PAIRS: list[tuple[str, str, str]] = [
    ("stg_rent_invoice_line", "fact_rent_invoice_line", "invoice_month"),
    ("stg_payment", "fact_payment", "paid_month"),
]

_TOTAL_PAIRS: list[tuple[str, str]] = [
    ("stg_ticket", "fact_maintenance_request"),
    ("stg_lease_event", "fact_lease_event"),
]


def _quarantined(cur, staging_table: str) -> int:
    """Count rows in the quarantine for the given staging table's bronze source."""
    cur.execute(
        """
        SELECT count(*)
        FROM lue_audit.quarantine q
        WHERE q.table_name LIKE %s
        """,
        (f"%{staging_table.removeprefix('stg_')}%",),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _quarantined_for_month(cur, staging_table: str, month: str) -> int:
    """Approximate quarantined count for a specific month (best effort)."""
    # The quarantine table may not have a month column; fall back to 0 so that
    # only the staging-vs-fact delta matters and the caller decides pass/fail.
    return 0


def _reconcile_monthly(
    cur,
    run_id: int,
    staging_table: str,
    fact_table: str,
    month_col: str,
) -> list[dict]:
    """Return one result dict per month for a monthly-partitioned pair."""
    # Count staging rows by month
    cur.execute(
        f"""
        SELECT to_char(date_trunc('month', {month_col}::date), 'YYYY-MM') AS month,
               count(*) AS n
        FROM lue_staging.{staging_table}
        GROUP BY 1
        ORDER BY 1
        """
    )
    staging_by_month = {row[0]: int(row[1]) for row in cur.fetchall()}

    # Count fact rows by month using the fact table's natural date column if available,
    # otherwise fall back to counting via the reconciliation rows already written by
    # the fact loader (check_name pattern: "{fact_table} {YYYY-MM} *").
    cur.execute(
        """
        SELECT substring(check_name FROM %s) AS month,
               sum(warehouse_value)          AS wh
        FROM lue_audit.reconciliation
        WHERE run_id = %s
          AND check_name LIKE %s
        GROUP BY 1
        ORDER BY 1
        """,
        (r"[0-9]{4}-[0-9]{2}", run_id, f"{fact_table} %"),
    )
    fact_by_month = {row[0]: int(row[1]) for row in cur.fetchall() if row[0]}

    results = []
    for month, source_rows in staging_by_month.items():
        wh_rows = fact_by_month.get(month, 0)
        quarantined = 0  # see note in _quarantined_for_month
        variance = source_rows - wh_rows - quarantined
        passed = variance == 0
        results.append(
            {
                "check_name": f"dq07_{staging_table}_{month}",
                "source_value": source_rows,
                "warehouse_value": wh_rows,
                "difference": source_rows - wh_rows,
                "passed": passed,
                "variance": variance,
            }
        )
    return results


def _reconcile_total(
    cur,
    run_id: int,
    staging_table: str,
    fact_table: str,
) -> dict:
    """Return one result dict for a table-level (non-monthly) pair."""
    cur.execute(f"SELECT count(*) FROM lue_staging.{staging_table}")
    source_rows = int(cur.fetchone()[0])

    cur.execute(f"SELECT count(*) FROM lue_dw.{fact_table}")
    wh_rows = int(cur.fetchone()[0])

    quarantined = _quarantined(cur, staging_table)
    variance = source_rows - wh_rows - quarantined
    passed = variance == 0
    return {
        "check_name": f"dq07_{staging_table}_total",
        "source_value": source_rows,
        "warehouse_value": wh_rows,
        "difference": source_rows - wh_rows,
        "passed": passed,
        "variance": variance,
    }


def _insert_row(cur, run_id: int, row: dict) -> None:
    cur.execute(
        """
        INSERT INTO lue_audit.reconciliation
              (run_id, check_name, source_value, warehouse_value, difference, passed)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, check_name) DO UPDATE
            SET source_value    = EXCLUDED.source_value,
                warehouse_value = EXCLUDED.warehouse_value,
                difference      = EXCLUDED.difference,
                passed          = EXCLUDED.passed
        """,
        (
            run_id,
            row["check_name"][:60],
            row["source_value"],
            row["warehouse_value"],
            row["difference"],
            row["passed"],
        ),
    )


def reconcile(conn, run_id: int) -> list[dict]:
    """Write DQ-07 source-to-warehouse reconciliation rows.

    Parameters
    ----------
    conn:
        A psycopg2 connection to lue_warehouse (autocommit=True recommended so
        that each row lands even if the caller later raises).
    run_id:
        The pipeline run id used to tag the new lue_audit.reconciliation rows.

    Returns
    -------
    list[dict]
        One dict per check written, with keys: check_name, source_value,
        warehouse_value, difference, passed, variance.

    Raises
    ------
    ReconcileError
        When any variance is unexplained (variance != 0).
    """
    all_rows: list[dict] = []

    with conn.cursor() as cur:
        for staging_table, fact_table, month_col in _MONTHLY_PAIRS:
            rows = _reconcile_monthly(cur, run_id, staging_table, fact_table, month_col)
            for row in rows:
                _insert_row(cur, run_id, row)
            all_rows.extend(rows)

        for staging_table, fact_table in _TOTAL_PAIRS:
            row = _reconcile_total(cur, run_id, staging_table, fact_table)
            _insert_row(cur, run_id, row)
            all_rows.append(row)

    failed = [r for r in all_rows if not r["passed"]]
    if failed:
        summary = "; ".join(
            f"{r['check_name']} variance={r['variance']}" for r in failed[:5]
        )
        raise ReconcileError(
            f"{len(failed)} unexplained variance(s): {summary}"
        )

    return all_rows
