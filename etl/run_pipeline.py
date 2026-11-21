#!/usr/bin/env python3
"""The LUE pipeline in one command (US-8.1): python etl/run_pipeline.py

Runs the brief's order as one pipeline run (one run_id in lue_audit.etl_run_log):

  generate    the seeded source data into data/ (etl/generate_data.py)       --skip-generate skips it
  setup       databases, roles and schemas; safe to re-run (scripts/db_setup.py)
  deploy      the warehouse DDL; safe to re-run (scripts/db_deploy.py)
  reference   dim_date and the static dimensions (scripts/db_load_reference.py)
  source      the generated S1 extract into lue_source.src_pms (scripts/db_load_source.py)
  ingest      all six sources into bronze, reconciled to their sources (E3)
  validate    the quality rules on bronze; rejected rows to quarantine (E4)
  transform   staging: clean, standardise, deduplicate, business fields (E5)
  dimensions  surrogate keys, SCD Type 2, hierarchies, inferred members (E6)
  facts       the six facts, then the 71 fact tests (E7)
  reconcile   DQ-07: by month, source = warehouse + quarantined for billed, paid, tickets and lease
              events (etl/reconcile.py, US-8.2); any unexplained variance fails it

Every step writes a start and an end row to the run log with its status and counts (rows read,
inserted, updated, rejected); each layer records its lineage (source to bronze, bronze to
staging, staging to the dimensions and facts) in lue_audit.lineage. The first four stages create
the audit tables themselves, so their rows are written as soon as the run exists. A Failed step
in a critical stage stops the run (exit 1); a non-critical step (the S5 weather, which may be cut,
D19) is reported and the run goes on. Options: --profile and --seed for the generation,
--from-step NAME to resume at a stage, --only NAME[,NAME] to run just those stages.
Exit 0 when every step succeeded (Warnings allowed), 1 when one Failed, 2 for a bad option.

One warehouse holds one generation of the data (US-8.3): the profile, seed and content hash of the
data folder's run_manifest.json are recorded after the first ingest (lue_audit.file_load, source
GEN). A run on other generated data stops before it touches the source or bronze (mixing two
generations would corrupt bronze); reset first (python scripts/db_reset.py, or make rebuild).
"""

# ruff: noqa: E501  (the result table: long lines read better)

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl import reconcile  # noqa: E402
from etl.dimensions import run as dimensions  # noqa: E402
from etl.facts import run as facts  # noqa: E402
from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import Run, StepResult  # noqa: E402
from etl.quality import run as quality  # noqa: E402
from etl.staging import run as staging  # noqa: E402

DATA = ROOT / "data"
LOGS = ROOT / "logs"
NON_CRITICAL = {"ingest_s5_weather"}  # the weather may be cut (D19): its keys then resolve to -1


@dataclass(frozen=True)
class Stage:
    name: str
    what: str
    script: str | None = None  # a setup script run as a subprocess (it creates what Run needs)
    before_run: bool = False  # runs before the pipeline run exists (no audit tables yet)


STAGES = [
    Stage("generate", "seeded source data into data/", "etl/generate_data.py", before_run=True),
    Stage("setup", "databases, roles and schemas", "scripts/db_setup.py", before_run=True),
    Stage("deploy", "warehouse DDL", "scripts/db_deploy.py", before_run=True),
    Stage("reference", "dim_date and the static dimensions", "scripts/db_load_reference.py", before_run=True),
    Stage("source", "the S1 extract into lue_source.src_pms", "scripts/db_load_source.py"),
    Stage("ingest", "six sources into bronze (E3)"),
    Stage("validate", "quality rules, quarantine (E4)"),
    Stage("transform", "staging (E5)"),
    Stage("dimensions", "dimensions (E6)"),
    Stage("facts", "facts and the fact tests (E7)"),
    Stage("reconcile", "source = warehouse + quarantined (DQ-07)"),
]
NAMES = [s.name for s in STAGES]


class PipelineError(Exception):
    """A setup script failed (named, with the end of its output)."""


GEN = "GEN"  # lue_audit.file_load source_system of the generation record


def generation(data: Path) -> tuple[str, str] | None:
    """(content hash, "profile P, seed S") of the generated data, from its run_manifest.json."""
    f = data / "run_manifest.json"
    if not f.is_file():
        return None
    m = json.loads(f.read_text(encoding="utf-8"))
    return m["content_hash"], f"profile {m['profile']['name']}, seed {m['seed']}"


def loaded_generation(cur) -> tuple[str, str, int] | None:
    """The generation the warehouse was loaded from: (content hash, profile and seed, run), or None."""
    cur.execute("SELECT checksum_sha256, message, run_id FROM lue_audit.file_load WHERE source_system = %s "
                "AND status = 'Loaded' ORDER BY file_load_id DESC LIMIT 1", (GEN,))  # fmt: skip
    return cur.fetchone()


def check_generation(data: Path):
    """A step: refuse data from another generation than the warehouse holds."""

    def run(step) -> None:
        gen = generation(data)
        if gen is None:
            raise PipelineError(f"no run_manifest.json in {data}: generate the data first (python etl/generate_data.py)")
        have = loaded_generation(step.cur)
        step.result.rows_read = 1
        if have and have[0] != gen[0]:
            raise PipelineError(f"the warehouse holds other generated data ({have[1]}, {have[0][:12]}, run {have[2]}) "
                                f"than {data.name}/ ({gen[1]}, {gen[0][:12]}); mixing them would corrupt bronze. "
                                "Reset first: python scripts/db_reset.py (or make rebuild)")  # fmt: skip

    return run


def record_generation(r: Run, data: Path) -> None:
    """After an ingest: the warehouse now holds this generation (kept unless it changes)."""
    gen = generation(data)
    with r.audit.cursor() as cur:
        have = loaded_generation(cur)
        if gen and (have is None or have[0] != gen[0]):
            cur.execute("INSERT INTO lue_audit.file_load (run_id, source_system, file_name, checksum_sha256, target_table, "
                        "rows_landed, status, message, loaded_at) VALUES (%s, %s, 'run_manifest.json', %s, 'generation', 0, "
                        "'Loaded', %s, now()::timestamp(0))", (r.run_id, GEN, gen[0], gen[1]))  # fmt: skip


def select(only: list[str] | None, from_step: str | None, skip_generate: bool) -> list[Stage]:
    """The stages to run, in pipeline order. Raises ValueError for an unknown or empty choice."""
    for name in [*(only or []), *([from_step] if from_step else [])]:
        if name not in NAMES:
            raise ValueError(f"no such stage: {name} (stages: {', '.join(NAMES)})")
    if only and from_step:
        raise ValueError("--only and --from-step cannot be combined")
    chosen = [s for s in STAGES if s.name in only] if only else STAGES[NAMES.index(from_step):] if from_step else list(STAGES)
    if skip_generate:
        chosen = [s for s in chosen if s.name != "generate"]
    if not chosen:
        raise ValueError("nothing to run")
    return chosen


def script_args(stage: Stage, profile: str, seed: int, data: Path) -> list[str]:
    args = [sys.executable, str(ROOT / stage.script)]
    if stage.name == "generate":
        args += ["--profile", profile, "--seed", str(seed), "--out", str(data)]
    elif stage.name == "source":
        args += ["--data", str(data)]
    return args


def run_script(stage: Stage, args: list[str], log: Path) -> None:
    """Run a setup script; its output goes to the log file. Raises PipelineError when it fails."""
    done = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"===== {stage.name}: {' '.join(Path(a).name if i < 2 else a for i, a in enumerate(args))}\n")
        f.write(done.stdout + done.stderr + "\n")
    if done.returncode != 0:
        tail = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()][-3:]
        raise PipelineError(f"{stage.script} exited {done.returncode}: " + " | ".join(tail))


def critical_failures(results: list[StepResult]) -> list[StepResult]:
    return [r for r in results if r.status == "Failed" and r.step not in NON_CRITICAL]


def layer(stage: Stage, r: Run, data: Path) -> list[StepResult]:
    """Run one ETL layer inside the pipeline run; returns its step results."""
    if stage.name == "ingest":
        _id, results, checks = ingest.run(data, run=r)
        bad = [c[0] for c in checks if not c[4]]
        if bad:  # bronze must equal its sources (US-3.4): a gap is a failure, not a warning
            results.append(_failed(r, "ingest_reconciliation", f"bronze differs from its source: {', '.join(bad[:5])}"))
        return results
    if stage.name == "validate":
        with r.audit.cursor() as cur:  # only the batches not validated yet: a rerun rejects nothing twice (D14)
            batches = quality.unvalidated(cur)
        return [quality.validate(batches=batches, run=r)[1]]
    if stage.name == "transform":
        return staging.stage(run=r)[1]  # with the cleaning evidence CSVs, as make stage
    if stage.name == "dimensions":
        return dimensions.load_all(run=r)[1]
    if stage.name == "facts":
        return facts.load_all(run=r)[1]
    if stage.name == "reconcile":
        return [r.step(reconcile.STEP, "DW", reconcile.step({}))]
    raise ValueError(stage.name)


def _failed(r: Run, step: str, message: str) -> StepResult:
    """A step of the pipeline itself that failed (a layer refused to start, a gap in bronze)."""

    def fail(_step) -> None:
        raise PipelineError(message)

    return r.step(step, "PIPE", fail)


def pipeline(profile: str, seed: int, chosen: list[Stage], data: Path = DATA, settings: dict | None = None):
    """One pipeline run. Returns (run_id, [(stage, [StepResult])], stopped_at or None)."""
    LOGS.mkdir(exist_ok=True)
    log = LOGS / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
    done: list[tuple[Stage, list[StepResult]]] = []
    early: list[tuple[StepResult, datetime, datetime]] = []  # before_run stages, logged once the run exists
    for stage in [s for s in chosen if s.before_run]:
        result = StepResult(stage.name, "PIPE")
        started, clock = datetime.now().replace(microsecond=0), time.monotonic()
        try:
            run_script(stage, script_args(stage, profile, seed, data), log)
            result.status = "Success"
        except PipelineError as exc:
            result.status, result.message = "Failed", str(exc)[:300]
        result.seconds = time.monotonic() - clock
        early.append((result, started, datetime.now().replace(microsecond=0)))
        done.append((stage, [result]))
        if result.status == "Failed":
            break
    if done and done[-1][1][0].status == "Failed":
        try:  # log the failure too when the audit tables exist already
            r = Run(settings)
        except Exception:  # noqa: BLE001  (no warehouse yet: the terminal output is the record)
            return None, done, done[-1][0].name
        try:
            for result, started, ended in early:
                r.record(result, started, ended)
            return r.run_id, done, done[-1][0].name
        finally:
            r.close()
    r = Run(settings)
    try:
        for result, started, ended in early:
            r.record(result, started, ended)
        checked = False
        for stage in [s for s in chosen if not s.before_run]:
            guard = []
            if stage.name in ("source", "ingest") and not checked:  # before the source or bronze changes
                checked = True
                guard = [r.step("check_generation", "PIPE", check_generation(data))]
                if guard[0].status == "Failed":
                    done.append((stage, guard))
                    return r.run_id, done, stage.name
            if stage.script:
                results = [r.step(stage.name, "PIPE", lambda _s, st=stage: run_script(st, script_args(st, profile, seed, data), log))]
            else:
                try:
                    results = layer(stage, r, data)
                except Exception as exc:  # noqa: BLE001  a layer that cannot start (not ready, no data, no database): a failed step, not a crash
                    results = [_failed(r, f"{stage.name}_not_ready", f"{type(exc).__name__}: {exc}")]
            results = guard + results
            done.append((stage, results))
            if critical_failures(results):
                return r.run_id, done, stage.name
            if stage.name == "ingest":
                record_generation(r, data)
        return r.run_id, done, None
    finally:
        r.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", choices=["small", "full"], default="small", help="generation profile (default: small)")
    ap.add_argument("--seed", type=int, default=3004, help="generation seed (default: 3004)")
    ap.add_argument("--data", type=Path, default=DATA, help="the generated data folder (default: data/)")
    ap.add_argument("--skip-generate", action="store_true", help="use the data already in the data folder")
    ap.add_argument("--from-step", metavar="STAGE", help=f"start at this stage ({', '.join(NAMES)})")
    ap.add_argument("--only", metavar="STAGE[,STAGE]", help="run only these stages, in pipeline order")
    args = ap.parse_args(argv)
    try:
        only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
        chosen = select(only, args.from_step, args.skip_generate)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 2
    started = time.monotonic()
    run_id, done, stopped = pipeline(args.profile, args.seed, chosen, args.data.resolve())
    line = "=" * 104
    print(line)
    print(f" Pipeline run {run_id if run_id is not None else '(none: no warehouse yet)'}: "
          f"{', '.join(s.name for s in chosen)}")  # fmt: skip
    print(line)
    print(f"  {'stage':11} {'steps':>5} {'status':8} {'read':>11} {'inserted':>11} {'updated':>10} {'rejected':>9} {'seconds':>8}")
    for stage, results in done:
        failed = [x for x in results if x.status == "Failed"]
        status = "Failed" if failed else "Warning" if any(x.status == "Warning" for x in results) else "Success"
        print(f"  {stage.name:11} {len(results):>5} {status:8} {sum(x.rows_read for x in results):>11,} "
              f"{sum(x.rows_written for x in results):>11,} {sum(x.rows_updated for x in results):>10,} "
              f"{sum(x.rows_rejected for x in results):>9,} {sum(x.seconds for x in results):>8.1f}")  # fmt: skip
        for x in results:
            if x.status != "Success":
                print(f"      {x.status:7} {x.step}: {(x.message or f'{x.rows_rejected:,} rows rejected (quarantined)')[:150]}")
    print(line)
    steps = sum(len(results) for _, results in done)
    bad = sum(1 for _, results in done for x in results if x.status == "Failed")
    if stopped:
        rest = [s.name for s in chosen[[s.name for s in chosen].index(stopped) + 1:]]
        print(f" STOPPED at {stopped} (a critical step failed)" + (f"; not run: {', '.join(rest)}" if rest else ""))
        data = "" if args.data.resolve() == DATA.resolve() else f" --data {args.data}"
        if stopped == "generate":
            print(f" Fix it, then run again: python etl/run_pipeline.py --profile {args.profile} --seed {args.seed}{data}")
        else:
            print(f" Fix it, then resume: python etl/run_pipeline.py --skip-generate --from-step {stopped}{data}")
    print(f" RESULT: {steps - bad}/{steps} steps without failure in {time.monotonic() - started:.0f} s"
          + (f"; the run log: SELECT * FROM lue_audit.etl_run_log WHERE run_id = {run_id}" if run_id is not None else ""))
    print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
