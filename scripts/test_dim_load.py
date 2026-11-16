#!/usr/bin/env python3
"""Acceptance tests for US-6.1: the dimension loader and surrogate keys. Needs the database.

    python etl/staging/run.py          # staging loaded (E5)
    python scripts/test_dim_load.py

Empties the members of the dimensions in the spec (the special members -1 and -2 stay), loads
them, and checks:
  US-6.1  every staged member is created once with an identity surrogate key (positive, unique,
          the special members untouched); a rerun inserts and updates nothing (the run log
          agrees); a Type 1 change is overwritten in place with the key kept, a Type 2 change is
          left to the SCD2 step; a deleted member comes back with a new key (never reused); a
          source with a natural key twice is refused and changes nothing; the business key and
          surrogate key side by side (the brief's evidence).
At the end the dimensions hold staging again and staging is as it was.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.dimensions import load, spec  # noqa: E402
from etl.dimensions import run as dims  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def by_step(res) -> dict:
    return {r.step: r for r in res}


def loader_tests(cur) -> None:
    print("US-6.1 The loader and the surrogate keys")
    for d in spec.DIMS:
        cur.execute(f"DELETE FROM lue_dw.{d.name} WHERE {d.key} > 0")
    specials = {d.name: scalar(cur, f"SELECT count(*) FROM lue_dw.{d.name} WHERE {d.key} < 0") for d in spec.DIMS}
    run_id, res, loads = dims.load_all()
    t = spec.BY_NAME["dim_tenant"]
    staged = scalar(cur, "SELECT count(*) FROM lue_staging.stg_tenant")
    x = loads["dim_tenant"]
    check(all(r.status == "Success" for r in res) and x.inserted == staged == x.read,
          f"first load: every staged tenant is a member ({x.inserted:,} of {staged:,})")
    cur.execute(f"SELECT count(*), count(DISTINCT {t.key}), min({t.key}), count(DISTINCT tenant_code), "
                f"count(*) FILTER (WHERE NOT is_current OR effective_from <> '{spec.FIRST_DAY}' OR "
                f"effective_to <> '{spec.OPEN_END}' OR is_inferred) FROM lue_dw.dim_tenant WHERE {t.key} > 0")
    n, keys, low, codes, odd = cur.fetchone()
    check(n == keys == codes == staged and low >= 1 and odd == 0,
          f"surrogate keys from the identity: {keys:,} unique, all positive (from {low}); one row per "
          "tenant code, current, valid 1900-01-01 to 9999-12-31, not inferred")
    check(all(scalar(cur, f"SELECT count(*) FROM lue_dw.{d.name} WHERE {d.key} < 0") == specials[d.name] == 2
              for d in spec.DIMS),
          "the special members -1 (Unknown) and -2 (Not applicable) are untouched")
    wrong = scalar(cur, "SELECT count(*) FROM lue_dw.dim_tenant d JOIN lue_staging.stg_tenant s USING (tenant_code) "
                        "WHERE (d.tenant_name, d.tenant_type, d.employer_sector, d.contact_channel, d.source_system, "
                        "d.batch_id) IS DISTINCT FROM (s.tenant_name, s.tenant_type, s.employer_sector, "
                        "s.contact_channel, s.source_system, %s::bigint)", (run_id,))
    check(wrong == 0, "every member carries its staged values; batch_id is the pipeline run that loaded it")

    run2, res, loads = dims.load_all()
    x = loads["dim_tenant"]
    cur.execute("SELECT sum(rows_inserted), sum(rows_updated) FROM lue_audit.etl_run_log WHERE run_id = %s", (run2,))
    logged = tuple(cur.fetchone())
    check(x.inserted == 0 and x.updated == 0 and x.unchanged == staged and logged == (0, 0),
          f"a rerun inserts 0 and updates 0 ({x.unchanged:,} unchanged); the run log agrees")

    # Type 1 and Type 2 changes in staging.
    cur.execute("SELECT tenant_code, tenant_name, contact_channel, tenant_type FROM lue_staging.stg_tenant "
                "ORDER BY tenant_code LIMIT 2")
    (c1, name1, _ch1, type1), (c2, _n2, ch2, _t2) = cur.fetchall()
    key1 = scalar(cur, "SELECT tenant_key FROM lue_dw.dim_tenant WHERE tenant_code = %s", (c1,))
    other = "Corporate" if type1 != "Corporate" else "Individual"
    new_ch = "Email" if ch2 != "Email" else "Phone"
    cur.execute("UPDATE lue_staging.stg_tenant SET tenant_name = tenant_name || ' (corrected)', tenant_type = %s "
                "WHERE tenant_code = %s", (other, c1))
    cur.execute("UPDATE lue_staging.stg_tenant SET contact_channel = %s WHERE tenant_code = %s", (new_ch, c2))
    try:
        run3, res, loads = dims.load_all()
        x = loads["dim_tenant"]
        cur.execute("SELECT tenant_key, tenant_name, tenant_type, batch_id FROM lue_dw.dim_tenant WHERE tenant_code = %s",
                    (c1,))
        k, nm, typ, batch = cur.fetchone()
        ch = scalar(cur, "SELECT contact_channel FROM lue_dw.dim_tenant WHERE tenant_code = %s", (c2,))
        check(x.updated == 2 and x.inserted == 0 and k == key1 and nm == name1 + " (corrected)" and ch == new_ch
              and batch == run3,
              f"Type 1 (name of {c1}, contact channel of {c2}): overwritten in place, same surrogate key "
              f"({key1}), 2 rows updated, batch_id = the run")
        check(typ == type1, f"Type 2 (tenant type of {c1} to {other}): left as it was, for the SCD2 step (US-6.2)")
    finally:
        cur.execute("UPDATE lue_staging.stg_tenant SET tenant_name = %s, tenant_type = %s WHERE tenant_code = %s",
                    (name1, type1, c1))
        cur.execute("UPDATE lue_staging.stg_tenant SET contact_channel = %s WHERE tenant_code = %s", (ch2, c2))
    dims.load_all()

    top_key, top_code = None, None
    cur.execute("SELECT tenant_key, tenant_code FROM lue_dw.dim_tenant ORDER BY tenant_key DESC LIMIT 1")
    top_key, top_code = cur.fetchone()
    cur.execute("DELETE FROM lue_dw.dim_tenant WHERE tenant_key = %s", (top_key,))
    _r, _res, loads = dims.load_all()
    again = scalar(cur, "SELECT tenant_key FROM lue_dw.dim_tenant WHERE tenant_code = %s", (top_code,))
    check(loads["dim_tenant"].inserted == 1 and again > top_key,
          f"a member deleted and loaded again gets a new key ({top_code}: {top_key} -> {again}): keys are never reused")

    # A source with a natural key twice is refused, and nothing changes.
    before = scalar(cur, "SELECT count(*) FROM lue_dw.dim_tenant")
    bad = spec.Dim("dim_tenant", "tenant_key", ["tenant_code"], story="test", scd2=True, inferred=True,
                   source=t.source + " UNION ALL (" + t.source + " ORDER BY 1 LIMIT 1)", cols=t.cols)
    conn = connect("lue_warehouse")
    try:
        with conn.cursor() as c:
            try:
                load.load_dimension(c, bad, 0, None)
                refused = ""
            except load.DimensionError as exc:
                refused = str(exc)
        conn.rollback()
    finally:
        conn.close()
    check("appear twice" in refused and scalar(cur, "SELECT count(*) FROM lue_dw.dim_tenant") == before,
          f"a source with a natural key twice is refused, nothing changed ({refused[:60]}...)")

    print("US-6.1 Evidence: business key and surrogate key side by side")
    cur.execute("SELECT tenant_code, tenant_key, tenant_name, tenant_type, is_current FROM lue_dw.dim_tenant "
                "ORDER BY tenant_key LIMIT 7")
    rows = cur.fetchall()
    print(f"    {'tenant_code':12} {'tenant_key':>10}  tenant_name / type / current")
    for code, key, name, typ, cur_ in rows:
        print(f"    {code:12} {key:>10}  {name} / {typ} / {cur_}")
    check(len(rows) == 7 and rows[0][1] == -2 and rows[1][1] == -1, "the query lists the special members first, "
          "then tenants with their keys")


def main() -> int:
    print("=" * 70)
    print(" US-6.1 acceptance tests: the dimension loader (database)")
    print("=" * 70)
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
            loader_tests(cur)
            _r, res, _l = dims.load_all()
            check(all(r.status == "Success" for r in res), "the dimensions hold staging again")
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
