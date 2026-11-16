#!/usr/bin/env python3
"""Acceptance tests for E4 (US-4.1 to US-4.4): the data quality engine. Needs the database.

    python scripts/db_deploy.py
    python scripts/db_load_source.py
    python scripts/test_quality.py

Works on your data folder (with the US-2.6 defects: a plain python etl/generate_data.py). It
re-ingests it into a fresh bronze, validates, and checks:
  US-4.1  the catalogue drives the engine (a rule added to a copy of the file changes the result,
          no code edited), validating twice gives the same counts, a failed validation changes
          nothing, quarantine rows carry the row, the check and a readable reason;
  US-4.2  and US-4.3: every rule of the catalogue on a known bad row (caught by that rule) and a
          known good row (no finding at all);
  US-4.4  the comparison with the answer key: every planted defect in scope detected, no false
          positive; then a CLEAN control batch (a clean generation in a temporary folder, loaded
          into src_pms and bronze): zero rejections, zero warnings.
At the end src_pms and bronze hold your data folder again, validated.
"""

import json
import subprocess
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402
from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402
from etl.quality import answer_key, engine  # noqa: E402
from etl.quality import run as quality  # noqa: E402

DATA = ROOT / "data"
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def reset_bronze(cur) -> None:
    for t in engine.bronze_tables(cur):
        cur.execute(f"TRUNCATE lue_staging.{t}")
    cur.execute("TRUNCATE lue_audit.file_load, lue_audit.dq_result")
    cur.execute("DELETE FROM lue_audit.quarantine")
    cur.execute("DELETE FROM lue_audit.etl_watermark WHERE source_system = 'S1'")


def load_and_ingest(cur, data: Path) -> bool:
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "db_load_source.py"), "--data",
                          str(data)], capture_output=True, text=True)  # fmt: skip
    if out.returncode != 0:
        print(out.stdout[-2000:], out.stderr[-2000:])
        return False
    reset_bronze(cur)
    _run_id, res, checks = ingest.run(data, list(ingest.SOURCES))
    return all(r.status == "Success" for r in res) and all(c[4] for c in checks)


def counts(cur, run_id: int) -> dict:
    cur.execute("SELECT rule_id, severity, count(*) FROM lue_audit.dq_result WHERE run_id = %s "
                "GROUP BY 1, 2", (run_id,))  # fmt: skip
    return {(r, s): n for r, s, n in cur.fetchall()}


# ----------------------------------------------------------------------------- US-4.1
def engine_tests(cur, tmp: Path) -> int:
    print("US-4.1 Catalogue and engine")
    rules = engine.load_rules()
    checks_order = [r.check for r in rules]
    check(len(rules) >= 100 and checks_order == sorted(checks_order),
          f"the catalogue (etl/quality/rules.toml) has {len(rules)} rules, run in the order "
          "DQ-01 to DQ-06")  # fmt: skip
    run1, res1, s1 = quality.validate()
    q1 = scalar(cur, "SELECT count(*) FROM lue_audit.quarantine")
    run2, res2, s2 = quality.validate()
    c2 = counts(cur, run2)
    q = scalar(cur, "SELECT count(*) FROM lue_audit.quarantine")
    check(res1.status in ("Success", "Warning") and s1.by_rule == s2.by_rule and q1 == q
          and q == s2.rejected and sum(c2.values()) == s2.rejected + s2.warned,
          f"validating twice gives identical counts ({s1.rejected:,} rejected, {s1.warned:,} "
          f"warnings) and the quarantine holds each rejection once ({q:,})")  # fmt: skip
    cur.execute("SELECT count(*), count(DISTINCT (source_table, row_id)) FROM lue_audit.dq_result "
                "WHERE run_id = %s AND severity = 'reject'", (run2,))  # fmt: skip
    n, distinct = cur.fetchone()
    check(n == distinct, "a row is rejected at most once: by the first rule it fails")
    cur.execute("SELECT step, status, rows_read, rows_rejected FROM lue_audit.etl_run_log WHERE "
                "run_id = %s", (run2,))  # fmt: skip
    step = cur.fetchone()
    check(step == ("validate_dq", res2.status, s2.rows_checked, s2.rejected),
          f"the run log has the step: {step[0]}, {step[1]}, {step[2]:,} rows checked, "
          f"{step[3]:,} rejected")  # fmt: skip

    cur.execute("SELECT q.record, q.check_name, q.rejection_reason, q.source_table, q.batch_id "
                "FROM lue_audit.quarantine q WHERE q.run_id = %s ORDER BY q.quarantine_id "
                "LIMIT 1", (run2,))  # fmt: skip
    record, check_name, reason, table, batch = cur.fetchone()
    cur.execute(f"SELECT to_jsonb(b) FROM lue_staging.{table} b WHERE row_id = %s",
                (record["row_id"],))  # fmt: skip
    check(cur.fetchone()[0] == record and record["batch_id"] == batch
          and check_name in engine.CHECKS.values() and reason.startswith("[")
          and (" = " in reason or "is empty" in reason),
          f"a quarantine row holds the bronze row as JSON, the check and a reason: "
          f"{check_name}: {reason[:70]}")  # fmt: skip

    extra = tmp / "rules_plus_one.toml"
    extra.write_text(engine.RULES_FILE.read_text(encoding="utf-8") + '''
[[rule]]
id = "TEST-SHOP-01"
check = "DQ-04"
table = "brz_unit"
type = "in_list"
columns = ["unit_type"]
values = ["Apartment", "Office"]
severity = "warn"
message = "a test rule: shops are reported"
''', encoding="utf-8")
    run3, _res3, s3 = quality.validate(extra)
    shops = scalar(cur, "SELECT count(*) FROM lue_staging.brz_unit b WHERE b.unit_type NOT IN "
                        "('Apartment', 'Office') AND btrim(b.unit_type) <> '' AND NOT EXISTS "
                        "(SELECT 1 FROM lue_audit.dq_result r WHERE r.run_id = %s AND "
                        "r.source_table = 'brz_unit' AND r.row_id = b.row_id AND "
                        "r.severity = 'reject' AND r.rule_id <> 'TEST-SHOP-01')", (run3,))
    c3 = counts(cur, run3)
    check(c3.get(("TEST-SHOP-01", "warn"), 0) == shops > 0
          and {k: v for k, v in c3.items() if k[0] != "TEST-SHOP-01"} == c2,
          f"a rule added to a copy of the catalogue works with no code change ({shops} "
          "findings) and changes nothing else")  # fmt: skip

    broken = tmp / "rules_broken.toml"
    broken.write_text(engine.RULES_FILE.read_text(encoding="utf-8") + '''
[[rule]]
id = "TEST-BROKEN-01"
check = "DQ-06"
table = "brz_unit"
type = "condition"
sql = "lue_audit.no_such_function(b.unit_type)"
severity = "reject"
message = "a test rule that cannot run"
bad = { unit_type = "x" }
''', encoding="utf-8")
    before = scalar(cur, "SELECT count(*) FROM lue_audit.dq_result")
    run4, res4, s4 = quality.validate(broken)
    after = scalar(cur, "SELECT count(*) FROM lue_audit.dq_result")
    check(res4.status == "Failed" and s4 is None and after == before,
          "a validation that fails (a rule with bad SQL) is rolled back: the earlier findings "
          "stay as they were")  # fmt: skip
    try:
        bad = tmp / "rules_bad.toml"
        bad.write_text('[[rule]]\nid = "X"\ncheck = "DQ-09"\ntable = "units"\ntype = "nope"\n'
                       'severity = "maybe"\nmessage = "m"\n', encoding="utf-8")  # fmt: skip
        engine.load_rules(bad)
        message = ""
    except engine.RuleError as exc:
        message = str(exc)
    check(all(w in message for w in ("check must be", "type must be", "severity must be",
                                     "table must be")),
          "a malformed rule is refused with every problem named")  # fmt: skip
    run5, _r, _s = quality.validate()
    return run5


# ----------------------------------------------------------------------------- US-4.2 / 4.3
def bad_value(rule: engine.Rule, base: dict) -> dict:
    """The one change that should make a good row fail this rule (fixtures)."""
    if rule.bad:
        return dict(rule.bad)
    if not rule.columns:
        return {}
    c = rule.columns[0]
    if rule.type == "number_range":
        return {c: str(int(rule.max) * 10 + 1)}
    if rule.type == "date_range":
        clock = " 10:00:00" if ":" in str(base.get(c) or "") else ""
        return {c: "1999-01-01" + clock}
    return {c: {"required": "", "numeric": "not-a-number", "integer": "1.5", "date": "2025-02-30",
                "timestamp": "2025-13-01 10:00:00", "boolean": "yes", "in_list": "ZZZ",
                # unique per rule, so one rule's bad row is never another's missing reference
                "reference": str(900000000 + rule.position) if str(base.get(c) or "").isdigit()
                else f"NO-SUCH-{rule.id}",
    }[rule.type]}  # fmt: skip


def insert_rows(cur, table: str, columns: list[str], rows: list) -> None:
    for batch, row in rows:
        values = [batch if c == "batch_id" else row.get(c) for c in columns]
        cur.execute(f"INSERT INTO lue_staging.{table} ({', '.join(columns)}) VALUES "
                    f"({', '.join(['%s'] * len(columns))})", values)  # fmt: skip


def cast_tests(cur) -> None:
    print("US-4.2 The safe casts of DQ-02")
    cur.execute("SELECT lue_audit.try_date('2024-12-08'), lue_audit.try_date('08/12/2024'), "
                "lue_audit.try_date('2025-02-30'), lue_audit.try_date('TBD'), "
                "lue_audit.try_date('2025-12-32'), lue_audit.try_date('12/13/2024')")  # fmt: skip
    iso, day_first, feb30, tbd, day32, month13 = cur.fetchone()
    check(iso == day_first == date(2024, 12, 8) and feb30 is None and tbd is None
          and day32 is None and month13 is None,
          "dates: 2024-12-08 and the day-first 08/12/2024 parse (the same day; repaired in "
          "staging); 2025-02-30, TBD, day 32 and month 13 do not")  # fmt: skip
    cur.execute("SELECT lue_audit.try_numeric('-12.50'), lue_audit.try_numeric('4850'), "
                "lue_audit.try_numeric('Rs. 8,300'), lue_audit.try_numeric('8300/-'), "
                "lue_audit.try_numeric(''), lue_audit.try_timestamp('2023-07-01T12:26:00'), "
                "lue_audit.try_timestamp('2023-07-01 12:26'), "
                "lue_audit.try_timestamp('2025-13-01 10:00:00')")  # fmt: skip
    a, b, c, d, e, ts1, ts2, ts3 = cur.fetchone()
    check(a == Decimal("-12.50") and b == 4850 and c is None and d is None and e is None,
          "numbers: -12.50 and 4850 parse; 'Rs. 8,300', '8300/-' and '' do not")
    check(ts1 == ts2 == datetime(2023, 7, 1, 12, 26) and ts3 is None,
          "timestamps: with T or a space, with or without seconds; month 13 does not")


def fixture_tests(cur, run_id: int) -> None:
    print("US-4.2 and US-4.3 Every rule on a known bad and a known good row")
    rules = engine.load_rules()
    tables = engine.bronze_tables(cur)
    plan = {}  # rule id -> (rule, base row) ; None when bronze has no good row for it
    for i, r in enumerate(rules):
        where = " AND ".join(f"({w})" for w in (r.where, r.fixture_where) if w) or "TRUE"
        clean = (f"FROM lue_staging.{r.table} b WHERE {where} AND NOT EXISTS (SELECT 1 FROM "
                 "lue_audit.dq_result x WHERE x.run_id = %s AND x.source_table = %s AND "
                 "x.row_id = b.row_id)")  # fmt: skip
        n = scalar(cur, f"SELECT count(*) {clean}", (run_id, r.table))
        if not n:
            plan[r.id] = (r, None)
            continue
        # A different real row for each rule (where the table has enough), so that one rule's
        # bad row does not meet another rule's copy of the same row.
        cur.execute(f"SELECT to_jsonb(b) {clean} ORDER BY b.row_id OFFSET %s LIMIT 1",
                    (run_id, r.table, i % n))  # fmt: skip
        plan[r.id] = (r, cur.fetchone()[0])

    def phase(kind: str) -> dict:
        """Insert every rule's good (or bad) rows, each rule in its own batch, and validate them
        together. Good and bad rows are never in bronze at the same time."""
        batch_of, batches = {}, []
        for rid, (r, base) in plan.items():
            if base is None:
                continue
            batch = scalar(cur, "SELECT nextval('lue_audit.seq_batch_id')")
            batch_of[rid] = batch
            batches.append(batch)
            cols = [c for c in tables[r.table] if c != "row_id"]
            if kind == "good":
                rows = [base]
            elif r.type == "duplicate_exact":
                rows = [base, base]
            elif r.type == "duplicate_conflict":
                other = next(c for c in cols if c not in r.key and c not in engine.METADATA)
                rows = [base, dict(base) | {other: f"{base[other]} (changed)"}]
            else:
                rows = [dict(base) | bad_value(r, base)]
            insert_rows(cur, r.table, cols, [(batch, row) for row in rows])
        run, res, _summary = quality.validate(batches=batches)
        cur.execute("SELECT batch_id, rule_id, severity, reason FROM lue_audit.dq_result WHERE "
                    "run_id = %s", (run,))  # fmt: skip
        found = {}
        for b, rule_id, sev, reason in cur.fetchall():
            found.setdefault(b, []).append((rule_id, sev, reason))
        for t in tables:
            cur.execute(f"DELETE FROM lue_staging.{t} WHERE batch_id = ANY(%s)", (batches,))
        cur.execute("DELETE FROM lue_audit.dq_result WHERE batch_id = ANY(%s)", (batches,))
        cur.execute("DELETE FROM lue_audit.quarantine WHERE batch_id = ANY(%s)", (batches,))
        print(f"         {kind} rows: validation run {run}, {res.status}")
        return {rid: found.get(b, []) for rid, b in batch_of.items()}

    good, bad = phase("good"), phase("bad")
    missing = [rid for rid, (_r, base) in plan.items() if base is None]
    problems = []
    for rid, (r, base) in plan.items():
        if base is None:
            continue
        if good[rid]:
            problems.append(f"{rid} good row flagged by {good[rid][0][0]}")
        # The rule only fires on a row no earlier rule rejected, so a finding of this rule on
        # the bad row also shows that no earlier rule took it.
        if not any(x[0] == rid and x[1] == r.severity for x in bad[rid]):
            problems.append(f"{rid} bad row: {[x[0] for x in bad[rid]] or 'nothing found'}")
    for p in problems[:12]:
        print(f"         {p}")
    tested = len(rules) - len(missing)
    check(not missing, f"a good row exists in bronze for every rule ({tested} of {len(rules)})"
          + (f"; none for {', '.join(missing)}" if missing else ""))  # fmt: skip
    check(not any(" bad row" in p for p in problems),
          f"{tested} rules each catch their bad row, and no earlier rule takes it")
    check(not any(" good row" in p for p in problems),
          f"{tested} good rows pass every rule (no finding at all)")
    sample = [x[2] for x in bad.get("S4-TKT-03", []) if x[0] == "S4-TKT-03"]
    check(bool(sample) and "estimate = 'not-a-number'" in sample[0],
          f"reasons show the column and the value: {sample[0] if sample else ''}")


# ----------------------------------------------------------------------------- US-4.4
def answer_key_tests(cur, tmp: Path) -> None:
    print("US-4.4 Against the answer key, and a clean control batch")
    run_id, res, summary = quality.validate()
    key = DATA / "answer_key" / "defects_answer_key.csv"
    cmp = answer_key.compare(cur, key, run_id)
    out = tmp / "dq_validation.csv"
    answer_key.write(cmp, out)
    planted = [r for r in cmp.rows if r[0] == "planted"]
    check(cmp.expected > 0 and cmp.detected == cmp.expected,
          f"detection is 100%: {cmp.detected:,} of {cmp.expected:,} planted defects in scope, "
          f"in {len(planted)} groups (source, table, type, rule)")  # fmt: skip
    check(cmp.false_positives == 0,
          "no false positive: every finding is a planted defect; nothing a later stage handles "
          "is rejected")  # fmt: skip
    warn_groups = [r for r in planted if r[4] == "warn"]
    check(all(r[8] == 0 for r in warn_groups) and len(warn_groups) == 4,
          "the warn-only types (conflicting duplicate, late tenant on leases and payments, "
          "mid-lease rent change) are reported as warnings, not rejected")  # fmt: skip
    expected_rejects = sum(int(r[6]) for r in planted if r[4] == "reject")
    check(summary.rejected == expected_rejects,
          f"rejections equal the answer key's rejectable defects ({summary.rejected:,})")
    check(out.read_text(encoding="utf-8").splitlines()[0].startswith("kind,source,table"),
          "dq_validation.csv is written")
    # The comparison itself must notice a finding with the wrong rule: relabel one rejection.
    cur.execute("UPDATE lue_audit.dq_result SET check_name = 'DQ-06 Range', rule_id = "
                "'TEST-WRONG' WHERE ctid = (SELECT ctid FROM lue_audit.dq_result WHERE run_id = %s "
                "AND check_name = 'DQ-01 NULL' LIMIT 1)", (run_id,))  # fmt: skip
    wrong = answer_key.compare(cur, key, run_id)
    check(wrong.detected == cmp.detected - 1 and wrong.false_positives == 1,
          "the comparison catches a finding made by the wrong rule (1 missed, 1 false positive)")

    profile = json.loads((DATA / "run_manifest.json").read_text(encoding="utf-8"))["profile"]
    clean_dir = tmp / "clean"
    gd.run(cfg.clean_profile(cfg.get_profile(profile["name"])),
           json.loads((DATA / "run_manifest.json").read_text())["seed"], clean_dir)  # fmt: skip
    try:
        loaded = load_and_ingest(cur, clean_dir)
        check(loaded, f"control batch: a clean {profile['name']} generation loaded into src_pms "
                      "and ingested")  # fmt: skip
        crun, cres, csum = quality.validate()
        check(loaded and csum is not None and csum.rejected == 0 and csum.warned == 0,
              f"control batch: zero rejections and zero warnings ({csum.rows_checked:,} rows "
              f"checked by {len(csum.by_rule)} rules)" if csum else "control batch: validation "
              "failed")  # fmt: skip
    finally:
        restored = load_and_ingest(cur, DATA)
        quality.validate()
    check(restored, "src_pms and bronze hold your data folder again (validated)")


def main() -> int:
    print("=" * 70)
    print(" E4 acceptance tests: data quality and quarantine (US-4.1 to US-4.4)")
    print("=" * 70)
    if not (DATA / "answer_key" / "defects_answer_key.csv").is_file():
        print("  [FAIL] no data/answer_key: run python etl/generate_data.py first")
        return 1
    manifest = json.loads((DATA / "run_manifest.json").read_text(encoding="utf-8"))
    if not any(float(v) for v in manifest["profile"]["defect_rates"].values()):
        print("  [FAIL] data/ is a clean control batch: generate it with the defects "
              "(python etl/generate_data.py) and load it (python scripts/db_load_source.py)")
        return 1
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    try:
        with wh.cursor() as cur, tempfile.TemporaryDirectory(prefix="lue_quality_") as tmp:
            print("Setup: your data folder into src_pms and a fresh bronze")
            check(load_and_ingest(cur, DATA), "loaded and ingested: 6/6 sources, reconciled")
            run_id = engine_tests(cur, Path(tmp))
            cast_tests(cur)
            fixture_tests(cur, run_id)
            answer_key_tests(cur, Path(tmp))
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
