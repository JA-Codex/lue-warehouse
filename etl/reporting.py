#!/usr/bin/env python3
"""The reporting marts (US-10.2): python etl/reporting.py

Refreshes the four materialized marts of lue_reporting through lue_reporting.refresh_marts()
(sql/50_reporting/01_reporting.sql): concurrently once a mart holds data, so Power BI and the views
keep reading the previous rows until the new ones are complete. In the pipeline this is the marts
stage, the last one: after the facts are loaded and reconciled. One step, refresh_marts, in
lue_audit.etl_run_log (rows read = the marts' rows), and the lineage of every mart.
Exit 0 when the refresh succeeded, 1 when it failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.ingest.base import IngestError, Run  # noqa: E402

STEP = "refresh_marts"
# each mart and the facts it is built from (lineage)
MARTS = {
    "mart_collections_monthly": ["fact_rent_invoice_line", "fact_payment"],
    "mart_occupancy_monthly": ["fact_unit_occupancy_daily"],
    "mart_maintenance_monthly": ["fact_maintenance_request"],
    "mart_owner_portfolio_monthly": [
        "fact_payment", "fact_maintenance_request", "fact_unit_occupancy_daily"],
}


def step(box: dict):
    """The pipeline's marts step: refresh every mart in the step's transaction."""

    def run(s) -> None:
        s.cur.execute("SELECT mart, row_count, seconds FROM lue_reporting.refresh_marts()")
        rows = s.cur.fetchall()
        box[STEP] = rows
        s.result.rows_read = sum(n for _m, n, _s in rows)
        for mart, facts in MARTS.items():
            for fact in facts:
                s.lineage(f"lue_reporting.{mart}", f"lue_dw.{fact}", "warehouse -> mart",
                          "monthly sums and counts (sql/50_reporting)")  # fmt: skip
        missing = set(MARTS) - {m for m, _n, _s in rows}
        if missing:
            raise RuntimeError(f"refresh_marts() did not refresh {', '.join(sorted(missing))}")

    return run


def main() -> int:
    try:
        r = Run()
    except IngestError as exc:
        print(f"[FAIL] {exc}")
        return 2
    box: dict = {}
    try:
        result = r.step(STEP, "RPT", step(box))
        print(f" Mart refresh, run {r.run_id}: {result.status}")
        for mart, n, seconds in box.get(STEP, []):
            print(f"  {mart:32} {n:>8,} rows {seconds:>7} s")
        if result.status == "Failed":
            print(f"  [FAIL] {result.message}")
        return 0 if result.status != "Failed" else 1
    finally:
        r.close()


if __name__ == "__main__":
    sys.exit(main())
