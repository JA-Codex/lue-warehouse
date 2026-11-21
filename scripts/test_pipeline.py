#!/usr/bin/env python3
"""Acceptance tests for E8: the pipeline. Needs PostgreSQL (the superuser of .env, as db_reset).

    python scripts/test_pipeline.py

  US-8.1  from an empty warehouse (scripts/db_reset.py) one command generates the small profile
          into a temporary folder and loads the whole warehouse; the run log holds every step of
          that one run with its counts and a final status; lineage links the sources to bronze,
          staging, the dimensions and the facts; --only and --from-step run just their stages; a
          failed critical step stops the run with exit 1 and names where to resume; a failed
          non-critical step (S5 weather) is reported and the run goes on
  US-8.2  by month, source = warehouse + quarantined for billed, paid, tickets and lease events,
          every row in lue_audit.reconciliation passed; a fact row removed and an amount changed
          fail exactly their months and the step; reloading the facts restores the pass
The warehouse is left loaded with the small profile (rerun the pipeline on your own data after).
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl import reconcile  # noqa: E402
from etl import run_pipeline as p  # noqa: E402
from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402

results: list[bool] = []
PIPELINE = [sys.executable, str(ROOT / "etl" / "run_pipeline.py")]


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def run(args: list[str]) -> tuple[int, str]:
    done = subprocess.run(PIPELINE + args, cwd=ROOT, capture_output=True, text=True)
    return done.returncode, done.stdout


def last_run(cur) -> int:
    return scalar(cur, "SELECT max(run_id) FROM lue_audit.etl_run_log")


def one_command(cur, data: Path) -> None:
    print("US-8.1 One command: an empty warehouse to a loaded one")
    reset = subprocess.run([sys.executable, str(ROOT / "scripts" / "db_reset.py")], cwd=ROOT, capture_output=True, text=True)
    empty = scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment") + scalar(cur, "SELECT count(*) FROM lue_dw.dim_tenant WHERE tenant_key > 0")
    check(reset.returncode == 0 and empty == 0, "scripts/db_reset.py leaves an empty warehouse (no tenants, no facts)")
    code, out = run(["--profile", "small", "--data", str(data)])
    print("\n".join("    " + line for line in out.splitlines() if line.startswith("  ") and not line.startswith("      ")))
    rid = last_run(cur)
    cur.execute("SELECT step, status, rows_read, rows_inserted, rows_updated, rows_rejected, ended_at IS NOT NULL FROM lue_audit.etl_run_log WHERE run_id = %s", (rid,))
    log = cur.fetchall()
    steps = {s for s, *_ in log}
    check(code == 0 and "RESULT:" in out and (data / "run_manifest.json").is_file(),
          f"python etl/run_pipeline.py --profile small generates the data and runs every stage (exit {code})")
    expected = {"generate", "setup", "deploy", "reference", "source", "validate_dq", "stage_business", "dim_date_holidays", "fact_tests", "reconcile_dq07"}
    check(expected <= steps and len(log) >= 45 and all(done and status in ("Success", "Warning") for _s, status, *_r, done in log),
          f"the run log holds all {len(log)} steps of run {rid}, each ended with a final status (Success or Warning)")
    by = {s: (rr, ri, ru, rj) for s, _st, rr, ri, ru, rj, _d in log}
    check(by["ingest_s1_pms"][1] > 0 and by["stage_tenant"][1] > 0 and by["dim_tenant"][1] > 0 and by["fact_payment"][1] > 0
          and by["fact_unit_occupancy_daily"][1] > 0 and by["validate_dq"][3] > 0 and by["fact_tests"][0] == 71,
          f"with their counts: e.g. S1 landed {by['ingest_s1_pms'][1]:,}, {by['validate_dq'][3]:,} rows rejected, "
          f"{by['dim_tenant'][1]:,} tenants, {by['fact_payment'][1]:,} payments, 71 fact tests read")
    facts = {t: scalar(cur, f"SELECT count(*) FROM lue_dw.{t}") for t in ("fact_rent_invoice_line", "fact_payment", "fact_unit_occupancy_daily", "fact_maintenance_request", "fact_lease_event", "fact_vacancy_incentive_coverage")}
    check(all(facts.values()), "every fact is loaded: " + ", ".join(f"{k.replace('fact_', '')} {v:,}" for k, v in facts.items()))
    cur.execute("SELECT layer_path, count(*) FROM lue_audit.lineage GROUP BY 1")
    paths = dict(cur.fetchall())
    check(all(f"S{i} -> bronze" in paths for i in range(1, 7)) and paths.get("bronze -> staging", 0) >= 20
          and paths.get("staging -> dimension", 0) > 0 and paths.get("staging -> fact", 0) > 0,
          "lineage links each source to bronze, bronze to staging, staging to the dimensions and the facts: "
          + ", ".join(f"{k} {v}" for k, v in sorted(paths.items())))


def options(cur, data: Path) -> None:
    print("US-8.1 --only and --from-step")
    code, out = run(["--data", str(data), "--only", "facts"])
    cur.execute("SELECT array_agg(step ORDER BY step) FROM lue_audit.etl_run_log WHERE run_id = %s", (last_run(cur),))
    steps = cur.fetchone()[0]
    check(code == 0 and all(s.startswith("fact_") for s in steps) and len(steps) == 7, f"--only facts: just the 6 facts and their tests ({len(steps)} steps)")
    code, out = run(["--data", str(data), "--skip-generate", "--from-step", "dimensions"])
    cur.execute("SELECT array_agg(DISTINCT left(step, 4)) FROM lue_audit.etl_run_log WHERE run_id = %s", (last_run(cur),))
    kinds = set(cur.fetchone()[0])
    check(code == 0 and kinds == {"dim_", "fact", "reco"}, "--from-step dimensions: the dimensions, the facts and the reconciliation, nothing before")


def reconciliation(cur) -> None:
    print("US-8.2 Source-to-warehouse reconciliation (DQ-07)")
    code, out = run(["--only", "reconcile"])
    rid = last_run(cur)
    cur.execute("SELECT count(*), count(*) FILTER (WHERE passed), count(*) FILTER (WHERE source_value <> warehouse_value OR difference <> 0) "
                "FROM lue_audit.reconciliation WHERE run_id = %s AND check_name LIKE 'DQ-07 %%'", (rid,))
    rows, passed, off = cur.fetchone()
    src = connect("lue_source")
    try:
        with src.cursor() as sc:
            lines = reconcile.reconcile(cur, sc)
    finally:
        src.close()
    by = {m: [x for x in lines if x.measure == m] for m in reconcile.BY_NAME}
    quarantined = {m: sum(x.quarantined for x in ls) for m, ls in by.items()}
    check(code == 0 and rows == passed == len(lines) and off == 0 and all(by.values()),
          f"every measure and month reconciles: {len(lines)} rows in lue_audit.reconciliation, all passed, unexplained variance 0")
    check(quarantined["tickets"] > 0 and quarantined["lease events"] > 0
          and all(sum(x.source for x in ls) == sum(x.warehouse + x.quarantined for x in ls) for ls in by.values()),
          "source = warehouse + quarantined: " + ", ".join(f"{m} {sum(x.source for x in ls):,.0f} = {sum(x.warehouse for x in ls):,.0f} + {quarantined[m]:,.0f}" for m, ls in by.items()))
    # Deliberate failures: a fact row removed, an amount changed. Exactly that month fails, the run exits 1.
    cur.execute("SELECT lease_event_sk, event_date_key FROM lue_dw.fact_lease_event ORDER BY lease_event_sk LIMIT 1")
    sk, key = cur.fetchone()
    cur.execute("DELETE FROM lue_dw.fact_lease_event WHERE lease_event_sk = %s", (sk,))
    cur.execute("UPDATE lue_dw.fact_rent_invoice_line SET billed_amount = billed_amount + 5, net_amount = net_amount + 5 "
                "WHERE invoice_line_sk = (SELECT max(invoice_line_sk) FROM lue_dw.fact_rent_invoice_line) RETURNING invoice_date_key")
    billed_key = cur.fetchone()[0]
    code, out = run(["--only", "reconcile"])  # the facts are restored below, by reloading them from staging
    rid = last_run(cur)
    cur.execute("SELECT check_name, difference FROM lue_audit.reconciliation WHERE run_id = %s AND NOT passed ORDER BY 1", (rid,))
    failed = cur.fetchall()
    status = scalar(cur, "SELECT status FROM lue_audit.etl_run_log WHERE run_id = %s AND step = %s", (rid, reconcile.STEP))
    month = lambda k: f"{str(k)[:4]}-{str(k)[4:6]}"  # noqa: E731
    want = [(f"DQ-07 billed {month(billed_key)}", 5), (f"DQ-07 lease events {month(key)}", -1)]
    check(code == 1 and status == "Failed" and [(n, int(d)) for n, d in failed] == sorted(want),
          f"a fact row removed and an amount changed by PKR 5: exactly those months fail ({', '.join(n for n, _ in failed)}), the step Failed, exit 1")
    code, out = run(["--only", "facts,reconcile"])
    rid = last_run(cur)
    ok = scalar(cur, "SELECT count(*) FILTER (WHERE NOT passed) FROM lue_audit.reconciliation WHERE run_id = %s AND check_name LIKE 'DQ-07 %%'", (rid,))
    check(code == 0 and ok == 0, "reloading the facts from staging restores them, and the reconciliation passes again")


def failures(cur, data: Path) -> None:
    print("US-8.1 A failed critical step stops the run")
    code, out = run(["--skip-generate", "--from-step", "source", "--data", str(data / "missing")])
    rid = last_run(cur)
    cur.execute("SELECT step, status FROM lue_audit.etl_run_log WHERE run_id = %s", (rid,))
    log = dict(cur.fetchall())
    check(code == 1 and log == {"source": "Failed"} and "STOPPED at source" in out and "--from-step source" in out,
          "a missing data folder fails the source stage: the run stops there (no ingest, no later stage), exit 1, and says how to resume")
    print("US-8.1 A failed non-critical step is reported, the run goes on")
    real = ingest.steps

    def weather_down(data_dir):
        table = real(data_dir)

        def fail(_step):
            raise IngestError("weather cache unreadable (test)")

        table["S5"] = ("ingest_s5_weather", fail)
        return table

    ingest.steps = weather_down
    try:
        rid, done, stopped = p.pipeline("small", 3004, p.select(["ingest", "validate", "transform", "dimensions", "facts", "reconcile"], None, True), data)
    finally:
        ingest.steps = real
    cur.execute("SELECT step, status FROM lue_audit.etl_run_log WHERE run_id = %s", (rid,))
    log = dict(cur.fetchall())
    check(stopped is None and log.get("ingest_s5_weather") == "Failed" and log.get("fact_tests") == "Success" and log.get("reconcile_dq07") == "Success",
          f"S5 weather Failed (it may be cut, D19), yet every later stage ran: fact_tests {log.get('fact_tests')}, reconcile {log.get('reconcile_dq07')}")


def main() -> int:
    print("=" * 70)
    print(" E8 acceptance tests: the pipeline (database)")
    print("=" * 70)
    data = Path(tempfile.mkdtemp(prefix="lue_pipeline_"))
    try:
        try:
            wh = connect("lue_warehouse")
        except IngestError as exc:
            print(f"  [FAIL] {exc}")
            return 1
        wh.autocommit = True
        try:
            with wh.cursor() as cur:
                one_command(cur, data)
                options(cur, data)
                reconciliation(cur)
                failures(cur, data)
        finally:
            wh.close()
    finally:
        shutil.rmtree(data, ignore_errors=True)
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
