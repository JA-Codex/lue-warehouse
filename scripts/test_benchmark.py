#!/usr/bin/env python3
"""E12 acceptance tests: the benchmark harness on the loaded warehouse (US-12.1, US-12.2).

    python scripts/test_benchmark.py

Runs python scripts/benchmark.py with 2 rounds into a temporary folder, on whichever profile is loaded:
it writes every results file, measures every query in both states, sizes every index, and leaves the
warehouse at the D20 baseline (no candidate index, no copy). Then --keep leaves the indexes in place and
sql/70_performance/03_drop_indexes.sql takes them away again. The verdicts are not judged here: they
depend on the data's size (the recorded full-profile run is checked by test_benchmark_contract.py).
"""

# ruff: noqa: E501  (messages: long lines read better)

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark  # noqa: E402

from etl.ingest.base import IngestError, connect  # noqa: E402

results: list[bool] = []
CANDIDATES = ["ix_invoice_line_due_unit", "ix_payment_due_unit", "ix_occupancy_unit_date", "ix_dim_tenant_current_segment"]


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def table(path: Path) -> list[dict]:
    """A CSV's rows; the file is closed again (Windows cannot delete an open file)."""
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def present(cur) -> tuple[list[str], bool]:
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'lue_dw' AND indexname = ANY(%s)", (CANDIDATES,))
    found = sorted(r[0] for r in cur.fetchall())
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (benchmark.COPY,))
    return found, cur.fetchone()[0]


def main() -> int:
    print("=" * 70)
    print(" E12 acceptance tests: the benchmark harness (database)")
    print("=" * 70)
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    cur = wh.cursor()
    out = Path(tempfile.mkdtemp(prefix="lue_bench_"))
    try:
        cur.execute("SELECT count(*) FROM lue_dw.fact_payment")
        if not cur.fetchone()[0]:
            print("  [FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
            return 1
        print("US-12.1 One command, the results")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark.py"), "--runs", "2", "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
        files = {f: (out / f).is_file() for f in ("baseline.csv", "after.csv", "summary.csv", "indexes.csv", "run.json")}
        check(done.returncode == 0 and all(files.values()), "python scripts/benchmark.py runs from one command and writes baseline.csv, after.csv, summary.csv, indexes.csv, run.json"
              + ("" if done.returncode == 0 else f": exit {done.returncode}: {done.stdout[-300:]} {done.stderr[-300:]}"))
        if not all(files.values()):
            return 1
        base, after = table(out / "baseline.csv"), table(out / "after.csv")
        labels = [w.label for w in benchmark.workload()]
        per = {q: (sum(1 for r in base if r["query"] == q), sum(1 for r in after if r["query"] == q)) for q in labels}
        check(all(b >= 2 and a == 2 for b, a in per.values()) and all(float(r["execution_ms"]) > 0 and float(r["total_cost"]) > 0 and r["scans"] for r in base + after),
              "every query measured in each of the 2 rounds, before and after: execution time, plan cost and scans recorded")
        plans = list((out / "plans").glob("*.txt"))
        check(len(plans) == 13 and all("Execution Time" in p.read_text(encoding="utf-8") for p in plans), f"a text plan for every query and state ({len(plans)})")
        idx = table(out / "indexes.csv")
        run = json.loads((out / "run.json").read_text(encoding="utf-8"))
        check(sorted(i["index"] for i in idx) == sorted(CANDIDATES) and all(int(i["size_bytes"]) > 0 for i in idx) and run["baseline_indexes"],
              "every candidate index sized and timed; the baseline's own indexes listed")

        print("US-12.2 The warehouse is left as it was")
        found, copy = present(cur)
        check(not found and not copy, "after a run: no candidate index and no unpartitioned copy (the D20 baseline)" + (f": left {found} copy={copy}" if found or copy else ""))
        kept = subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark.py"), "--runs", "1", "--keep", "--out", str(out / "keep")], cwd=ROOT, capture_output=True, text=True)
        found, copy = present(cur)
        check(kept.returncode == 0 and found == sorted(CANDIDATES) and not copy, "--keep leaves the four indexes in place (the copy is still dropped)")
        for s in benchmark.statements(benchmark.PERF / "03_drop_indexes.sql"):
            cur.execute(s)
        found, copy = present(cur)
        check(not found and not copy, "sql/70_performance/03_drop_indexes.sql returns the warehouse to the baseline")
    finally:
        for s in benchmark.statements(benchmark.PERF / "03_drop_indexes.sql"):
            cur.execute(s)
        wh.close()
        shutil.rmtree(out, ignore_errors=True)
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
