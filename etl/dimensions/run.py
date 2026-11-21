#!/usr/bin/env python3
"""Load the dimensions (E6): python etl/dimensions/run.py

One pipeline run (lue_audit.etl_run_log): one step per dimension of etl/dimensions/spec.py, in
load order, each its own transaction (a failure rolls that dimension back; the next still runs).
The run log gets rows read, inserted and updated per dimension (US-6.1 step 4).

Refuses to start (exit 2) when the static dimensions of US-1.4 are not loaded (python
scripts/db_load_reference.py) or staging is empty (python etl/staging/run.py). Exit 1 when a step
Failed, 0 otherwise. Safe to re-run: a second run inserts nothing and changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.dimensions import load, spec  # noqa: E402
from etl.ingest.base import WAREHOUSE_DB, IngestError, Run, connect  # noqa: E402


class NotReady(Exception):
    """The dimensions cannot be loaded yet: the reason and what to run first."""


def check_ready(cur) -> None:
    for t, rows in spec.STATIC.items():
        cur.execute(f"SELECT count(*) FROM lue_dw.{t} WHERE {spec.STATIC_KEY[t]} > 0")
        if cur.fetchone()[0] != rows:
            raise NotReady(f"lue_dw.{t} does not hold its {rows} rows: run python "
                           "scripts/db_load_reference.py (US-1.4)")  # fmt: skip
    cur.execute("SELECT to_regclass('lue_staging.stg_tenant') IS NOT NULL")
    if not cur.fetchone()[0]:
        raise NotReady("the staging tables do not exist: run python scripts/db_deploy.py, then "
                       "python etl/staging/run.py (E5)")  # fmt: skip
    cur.execute("SELECT count(*) FROM lue_staging.stg_tenant")
    if cur.fetchone()[0] == 0:
        raise NotReady("staging is empty: run python etl/staging/run.py (E5)")


def dim_step(d: spec.Dim, now: datetime, box: dict):
    def run(step) -> None:
        result = load.load_dimension(step.cur, d, step.run.run_id, now)
        for table in d.staging:
            step.lineage(f"lue_dw.{d.name}", f"lue_staging.{table}", "staging -> dimension",
                         "new members inserted (identity surrogate key); Type 1 overwritten in "
                         "place" + ("; Type 2 by the SCD2 step" if d.type2 else ""))  # fmt: skip
        r = step.result
        r.rows_read, r.rows_written, r.rows_updated = result.read, result.written, result.changed
        if result.history_conflicts:
            r.warning = True
            step.warn(f"{result.history_conflicts} members' history disagrees with a stored "
                      "version (left as stored)")  # fmt: skip
        box[d.name] = result

    return run


def holiday_step(box: dict):
    def run(step) -> None:
        step.result.rows_updated = box["holidays"] = load.load_holidays(step.cur)
        step.result.rows_read = step.result.rows_updated
        step.lineage("lue_dw.dim_date", "lue_staging.stg_holiday", "staging -> dimension",
                     "holiday and Ramadan flags from the S2 register (US-6.4)")

    return run


def load_all(settings: dict | None = None, run: Run | None = None):
    """One run. Returns (run_id, step results, {dimension: DimLoad}). Inside a pipeline run
    (US-8.1) pass `run`: the steps join that run, which the caller closes."""
    probe = connect(WAREHOUSE_DB, settings)
    probe.autocommit = True
    try:
        with probe.cursor() as cur:
            check_ready(cur)
    finally:
        probe.close()
    r = run or Run(settings)
    box: dict = {}
    try:
        now = datetime.now().replace(microsecond=0)
        results = [r.step("dim_date_holidays", "S2", holiday_step(box))]
        results += [r.step(d.name, "STG", dim_step(d, now, box)) for d in spec.DIMS]
        with r.audit.cursor() as cur:  # fresh statistics for the facts' key lookups (US-8.4)
            for d in spec.DIMS:
                cur.execute(f"ANALYZE lue_dw.{d.name}")
        return r.run_id, results, box
    finally:
        if run is None:
            r.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)
    try:
        run_id, results, loads = load_all()
    except (IngestError, NotReady) as exc:
        print(f"[FAIL] {exc}")
        return 2
    line = "=" * 96
    print(line)
    print(f" Dimension run {run_id}")
    print(line)
    print(f"  {'dimension':26} {'status':8} {'read':>7} {'inserted':>8} {'versions':>8} "
          f"{'inferred':>8} {'completed':>9} {'type 1':>7} {'unchanged':>9}")  # fmt: skip
    for res in results:
        x = loads.get(res.step)
        if res.step == "dim_date_holidays":
            print(f"  {'dim_date (holidays)':26} {res.status:8} {'':>7} {'':>8} {'':>8} {'':>8} "
                  f"{'':>9} {loads.get('holidays', 0):>7,}")  # fmt: skip
        elif x is None:
            print(f"  {res.step:26} {res.status:8} {res.message}")
        else:
            print(f"  {res.step:26} {res.status:8} {x.read:>7,} {x.inserted:>8,} {x.versions:>8,} "
                  f"{x.inferred_created:>8,} {x.inferred_completed:>9,} {x.updated:>7,} "
                  f"{x.unchanged:>9,}" + (f"  history conflicts {x.history_conflicts}"
                                           if x.history_conflicts else ""))  # fmt: skip
    print(line)
    return 1 if any(res.status == "Failed" for res in results) else 0


if __name__ == "__main__":
    sys.exit(main())
