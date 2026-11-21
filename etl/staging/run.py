#!/usr/bin/env python3
"""Load staging (E5): python etl/staging/run.py [--full] [--compare] [--data data] [--evidence dir]

One pipeline run (lue_audit.etl_run_log): one step per staging table in contract order
(US-5.1, US-5.3), each its own transaction, then stage_business (US-5.2). Cleaning evidence is
recorded per table (lue_audit.cleaning_evidence, US-5.4) and written as CSV files to the
evidence folder (default data/staging_evidence): one per source, the count bridge and the
distinct values before and after.

--compare then checks staging against the answer key of the generated data (US-5.1 repairs and
US-5.2 matching; <data>/answer_key) and writes answer_key_check.csv to the evidence folder.

Incremental by default: each table reads only the bronze rows landed after its watermark. --full
empties staging and its watermarks first and reloads everything (after a change to the rules of
E4 or to etl/staging/spec.py).

Refuses to start (exit 2) when the staging tables are not deployed or differ from the spec, when
no bronze batch has been validated, when a bronze batch waits for validation (python
etl/quality/run.py), or when another staging run is in progress. Exit 1 when a step Failed or the
count bridge does not balance (or, with --compare, the answer key is not met), 0 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.ingest.base import WAREHOUSE_DB, IngestError, Run, connect, kv  # noqa: E402
from etl.staging import answer_key, business, evidence, load, spec  # noqa: E402

EVIDENCE = ROOT / "data" / "staging_evidence"
LOCK = "lue_staging.run"  # one staging run at a time (pg advisory lock on this name)


class StagingError(Exception):
    """Staging cannot start: the reason and what to run first."""


def step_name(table: str) -> str:
    return "stage_" + table.removeprefix("stg_")


# ----------------------------------------------------------------------------- guards
def check_ready(cur) -> None:
    """The guards of the module docstring; raises StagingError with what to do."""
    cur.execute("SELECT table_name, array_agg(column_name::text ORDER BY ordinal_position) FROM "
                "information_schema.columns WHERE table_schema = 'lue_staging' AND table_name "
                "LIKE 'stg\\_%' GROUP BY 1")  # fmt: skip
    found = dict(cur.fetchall())
    for t in spec.TABLES:
        want = [c.name for c in t.cols] + [c.name for c in spec.LINEAGE + t.extra_lineage]
        if found.get(t.name) is None:
            raise StagingError(f"lue_staging.{t.name} does not exist: run python "
                               "scripts/db_deploy.py")  # fmt: skip
        if sorted(found[t.name]) != sorted(want):
            raise StagingError(f"lue_staging.{t.name} has other columns than etl/staging/spec.py: "
                               "run python etl/staging/ddl.py, then python scripts/db_deploy.py "
                               "(a changed table: drop it first)")  # fmt: skip
    cur.execute("SELECT count(*) FROM lue_audit.dq_batch")
    if cur.fetchone()[0] == 0:
        raise StagingError("no bronze batch has been validated: run python etl/ingest/run.py, then "
                           "python etl/quality/run.py")  # fmt: skip
    waiting = []
    for t in sorted({t.bronze for t in spec.TABLES}):
        cur.execute(f"SELECT count(DISTINCT batch_id) FROM lue_staging.{t} WHERE batch_id NOT IN "
                    "(SELECT batch_id FROM lue_audit.dq_batch)")  # fmt: skip
        n = cur.fetchone()[0]
        if n:
            waiting.append(f"{t} ({n})")
    if waiting:
        raise StagingError("bronze batches wait for validation in " + ", ".join(waiting)
                           + ": run python etl/quality/run.py first")  # fmt: skip


# ----------------------------------------------------------------------------- steps
def _repeatable(cur) -> None:
    # One snapshot for the whole step: the window, the counts and the merge see the same bronze.
    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")


def reset_step(step) -> None:
    _repeatable(step.cur)
    names = ", ".join(f"lue_staging.{t.name}" for t in spec.TABLES)
    step.cur.execute(f"TRUNCATE {names}")
    step.cur.execute("DELETE FROM lue_audit.etl_watermark WHERE source_system = 'STG'")
    step.result.rows_updated = step.cur.rowcount


def table_step(t: spec.Table, now: datetime, box: dict):
    def run(step) -> None:
        cur = step.cur
        _repeatable(cur)
        result = load.load_table(cur, t, step.run.run_id, now)
        if not result.balanced:  # cannot happen by construction; refuse to commit if it does
            raise IngestError(f"{t.name}: the count bridge does not balance: {result}")
        rows = evidence.load_rows(result) + evidence.column_evidence(cur, t, step.run.run_id)
        evidence.record(cur, step.run.run_id, t.source_system, t.name, rows)
        step.lineage(f"lue_staging.{t.name}", f"lue_staging.{t.bronze}", "bronze -> staging",
                     "cleaned and typed (clean_text, std, safe casts); E4 rejections left out; "
                     "latest version per key (D15); incremental merge (watermark)")  # fmt: skip
        r = step.result
        r.rows_read, r.rows_written, r.rows_updated = result.read, result.inserted, result.updated
        r.rows_rejected = result.rejected + result.unusable
        r.rejects_warn = False  # rows E4 rejected are expected
        if result.unusable:
            r.warning = True
            step.warn(f"{result.unusable} rows with an empty key after cleaning were not staged")
        box[t.name] = result

    return run


def business_step(now: datetime, box: dict):
    def run(step) -> None:
        cur = step.cur
        _repeatable(cur)
        result = business.apply(cur, step.run.run_id, now)
        for table, rows in evidence.business_rows(cur, result).items():
            evidence.record(cur, step.run.run_id, spec.BY_NAME[table].source_system, table, rows)
        for table, n in result.changed.items():
            evidence.record(cur, step.run.run_id, spec.BY_NAME[table].source_system, table,
                            [("derived_values_changed", "*", n, None, None)])  # fmt: skip
        step.result.rows_read = sum(result.changed.values())
        step.result.rows_written = result.derived_inserted
        step.result.rows_updated = result.total + result.derived_updated
        box["_business"] = result

    return run


def stage(full: bool = False, folder: Path | None = EVIDENCE, settings: dict | None = None,
          run: Run | None = None):
    """One staging run. Returns (run_id, step results, loads, business result, bridge rows).
    Inside a pipeline run (US-8.1) pass `run`: the steps join that run, which the caller closes."""
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
        with r.audit.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK,))
            if not cur.fetchone()[0]:
                raise StagingError("another staging run is in progress")
        now = datetime.now().replace(microsecond=0)
        results = []
        if full:
            results.append(r.step("stage_reset", "STG", reset_step))
            if results[-1].status == "Failed":
                return r.run_id, results, box, None, []
        for t in spec.TABLES:
            results.append(r.step(step_name(t.name), t.source_system, table_step(t, now, box)))
        results.append(r.step("stage_business", "STG", business_step(now, box)))
        with r.audit.cursor() as cur:
            bridge = evidence.bridge(cur)
            if folder is not None:
                for path in evidence.write_files(cur, r.run_id, folder):
                    r.log.info(kv(event="evidence", file=path.as_posix()))
        biz = box.pop("_business", None)
        return r.run_id, results, box, biz, bridge
    finally:
        if run is None:
            r.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--full", action="store_true", help="empty staging first and reload everything")
    ap.add_argument("--evidence", type=Path, default=EVIDENCE, help="folder for the evidence CSVs")
    ap.add_argument("--compare", action="store_true", help="check against the answer key")
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="the generated data folder")
    args = ap.parse_args(argv)
    try:
        run_id, results, loads, biz, bridge = stage(args.full, args.evidence)
    except (IngestError, StagingError) as exc:
        print(f"[FAIL] {exc}")
        return 2
    print("=" * 96)
    print(f" Staging run {run_id}" + (" (full reload)" if args.full else " (incremental)"))
    print("=" * 96)
    print(f"  {'table':24} {'status':8} {'read':>8} {'rejected':>8} {'unusable':>8} "
          f"{'superseded':>10} {'inserted':>8} {'updated':>8} {'unchanged':>9}")  # fmt: skip
    for res in results:
        name = "stg_" + res.step.removeprefix("stage_")
        x = loads.get(name)
        if x is None:
            print(f"  {res.step:24} {res.status:8} {res.message}")
            continue
        print(f"  {name:24} {res.status:8} {x.read:>8,} {x.rejected:>8,} {x.unusable:>8,} "
              f"{x.superseded:>10,} {x.inserted:>8,} {x.updated:>8,} {x.unchanged:>9,}"
              + (f"  deleted {x.deleted:,}" if x.deleted else "")
              + (f"  {res.message}" if res.status == "Failed" else ""))  # fmt: skip
    if biz is not None:
        print(f" Business (US-5.2): derived allocations +{biz.derived_inserted:,} "
              f"~{biz.derived_updated:,} -{biz.derived_deleted:,} "
              f"({biz.payments_derived:,} payments); rows with changed derived values: "
              + ", ".join(f"{t} {n:,}" for t, n in biz.changed.items()))  # fmt: skip
    bad = [b for b in bridge if b[9] != 0]
    print(f" Count bridge (US-5.1): {len(bridge) - len(bad)}/{len(bridge)} tables balance"
          + ("" if not bad else ": " + ", ".join(f"{b[0]} off by {b[9]:+,}" for b in bad)))
    shown = args.evidence.resolve()
    shown = shown.relative_to(ROOT) if shown.is_relative_to(ROOT) else shown
    print(f" Evidence (US-5.4): {shown.as_posix()}")
    failed = any(res.status == "Failed" for res in results)
    code = 1 if failed or bad else 0
    if args.compare:
        if not (args.data / "answer_key" / "defects_answer_key.csv").is_file():
            print(f"[FAIL] {args.data / 'answer_key'} not found: run python etl/generate_data.py")
            return 2
        conn = connect(WAREHOUSE_DB)
        try:
            with conn.cursor() as cur:
                cmp = answer_key.compare(cur, args.data)
        finally:
            conn.close()
        answer_key.write(cmp, args.evidence / "answer_key_check.csv")
        print(" Answer key (US-5.1 repairs, US-5.2 matching)")
        for row in cmp.rows:
            check, table, col, expected, found, missing, wrong, ok, note = row
            extra = f", not staged {missing}" if missing else ""
            print(f"  [{'PASS' if ok else 'FAIL'}] {check:6} {table}.{col}: {found}/{expected}"
                  f"{extra}  {note}")  # fmt: skip
        code = code or (0 if cmp.ok else 1)
    print("=" * 96)
    return code


if __name__ == "__main__":
    sys.exit(main())
