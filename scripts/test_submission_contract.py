#!/usr/bin/env python3
"""US-9.3 checks that need no database (run by CI in make gen-test).

    python scripts/test_submission_contract.py

The Phase 2 checklist (docs/phase2_checklist.md) lists the plan's Appendix B deliverables in order,
each ticked, and every file it names exists; the load scripts equal the loaders; the README holds
the fresh-clone steps; and one list of CI checks (scripts/run_ci.py) serves make and Windows alike.
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import export_load_sql as export  # noqa: E402
import run_ci  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def rows(table_text: str) -> list[list[str]]:
    """The body rows of the first Markdown table in the text, as cells."""
    lines = [line for line in table_text.splitlines() if line.startswith("|")]
    return [[c.strip() for c in line.strip("|").split("|")] for line in lines[2:]]


def main() -> int:
    print("=" * 70)
    print(" US-9.3 contract tests: the Phase 2 submission (no database)")
    print("=" * 70)
    plan = (ROOT / "docs" / "plan" / "LUE_Development_Plan_v1.1.md").read_text(encoding="utf-8")
    appendix = plan.split("## Phase 2 (40 marks)")[1].split("## Phase 3")[0]
    wanted = [r[0] for r in rows(appendix)]
    checklist = (ROOT / "docs" / "phase2_checklist.md").read_text(encoding="utf-8")
    ours = rows(checklist)

    print("The checklist (plan Appendix B, Phase 2)")
    check([r[0] for r in ours] == wanted and len(wanted) == 9,
          f"docs/phase2_checklist.md lists the plan's {len(wanted)} Phase 2 deliverables, in its order")
    check(all(r[-1] == "[x]" for r in ours), "every deliverable is ticked")
    paths = sorted({p for r in ours for p in re.findall(r"`([\w./-]+/[\w./-]*|[\w-]+\.md)`", r[3])})
    missing = [p for p in paths if not (ROOT / p).exists()]
    check(len(paths) >= 30 and not missing, f"every file it names exists ({len(paths)} paths)" + (f": missing {missing}" if missing else ""))
    files = {r[0]: r[3] for r in ours}
    check(".pdf" in files["Data Cleaning Report"] and ".pdf" in files["Data Quality Report"]
          and all(".sql" in files[k] for k in ("PostgreSQL database SQL scripts", "Staging Schema SQL", "DW Schema SQL", "Dimension Load Scripts", "Fact Load Scripts"))
          and ".py" in files["ETL scripts"] and "github.com/JA-Codex/lue-warehouse" in files["GitHub repository link"],
          "each deliverable is in the brief's format: the reports PDF, the schemas and load scripts SQL, the ETL SQL and Python, a URL")

    print("The load scripts")
    stale = [p.relative_to(ROOT).as_posix() for p, render in export.FILES.items()
             if not p.is_file() or p.read_text(encoding="utf-8") != render()]  # fmt: skip
    check(not stale, "sql/30_dimensions/02_dimension_loads.sql and sql/40_facts/01_fact_loads.sql equal what the loaders run" + (f": re-export {stale}" if stale else ""))
    text = export.fact_sql() + export.dimension_sql()
    check(not re.search(r"%\(\w+\)s", text) and text.count("BEGIN;") == 2 and text.count("COMMIT;") == 2,
          "both files run as they are in psql (no loader placeholders left; one transaction each)")

    print("The README")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    fresh = readme.split("## Run it from a fresh clone")[1].split("\n## ")[0] if "## Run it from a fresh clone" in readme else ""
    steps = ["git clone", "requirements.txt", ".env", "scripts/test_connection.py", "scripts/run_ci.py",
             "scripts/db_reset.py", "etl/run_pipeline.py --profile small", "etl/reports/build.py",
             "scripts/test_reports.py", "scripts/test_load_sql.py", "phase2-submission"]
    absent = [s for s in steps if s not in fresh]
    check(fresh and not absent, "the README's fresh-clone section: prerequisites, setup, rebuild, tests, reports and the tag" + (f": missing {absent}" if absent else ""))
    check("docs/phase2_checklist.md" in readme and "## Names" in readme and "US-10.1" in readme.split("## Names")[1],
          "the README links the checklist and maps the brief's names (alias views: Phase 3, US-10.1)")

    print("One list of CI checks")
    contracts = sorted(p.stem for p in (ROOT / "scripts").glob("test_*_contract.py"))
    listed = {Path(c[1]).stem for cs in run_ci.GROUPS.values() for c in cs if len(c) > 1}
    check(set(contracts) <= listed, f"scripts/run_ci.py runs every contract test ({len(contracts)})"
          + (f": not run {sorted(set(contracts) - listed)}" if set(contracts) - listed else ""))
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    check("scripts/run_ci.py" in mk.split("\ntest:")[1].split("\n\n")[0] and "scripts/export_load_sql.py" in str(run_ci.GROUPS["contract"]),
          "make test runs scripts/run_ci.py (the same checks without make, on Windows); the contract group checks the load scripts")
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
