#!/usr/bin/env python3
"""Acceptance tests for E3 (US-3.1 to US-3.4): ingestion into bronze. Needs the database.

    python scripts/db_deploy.py && python scripts/db_load_source.py && python scripts/test_ingest.py

Uses what is loaded in src_pms (S1) and a temporary COPY of the data folder for the file sources
(so it can edit, rename and break files without touching yours). It EMPTIES the bronze tables and
lue_audit.file_load first, and ends with a normal ingestion of your data folder, so bronze is full
and current afterwards. One row of src_pms.tenants is changed during the test and put back.
"""

import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.ingest import files, json_weather, s1_pms  # noqa: E402
from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import LOG_FILE, IngestError, Run, connect, settings  # noqa: E402

DATA = ROOT / "data"
BRONZE = sorted(
    list(s1_pms.TABLES.values())
    + [t for t, _c in files.S2_SHEETS.values()]
    + ["brz_settlement"]
    + [t for t, _c in files.S6_FILES.values()]
    + ["brz_ticket", "brz_ticket_status", "brz_weather"]
)
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def by_step(res) -> dict:
    return {r.source_system: r for r in res}


def reset(cur) -> None:
    for t in BRONZE:
        cur.execute(f"TRUNCATE lue_staging.{t}")
    cur.execute("TRUNCATE lue_audit.file_load")
    cur.execute("DELETE FROM lue_audit.etl_watermark WHERE source_system = 'S1'")
    # E4's findings name bronze rows by row_id: with bronze emptied they would point at nothing.
    cur.execute("SELECT to_regclass('lue_audit.dq_result') IS NOT NULL")
    if cur.fetchone()[0]:
        cur.execute("TRUNCATE lue_audit.dq_result")
        cur.execute("DELETE FROM lue_audit.quarantine")


def run(data: Path, only: list[str]):
    run_id, res, checks = ingest.run(data, only)
    return run_id, by_step(res), checks


def framework(cur) -> None:
    print("US-3.1 The framework")
    cur.execute(
        "SELECT table_name, string_agg(column_name || ':' || is_nullable, ',') FROM "
        "information_schema.columns WHERE table_schema = 'lue_staging' AND column_name IN "
        "('batch_id', 'source_system', 'loaded_at') GROUP BY table_name"
    )
    meta = dict(cur.fetchall())
    check(
        all(meta.get(t, "").count(":NO") == 3 for t in BRONZE) and len(BRONZE) == 20,
        "20 bronze tables, each with batch_id, source_system and loaded_at NOT NULL",
    )

    def land_then_fail(step):
        batch = step.new_batch()
        step.land("brz_incentive_offer", files.S6_FILES["offers.csv"][1],
                  [("X1", "t", "d", "0", "0")] * 5, batch,
                  extra={"source_file": "forced", "source_row": 1})  # fmt: skip
        step.read(5)
        raise RuntimeError("forced failure after 5 rows were written")

    r = Run()
    try:
        failed = r.step("test_forced_failure", "S6", land_then_fail)
        after = r.step("test_after_failure", "S6", lambda step: step.read(0))
    finally:
        r.close()
    left = scalar(cur, "SELECT count(*) FROM lue_staging.brz_incentive_offer WHERE "
                       "source_file = 'forced'")  # fmt: skip
    cur.execute("SELECT step, status, rows_read, rows_inserted, ended_at IS NOT NULL FROM "
                "lue_audit.etl_run_log WHERE run_id = %s ORDER BY step", (r.run_id,))  # fmt: skip
    log_rows = {s: (st, rd, ins, done) for s, st, rd, ins, done in cur.fetchall()}
    check(left == 0, "a failed load leaves no partial rows in bronze (5 written, 0 kept)")
    check(
        failed.status == "Failed" and log_rows.get("test_forced_failure") == ("Failed", 5, 0, True),
        "the failure is in etl_run_log: status Failed, 5 rows read, 0 inserted, end time set",
    )
    check(
        after.status == "Success" and log_rows.get("test_after_failure", ("",))[0] == "Success",
        "the next source of the same run still runs (one transaction per source)",
    )
    text = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.is_file() else ""
    check(
        "step=test_forced_failure source=S6 status=Failed" in text
        and "forced failure after 5 rows" in text,
        "the structured log (logs/ingest.log) records step, source, status and the error",
    )
    bad = dict(settings()) | {"LUE_ETL_PASSWORD": "not-the-password"}
    try:
        connect("lue_warehouse", bad)
        message = ""
    except IngestError as exc:
        message = str(exc)
    check("cannot connect to lue_warehouse as lue_etl" in message,
          "a wrong password stops with a clear message, not a traceback")  # fmt: skip


def source_rows(src_cur, table: str, columns: list[str]) -> Counter:
    src_cur.execute(f"SELECT {', '.join(c + '::text' for c in columns)} FROM src_pms.{table}")
    return Counter(src_cur.fetchall())


def bronze_rows(cur, target: str, columns: list[str]) -> Counter:
    cur.execute(f"SELECT {', '.join(columns)} FROM lue_staging.{target}")
    return Counter(cur.fetchall())


def s1_tests(cur, src, src_cur) -> None:
    print("US-3.2 S1, incremental")
    run_id, res, checks = run(DATA, ["S1"])
    s1 = res["S1"]
    counts = {}
    for table, target in s1_pms.TABLES.items():
        counts[table] = (scalar(src_cur, f"SELECT count(*) FROM src_pms.{table}"),
                         scalar(cur, f"SELECT count(*) FROM lue_staging.{target}"))  # fmt: skip
    check(s1.status == "Success" and all(a == b for a, b in counts.values()),
          f"run 1 lands everything: {s1.rows_written:,} rows, every table equals its source")
    same = True
    for table, target in s1_pms.TABLES.items():
        cols = s1_pms.source_columns(src_cur, table)
        same &= source_rows(src_cur, table, cols) == bronze_rows(cur, target, cols)
    check(same, "every value in bronze is the source's value as text, row for row (9 tables)")
    check(all(c[4] for c in checks) and len(checks) == 9,
          "9 reconciliation rows (source rows found in bronze), all passed")  # fmt: skip
    cur.execute("SELECT table_name, last_watermark_value FROM lue_audit.etl_watermark "
                "WHERE source_system = 'S1' ORDER BY 1")  # fmt: skip
    marks = dict(cur.fetchall())
    newest = {t: scalar(src_cur, f"SELECT max(updated_at) FROM src_pms.{t}")
              for t in ("tenants", "units")}  # fmt: skip
    check(marks == {f"src_pms.{t}": v for t, v in sorted(newest.items())},
          "the watermark of units and tenants is the newest updated_at loaded")  # fmt: skip

    _run2, res2, _c = run(DATA, ["S1"])
    check(res2["S1"].rows_written == 0 and res2["S1"].rows_read == s1.rows_read,
          f"run 2 straight after: reads {res2['S1'].rows_read:,}, lands 0")  # fmt: skip

    # The tenant with the NEWEST updated_at: dating it back lowers the source's maximum, so the
    # watermark would move back if the extract did not keep the greater of the two.
    src_cur.execute("SELECT tenant_code, phone, updated_at FROM src_pms.tenants "
                    "ORDER BY updated_at DESC, tenant_code LIMIT 1")  # fmt: skip
    code, phone, stamp = src_cur.fetchone()
    try:
        # A change dated BEFORE the watermark, like the US-2.6 changes in s1/changes/: a pure
        # updated_at filter would miss it; the row hash does not.
        src_cur.execute(
            "UPDATE src_pms.tenants SET phone = '0300-1234567', "
            "updated_at = TIMESTAMP '2023-07-15 10:00:00' WHERE tenant_code = %s",
            (code,),
        )
        src.commit()
        _r3, res3, _c = run(DATA, ["S1"])
        cur.execute("SELECT phone FROM lue_staging.brz_tenant WHERE tenant_code = %s "
                    "ORDER BY batch_id", (code,))  # fmt: skip
        versions = [r[0] for r in cur.fetchall()]
        check(res3["S1"].rows_written == 1 and versions == [phone, "0300-1234567"],
              "updating one source row lands exactly that row, as a new version (even with an "
              "updated_at older than the watermark)")  # fmt: skip
        mark = scalar(cur, "SELECT last_watermark_value FROM lue_audit.etl_watermark WHERE "
                           "table_name = 'src_pms.tenants'")  # fmt: skip
        check(mark == newest["tenants"], "an older updated_at never moves the watermark back")
    finally:
        src_cur.execute("UPDATE src_pms.tenants SET phone = %s, updated_at = %s "
                        "WHERE tenant_code = %s", (phone, stamp, code))  # fmt: skip
        src.commit()
    _r4, res4, _c = run(DATA, ["S1"])
    check(res4["S1"].rows_written == 0,
          "putting the row back lands nothing (that version is already in bronze)")

    before = {t: scalar(cur, f"SELECT count(*) FROM lue_staging.{t}")
              for t in s1_pms.TABLES.values()}  # fmt: skip
    marks_before = scalar(cur, "SELECT max(updated_at) FROM lue_audit.etl_watermark")
    src_cur.execute("UPDATE src_pms.units SET furnished = NOT furnished WHERE unit_id = "
                    "(SELECT min(unit_id) FROM src_pms.units)")  # fmt: skip
    src.commit()
    try:
        r = Run()
        try:
            broken = dict(s1_pms.TABLES) | {"no_such_table": "brz_unit"}
            failed = r.step("ingest_s1_pms", "S1", lambda step: s1_pms.ingest_s1(step, broken))
        finally:
            r.close()
        after = {t: scalar(cur, f"SELECT count(*) FROM lue_staging.{t}")
                 for t in s1_pms.TABLES.values()}  # fmt: skip
        check(failed.status == "Failed" and after == before
              and scalar(cur, "SELECT max(updated_at) FROM lue_audit.etl_watermark")
              == marks_before,
              "a failed S1 run lands nothing (the changed unit included) and leaves the watermark "
              "alone")  # fmt: skip
    finally:
        src_cur.execute("UPDATE src_pms.units SET furnished = NOT furnished WHERE unit_id = "
                        "(SELECT min(unit_id) FROM src_pms.units)")  # fmt: skip
        src.commit()


def copy_data(tmp: Path) -> Path:
    data = tmp / "data"
    for part in ("s2", "s3", "s4", "s6", "answer_key"):
        if (DATA / part).is_dir():
            shutil.copytree(DATA / part, data / part)
    shutil.copy2(json_weather.weather_file(DATA), data / "weather_cache.json")
    return data


def file_tests(cur, tmp: Path) -> None:
    print("US-3.3 S2, S3, S6 files")
    data = copy_data(tmp)
    run_id, res, checks = run(data, ["S2", "S3", "S6"])
    n_s3 = len(list((data / "s3").glob("settlement_*.csv")))
    cur.execute("SELECT status, count(*), bool_and(checksum_sha256 ~ '^[0-9a-f]{64}$') FROM "
                "lue_audit.file_load WHERE run_id = %s GROUP BY status", (run_id,))  # fmt: skip
    reg = {s: (n, ok) for s, n, ok in cur.fetchall()}
    distinct = len({files.sha256_file(p) for p in (data / "s3").glob("settlement_*.csv")})
    check(all(r.status == "Success" for r in res.values())
          and reg.get("Loaded") == (5 + distinct + 2, True)
          and reg.get("Skipped", (0, True))[0] == n_s3 - distinct,
          f"run 1: a Loaded file_load row per file and target, each with its SHA-256 "
          f"({5 + distinct + 2}); {n_s3 - distinct} empty settlement files with the same bytes "
          "as an earlier one are skipped by checksum (D16)")  # fmt: skip
    header, rows = files.read_csv(data / "s6" / "offers.csv")
    cur.execute("SELECT " + ", ".join(header) + " FROM lue_staging.brz_incentive_offer "
                "ORDER BY source_row")  # fmt: skip
    check(cur.fetchall() == rows, "S6 offers land exactly as written in the file, in order")
    with (data / "s6" / "incentive_log.csv").open(encoding="utf-8") as f:
        raw = f.read().splitlines()[1:]
    empty = sum(1 for line in raw if ",," in line or line.startswith(","))
    check(scalar(cur, "SELECT count(*) FROM lue_staging.brz_incentive_log WHERE offer_code = '' "
                      "OR building_code = '' OR unit_no = '' OR start_date = '' OR end_date = ''")
          == empty, f"empty cells stay empty texts ({empty}), they do not become NULL or vanish")
    check(all(c[4] for c in checks), f"{len(checks)} reconciliation checks, all passed")

    _r, res2, _c = run(data, ["S2", "S3", "S6"])
    cur.execute("SELECT status, count(*) FROM lue_audit.file_load WHERE run_id = %s "
                "GROUP BY status", (_r,))  # fmt: skip
    check(sum(r.rows_written for r in res2.values()) == 0
          and dict(cur.fetchall()) == {"Skipped": 5 + n_s3 + 2},
          "run 2 with unchanged files lands 0 rows; every file is logged Skipped, unchanged")

    target = sorted((data / "s3").glob("settlement_*.csv"))[len(list((data / "s3").glob(
        "settlement_*.csv"))) // 2]  # fmt: skip
    text = target.read_text(encoding="utf-8").splitlines()
    header3 = text[0].split(",")
    first = text[1].split(",")
    first[header3.index("fee_amount")] = "0.00"
    text[1] = ",".join(first)
    target.write_text("\n".join(text) + "\n", encoding="utf-8")
    name = f"s3/{target.name}"
    _r, res3, checks3 = run(data, ["S3"])
    copies = scalar(cur, "SELECT count(DISTINCT batch_id) FROM lue_staging.brz_settlement "
                         "WHERE source_file = %s", (name,))  # fmt: skip
    check(res3["S3"].rows_written == len(text) - 1 and copies == 2 and all(c[4] for c in checks3),
          f"an edited file lands exactly its {len(text) - 1} rows as a new batch; the old batch "
          "stays (append, never truncate)")  # fmt: skip

    cur.execute("DELETE FROM lue_staging.brz_incentive_log WHERE ctid = (SELECT min(ctid) FROM "
                "lue_staging.brz_incentive_log)")  # fmt: skip
    _r, _res, lost = run(data, ["S6"])
    lost = {c[0]: c for c in lost}
    row = lost.get("brz_incentive_log rows vs the files")
    check(row is not None and not row[4] and int(row[3]) == -1,
          "reconciliation catches a row lost from bronze (difference -1, FAIL)")

    offers = data / "s6" / "offers.csv"
    lines = offers.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("rent_free_days", "free_days")
    offers.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _r, res4, _c = run(data, ["S6"])
    cur.execute("SELECT file_name, status, rows_landed, message FROM lue_audit.file_load WHERE "
                "run_id = %s ORDER BY file_name", (_r,))  # fmt: skip
    reg4 = cur.fetchall()
    rejected = [r for r in reg4 if r[1] == "Rejected"]
    message = rejected[0][3] if rejected else ""
    print(f"         message: {message}")
    check(res4["S6"].status == "Warning" and res4["S6"].rows_written == 0 and len(rejected) == 1
          and "'rent_free_days'" in message and "'free_days'" in message,
          "a file with a renamed column is rejected before load, saying which column")
    check([r[:2] for r in reg4 if r[1] != "Rejected"] == [("s6/incentive_log.csv", "Skipped")],
          "the other file of the source still goes through (unchanged: skipped)")
    status = scalar(cur, "SELECT status FROM lue_audit.etl_run_log WHERE run_id = %s", (_r,))
    check(status == "Warning", "the run log marks the step Warning")

    import openpyxl

    book = openpyxl.load_workbook(data / "s2" / "registers.xlsx")
    book["vendors"]["C1"] = "Trade"
    book.save(data / "s2" / "registers.xlsx")
    _r, res5, _c = run(data, ["S2"])
    cur.execute("SELECT target_table, status FROM lue_audit.file_load WHERE run_id = %s "
                "ORDER BY 1", (_r,))  # fmt: skip
    reg5 = dict(cur.fetchall())
    check(reg5.get("brz_vendor") == "Rejected" and res5["S2"].status == "Warning"
          and {v for k, v in reg5.items() if k != "brz_vendor"} == {"Loaded"},
          "S2: a sheet whose header changed is rejected; the workbook's other sheets land (the "
          "file changed, so as a new batch)")  # fmt: skip


def json_tests(cur, tmp: Path) -> None:
    print("US-3.4 S4 tickets, S5 weather, reconciliation")
    data = tmp / "data"
    path = data / "s4" / "tickets.json"
    export = json.loads(path.read_text(encoding="utf-8"))
    # An older copy of the first ticket at the end (as US-2.6 plants them), so the check below runs
    # on a clean batch too.
    stale = json.loads(json.dumps(export["tickets"][0]))
    stale["status_history"] = stale["status_history"][:1]
    export["tickets"].append(stale)
    path.write_text(json.dumps(export, indent=2) + "\n", encoding="utf-8")
    tickets = export["tickets"]
    run_id, res, checks = run(data, ["S4", "S5"])
    n_t = scalar(cur, "SELECT count(*) FROM lue_staging.brz_ticket")
    n_s = scalar(cur, "SELECT count(*) FROM lue_staging.brz_ticket_status")
    history = sum(len(t["status_history"]) for t in tickets)
    check(n_t == len(tickets) and n_s == history,
          f"{n_t:,} ticket rows = tickets in the file; {n_s:,} status rows = the sum of the "
          "status_history lengths")  # fmt: skip
    ids = Counter(t["ticket_id"] for t in tickets)
    twice = [stale["ticket_id"]] + [i for i, n in ids.items() if n > 1]
    if twice:
        cur.execute("SELECT source_row, count(*) FROM lue_staging.brz_ticket_status WHERE "
                    "ticket_id = %s GROUP BY source_row ORDER BY 1", (twice[0],))  # fmt: skip
        per_copy = [n for _r, n in cur.fetchall()]
        want = [len(t["status_history"]) for t in tickets if t["ticket_id"] == twice[0]]
        check(per_copy == want, f"the two copies of {twice[0]} keep their own histories {want}")
    sample = tickets[len(tickets) // 3]
    cur.execute("SELECT " + ", ".join(json_weather.TICKET_COLUMNS) + " FROM lue_staging.brz_ticket"
                " WHERE source_row = %s", (len(tickets) // 3 + 1,))  # fmt: skip
    got = cur.fetchone()
    check(got == tuple(files.as_text(sample[c]) for c in json_weather.TICKET_COLUMNS),
          "a ticket lands field for field as text (null stays NULL, true stays true)")
    key = data / "answer_key" / "defects_answer_key.csv"
    if key.is_file():
        import csv

        planted = Counter(
            r["defect_type"] for r in csv.DictReader(key.open(encoding="utf-8"))
            if r["source"] == "S4"
        )  # fmt: skip
        last = len(tickets)  # the copy this test appended is not one of the planted defects
        as_text = scalar(cur, "SELECT count(*) FROM lue_staging.brz_ticket WHERE estimate !~ "
                              "'^[0-9]+$' AND source_row <> %s", (last,))  # fmt: skip
        no_unit = scalar(cur, "SELECT count(*) FROM lue_staging.brz_ticket WHERE unit_no IS NULL "
                              "AND source_row <> %s", (last,))  # fmt: skip
        check(as_text == planted["wrong_data_type"]
              and no_unit == planted["null_required_value"],
              f"US-2.6 defects arrive untouched: {as_text} estimates as text, {no_unit} tickets "
              "without a unit, as the answer key says")  # fmt: skip
    cache = json.loads((data / "weather_cache.json").read_text(encoding="utf-8"))
    days = sum(len(c["daily"]["time"]) for c in cache["cities"])
    nulls = sum(v is None for c in cache["cities"] for k in ("temperature_2m_max",
                "precipitation_sum") for v in c["daily"][k])  # fmt: skip
    check(scalar(cur, "SELECT count(*) FROM lue_staging.brz_weather") == days
          and scalar(cur, "SELECT count(*) FROM lue_staging.brz_weather WHERE max_temp_c IS NULL "
                          "OR rainfall_mm IS NULL") == nulls,
          f"weather: {days:,} city-days, {nulls} missing values kept as NULL")  # fmt: skip
    check(len(checks) == 3 and all(c[4] for c in checks),
          "reconciliation: tickets, status entries and city-days, all with difference 0")
    _r, res2, _c = run(data, ["S4", "S5"])
    check(sum(r.rows_written for r in res2.values()) == 0, "rerun: both files skipped, unchanged")

    broken = data / "s4" / "tickets.json"
    broken.write_text(broken.read_text(encoding="utf-8")[:-200], encoding="utf-8")
    _r, res3, _c = run(data, ["S4"])
    cur.execute("SELECT message FROM lue_audit.file_load WHERE run_id = %s AND status = "
                "'Rejected'", (_r,))  # fmt: skip
    messages = [m for (m,) in cur.fetchall()]
    check(res3["S4"].status == "Warning" and res3["S4"].rows_written == 0 and len(messages) == 2
          and "not valid JSON" in messages[0],
          "a cut-off JSON file is rejected for both ticket tables; nothing lands")


def full_run(cur) -> None:
    print("Your data folder, all six sources (bronze is left full and current)")
    reset(cur)
    run_id, res, checks = run(DATA, list(ingest.SOURCES))
    check(all(r.status == "Success" for r in res.values()),
          f"run {run_id}: all six sources Success, {sum(r.rows_written for r in res.values()):,} "
          "rows landed")  # fmt: skip
    check(len(checks) == 20 and all(c[4] and c[3] == 0 for c in checks),
          "20 reconciliation rows, one per bronze table, all with difference 0")
    cur.execute("SELECT count(*) FROM lue_audit.lineage WHERE target_table LIKE "
                "'lue_staging.brz_%'")  # fmt: skip
    check(cur.fetchone()[0] == 20, "lineage: one row per bronze table and its source")
    empty = [t for t in BRONZE if scalar(cur, f"SELECT count(*) FROM lue_staging.{t} WHERE "
             "batch_id IS NULL OR source_system IS NULL OR loaded_at IS NULL") != 0]  # fmt: skip
    check(not empty, "every landed row carries batch_id, source_system and loaded_at")
    systems = {t: scalar(cur, f"SELECT string_agg(DISTINCT source_system, ',') FROM "
                              f"lue_staging.{t}") for t in BRONZE}  # fmt: skip
    check(set(systems.values()) == {"S1", "S2", "S3", "S4", "S5", "S6"},
          "every bronze table is stamped with its own source system")


def main() -> int:
    print("=" * 70)
    print(" E3 acceptance tests: ingestion into bronze (US-3.1 to US-3.4)")
    print("=" * 70)
    if not (DATA / "run_manifest.json").is_file():
        print("  [FAIL] no data/run_manifest.json: run python etl/generate_data.py first")
        return 1
    try:
        wh = connect("lue_warehouse")
        src = connect("lue_source")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    try:
        with wh.cursor() as cur, src.cursor() as src_cur:
            if scalar(src_cur, "SELECT count(*) FROM information_schema.tables WHERE "
                               "table_schema = 'src_pms'") == 0:  # fmt: skip
                print("  [FAIL] src_pms is empty: run python scripts/db_load_source.py first")
                return 1
            reset(cur)
            framework(cur)
            s1_tests(cur, src, src_cur)
            with tempfile.TemporaryDirectory(prefix="lue_ingest_") as tmp:
                file_tests(cur, Path(tmp))
                json_tests(cur, Path(tmp))
            full_run(cur)
    finally:
        src.close()
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
