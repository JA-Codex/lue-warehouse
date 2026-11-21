#!/usr/bin/env python3
"""Acceptance tests for E9: the Phase 2 reports. Needs a loaded warehouse (python etl/run_pipeline.py).

    python scripts/test_reports.py [--data data]

  US-9.1  the Data Cleaning Report builds from the warehouse; its totals equal the audit tables
          (rejected = quarantine = the run log, staged = staging); every staging table's rows equal
          the rows the run log says were inserted; the answer key is fully detected; the cleaning
          evidence comes from the run that built staging
  US-9.2  the Data Quality Report builds; its reconciliation is the latest DQ-07 run, every month
          passed; its fact tests are the latest run's, 0 orphan rows, and the query it quotes is in
          sql/90_tests/02_fact_tests.sql and returns 0; the SCD continuity tests are 0; the pipeline
          run it describes completed
  Both    no count is typed into the generator: the counts it prints come from the data
The reports are written to a temporary folder; docs/reports is left as it is.
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.ingest.base import IngestError, connect  # noqa: E402
from etl.reports import facts as report_facts  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf.read_bytes()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    args = ap.parse_args()
    print("=" * 70)
    print(" E9 acceptance tests: the Phase 2 reports (database)")
    print("=" * 70)
    try:
        wh, src = connect("lue_warehouse"), connect("lue_source")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    out = Path(tempfile.mkdtemp(prefix="lue_reports_"))
    try:
        wh.autocommit = True
        cur = wh.cursor()
        if not scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment"):
            print("  [FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
            return 1
        f = report_facts.collect(cur, src.cursor(), args.data)
        done = subprocess.run([sys.executable, str(ROOT / "etl" / "reports" / "build.py"), "--data", str(args.data), "--out", str(out)],
                              cwd=ROOT, capture_output=True, text=True)  # fmt: skip
        clean, quality = out / "LUE_Data_Cleaning_Report.pdf", out / "LUE_Data_Quality_Report.pdf"

        print("US-9.1 The Data Cleaning Report")
        check(done.returncode == 0 and clean.is_file() and clean.read_bytes()[:5] == b"%PDF-" and pages(clean) >= 3,
              f"python etl/reports/build.py writes the Data Cleaning Report ({pages(clean) if clean.is_file() else 0} pages)")
        rejected = sum(r[5] for r in f.findings if r[4] == "reject")
        quarantined = scalar(cur, "SELECT count(*) FROM lue_audit.quarantine")
        check(rejected == quarantined == f.log_rejected and f.findings and sum(r[5] for r in f.findings) == scalar(cur, "SELECT count(*) FROM lue_audit.dq_result"),
              f"rows rejected: {rejected:,} in the findings = {quarantined:,} in quarantine = {f.log_rejected:,} in the run log; every finding of every batch counted")
        staged = {b[0]: b[7] for b in f.bridge}
        direct = {t: scalar(cur, f"SELECT count(*) FROM lue_staging.{t} WHERE {'allocation_source = %s' if t == 'stg_payment_allocation' else 'TRUE'}", ('S1',) if t == "stg_payment_allocation" else None) for t in staged}
        differ = [t for t in staged if not (staged[t] == direct[t] == f.log_staged.get(t))]
        check(len(staged) == 20 and not differ, f"every staging table: the rows in the report = the rows in the table = the rows the run log inserted ({len(staged)} tables)" + (f": differ {differ}" if differ else ""))
        evidence_rows = scalar(cur, "SELECT count(*) FROM lue_audit.cleaning_evidence WHERE run_id = %s", (f.stage_run,))
        check(f.stage_run is not None and evidence_rows > 0 and f.column_issues and f.table_counts,
              f"the cleaning evidence is the run that built staging (run {f.stage_run}, {evidence_rows:,} evidence rows), not an empty rerun")
        check(f.e4.expected > 0 and f.e4.detected == f.e4.expected and f.e4.false_positives == 0 and all(r[7] for r in f.e5.rows),
              f"the answer key: {f.e4.detected:,} of {f.e4.expected:,} planted defects detected, {f.e4.false_positives} false positives; every cleaning check passes")

        print("US-9.2 The Data Quality Report")
        check(done.returncode == 0 and quality.is_file() and quality.read_bytes()[:5] == b"%PDF-" and pages(quality) >= 5,
              f"python etl/reports/build.py writes the Data Quality Report ({pages(quality) if quality.is_file() else 0} pages)")
        latest = scalar(cur, "SELECT max(run_id) FROM lue_audit.reconciliation WHERE check_name LIKE 'DQ-07 %%'")
        audit = scalar(cur, "SELECT count(*) FROM lue_audit.reconciliation WHERE run_id = %s AND check_name LIKE 'DQ-07 %%'", (latest,))
        check(f.recon_run == latest and len(f.recon) == audit > 0 and all(r[5] for r in f.recon) and sum(abs(r[4]) for r in f.recon) == 0
              and {r[0] for r in f.recon} == {"billed", "paid", "tickets", "lease events"},
              f"accuracy: the DQ-07 reconciliation of run {latest}, {audit} measure-months of billed, paid, tickets and lease events, all passed, unexplained 0")
        orphans = [n for name, n, _ok in f.fact_tests if ": no orphan " in name]
        tests_sql = (ROOT / "sql" / "90_tests" / "02_fact_tests.sql").read_text(encoding="utf-8")
        quoted = scalar(cur, f.orphan_sql.split(" UNION ALL")[0].replace("SELECT 'fact_payment: no orphan tenant_key', ", "SELECT ")) if f.orphan_sql else None
        check(len(f.fact_tests) == 71 and len(orphans) == 41 and sum(orphans) == 0 and all(ok for *_r, ok in f.fact_tests)
              and f.orphan_sql and f.orphan_sql in tests_sql and quoted == 0,
              f"integrity: the fact tests of run {f.test_run}, 0 rows in 41 orphan checks; the query the report quotes is in 02_fact_tests.sql and returns {quoted}")
        scd = [(t, n) for t, n in f.dim_tests if t.split(": ")[0] in ("dim_unit", "dim_tenant", "dim_vendor", "dim_maintenance_category")]
        check(len(f.dim_tests) == 47 and scd and all(n == 0 for _t, n in f.dim_tests),
              f"SCD continuity: {len(scd)} tests of the four Type 2 dimensions and {len(f.dim_tests) - len(scd)} others, all 0 violations")
        from etl.run_pipeline import NON_CRITICAL

        check(f.pipeline_run is not None and set(f.pipeline_failed) <= NON_CRITICAL and dict(f.fact_rows)["fact_payment"] == scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment"),
              f"the pipeline run it describes (run {f.pipeline_run}) reached the reconciliation; failed steps, if any, are non-critical and named ({f.pipeline_failed or 'none'}); its fact counts are the tables'")

        print("US-9.1, US-9.2 Nothing typed")
        build = (ROOT / "etl" / "reports" / "build.py").read_text(encoding="utf-8")
        typed = [str(n) for n in {len(f.rules), len(f.bridge), f.fks, quarantined, f.e4.expected} if n > 9 and re.search(rf"(?<![\w.,]){n}(?![\w.,])", build)]
        check(not typed, "the counts the reports print (rules, tables, foreign keys, quarantine, planted defects) are not typed into the generator" + (f": {typed}" if typed else ""))
    finally:
        wh.close()
        src.close()
        shutil.rmtree(out, ignore_errors=True)
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
