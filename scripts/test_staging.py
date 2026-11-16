#!/usr/bin/env python3
"""Acceptance tests for E5 (US-5.1 to US-5.4): staging. Needs the database.

    python scripts/db_deploy.py
    python scripts/db_load_source.py
    python scripts/test_staging.py

Works on your data folder (with the US-2.6 defects: a plain python etl/generate_data.py). It
re-ingests it into a fresh bronze, validates it (E4), loads staging in full, and checks:
  US-5.1  the cleaning functions; one spelling per city, unit type and payment method, nothing
          outside the vocabularies; per table staged rows = bronze - rejected - deduplicated
          (the count bridge); survivorship (D15) on the planted conflicting tickets and on a
          fixture unit (latest updated_at wins whatever the load order); the guards (a batch
          waiting for validation, a key empty after cleaning, a second run at the same time);
  US-5.2  allocations never exceed a payment or a line, every allocatable payment is fully
          allocated, reversals too; days_past_due, settlement lag, term, ticket lifecycle; the
          answer key (repairs, 541 unmatched settlements, 722 unsettled electronic payments);
  US-5.3  a second run inserts and updates nothing; one changed source row gives exactly one
          update; a failed step leaves its watermark and table as they were; a batch landed in
          the same second as the watermark is still read; an older version never replaces a
          newer one;
  US-5.4  an evidence file per source, its counts reconcile with the count bridge, the ' lahore '
          sample, the repairs the answer key planted are counted.
At the end src_pms, bronze and staging hold your data folder again (validated, staged in full).
"""

# ruff: noqa: E501  (SQL text: long lines read better)

import csv
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import test_quality as tq  # noqa: E402

from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402
from etl.quality import run as quality  # noqa: E402
from etl.staging import answer_key, spec  # noqa: E402
from etl.staging import run as staging  # noqa: E402

DATA = ROOT / "data"
results: list[bool] = []
FIXTURES: list[tuple[str, int]] = []  # (bronze table, batch_id) to remove at the end


def planted() -> dict:
    """What the US-2.6 answer key planted, so the checks hold for any profile (small or full)."""
    with (DATA / "answer_key" / "defects_answer_key.csv").open(encoding="utf-8", newline="") as f:
        key = list(csv.DictReader(f))

    def n(**match) -> int:
        return sum(all(k[c] == v for c, v in match.items()) for k in key)

    return {
        "lease_events": n(source="S1", table="lease_events", expected_handling="reject"),
        "allocations": n(source="S1", table="payment_allocations", expected_handling="reject"),
        "settlements": n(source="S3", table="settlements", expected_handling="reject"),
        "duplicate_lines": n(defect_type="duplicate_settlement_line"),
        "conflicts": n(source="S4", table="tickets", defect_type="conflicting_duplicate"),
        "repairs": {
            ("stg_unit", "unit_type"): n(table="units", column="unit_type", expected_rule="US-5.1"),
            ("stg_building", "city"): n(table="buildings", column="city", expected_rule="US-5.1"),
            ("stg_incentive_log", "start_date"): n(table="incentive_log", column="start_date",
                                                   expected_rule="US-5.1"),
        },
    }  # fmt: skip


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def stage(full: bool = False, folder: Path | None = None):
    return staging.stage(full, folder)


def by_step(res) -> dict:
    return {r.step: r for r in res}


def loads_of(cur, run_id: int) -> dict:
    cur.execute("SELECT stg_table, bronze_rows_read, rows_rejected, rows_unusable, rows_superseded, "
                "rows_inserted, rows_updated, rows_unchanged, rows_deleted FROM lue_audit.stg_load "
                "WHERE run_id = %s", (run_id,))  # fmt: skip
    return {r[0]: r[1:] for r in cur.fetchall()}


def fixture(cur, table: str, rows: list[dict], loaded_at=None, validated: bool = True) -> int:
    """Land rows in a new bronze batch (as E3 would, with its metadata), validated or not."""
    batch = scalar(cur, "SELECT nextval('lue_audit.seq_batch_id')")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = "
                "'lue_staging' AND table_name = %s AND is_nullable = 'NO' AND column_default IS "
                "NULL AND is_identity = 'NO'", (table,))  # fmt: skip
    required = {r[0] for r in cur.fetchall()}
    stamp = loaded_at or scalar(cur, "SELECT date_trunc('second', localtimestamp)")
    system = spec.BY_BRONZE[table].source_system
    for i, row in enumerate(rows):
        meta = {"batch_id": batch, "source_system": system, "loaded_at": stamp}
        if "row_hash" in required:
            meta["row_hash"] = "f" * 32
        if "source_file" in required:
            meta["source_file"] = row.pop("source_file", "test/fixture.csv")
            meta["source_row"] = row.pop("source_row", 900000 + i)
        full = {**row, **meta}
        cols = ", ".join(full)
        cur.execute(f"INSERT INTO lue_staging.{table} ({cols}) VALUES "
                    f"({', '.join(['%s'] * len(full))})", list(full.values()))  # fmt: skip
    if validated:
        cur.execute("INSERT INTO lue_audit.dq_batch (batch_id, run_id, validated_at) VALUES "
                    "(%s, 0, localtimestamp)", (batch,))  # fmt: skip
    FIXTURES.append((table, batch))
    return batch


def drop_fixtures(cur) -> None:
    for table, batch in FIXTURES:
        cur.execute(f"DELETE FROM lue_staging.{table} WHERE batch_id = %s", (batch,))
        cur.execute("DELETE FROM lue_audit.dq_batch WHERE batch_id = %s", (batch,))
    FIXTURES.clear()


# ----------------------------------------------------------------------------- US-5.1
def clean_tests(cur, tmp: Path) -> int:
    print("US-5.1 Clean, standardise and deduplicate (full load)")
    run_id, res, loads, biz, bridge = stage(full=True, folder=tmp)
    check(all(r.status == "Success" for r in res) and len(res) == 22,
          f"full load: stage_reset, 20 tables and stage_business, all Success "
          f"({sum(r.status == 'Success' for r in res)}/{len(res)})")  # fmt: skip
    cur.execute("SELECT lue_staging.std('city', ' lahore '), lue_staging.std('city', 'LAHORE'), "
                "lue_staging.std('city', 'Lahore'), lue_staging.std('city', 'khi'), "
                "lue_staging.std('city', 'Lahor'), lue_staging.std('city', ''), "
                "lue_staging.std('city', NULL), lue_staging.clean_text('  a   b  '), "
                "lue_staging.clean_text('   '), lue_staging.clean_text(NULL), "
                "lue_staging.std('employer_sector', 'it  AND software'), "
                "lue_staging.std('contact_channel', 'whatsapp'), lue_staging.region_of('Karachi'), "
                "lue_staging.city_code('Islamabad'), lue_audit.try_date('08/12/2024')::text")  # fmt: skip
    got = cur.fetchone()
    check(got == ("Lahore", "Lahore", "Lahore", "Karachi", None, None, None, "a b", None, None,
                  "IT and Software", "WhatsApp", "Sindh", "ISB", "2024-12-08"),
          "' lahore ' and 'LAHORE' -> 'Lahore', 'khi' -> 'Karachi', an unknown or empty value -> "
          "NULL; clean_text trims and collapses, blank -> NULL; region, city code, day-first "
          "date")  # fmt: skip
    spellings = []
    for table, col in (("stg_building", "city"), ("stg_weather", "city"), ("stg_unit", "unit_type"),
                       ("stg_payment", "method_code")):  # fmt: skip
        cur.execute(f"SELECT count(DISTINCT {col}), count(DISTINCT lower({col})), "
                    f"count(*) FILTER (WHERE {col} IS NULL) FROM lue_staging.{table}")  # fmt: skip
        spellings.append((table, col, *cur.fetchone()))
    one = all(a == b and n == 0 for _t, _c, a, b, n in spellings)
    check(one, "no city, unit type or payment method in more than one spelling, none NULL: "
          + ", ".join(f"{t}.{c} {a}" for t, c, a, _b, _n in spellings))  # fmt: skip
    outside = scalar(cur, "SELECT count(*) FROM lue_staging.stg_payment p WHERE NOT EXISTS "
                          "(SELECT 1 FROM lue_staging.payment_method m WHERE m.method_code = "
                          "p.method_code)")  # fmt: skip
    vocab = scalar(cur, "SELECT count(*) FROM lue_audit.cleaning_evidence WHERE run_id = %s AND "
                        "issue = 'not_in_vocabulary'", (run_id,))  # fmt: skip
    check(outside == 0 and vocab == 0,
          "every payment method is in lue_staging.payment_method; no source value is outside its "
          "vocabulary (no not_in_vocabulary evidence)")  # fmt: skip
    bad = [b for b in bridge if b[9] != 0]
    check(len(bridge) == 20 and not bad,
          "count bridge: staged rows = bronze - rejected by E4 - unusable - deduplicated, for all "
          "20 tables" + (f"; off: {bad}" if bad else ""))  # fmt: skip
    b = {r[0]: r for r in bridge}
    p = planted()
    check(b["stg_lease_event"][3] == p["lease_events"]
          and b["stg_payment_allocation"][3] == p["allocations"]
          and b["stg_settlement"][3] == p["settlements"] and b["stg_ticket"][5] == p["conflicts"],
          f"the differences are the planted ones: {p['lease_events']:,} lease events, "
          f"{p['allocations']:,} allocations and {p['settlements']:,} settlement lines rejected "
          f"by E4; {p['conflicts']:,} ticket copies deduplicated (conflicting duplicates, D15)")
    # D15 on the planted conflicting tickets: the copy with the latest status time survived.
    wrong = scalar(cur, """
        WITH copies AS (
            SELECT t.ticket_id, t.source_row, max(lue_audit.try_timestamp(s.status_at)) AS last
            FROM lue_staging.brz_ticket t JOIN lue_staging.brz_ticket_status s
              ON s.loaded_at = t.loaded_at AND s.source_file = t.source_file
             AND s.source_row = t.source_row
            WHERE NOT EXISTS (SELECT 1 FROM lue_audit.dq_result r WHERE r.source_table =
                              'brz_ticket' AND r.row_id = t.row_id AND r.severity = 'reject')
            GROUP BY 1, 2),
        pairs AS (SELECT ticket_id FROM copies GROUP BY 1 HAVING count(*) > 1)
        SELECT count(*) FROM pairs p JOIN lue_staging.stg_ticket k USING (ticket_id)
        WHERE k.src_row <> (SELECT c.source_row FROM copies c WHERE c.ticket_id = p.ticket_id
                            ORDER BY c.last DESC, c.source_row DESC LIMIT 1)""")
    pairs = scalar(cur, "SELECT count(*) FROM lue_audit.dq_result WHERE rule_id = 'S4-TKT-05'")
    check(wrong == 0 and pairs == 2 * p["conflicts"],
          f"survivorship on the {p['conflicts']} conflicting ticket pairs ({pairs} warned copies): "
          "the copy with the latest status time is staged, every time")  # fmt: skip
    ghosts = scalar(cur, "SELECT count(*) FROM lue_staging.stg_ticket_status s WHERE NOT EXISTS "
                         "(SELECT 1 FROM lue_staging.stg_ticket k JOIN lue_staging."
                         "brz_ticket_status b ON b.loaded_at = k.loaded_at AND b.source_file = "
                         "k.src_file AND b.source_row = k.src_row WHERE k.ticket_id = s.ticket_id "
                         "AND b.row_id = s.src_row_id)")  # fmt: skip
    check(ghosts == 0, "every staged status entry belongs to the staged copy of its ticket")
    return run_id


def survivorship_fixture(cur) -> None:
    print("US-5.1 Survivorship (D15) and the guards, on fixture rows")
    cur.execute("SELECT u.unit_id, b.building_code, b.unit_no, b.floor_no, b.unit_type, "
                "b.area_sqft, b.bedrooms, b.furnished FROM lue_staging.stg_unit u JOIN "
                "lue_staging.brz_unit b ON b.row_id = u.src_row_id ORDER BY u.unit_id LIMIT 1")  # fmt: skip
    uid, bcode, uno, floor, utype, area, beds, furn = cur.fetchone()
    base = {"unit_id": str(uid), "building_code": bcode, "unit_no": uno, "unit_type": utype,
            "area_sqft": area, "bedrooms": beds, "furnished": furn}  # fmt: skip
    # Newer by updated_at first, then an older one with a higher row_id in the same batch.
    fixture(cur, "brz_unit", [{**base, "floor_no": "41", "updated_at": "2026-06-02 10:00:00"},
                              {**base, "floor_no": "42", "updated_at": "2026-06-01 10:00:00"}])
    run_id, res, loads, _b, _br = stage()
    floor_now = scalar(cur, "SELECT floor_no FROM lue_staging.stg_unit WHERE unit_id = %s", (uid,))
    x = loads.get("stg_unit")
    check(floor_now == 41 and x and x.superseded == 1 and x.updated == 1,
          "two versions of a unit in one batch: the latest updated_at (floor 41) wins although "
          "it was landed first; 1 superseded, 1 updated")  # fmt: skip
    fixture(cur, "brz_unit", [{**base, "floor_no": "43", "updated_at": "2020-01-01 10:00:00"}],
            loaded_at=scalar(cur, "SELECT date_trunc('second', localtimestamp) + interval "
                                  "'1 second'"))  # fmt: skip
    _r, _res, loads, _b, _br = stage()
    x = loads.get("stg_unit")
    floor_now = scalar(cur, "SELECT floor_no FROM lue_staging.stg_unit WHERE unit_id = %s", (uid,))
    check(floor_now == 41 and x and x.read == 1 and x.unchanged == 1 and x.updated == 0,
          "an older version landed later (updated_at 2020) does not replace the newer one: "
          "unchanged (US-5.3: never with an older version)")  # fmt: skip

    fixture(cur, "brz_building", [{"building_code": "   ", "building_name": "Blank key",
                                   "city": "Lahore", "locality": "x", "building_class": "A",
                                   "year_built": "2001"}])  # fmt: skip
    _r, res, loads, _b, _br = stage()
    x = loads.get("stg_building")
    check(x and x.unusable == 1 and x.inserted == 0 and by_step(res)["stage_building"].status
          == "Warning", "a key that is empty after cleaning: counted as unusable, not staged, "
          "step Warning")  # fmt: skip

    fixture(cur, "brz_owner", [{"owner_code": "OWN-TEST", "owner_name": "Test",
                                "owner_type": "Company"}], validated=False)  # fmt: skip
    try:
        stage()
        refused = ""
    except staging.StagingError as exc:
        refused = str(exc)
    check("wait for validation" in refused and "brz_owner" in refused,
          f"a bronze batch not yet validated: staging refuses to start ({refused[:70]}...)")
    cur.execute("DELETE FROM lue_staging.brz_owner WHERE owner_code = 'OWN-TEST'")

    other = connect("lue_warehouse")
    other.autocommit = True
    try:
        with other.cursor() as oc:
            oc.execute("SELECT pg_advisory_lock(hashtext(%s))", (staging.LOCK,))
            try:
                stage()
                refused = ""
            except staging.StagingError as exc:
                refused = str(exc)
    finally:
        other.close()
    check("in progress" in refused, "a second staging run at the same time is refused")


# ----------------------------------------------------------------------------- US-5.2
def business_tests(cur) -> None:
    print("US-5.2 Business transformations")
    over_pay = scalar(cur, "SELECT count(*) FROM lue_staging.stg_payment WHERE amount > 0 AND "
                           "allocated_amount > amount")  # fmt: skip
    over_line = scalar(cur, "SELECT count(*) FROM lue_staging.stg_invoice_line WHERE net_amount "
                            "> 0 AND allocated_amount > net_amount")  # fmt: skip
    check(over_pay == 0 and over_line == 0,
          "no payment allocated more than its amount, no line more than its net amount")
    cur.execute("""
        SELECT count(*), count(*) FILTER (WHERE p.allocated_amount = p.amount),
               count(*) FILTER (WHERE p.allocated_amount < p.amount AND EXISTS (
                   SELECT 1 FROM lue_staging.stg_invoice_line il
                   JOIN lue_staging.stg_invoice i USING (invoice_number)
                   JOIN lue_staging.stg_lease l USING (lease_number)
                   WHERE l.tenant_code = p.tenant_code AND il.open_balance > 0
                     AND i.invoice_date <= p.paid_at::date))
        FROM lue_staging.stg_payment p
        WHERE p.status = 'Cleared' AND p.reversal_of IS NULL AND p.amount > 0""")
    total, full, stuck = cur.fetchone()
    check(stuck == 0 and full > 0,
          f"sum of allocations = amount for {full:,} of {total:,} cleared payments"
          + (f"; the other {total - full} have no open line left to take the rest"
             if total > full else ""))  # fmt: skip
    cur.execute("SELECT count(*), count(*) FILTER (WHERE allocated_amount = amount) FROM "
                "lue_staging.stg_payment WHERE reversal_of IS NOT NULL")  # fmt: skip
    rev, rev_ok = cur.fetchone()
    check(rev > 0 and rev == rev_ok, f"every reversal is fully allocated ({rev_ok}/{rev}), with "
          "staging mirroring the original where E4 rejected its allocation")  # fmt: skip
    cur.execute("SELECT count(*), count(DISTINCT payment_reference), count(*) FILTER (WHERE "
                "src_row_id IS NOT NULL OR batch_id IS NOT NULL) FROM "
                "lue_staging.stg_payment_allocation WHERE allocation_source = 'derived'")  # fmt: skip
    n, pays, with_bronze = cur.fetchone()
    s1_only = scalar(cur, "SELECT count(*) FROM lue_staging.stg_payment_allocation a WHERE "
                          "allocation_source = 'derived' AND NOT EXISTS (SELECT 1 FROM "
                          "lue_staging.brz_payment_allocation b JOIN lue_audit.dq_result r ON "
                          "r.source_table = 'brz_payment_allocation' AND r.row_id = b.row_id AND "
                          "r.severity = 'reject' WHERE upper(trim(b.payment_reference)) = "
                          "a.payment_reference)")  # fmt: skip
    check(n > 0 and with_bronze == 0 and s1_only == 0,
          f"{n:,} derived allocations for {pays:,} payments, each one of a payment whose S1 "
          "allocation E4 rejected; marked derived, no bronze lineage")  # fmt: skip
    mism = scalar(cur, "SELECT count(*) FROM lue_staging.stg_payment_allocation a JOIN "
                       "lue_staging.stg_payment p USING (payment_reference) JOIN "
                       "lue_staging.stg_invoice i USING (invoice_number) WHERE "
                       "a.days_past_due IS DISTINCT FROM (p.paid_at::date - i.due_date) OR "
                       "a.is_reversal IS DISTINCT FROM (p.status = 'Bounced')")  # fmt: skip
    revs = scalar(cur, "SELECT count(*) FROM lue_staging.stg_payment_allocation WHERE is_reversal "
                       "AND days_past_due IS NOT NULL")  # fmt: skip
    check(mism == 0 and revs > 0,
          f"days_past_due = paid date - due date on every allocation, reversals too ({revs:,})")
    lag = scalar(cur, "SELECT count(*) FROM lue_staging.stg_settlement s JOIN "
                      "lue_staging.stg_payment p USING (payment_reference) WHERE "
                      "s.settlement_lag_days IS DISTINCT FROM (s.settlement_date - "
                      "p.paid_at::date) OR NOT s.is_matched")  # fmt: skip
    check(lag == 0, "a matched settlement line has its lag = settlement date - paid date")
    terms = scalar(cur, "SELECT count(*) FROM lue_staging.stg_lease WHERE term_months IS NULL OR "
                        "term_months <> (date_part('year', age(end_date + 1, start_date)) * 12 + "
                        "date_part('month', age(end_date + 1, start_date)))")  # fmt: skip
    # And independently of SQL, in Python, on every lease: whole months from start to end + 1 day.
    cur.execute("SELECT lease_number, start_date, end_date, term_months FROM lue_staging.stg_lease "
                "ORDER BY lease_number")  # fmt: skip
    leases = cur.fetchall()
    off = 0
    for _n, start, end, term in leases:
        after = end + timedelta(days=1)
        months = (after.year - start.year) * 12 + after.month - start.month - (after.day < start.day)
        off += months != term
    ex = leases[0] if leases else ("", "", "", "")
    check(terms == 0 and off == 0 and leases,
          f"term in months for every lease ({len(leases):,}; e.g. {ex[0]} {ex[1]} to {ex[2]} = "
          f"{ex[3]})")  # fmt: skip
    cur.execute("""
        SELECT count(*) FILTER (WHERE is_emergency IS DISTINCT FROM (priority = 'Emergency')),
               count(*) FILTER (WHERE raised_at IS NULL),
               count(*) FILTER (WHERE days_to_resolve IS DISTINCT FROM
                   round(extract(epoch FROM resolved_at - raised_at) / 86400, 2)),
               count(*) FILTER (WHERE sla_breached IS DISTINCT FROM
                   (extract(epoch FROM resolved_at - raised_at) / 3600 > sla_hours)),
               count(*) FILTER (WHERE status IN ('Resolved', 'Verified') AND resolved_at IS NULL),
               count(*) FILTER (WHERE is_recurring), count(*)
        FROM lue_staging.stg_ticket""")
    emerg, raised, dur, sla, open_res, rec, n = cur.fetchone()
    check(emerg == raised == dur == sla == open_res == 0 and 0 < rec < n,
          f"tickets: emergency flag = priority Emergency, every ticket raised, durations and SLA "
          f"breach consistent; {rec:,} of {n:,} recurring within {spec.RECURRING_DAYS} days")
    cmp = answer_key.compare(cur, DATA)
    rows = {(r[0], r[1], r[2], r[3]): r for r in cmp.rows}
    unmatched = next(r for r in cmp.rows if r[0] == "total" and r[2] == "is_matched")
    unsettled = next(r for r in cmp.rows if r[0] == "total" and r[2] == "is_unsettled")
    check(cmp.ok, f"answer key: every planted repair, {unmatched[4]:,} unmatched settlements "
          f"(expected {unmatched[3]:,}), {unsettled[4]:,} unsettled electronic payments "
          f"(expected {unsettled[3]:,}); late lines still matched ({len(rows)} checks)")


# ----------------------------------------------------------------------------- US-5.3
def incremental_tests(cur, tmp: Path) -> None:
    print("US-5.3 Incremental loading with watermarks")
    run_id, res, loads, biz, _br = stage()
    moved = {t: (x.inserted, x.updated) for t, x in loads.items() if x.inserted or x.updated}
    cur.execute("SELECT sum(rows_inserted), sum(rows_updated) FROM lue_audit.etl_run_log WHERE "
                "run_id = %s", (run_id,))  # fmt: skip
    logged = cur.fetchone()
    check(not moved and biz.total == 0 and biz.derived_inserted + biz.derived_updated +
          biz.derived_deleted == 0 and tuple(logged) == (0, 0),
          "a second run with no source change inserts and updates zero rows (the run log "
          "agrees), derived values included")  # fmt: skip

    src = connect("lue_source")
    src.autocommit = True
    with src.cursor() as sc:
        sc.execute("SELECT tenant_code, phone FROM src_pms.tenants ORDER BY tenant_code LIMIT 1")
        code, phone = sc.fetchone()
        sc.execute("UPDATE src_pms.tenants SET phone = '0399-1234567', updated_at = "
                   "localtimestamp(0) WHERE tenant_code = %s", (code,))  # fmt: skip
    src.close()
    _i, ires, _c = ingest.run(DATA, ["S1"])
    quality.validate()
    run_id, res, loads, biz, _br = stage()
    moved = {t: (x.inserted, x.updated) for t, x in loads.items() if x.inserted or x.updated}
    cur.execute("SELECT step, rows_updated FROM lue_audit.etl_run_log WHERE run_id = %s AND "
                "(rows_inserted > 0 OR rows_updated > 0)", (run_id,))  # fmt: skip
    logged = cur.fetchall()
    staged_phone = scalar(cur, "SELECT phone FROM lue_staging.stg_tenant WHERE tenant_code = %s",
                          (code,))  # fmt: skip
    check(moved == {"stg_tenant": (0, 1)} and biz.total == 0 and logged == [("stage_tenant", 1)]
          and staged_phone == "0399-1234567",
          f"one source row changed (tenant {code}'s phone): exactly one update in staging, "
          f"stage_tenant rows_updated = 1 in the run log, nothing else moves")  # fmt: skip

    wm_before = scalar(cur, "SELECT last_watermark_value FROM lue_audit.etl_watermark WHERE "
                            "source_system = 'STG' AND table_name = 'stg_building'")  # fmt: skip
    rows_before = scalar(cur, "SELECT count(*) FROM lue_staging.stg_building")
    fixture(cur, "brz_building", [{"building_code": "ZZZ99", "building_name": "Too old",
                                   "city": "Lahore", "locality": "x", "building_class": "A",
                                   "year_built": "99999"}],
            loaded_at=scalar(cur, "SELECT date_trunc('second', localtimestamp) + interval "
                                  "'2 seconds'"))  # fmt: skip
    _r, res, loads, _b, _br = stage()
    wm_after = scalar(cur, "SELECT last_watermark_value FROM lue_audit.etl_watermark WHERE "
                           "source_system = 'STG' AND table_name = 'stg_building'")  # fmt: skip
    steps = by_step(res)
    check(steps["stage_building"].status == "Failed" and wm_after == wm_before and
          scalar(cur, "SELECT count(*) FROM lue_staging.stg_building") == rows_before and
          all(r.status != "Failed" for r in res if r.step != "stage_building"),
          "a step that fails (year 99999 does not fit SMALLINT) rolls back: watermark and table "
          "as they were, the other steps still run")  # fmt: skip
    cur.execute("DELETE FROM lue_staging.brz_building WHERE building_code = 'ZZZ99'")
    _r, res, loads, _b, _br = stage()
    check(by_step(res)["stage_building"].status != "Failed", "fixed, the next run succeeds")

    wm = scalar(cur, "SELECT last_watermark_value FROM lue_audit.etl_watermark WHERE "
                     "source_system = 'STG' AND table_name = 'stg_owner'")  # fmt: skip
    fixture(cur, "brz_owner", [{"owner_code": "OWN-SAME", "owner_name": "Same second",
                                "owner_type": "Company"}], loaded_at=wm)  # fmt: skip
    _r, _res, loads, _b, _br = stage()
    first = loads["stg_owner"]
    _r, _res, loads, _b, _br = stage()
    second = loads["stg_owner"]
    check(first.read == 1 and first.inserted == 1 and second.read == 0,
          f"a batch landed in the same second as the watermark ({wm}) is read once, then not "
          "again")  # fmt: skip
    # The source sends a row again, unchanged (a file landed again): read, but not an update.
    cur.execute("SELECT b.owner_code, b.owner_name, b.owner_type FROM lue_staging.stg_owner s "
                "JOIN lue_staging.brz_owner b ON b.row_id = s.src_row_id ORDER BY 1 LIMIT 1")  # fmt: skip
    code, name, kind = cur.fetchone()
    fixture(cur, "brz_owner", [{"owner_code": code, "owner_name": name, "owner_type": kind}],
            loaded_at=scalar(cur, "SELECT date_trunc('second', localtimestamp) + interval "
                                  "'3 seconds'"))  # fmt: skip
    _r, _res, loads, _b, _br = stage()
    again = loads["stg_owner"]
    check(again.read == 1 and again.unchanged == 1 and again.updated == 0,
          f"the same row landed again (owner {code}, a new batch): read 1, unchanged 1, updated 0 "
          "(an update only when a value differs)")  # fmt: skip


# ----------------------------------------------------------------------------- US-5.4
def evidence_tests(cur, run_id: int, tmp: Path) -> None:
    print("US-5.4 Cleaning evidence")
    files = {s: tmp / f"cleaning_evidence_{s}.csv" for s in ("S1", "S2", "S3", "S4", "S5", "S6")}
    check(all(p.is_file() and len(p.read_text(encoding="utf-8").splitlines()) > 1
              for p in files.values()) and (tmp / "count_bridge.csv").is_file()
          and (tmp / "distinct_values.csv").is_file(),
          "an evidence file per source (S1 to S6), the count bridge and the distinct values")
    cur.execute("SELECT stg_table, issue, rows_affected FROM lue_audit.cleaning_evidence WHERE "
                "run_id = %s AND column_name = '*'", (run_id,))  # fmt: skip
    ev: dict[str, dict] = {}
    for t, issue, n in cur.fetchall():
        ev.setdefault(t, {})[issue] = n
    loads = loads_of(cur, run_id)
    ok = []
    for t, x in loads.items():
        e = ev.get(t, {})
        parts = ("rejected_by_dq", "key_not_usable", "superseded", "inserted", "updated",
                 "unchanged")  # fmt: skip
        ok.append(e.get("rows_read") == x[0] == sum(e.get(p, -1) for p in parts)
                  and (e["rejected_by_dq"], e["key_not_usable"], e["superseded"], e["inserted"],
                       e["updated"], e["unchanged"]) == x[1:7])  # fmt: skip
    check(len(loads) == 20 and all(ok),
          "for every table the evidence counts reconcile with the count bridge: read = rejected "
          "+ unusable + superseded + inserted + updated + unchanged")  # fmt: skip
    with files["S1"].open(encoding="utf-8", newline="") as f:
        s1 = list(csv.DictReader(f))
    named = [r for r in s1 if r["issue"] == "named_sample"]
    check(named and named[0]["sample_before"] == " lahore " and named[0]["sample_after"] == "Lahore",
          "the plan's sample by name: ' lahore ' -> 'Lahore' (stg_building.city)")

    def count(table, issue, col):
        return scalar(cur, "SELECT coalesce(max(rows_affected), 0) FROM lue_audit.cleaning_evidence "
                           "WHERE run_id = %s AND stg_table = %s AND issue = %s AND column_name = "
                           "%s", (run_id, table, issue, col))  # fmt: skip

    p = planted()
    got = {k: count(k[0], "repaired", k[1]) for k in p["repairs"]}
    dup = count("stg_settlement", "duplicates_removed", "*")
    conflict = count("stg_ticket", "conflicts_resolved", "*")
    want = p["repairs"]
    check(got == want and dup == p["duplicate_lines"] and conflict == p["conflicts"],
          f"repairs counted as planted (unit type {want[('stg_unit', 'unit_type')]}, city "
          f"{want[('stg_building', 'city')]}, day-first dates "
          f"{want[('stg_incentive_log', 'start_date')]}), duplicates removed {dup} "
          f"(settlements), conflicts resolved by survivorship {conflict} (tickets)")
    with (tmp / "distinct_values.csv").open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["stg_table"] == "stg_unit"]
    before = {r["value"] for r in rows if r["stage"] == "before"}
    after = {r["value"] for r in rows if r["stage"] == "after"}
    check((len(before) > len(after) or not want[("stg_unit", "unit_type")])
          and after <= set(spec.VOCABULARY["unit_type"]),
          f"distinct unit types: {len(before)} spellings before, {sorted(after)} after")


def main() -> int:
    print("=" * 70)
    print(" E5 acceptance tests: staging (US-5.1 to US-5.4)")
    print("=" * 70)
    if not (DATA / "answer_key" / "defects_answer_key.csv").is_file():
        print("  [FAIL] no data/answer_key: run python etl/generate_data.py first")
        return 1
    manifest = json.loads((DATA / "run_manifest.json").read_text(encoding="utf-8"))
    if not any(float(v) for v in manifest["profile"]["defect_rates"].values()):
        print("  [FAIL] data/ is a clean control batch: generate it with the defects")
        return 1
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    try:
        with wh.cursor() as cur, tempfile.TemporaryDirectory(prefix="lue_staging_") as tmp:
            print("Setup: your data folder into src_pms and a fresh bronze, validated")
            check(tq.load_and_ingest(cur, DATA) and quality.validate()[1].status != "Failed",
                  "loaded, ingested (6/6 sources) and validated")  # fmt: skip
            try:
                run_id = clean_tests(cur, Path(tmp))
                evidence_tests(cur, run_id, Path(tmp))
                business_tests(cur)
                survivorship_fixture(cur)
                incremental_tests(cur, Path(tmp))
            finally:
                drop_fixtures(cur)
                restored = tq.load_and_ingest(cur, DATA)
                quality.validate()
                _r, res, _l, _b, bridge = stage(full=True, folder=staging.EVIDENCE)
            check(restored and all(r.status == "Success" for r in res)
                  and all(b[9] == 0 for b in bridge),
                  "src_pms, bronze and staging hold your data folder again (validated, staged "
                  "in full)")  # fmt: skip
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
