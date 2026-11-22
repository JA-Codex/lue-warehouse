#!/usr/bin/env python3
"""E12 checks that need no database (run by CI in make gen-test).

    python scripts/test_benchmark_contract.py

  US-12.1  the workload: Q1 and Q7 as answered, and the four benchmark queries, each with a stated change;
           the harness is one command that writes the baseline and after CSVs
  US-12.2  every candidate index has a purpose, a benchmark query that tests it, and a drop; none is in the
           deploy (D20); the recorded run (docs/evidence/us-12.2) meets the plan: at least two queries
           improved in time and cost, at least one change that did not help, every index sized and its use
           measured, the baseline stable within the stated tolerance
  US-12.3  the Indexing Report builds from the recorded run (into a temporary folder) and states D20
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import csv
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark  # noqa: E402

from etl.reports import indexing  # noqa: E402

PERF = ROOT / "sql" / "70_performance"
EVIDENCE = ROOT / "docs" / "evidence" / "us-12.2"
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def rows(name: str) -> list[dict]:
    with (EVIDENCE / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    print("=" * 70)
    print(" E12 contract tests: the benchmark and the Indexing Report (no database)")
    print("=" * 70)
    print("US-12.1 The harness and the workload")
    works = benchmark.workload()
    labels = [w.label for w in works]
    analytical = (ROOT / "sql" / "60_analytics" / "analytical.sql").read_text(encoding="utf-8")
    check(labels == ["B1", "B2", "B3", "B4", "B5", "B6"] and works[0].sql in analytical and works[2].sql in analytical,
          "six queries: Q1 (B1) and Q7 (B3) exactly as in analytical.sql, the plan's three heavy queries plus B2, B4, B5, B6")
    check(all(w.change for w in works) and [w.label for w in works if w.partitioning] == ["B4"],
          "each states the change it tests; B4 compares the partitioned fact with an unpartitioned copy")
    doc = benchmark.__doc__
    check(all(s in doc for s in ("python scripts/benchmark.py", "VACUUM ANALYZE", "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)", "baseline.csv", "after.csv")),
          "one command: VACUUM ANALYZE, warm-up, EXPLAIN (ANALYZE, BUFFERS) runs, results in baseline.csv and after.csv")

    print("US-12.2 The candidate indexes")
    creates = benchmark.statements(PERF / "02_indexes.sql")
    drops = " ".join(benchmark.statements(PERF / "03_drop_indexes.sql"))
    names = [re.search(r"IF NOT EXISTS (\w+)", s).group(1) for s in creates]
    text = (PERF / "02_indexes.sql").read_text(encoding="utf-8")
    purposed = [n for n in names if re.search(rf"-- Purpose: .*?\n(?:--.*\n)*CREATE INDEX IF NOT EXISTS {n}\b", text)]
    tested = [n for n in names if any(n in w.change for w in works)]
    check(len(names) == 4 and purposed == names and tested == names and all(f"lue_dw.{n}" in drops for n in names) and benchmark.COPY in drops,
          f"{len(names)} candidate indexes, each with a purpose, tested by a benchmark query and dropped by 03_drop_indexes.sql (with the copy)")
    check(any("(unit_key, snapshot_date_key)" in s for s in creates) and any("(due_date_key, unit_key)" in s for s in creates)
          and any("WHERE is_current" in s for s in creates),
          "the plan's candidates: (unit_key, snapshot_date_key) on the occupancy fact, (due_date_key, unit_key) on payments, a partial index on current SCD rows")
    ddl = " ".join(p.read_text(encoding="utf-8") for d in ("10_ddl", "20_staging", "50_reporting") for p in (ROOT / "sql" / d).glob("*.sql"))
    deploy = (ROOT / "scripts" / "db_deploy.py").read_text(encoding="utf-8")
    check(not any(n in ddl for n in names) and "70_performance" not in deploy.split("DDL_DIRS =")[1].split("\n")[0],
          "none is in the deploy: the warehouse stays at the D20 baseline (primary-key and unique-constraint indexes)")

    print("US-12.2 The recorded run (docs/evidence/us-12.2)")
    summary, idx = rows("summary.csv"), rows("indexes.csv")
    run = json.loads((EVIDENCE / "run.json").read_text(encoding="utf-8"))
    improved = [s for s in summary if s["verdict"] == "improved"]
    check(len(improved) >= 2 and all(float(s["after_ms"]) < float(s["before_ms"]) and float(s["after_cost"]) < float(s["before_cost"]) and s["runs_apart"] == "True" for s in improved),
          f"{len(improved)} queries improved in both execution time and cost, every run after faster than every run before ({', '.join(s['query'] for s in improved)})")
    nogain = [s["query"] for s in summary if s["verdict"] == "no gain"]
    check(nogain, f"at least one change did not help, and is explained in the report: {', '.join(nogain)}")
    check(all(int(i["size_bytes"]) > 0 and float(i["build_ms"]) > 0 and i["used_by"] for i in idx) and len(idx) == len(names),
          "every index has a measured size, build time and use (the queries whose plans used it)")
    check(all(s["stable"] == "True" for s in summary) and run["runs"] >= 5,
          f"the runs are stable within the stated tolerance ({run['tolerance']}), {run['runs']} interleaved rounds")
    base = run["baseline_indexes"]
    check(base and all(b["kind"].startswith(("primary key", "unique")) for b in base),
          f"the baseline held primary-key and unique indexes only ({len(base)} on the measured tables; D20)")
    plans = {p.name for p in (EVIDENCE / "plans").glob("*.txt")}
    check(all(f"{w.label}_baseline_" in " ".join(plans) and f"{w.label}_after_" in " ".join(plans) for w in works),
          f"a plan before and after for every query ({len(plans)} plans)")

    print("US-12.3 The Indexing Report")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / indexing.NAME
        indexing.report(EVIDENCE, out)
        built = out.read_bytes()
    committed = ROOT / "docs" / "reports" / indexing.NAME
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", built))
    check(built[:5] == b"%PDF-" and pages >= 5 and committed.is_file(),
          f"it builds from the recorded run ({pages} pages) and is committed in docs/reports")
    check(set(indexing.WHY) == set(labels) and all(s["verdict"] in indexing.WHY[s["query"]] for s in summary),
          "every query's measured verdict has its explanation; the report refuses to build otherwise")
    src = Path(indexing.__file__).read_text(encoding="utf-8")
    check("D20" in src and "primary-key and unique-constraint indexes only" in src, "the report states the D20 baseline: primary-key and unique-constraint indexes were already there")
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
