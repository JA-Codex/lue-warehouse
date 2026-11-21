#!/usr/bin/env python3
"""Run the full LUE pipeline in one command (US-8.1).

    python run_pipeline.py                    # small profile, seed 3004, all steps
    python run_pipeline.py --profile full     # full profile
    python run_pipeline.py --skip-generate    # skip data generation (data/ already exists)
    python run_pipeline.py --from-step stage  # resume from the stage step
    python run_pipeline.py --only facts       # run a single step
    python run_pipeline.py --skip reports     # run all except reports

Steps (in order):
  generate      etl/generate_data.py          optional; skip with --skip-generate
  db-setup      scripts/db_setup.py           critical
  db-deploy     scripts/db_deploy.py          critical
  db-load-ref   scripts/db_load_reference.py  critical
  db-load-src   scripts/db_load_source.py     critical (alias: db-load-source)
  ingest        etl/ingest/run.py             critical
  validate      etl/quality/run.py            critical
  stage         etl/staging/run.py            critical
  dims          etl/dimensions/run.py         critical
  facts         etl/facts/run.py              critical (includes fact_tests)
  reports       etl/reports/build.py          non-critical

Exit 0 when all critical steps pass, 1 when any critical step fails.
Logs are appended to logs/pipeline.log.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_FILE = ROOT / "logs" / "pipeline.log"

# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

STEPS: list[str] = [
    "generate",
    "db-setup",
    "db-deploy",
    "db-load-ref",
    "db-load-src",
    "ingest",
    "validate",
    "stage",
    "dims",
    "facts",
    "reports",
]

CRITICAL: set[str] = {
    "db-setup",
    "db-deploy",
    "db-load-ref",
    "db-load-src",
    "ingest",
    "validate",
    "stage",
    "dims",
    "facts",
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class StepOutcome:
    name: str
    status: str = "skipped"  # skipped | ok | failed
    seconds: float = 0.0
    rows: int | None = None
    message: str = ""
    critical: bool = field(init=False)

    def __post_init__(self) -> None:
        self.critical = self.name in CRITICAL


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _get_logger() -> logging.Logger:
    log = logging.getLogger("lue.pipeline")
    if not log.handlers:
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        log.addHandler(console)
        LOG_FILE.parent.mkdir(exist_ok=True)
        fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
        log.propagate = False
    return log


# ---------------------------------------------------------------------------
# Individual step runners (lazy imports so a missing DB doesn't crash at start)
# ---------------------------------------------------------------------------


def _run_generate(profile: str, seed: int) -> int:
    """Run the data generator."""
    from etl.generate_data import main as gen_main  # noqa: PLC0415

    return gen_main(["--profile", profile, "--seed", str(seed)])


def _run_db_setup() -> int:
    from scripts.db_setup import main as m  # noqa: PLC0415

    return m()


def _run_db_deploy() -> int:
    from scripts.db_deploy import main as m  # noqa: PLC0415

    return m()


def _run_db_load_ref() -> int:
    from scripts.db_load_reference import main as m  # noqa: PLC0415

    return m()


def _run_db_load_src(profile: str, seed: int) -> int:
    from scripts.db_load_source import main as m  # noqa: PLC0415

    return m(["--profile", profile, "--seed", str(seed)])


def _run_ingest() -> int:
    from etl.ingest.run import main as m  # noqa: PLC0415

    return m([])


def _run_validate() -> int:
    from etl.quality.run import main as m  # noqa: PLC0415

    return m([])


def _run_stage() -> int:
    from etl.staging.run import main as m  # noqa: PLC0415

    return m([])


def _run_dims() -> int:
    from etl.dimensions.run import main as m  # noqa: PLC0415

    return m([])


def _run_facts() -> int:
    from etl.facts.run import main as m  # noqa: PLC0415

    return m([])


def _run_reports() -> int:
    from etl.reports.build import main as m  # noqa: PLC0415

    return m([])


# Map step name -> callable; profile/seed injected at runtime
_STEP_FN: dict[str, str] = {
    "generate": "_run_generate",
    "db-setup": "_run_db_setup",
    "db-deploy": "_run_db_deploy",
    "db-load-ref": "_run_db_load_ref",
    "db-load-src": "_run_db_load_src",
    "ingest": "_run_ingest",
    "validate": "_run_validate",
    "stage": "_run_stage",
    "dims": "_run_dims",
    "facts": "_run_facts",
    "reports": "_run_reports",
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run_step(
    name: str,
    profile: str,
    seed: int,
    log: logging.Logger,
) -> StepOutcome:
    outcome = StepOutcome(name=name)
    print(f"[RUNNING] {name}")
    log.info("event=step_start step=%s", name)
    t0 = time.monotonic()
    try:
        if name == "generate":
            rc = _run_generate(profile, seed)
        elif name == "db-setup":
            rc = _run_db_setup()
        elif name == "db-deploy":
            rc = _run_db_deploy()
        elif name == "db-load-ref":
            rc = _run_db_load_ref()
        elif name == "db-load-src":
            rc = _run_db_load_src(profile, seed)
        elif name == "ingest":
            rc = _run_ingest()
        elif name == "validate":
            rc = _run_validate()
        elif name == "stage":
            rc = _run_stage()
        elif name == "dims":
            rc = _run_dims()
        elif name == "facts":
            rc = _run_facts()
        elif name == "reports":
            rc = _run_reports()
        else:
            raise ValueError(f"unknown step: {name}")
        outcome.status = "ok" if rc == 0 else "failed"
    except Exception as exc:  # noqa: BLE001
        outcome.status = "failed"
        outcome.message = f"{type(exc).__name__}: {exc}".strip()[:300]
        log.error("event=step_error step=%s error=%r", name, outcome.message)
    finally:
        outcome.seconds = time.monotonic() - t0
    log.info(
        "event=step_end step=%s status=%s seconds=%.1f",
        name,
        outcome.status,
        outcome.seconds,
    )
    return outcome


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def _print_summary(outcomes: list[StepOutcome]) -> None:
    sep = "-" * 68
    print(sep)
    print(f"  {'step':<18} {'status':<8} {'seconds':>8}  {'rows':>10}  note")
    print(sep)
    for o in outcomes:
        rows_str = f"{o.rows:,}" if o.rows is not None else ""
        note = o.message[:30] if o.message else ""
        print(
            f"  {o.name:<18} {o.status:<8} {o.seconds:>8.1f}  {rows_str:>10}  {note}"
        )
    print(sep)
    crit_failed = [o for o in outcomes if o.critical and o.status == "failed"]
    all_ok = not crit_failed
    print(
        f"  RESULT: {'OK' if all_ok else 'FAILED'} — "
        f"{sum(1 for o in outcomes if o.status == 'ok')}/{len(outcomes)} steps passed"
        + (f"; critical failures: {', '.join(o.name for o in crit_failed)}" if crit_failed else "")
    )
    print(sep)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--profile",
        choices=["small", "full"],
        default="small",
        help="data profile (default: small)",
    )
    ap.add_argument("--seed", type=int, default=3004, help="random seed (default: 3004)")
    ap.add_argument(
        "--skip-generate",
        action="store_true",
        help="skip the generate step (data/ already exists)",
    )
    ap.add_argument(
        "--from-step",
        metavar="STEP",
        help="skip all steps before STEP and start from there",
    )
    ap.add_argument(
        "--only",
        metavar="STEP",
        help="run only this one step",
    )
    ap.add_argument(
        "--skip",
        action="append",
        metavar="STEP",
        default=[],
        help="skip this step (repeatable)",
    )
    args = ap.parse_args(argv)

    # Validate step names in flags
    all_known = set(STEPS) | {"db-load-source"}  # accept alias
    for flag_name, val in [("--from-step", args.from_step), ("--only", args.only)]:
        if val and val not in all_known:
            print(f"[FAIL] {flag_name}: unknown step '{val}'. Known: {', '.join(STEPS)}")
            return 2
    for s in args.skip:
        if s not in all_known:
            print(f"[FAIL] --skip: unknown step '{s}'. Known: {', '.join(STEPS)}")
            return 2

    # Normalise alias
    from_step = args.from_step
    only = args.only
    skips = set(args.skip)

    log = _get_logger()
    log.info(
        "event=pipeline_start profile=%s seed=%s skip_generate=%s from_step=%s only=%s skip=%s",
        args.profile,
        args.seed,
        args.skip_generate,
        from_step or "",
        only or "",
        ",".join(sorted(skips)),
    )

    # Build the execution plan
    plan: list[str] = list(STEPS)

    if args.skip_generate:
        skips.add("generate")

    if only:
        plan = [only]
    else:
        if from_step:
            try:
                idx = plan.index(from_step)
            except ValueError:
                idx = 0
            plan = plan[idx:]
        plan = [s for s in plan if s not in skips]

    outcomes: list[StepOutcome] = []
    for name in plan:
        outcome = _run_step(name, args.profile, args.seed, log)
        outcomes.append(outcome)
        if outcome.status == "failed" and outcome.critical:
            # Mark remaining steps as skipped
            remaining = plan[plan.index(name) + 1 :]
            for r in remaining:
                outcomes.append(StepOutcome(name=r, status="skipped"))
            break

    _print_summary(outcomes)
    log.info("event=pipeline_end steps=%d", len(outcomes))

    critical_failed = any(o.critical and o.status == "failed" for o in outcomes)
    return 1 if critical_failed else 0


if __name__ == "__main__":
    sys.exit(main())
