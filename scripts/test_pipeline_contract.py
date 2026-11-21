#!/usr/bin/env python3
"""E8 checks that need no database (run by CI in make gen-test).

    python scripts/test_pipeline_contract.py

The orchestrator (etl/run_pipeline.py): the stages in the brief's order, the setup stages before
the run exists, the options and how they choose stages, every script present, every layer able to
join one pipeline run, the critical-step rule, and the make targets.
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl import run_pipeline as p  # noqa: E402
from etl.dimensions import run as dimensions  # noqa: E402
from etl.facts import run as facts  # noqa: E402
from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import Run, StepResult  # noqa: E402
from etl.quality import run as quality  # noqa: E402
from etl.staging import run as staging  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def raises(fn, *args) -> str:
    try:
        fn(*args)
        return ""
    except ValueError as exc:
        return str(exc)


def main() -> int:
    print("=" * 70)
    print(" E8 contract tests: the pipeline orchestrator (no database)")
    print("=" * 70)
    print("US-8.1 Stages and order")
    order = ["generate", "setup", "deploy", "reference", "source", "ingest", "validate", "transform", "dimensions", "facts", "reconcile"]
    check(p.NAMES == order, "the brief's order: generate, set up and deploy, load sources, ingest, validate, transform, dimensions, facts (tests inside), reconcile")
    before = [s.name for s in p.STAGES if s.before_run]
    check(before == p.NAMES[:4] and not any(s.before_run for s in p.STAGES[4:]),
          "generate, setup, deploy and reference run before the run exists (they create the audit tables), all others inside it")
    missing = [s.script for s in p.STAGES if s.script and not (ROOT / s.script).is_file()]
    check(not missing and all(bool(s.script) == (s.name in ("generate", "setup", "deploy", "reference", "source")) for s in p.STAGES),
          "every setup stage's script exists; the ETL layers run in process" + (f": missing {missing}" if missing else ""))
    joins = {name: "run" in inspect.signature(fn).parameters for name, fn in (
        ("ingest.run", ingest.run), ("quality.validate", quality.validate), ("staging.stage", staging.stage),
        ("dimensions.load_all", dimensions.load_all), ("facts.load_all", facts.load_all))}
    check(all(joins.values()) and hasattr(Run, "record"), "every layer can join one pipeline run (one run_id): " + ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in joins.items()))

    print("US-8.1 Options")
    names = lambda stages: [s.name for s in stages]  # noqa: E731
    check(names(p.select(None, None, False)) == order and names(p.select(None, None, True)) == order[1:],
          "no option: every stage; --skip-generate: all but generate")
    check(names(p.select(None, "dimensions", False)) == ["dimensions", "facts", "reconcile"] and names(p.select(None, "ingest", True)) == order[5:],
          "--from-step resumes at that stage and runs the rest in order")
    check(names(p.select(["facts", "ingest"], None, False)) == ["ingest", "facts"],
          "--only runs just the named stages, in pipeline order")
    errors = [raises(p.select, ["bogus"], None, False), raises(p.select, None, "bogus", False),
              raises(p.select, ["facts"], "ingest", False), raises(p.select, ["generate"], None, True)]
    check(all(errors) and "no such stage" in errors[0] and "cannot be combined" in errors[2] and "nothing to run" in errors[3],
          "an unknown stage, --only with --from-step, or nothing left to run is refused (exit 2)")
    ap = inspect.getsource(p.main)
    check(all(f'"{o}"' in ap for o in ("--profile", "--seed", "--data", "--skip-generate", "--from-step", "--only")),
          "options --profile, --seed, --data, --skip-generate, --from-step and --only")
    gen = p.script_args(p.STAGES[0], "full", 7, Path("/x"))
    src = p.script_args(p.STAGES[4], "small", 3004, Path("/x"))
    check(gen[-6:] == ["--profile", "full", "--seed", "7", "--out", str(Path("/x"))] and src[-2:] == ["--data", str(Path("/x"))] and gen[0] == sys.executable,
          "the generator gets the profile, seed and data folder; the source load the data folder; both with this Python")

    print("US-8.1 Critical steps")
    ingest_steps = {name for name, _fn in ingest.steps(Path(".")).values()}
    check(p.NON_CRITICAL <= ingest_steps and p.NON_CRITICAL == {"ingest_s5_weather"},
          "only the S5 weather is non-critical (it may be cut, D19); every other failed step stops the run")
    a, b, c = StepResult("ingest_s5_weather", "S5", "Failed"), StepResult("ingest_s1_pms", "S1", "Failed"), StepResult("stage_unit", "STG", "Warning")
    check(p.critical_failures([a, c]) == [] and p.critical_failures([a, b]) == [b], "a Warning or a non-critical failure goes on; a critical failure stops")

    print("US-8.2 Reconciliation (DQ-07)")
    from pglast import parse_sql

    from etl import reconcile

    check(list(reconcile.BY_NAME) == ["billed", "paid", "tickets", "lease events"] and p.NAMES[-2:] == ["facts", "reconcile"],
          "the plan's four measures (billed, paid, tickets, lease events), reconciled after the facts are loaded")
    bad = []
    for m in reconcile.MEASURES:
        for part in ("source", "warehouse", "quarantined"):
            try:
                parse_sql(getattr(m, part))
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{m.name} {part}: {exc}")
    check(not bad, "every measure's source, warehouse and quarantined query parses (pglast)" + (f": {bad}" if bad else ""))
    check(all("NOT EXISTS (SELECT 1 FROM lue_staging.stg_" in m.quarantined and "lue_audit.quarantine" in m.quarantined for m in reconcile.MEASURES),
          "a quarantined row explains a difference only when its key never reached staging")
    x = reconcile.Line("lease events", "2026-06", 10, 7, 2)
    check(x.variance == 1 and x.check_name == "DQ-07 lease events 2026-06" and max(len(reconcile.Line(m, "2026-06", 0, 0, 0).check_name) for m in reconcile.BY_NAME) <= 60,
          "unexplained = source - warehouse - quarantined; one check per measure and month, names within 60 characters")

    print("US-8.3 Reruns and recovery")
    import json
    import tempfile

    from etl.quality import run as qrun

    src = inspect.getsource(p.layer)
    check("quality.unvalidated(" in src and "batches=batches" in src and hasattr(qrun, "unvalidated"),
          "the pipeline validates only the batches not validated yet, so a rerun rejects nothing twice (D14)")
    loop = inspect.getsource(p.pipeline)
    check(loop.index("check_generation(data)") < loop.index("if stage.script:") and '("source", "ingest")' in loop
          and "record_generation(r, data)" in loop,
          "the generation is checked before the source or bronze changes, and recorded after an ingest")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "run_manifest.json").write_text(json.dumps({"content_hash": "ab" * 32, "seed": 7, "profile": {"name": "small"}}))
        gen, none = p.generation(Path(d)), p.generation(Path(d) / "missing")
    check(gen == ("ab" * 32, "profile small, seed 7") and none is None,
          "a generation is the run manifest's content hash, profile and seed; no manifest, no generation (the run stops)")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    check("## Recovery" in readme and "--from-step" in readme.split("## Recovery")[1],
          "the README documents the recovery procedure (resume with --from-step)")

    print("US-8.4 Full volume")
    sources = {name: (ROOT / path).read_text(encoding="utf-8") for name, path in (
        ("validation", "etl/quality/engine.py"), ("staging", "etl/staging/run.py"),
        ("dimensions", "etl/dimensions/run.py"), ("fact tests", "etl/facts/run.py"))}
    check(all("ANALYZE lue_" in s for s in sources.values()),
          "each layer refreshes the statistics of what it reads after a bulk load (" + ", ".join(sources) + "): the planner needs them")

    print("US-8.1 make targets")
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    check("etl/run_pipeline.py" in mk.split("\npipeline:")[1].split("\n\n")[0] and "scripts/db_reset.py" in mk.split("\nrebuild:")[1].split("\n\n")[0]
          and "etl/run_pipeline.py" in mk.split("\nrebuild:")[1].split("\n\n")[0],
          "make pipeline runs the pipeline; make rebuild resets the warehouse, then generates and runs it")
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
