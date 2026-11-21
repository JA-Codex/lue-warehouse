#!/usr/bin/env python3
"""Load the facts (E7): python etl/facts/run.py

One pipeline run (lue_audit.etl_run_log): one step per fact of etl/facts/spec.py, each its own
transaction. The run log gets rows read, inserted, updated and rejected per fact; unresolved keys
(-1) are reported per key column and make the step a Warning. Each fact is then reconciled to
staging by month (lue_audit.reconciliation, one row per month); a month that differs is a Warning.

The last step, fact_tests (US-7.6), runs sql/90_tests/02_fact_tests.sql: grain, an orphan check per
foreign key, impossible values; one row per test in lue_audit.reconciliation, and the step Fails on
any violation. It runs after a full run (no --fact) or with --tests; rows on the special members
-1 and -2 are counted per key and printed apart.

Refuses to start (exit 2) when the calendar does not hold its days (python
scripts/db_load_reference.py) or the dimensions are empty (python etl/dimensions/run.py). Exit 1
when a step Failed, 0 otherwise. Safe to re-run: a second run changes nothing.
"""

# ruff: noqa: E501  (SQL text and the result table: long lines read better)

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.facts import checks, keys, load, spec  # noqa: E402
from etl.ingest.base import WAREHOUSE_DB, IngestError, Run, connect  # noqa: E402


class NotReady(Exception):
    """The facts cannot be loaded yet: the reason and what to run first."""


def check_ready(cur) -> None:
    cur.execute("SELECT min(full_date)::text, max(full_date)::text, count(*) FROM lue_dw.dim_date WHERE date_key > 0")
    first, last, days = cur.fetchone()
    if (first, last) != keys.CALENDAR or days != 1461:
        raise NotReady(f"lue_dw.dim_date holds {days} days ({first} to {last}), not the calendar "
                       f"{keys.CALENDAR[0]} to {keys.CALENDAR[1]}: run python scripts/db_load_reference.py")  # fmt: skip
    for dim in ("dim_unit", "dim_tenant", "dim_lease", "dim_owner"):
        key = dim.replace("dim_", "") + "_key"
        cur.execute(f"SELECT count(*) FROM lue_dw.{dim} WHERE {key} > 0")
        if cur.fetchone()[0] == 0:
            raise NotReady(f"lue_dw.{dim} has no members: run python etl/dimensions/run.py (E6)")


def fact_step(f: spec.Fact, now: datetime, box: dict):
    def run(step) -> None:
        result = load.load_fact(step.cur, f, step.run.run_id, now)
        for table in f.staging:
            step.lineage(f"lue_dw.{f.name}", f"lue_staging.{table}", "staging -> fact",
                         "keys resolved point in time (SCD2 version and owner valid on the event "
                         "date); synced to the source on its grain")  # fmt: skip
        r = step.result
        r.rows_read, r.rows_written = result.read, result.inserted
        # D14: the occupancy refresh rewrites its last 35 days every run; reported, never hidden
        r.rows_updated = result.updated + result.deleted + result.refreshed
        r.rows_rejected = result.rejected
        if result.unknown or result.rejected:
            r.warning = True
            step.warn(f"unresolved keys (-1): {result.unknown_keys}; rows rejected: {result.rejected}")
        result.months = load.monthly(step.cur, f)  # in the step's transaction: the fact as just loaded
        for month, staged, loaded in result.months:
            step.reconcile(f"{f.name} {month} {f.monthly[0]}", staged, loaded)
        if result.months_off:
            r.warning = True
            step.warn(f"{f.monthly[0]}: staging and the fact differ in {len(result.months_off)} months "
                      f"({', '.join(result.months_off[:6])})")  # fmt: skip
        box[f.name] = result

    return run


TESTS = "fact_tests"


def tests_step(box: dict):
    def run(step) -> None:
        tests = checks.run_tests(step.cur)
        with step.run.audit.cursor() as audit:  # autocommit: the results stay if the step fails
            checks.record(audit, step.run.run_id, tests)
        failed = [(name, n) for name, n in tests if n]
        box[TESTS] = {"tests": tests, "special": checks.special_members(step.cur)}
        step.result.rows_read = len(tests)
        if failed:
            raise load.FactError(f"{len(failed)} of {len(tests)} fact tests found violations: "
                                 + "; ".join(f"{name} ({n})" for name, n in failed[:5]))  # fmt: skip

    return run


def load_all(settings: dict | None = None, only: list[str] | None = None, tests: bool | None = None):
    """One run of every fact, or of the facts named in `only` (in load order), then the fact tests
    (by default after a full run only). Returns (run_id, step results, box): box maps each fact
    loaded to its FactLoad, and "fact_tests" (when they ran) to {"tests", "special"}."""
    unknown = sorted(set(only or []) - set(spec.BY_NAME))
    if unknown:
        raise NotReady(f"no such fact: {', '.join(unknown)} (facts: {', '.join(spec.BY_NAME)})")
    probe = connect(WAREHOUSE_DB, settings)
    probe.autocommit = True
    try:
        with probe.cursor() as cur:
            check_ready(cur)
    finally:
        probe.close()
    r = Run(settings)
    box: dict = {}
    try:
        now = datetime.now().replace(microsecond=0)
        chosen = [f for f in spec.FACTS if not only or f.name in only]
        results = [r.step(f.name, "STG", fact_step(f, now, box)) for f in chosen]
        if only is None if tests is None else tests:
            results.append(r.step(TESTS, "DW", tests_step(box)))
        return r.run_id, results, box
    finally:
        r.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fact", action="append", metavar="NAME", help="load only this fact (repeatable); default: all")
    ap.add_argument("--tests", action="store_true", help="run the fact tests also after a --fact run")
    args = ap.parse_args(argv)
    try:
        run_id, results, loads = load_all(only=args.fact, tests=True if args.tests else None)
    except (IngestError, NotReady) as exc:
        print(f"[FAIL] {exc}")
        return 2
    line = "=" * 121
    print(line)
    print(f" Fact run {run_id}")
    print(line)
    print(f"  {'fact':32} {'status':8} {'read':>9} {'inserted':>9} {'updated':>8} {'deleted':>8} "
          f"{'rejected':>8} {'unknown':>8} {'months ok':>10} {'refreshed':>10}")  # fmt: skip
    for res in results:
        x = loads.get(res.step)
        if res.step == TESTS:
            got = loads.get(TESTS, {}).get("tests", [])
            bad = sum(1 for _, n in got if n)
            print(f"  {res.step:32} {res.status:8} {len(got) - bad} of {len(got)} tests passed (grain, orphans, values)"
                  + (f": {res.message}" if res.status == "Failed" else ""))
            continue
        if x is None:
            print(f"  {res.step:32} {res.status:8} {res.message}")
            continue
        print(f"  {res.step:32} {res.status:8} {x.read:>9,} {x.inserted:>9,} {x.updated:>8,} {x.deleted:>8,} "
              f"{x.rejected:>8,} {x.unknown:>8,} {f'{len(x.months) - len(x.months_off)}/{len(x.months)}':>10} {x.refreshed:>10,}"
              + (f"  -1 keys: {x.unknown_keys}" if x.unknown_keys else "")
              + (f"  months off: {', '.join(x.months_off[:6])}" if x.months_off else ""))  # fmt: skip
    print(line)
    special = loads.get(TESTS, {}).get("special", {})
    if special:
        print("  Rows on the special members (not orphans): key -1 Unknown / -2 Not applicable")
        for fact, used in special.items():
            print(f"    {fact:32} " + ", ".join(f"{k} {a:,}/{b:,}" for k, (a, b) in used.items()))
        print(line)
    return 1 if any(res.status == "Failed" for res in results) else 0


if __name__ == "__main__":
    sys.exit(main())
