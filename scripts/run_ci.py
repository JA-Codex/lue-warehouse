#!/usr/bin/env python3
"""Everything CI runs, on any operating system (Windows has no make): python scripts/run_ci.py

    python scripts/run_ci.py            every group, in order; stops at the first failure
    python scripts/run_ci.py gen-test   some groups: lint, sqlcheck, manifest, contract, gen-test

make test, make lint, make gen-test and the other targets call this script, so the list of checks
lives here only. No database is needed. Exit 0 when every check passed, 1 at the first failure.
"""

# ruff: noqa: E501  (the list of checks reads better one group to a line)

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

GROUPS: dict[str, list[list[str]]] = {
    "lint": [[PY, "-m", "ruff", "check", "etl", "scripts"]],
    "sqlcheck": [[PY, "scripts/ci_checks.py", "--sql"]],
    "manifest": [[PY, "scripts/ci_checks.py", "--manifest"]],
    "contract": [[PY, "scripts/check_contract.py"], [PY, "scripts/export_load_sql.py", "--check"],
                 [PY, "scripts/export_portal_sql.py", "--check"]],
    "gen-test": [[PY, f"scripts/{name}.py"] for name in (
        "test_generator", "test_master_data", "test_leases", "test_payments", "test_tickets", "test_weather",
        "test_defects", "test_ingest_contract", "test_quality_contract", "test_staging_contract",
        "test_dim_load_contract", "test_fact_load_contract", "test_pipeline_contract", "test_submission_contract", "test_reporting_contract", "test_analytics_contract", "test_benchmark_contract", "test_powerbi_contract", "test_frontend")],
}  # fmt: skip


def main(argv: list[str]) -> int:
    unknown = [g for g in argv if g not in GROUPS]
    if unknown:
        print(f"no such group: {', '.join(unknown)} (groups: {', '.join(GROUPS)})")
        return 2
    commands = [c for g in (argv or GROUPS) for c in GROUPS[g]]
    start = time.monotonic()
    for n, command in enumerate(commands, 1):
        shown = " ".join(["python", *command[1:]])
        print(f">> [{n}/{len(commands)}] {shown}", flush=True)
        if subprocess.run(command, cwd=ROOT).returncode != 0:
            print(f"FAILED: {shown}")
            return 1
    print(f"ALL PASSED: {len(commands)} checks in {time.monotonic() - start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
