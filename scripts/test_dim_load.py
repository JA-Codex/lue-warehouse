#!/usr/bin/env python3
"""Acceptance tests for E6 (US-6.1 to US-6.5): the dimensions. Needs the database.

    python scripts/db_deploy.py
    python scripts/db_load_reference.py
    python scripts/test_dim_load.py

Works on your data folder (with the US-2.6 defects). It loads the first extract (src_pms, bronze,
validation, staging), empties the dimension members (and the facts, which point at them), loads
the dimensions, then applies the next extract (s1/changes, s1/late_arriving) and loads again:
  US-6.1  one member per staged natural key with an identity surrogate key; special members
          untouched; a rerun inserts and updates nothing; Type 1 in place with the key kept;
          keys never reused; a source with a natural key twice is refused
  US-6.2  every planted tenant change: a Type 2 change (employer sector) gives exactly one new
          version from the change date, a Type 1 change (contact channel) overwrites in place;
          a rerun adds nothing; a past-month query returns the old value
  US-6.3  vendor rating and category SLA history: one version per change, history unaltered
  US-6.4  every dimension populated, hierarchy complete, bands in their domains, holidays set
  US-6.5  late tenants are inferred members first, then completed in place with no new version;
          the SQL dimension tests (sql/90_tests/01_dimension_tests.sql) find 0 violations
At the end the warehouse holds both extracts: src_pms, bronze, staging and the dimensions.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import db_apply_next_extract as next_extract  # noqa: E402
import test_quality as tq  # noqa: E402

from etl.dimensions import load, spec  # noqa: E402
from etl.dimensions import run as dims  # noqa: E402
from etl.ingest import run as ingest  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402
from etl.quality import run as quality  # noqa: E402
from etl.staging import run as staging  # noqa: E402

DATA = ROOT / "data"
TESTS_SQL = ROOT / "sql" / "90_tests" / "01_dimension_tests.sql"
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def profile() -> str:
    import json

    return json.loads((DATA / "run_manifest.json").read_text(encoding="utf-8"))["profile"]["name"]


def key_file(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def empty_dimensions(cur) -> None:
    """Facts point at the dimensions: empty them first (E7 reloads them), then the members."""
    cur.execute("SELECT string_agg('lue_dw.' || tablename, ', ') FROM pg_tables WHERE schemaname = 'lue_dw' AND tablename LIKE 'fact\\_%' ESCAPE '\\'")
    facts = cur.fetchone()[0]
    if facts:
        cur.execute(f"TRUNCATE {facts}")
    for d in reversed(spec.DIMS):
        cur.execute(f"DELETE FROM lue_dw.{d.name} WHERE {d.key} > 0")
    cur.execute("UPDATE lue_dw.dim_date SET is_public_holiday = FALSE, holiday_name = NULL, is_ramadan = FALSE WHERE date_key > 0")


def sql_tests(cur) -> list[tuple]:
    cur.execute(TESTS_SQL.read_text(encoding="utf-8"))
    return cur.fetchall()


# ----------------------------------------------------------------------------- first extract
def first_load(cur) -> dict:
    print("US-6.1 and US-6.4 The first load")
    _r, res, loads = dims.load_all()
    check(all(r.status == "Success" for r in res) and len(res) == len(spec.DIMS) + 1,
          f"holidays and {len(spec.DIMS)} dimensions loaded in order: " + ", ".join(r.step for r in res))
    staged = {"dim_owner": "stg_owner", "dim_vendor": "stg_vendor", "dim_incentive": "stg_incentive_offer",
              "dim_weather": "stg_weather", "dim_unit": "stg_unit", "dim_tenant": "stg_tenant", "dim_lease": "stg_lease"}
    counts = {d: scalar(cur, f"SELECT count(*) FROM lue_staging.{t}") for d, t in staged.items()}
    counts["dim_maintenance_category"] = scalar(cur, "SELECT count(DISTINCT subcategory_code) FROM lue_staging.stg_maintenance_category")
    ok = all(loads[d].inserted == n for d, n in counts.items())
    check(ok, "every staged natural key is a member, once: " + ", ".join(f"{d[4:]} {n:,}" for d, n in counts.items()))
    big = {d: n for d, n in counts.items() if d in ("dim_unit", "dim_tenant", "dim_lease", "dim_owner", "dim_weather", "dim_vendor")}
    if profile() == "full":
        check(all(n >= 100 for n in big.values()), "the large dimensions hold over 100 members (the brief's minimum, full profile)")
    else:
        check(all(n > 0 for n in big.values()), f"the large dimensions are populated ({profile()} profile; the brief's 100-member minimum applies to the full profile)")
    bad = []
    for d in spec.DIMS:
        n, keys, low, specials = cur.execute(f"SELECT count(*), count(DISTINCT {d.key}), min({d.key}) FILTER (WHERE {d.key} > 0), count(*) FILTER (WHERE {d.key} < 0) FROM lue_dw.{d.name}") or cur.fetchone()
        if n != keys or (low or 1) < 1 or specials != 2:
            bad.append(d.name)
    check(not bad, "surrogate keys unique and positive, the special members -1 and -2 untouched, in every dimension" + (f": {bad}" if bad else ""))
    late = {r["tenant_code"] for r in key_file("s1/late_arriving/tenants.csv")}
    inferred = {r[0] for r in (cur.execute("SELECT tenant_code FROM lue_dw.dim_tenant WHERE is_inferred") or cur.fetchall())}
    check(inferred == late and loads["dim_tenant"].inferred_created == len(late),
          f"US-6.5: the {len(late)} tenants leases and payments reference before they reach S1 are inferred members "
          "(the late_arriving file's tenants exactly)")
    cur.execute("SELECT count(*) FILTER (WHERE building_age_band NOT IN ('0–5 yrs', '6–15 yrs', '16+ yrs')), count(*) FILTER (WHERE unit_nk <> building_code || '-' || unit_no) FROM lue_dw.dim_unit WHERE unit_key > 0")
    age, nk = cur.fetchone()
    cur.execute("SELECT count(*) FILTER (WHERE rain_band NOT IN ('None', 'Light', 'Heavy') OR heat_band NOT IN ('Mild', 'Hot', 'Extreme')) FROM lue_dw.dim_weather WHERE weather_key > 0")
    weather = cur.fetchone()[0]
    cur.execute("SELECT count(*) FILTER (WHERE portfolio_size_band NOT IN ('None', '1 unit', '2–5 units', '6+ units')) FROM lue_dw.dim_owner WHERE owner_key > 0")
    owners = cur.fetchone()[0]
    check(age == nk == weather == owners == 0,
          "US-6.4: unit natural key building-unit; age, rain, heat and portfolio bands all in their domains")
    hol = scalar(cur, "SELECT count(*) FILTER (WHERE is_public_holiday) || '/' || count(*) FILTER (WHERE is_ramadan) FROM lue_dw.dim_date")
    reg = scalar(cur, "SELECT count(*) FILTER (WHERE is_public_holiday) || '/' || count(*) FILTER (WHERE is_ramadan) FROM lue_staging.stg_holiday")
    check(hol == reg, f"US-6.4: dim_date holiday and Ramadan flags from the S2 register ({hol} public holidays / Ramadan days)")

    print("US-6.3 Vendor and category history")
    rated = scalar(cur, "SELECT count(*) FROM lue_staging.stg_vendor WHERE rating_changed_on IS NOT NULL AND previous_rating IS DISTINCT FROM rating")
    wrong = scalar(cur, """
        SELECT count(*) FROM lue_staging.stg_vendor s WHERE s.rating_changed_on IS NOT NULL AND s.previous_rating IS DISTINCT FROM s.rating
          AND NOT EXISTS (SELECT 1 FROM lue_dw.dim_vendor a JOIN lue_dw.dim_vendor b USING (vendor_code)
                          WHERE a.vendor_code = s.vendor_code AND a.effective_to = s.rating_changed_on AND a.rating_band = s.previous_rating
                            AND b.effective_from = s.rating_changed_on AND b.rating_band = s.rating AND b.is_current)""")
    check(loads["dim_vendor"].versions == rated and wrong == 0,
          f"each vendor rating change ({rated}) is one new version from the change date, the old rating kept before it")
    sla = scalar(cur, """
        SELECT count(*) FROM lue_staging.stg_maintenance_category s WHERE NOT EXISTS (
            SELECT 1 FROM lue_dw.dim_maintenance_category d WHERE d.subcategory_code = s.subcategory_code
              AND d.default_sla_hours = s.default_sla_hours
              AND (d.effective_from = s.valid_from OR (d.effective_from = DATE '1900-01-01' AND s.valid_from = (
                   SELECT min(valid_from) FROM lue_staging.stg_maintenance_category m WHERE m.subcategory_code = s.subcategory_code))))""")
    changed = scalar(cur, "SELECT count(*) - count(DISTINCT subcategory_code) FROM lue_staging.stg_maintenance_category")
    check(sla == 0 and loads["dim_maintenance_category"].versions == changed,
          f"each SLA change ({changed}) is a new category version; every earlier SLA value is kept as it was")

    _r, res, loads2 = dims.load_all()
    moved = {d: (x.written, x.changed) for d, x in loads2.items() if isinstance(x, load.DimLoad) and (x.written or x.changed)}
    check(not moved and loads2["holidays"] == 0, "US-6.1: a rerun inserts nothing, adds no version and changes nothing")
    return loads


def type1_and_keys(cur) -> None:
    print("US-6.1 Type 1 in place, keys never reused, a bad source refused")
    cur.execute("SELECT tenant_code, tenant_name FROM lue_staging.stg_tenant ORDER BY tenant_code LIMIT 1")
    code, name = cur.fetchone()
    key = scalar(cur, "SELECT tenant_key FROM lue_dw.dim_tenant WHERE tenant_code = %s AND is_current", (code,))
    cur.execute("UPDATE lue_staging.stg_tenant SET tenant_name = tenant_name || ' (corrected)' WHERE tenant_code = %s", (code,))
    try:
        _r, _res, loads = dims.load_all()
        cur.execute("SELECT tenant_key, tenant_name FROM lue_dw.dim_tenant WHERE tenant_code = %s AND is_current", (code,))
        k, nm = cur.fetchone()
        check(loads["dim_tenant"].members_updated == 1 and loads["dim_tenant"].versions == 0 and k == key and nm.endswith("(corrected)"),
              f"a Type 1 correction (the name of {code}) is overwritten in place: same key {key}, no new version")
    finally:
        cur.execute("UPDATE lue_staging.stg_tenant SET tenant_name = %s WHERE tenant_code = %s", (name, code))
    dims.load_all()
    bad = []
    for d in spec.DIMS:
        cur.execute(f"SELECT pg_get_serial_sequence('lue_dw.{d.name}', '{d.key}')")
        seq = cur.fetchone()[0]
        last, top = scalar(cur, f"SELECT last_value FROM {seq}"), scalar(cur, f"SELECT max({d.key}) FROM lue_dw.{d.name}")
        if last < top:
            bad.append(d.name)
    check(not bad, "every surrogate key comes from its identity sequence, which only moves forward: a key is never reused")
    t = spec.BY_NAME["dim_tenant"]
    twice = spec.Dim("dim_tenant", "tenant_key", ["tenant_code"], story="test", scd2=True, inferred=True,
                     source=t.source + " UNION ALL (" + t.source + " ORDER BY 1 LIMIT 1)", cols=t.cols)
    before = scalar(cur, "SELECT count(*) FROM lue_dw.dim_tenant")
    conn = connect("lue_warehouse")
    try:
        with conn.cursor() as c:
            try:
                load.load_dimension(c, twice, 0, datetime.now())
                refused = ""
            except load.DimensionError as exc:
                refused = str(exc)
        conn.rollback()
    finally:
        conn.close()
    check("appear twice" in refused and scalar(cur, "SELECT count(*) FROM lue_dw.dim_tenant") == before,
          "a source with a natural key twice is refused and nothing changes")


# ----------------------------------------------------------------------------- next extract
def next_load(cur) -> None:
    print("US-6.2 and US-6.5 The next extract: tenant changes and late tenants")
    inferred_keys = dict(cur.execute("SELECT tenant_code, tenant_key FROM lue_dw.dim_tenant WHERE is_inferred") or cur.fetchall())
    check(next_extract.main([]) == 0, "next extract applied to src_pms (s1/changes and s1/late_arriving)")
    ingest.run(DATA, ["S1"])
    quality.validate()
    staging.stage(False, None)
    _r, res, loads = dims.load_all()
    x = loads["dim_tenant"]
    changes = key_file("s1/changes/tenants.csv")
    planted = {r["record_id"]: r for r in key_file("answer_key/defects_answer_key.csv") if r["defect_type"] == "tenant_attribute_change"}
    sector = [c for c in changes if planted[c["tenant_code"]]["column"] == "employer_sector"]
    channel = [c for c in changes if planted[c["tenant_code"]]["column"] == "contact_channel"]
    check(len(changes) == len(planted) == len(sector) + len(channel) and x.versions == len(sector),
          f"{len(planted)} planted changes: {len(sector)} employer-sector (Type 2) changes give {x.versions} new versions")
    wrong = []
    for c in sector:
        day = datetime.fromisoformat(c["updated_at"]).date()
        old = planted[c["tenant_code"]]["detail"].split("'")[1]
        cur.execute("SELECT employer_sector, effective_from, effective_to, is_current FROM lue_dw.dim_tenant WHERE tenant_code = %s ORDER BY effective_from", (c["tenant_code"],))
        v = cur.fetchall()
        if not (len(v) == 2 and v[0][0] == old and v[0][2] == day and not v[0][3] and v[1][0] == c["employer_sector"] and v[1][1] == day and v[1][3]):
            wrong.append(c["tenant_code"])
    check(not wrong, "each Type 2 change: the old sector valid until the change date, the new one from it (one current version)"
          + (f": {wrong[:5]}" if wrong else ""))
    wrong = [c["tenant_code"] for c in channel
             if (cur.execute("SELECT count(*), max(contact_channel) FROM lue_dw.dim_tenant WHERE tenant_code = %s", (c["tenant_code"],)) or cur.fetchone()) != (1, c["contact_channel"])]
    check(not wrong, f"each contact-channel change ({len(channel)}, Type 1 in the data dictionary) is overwritten in place, no version")
    if sector:  # past-month query on a tenant whose Type 2 attribute changed
        c = sector[0]
        member, day = c["tenant_code"], datetime.fromisoformat(c["updated_at"]).date()
        old, new = planted[member]["detail"].split("'")[1], c["employer_sector"]
        q = "SELECT employer_sector FROM lue_dw.dim_tenant WHERE tenant_code = %s AND %s >= effective_from AND %s < effective_to"
    else:  # no tenant Type 2 change planted in this profile: the same query on a vendor rating change
        cur.execute("SELECT vendor_code, rating_changed_on, previous_rating, rating FROM lue_staging.stg_vendor WHERE rating_changed_on IS NOT NULL AND previous_rating IS DISTINCT FROM rating ORDER BY vendor_code LIMIT 1")
        member, day, old, new = cur.fetchone()
        q = "SELECT rating_band FROM lue_dw.dim_vendor WHERE vendor_code = %s AND %s >= effective_from AND %s < effective_to"
    before = scalar(cur, q, (member, day - timedelta(days=30), day - timedelta(days=30)))
    after = scalar(cur, q, (member, day, day))
    check(before == old and after == new,
          f"past-month query: {member} a month before {day} is '{before}', from {day} '{after}'")
    cur.execute("SELECT tenant_code, tenant_key, is_inferred, (SELECT count(*) FROM lue_dw.dim_tenant v WHERE v.tenant_code = d.tenant_code) FROM lue_dw.dim_tenant d WHERE tenant_code = ANY(%s)", (list(inferred_keys),))
    done = cur.fetchall()
    check(x.inferred_completed == len(inferred_keys) and all(not inf and n == 1 and inferred_keys[code] == key for code, key, inf, n in done),
          f"the {len(inferred_keys)} inferred tenants are completed in place: same key, is_inferred FALSE, no new version")
    _r, res, loads = dims.load_all()
    y = loads["dim_tenant"]
    check(y.versions == y.written == y.changed == 0, "a rerun creates no version (idempotent)")

    print("US-6.5 The SQL dimension tests")
    rows = sql_tests(cur)
    bad = [(t, n) for t, n in rows if n]
    check(len(rows) >= 40 and not bad, f"{len(rows)} tests in sql/90_tests/01_dimension_tests.sql, 0 violations" + (f": {bad}" if bad else ""))


def main() -> int:
    print("=" * 70)
    print(" E6 acceptance tests: the dimensions (US-6.1 to US-6.5)")
    print("=" * 70)
    if not (DATA / "s1" / "changes" / "tenants.csv").is_file():
        print("  [FAIL] no data/s1/changes: run python etl/generate_data.py (with the defects)")
        return 1
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    try:
        with wh.cursor() as cur:
            try:
                dims.check_ready(cur)
            except dims.NotReady as exc:
                print(f"  [FAIL] {exc}")
                return 1
            print("Setup: the first extract into src_pms, bronze and staging; dimension members emptied")
            ok = tq.load_and_ingest(cur, DATA) and quality.validate()[1].status != "Failed"
            ok = ok and all(r.status != "Failed" for r in staging.stage(True, None)[1])
            empty_dimensions(cur)
            check(ok, "first extract loaded, validated and staged")
            first_load(cur)
            type1_and_keys(cur)
            next_load(cur)
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
