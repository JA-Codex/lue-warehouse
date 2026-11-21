#!/usr/bin/env python3
"""Land every source in bronze (E3): python etl/ingest/run.py [--data data] [--only S1,S4]

One run, one step per source, in this order: S1 (src_pms, incremental), S2, S3, S4, S5, S6 (files,
checksum policy D16). Each source is its own transaction: a failure rolls that source back and
the next one still runs. Prints one line per step and every reconciliation check of the run.
Exit code 0 when every step is Success or Warning (a rejected file), 1 when a step Failed or a
reconciliation check did not pass, 2 when the run could not start (no database, no data).

Needs: python scripts/db_deploy.py (bronze and audit tables), python scripts/db_load_source.py (S1)
and a generated data folder (python etl/generate_data.py).
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.ingest import files, json_weather, s1_pms  # noqa: E402
from etl.ingest.base import IngestError, Run  # noqa: E402

SOURCES = ("S1", "S2", "S3", "S4", "S5", "S6")


def steps(data: Path) -> dict:
    return {
        "S1": ("ingest_s1_pms", s1_pms.ingest_s1),
        "S2": ("ingest_s2_registers", partial(files.ingest_s2, data=data)),
        "S3": ("ingest_s3_settlements", partial(files.ingest_s3, data=data)),
        "S4": ("ingest_s4_tickets", partial(json_weather.ingest_s4, data=data)),
        "S5": ("ingest_s5_weather", partial(json_weather.ingest_s5, data=data)),
        "S6": ("ingest_s6_incentives", partial(files.ingest_s6, data=data)),
    }


def run(data: Path, only: list[str] | None = None, settings: dict | None = None,
        run: Run | None = None) -> tuple:
    """Run the chosen sources; returns (run_id, step results, reconciliation rows). Inside a
    pipeline run (US-8.1) pass `run`: its steps join that run, which the caller closes."""
    chosen = [s for s in SOURCES if not only or s in only]
    r = run or Run(settings)
    try:
        table = steps(data)
        results = []
        for source in chosen:
            name, fn = table[source]
            results.append(r.step(name, source, fn))
        with r.audit.cursor() as cur:
            cur.execute(
                "SELECT check_name, source_value, warehouse_value, difference, passed "
                "FROM lue_audit.reconciliation WHERE run_id = %s AND check_name LIKE 'brz\\_%%' "
                "ORDER BY check_name",
                (r.run_id,),
            )
            checks = cur.fetchall()
        return r.run_id, results, checks
    finally:
        if run is None:
            r.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="the generated data folder")
    ap.add_argument("--only", help="comma-separated sources, e.g. S1,S4 (default: all six)")
    args = ap.parse_args(argv)
    only = [s.strip().upper() for s in args.only.split(",")] if args.only else None
    if only and set(only) - set(SOURCES):
        print(f"unknown source(s): {', '.join(sorted(set(only) - set(SOURCES)))}")
        return 2
    try:
        run_id, results, checks = run(args.data, only)
    except IngestError as exc:
        print(f"[FAIL] {exc}")
        return 2
    print("=" * 78)
    print(f" Ingestion run {run_id}: {args.data}")
    print("=" * 78)
    for s in results:
        print(f"  [{s.status.upper():7}] {s.step:24} read {s.rows_read:>8,}  landed "
              f"{s.rows_written:>8,}  rejected {s.rows_rejected}  {s.seconds:5.1f} s")  # fmt: skip
        if s.message:
            print(f"            {s.message}")
    print(" Reconciliation (source rows vs rows in bronze)")
    for name, source, warehouse, _diff, passed in checks:
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name:56} {int(source):>8,} {int(warehouse):>8,}")
    failed = [s for s in results if s.status == "Failed"]
    bad = [c for c in checks if not c[4]]
    print("=" * 78)
    print(f" RESULT: {len(results) - len(failed)}/{len(results)} sources landed, "
          f"{len(checks) - len(bad)}/{len(checks)} reconciliation checks passed")  # fmt: skip
    print("=" * 78)
    return 1 if failed or bad else 0


if __name__ == "__main__":
    sys.exit(main())
