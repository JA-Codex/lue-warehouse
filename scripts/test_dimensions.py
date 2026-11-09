#!/usr/bin/env python3
"""Acceptance tests for US-1.2 (dimension DDL with keys and special members).

    python scripts/test_dimensions.py            run every check
    python scripts/test_dimensions.py --no-rerun skip the "deploy again, nothing changes" check

Runs as lue_etl. Constraint tests run inside a transaction that is rolled back, and the identity
sequences are put back afterwards, so the first real member loaded later still gets key 1.
Leaves nothing behind.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_contract import FROZEN, read_model  # noqa: E402
from db_setup import ETL_ROLE, READER_ROLE, WAREHOUSE_DB, load_settings  # noqa: E402

SMART_KEY = {"dim_date"}  # YYYYMMDD key, loaded in US-1.4; no identity
NO_SPECIAL = {"dim_request_flags"}  # all 8 flag combinations always exist (Phase 1 design)
NO_LINEAGE = {"dim_date", "dim_request_flags"}  # generated, not loaded from a source
SCD2 = {
    "dim_unit": "unit_nk",
    "dim_tenant": "tenant_code",
    "dim_maintenance_category": "subcategory_code",
    "dim_vendor": "vendor_code",
}
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def connect(s, user, password):
    import psycopg2

    return psycopg2.connect(
        host=s.get("PGHOST", "localhost"),
        port=int(s.get("PGPORT", "5432")),
        user=user,
        password=password,
        dbname=WAREHOUSE_DB,
        connect_timeout=10,
    )


def expected_dimensions() -> dict:
    """Dimension names and key columns, read from the frozen Phase 1 pack (not typed by hand)."""
    model = read_model([FROZEN.read_text(encoding="utf-8")])
    return {n: t["columns"][0][0] for n, t in model["tables"].items() if n.startswith("dim_")}


def violates(cur, statement, params=None) -> tuple[str | None, str | None]:
    """Run a statement inside a savepoint; return (sqlstate, constraint name) if it fails."""
    import psycopg2

    cur.execute("SAVEPOINT t")
    try:
        cur.execute(statement, params)
    except psycopg2.Error as exc:
        cur.execute("ROLLBACK TO SAVEPOINT t")
        return exc.pgcode, getattr(exc.diag, "constraint_name", None)
    cur.execute("RELEASE SAVEPOINT t")
    return None, None


def copy_special_row(cur, table, key, overrides):
    """INSERT ... SELECT that copies the -1 row of a table, letting the identity assign the key."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'lue_dw' "
        "AND table_name = %s AND column_name <> %s ORDER BY ordinal_position",
        (table, key),
    )
    cols = [r[0] for r in cur.fetchall()]
    exprs = [f"%({c})s" if c in overrides else c for c in cols]
    sql = (
        f"INSERT INTO lue_dw.{table} ({', '.join(cols)}) "
        f"SELECT {', '.join(exprs)} FROM lue_dw.{table} WHERE {key} = -1 RETURNING {key}"
    )
    return sql, overrides


def fingerprint(cur) -> list:
    cur.execute(
        "SELECT c.relname, (xpath('/row/n/text()', query_to_xml("
        "format('SELECT count(*) AS n FROM lue_dw.%I', c.relname), false, true, '')))[1]::text "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'lue_dw' AND c.relkind = 'r' ORDER BY 1"
    )
    rows = cur.fetchall()
    cur.execute(
        "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = 'lue_dw'::regnamespace ORDER BY 1, 2"
    )
    rows += cur.fetchall()
    cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'lue_dw' ORDER BY 1")
    return rows + cur.fetchall()


def main() -> int:
    import psycopg2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--no-rerun", action="store_true")
    args = ap.parse_args()
    s = load_settings()
    dims = expected_dimensions()

    print("=" * 70)
    print(" US-1.2 acceptance tests: dimension DDL, keys and special members")
    print("=" * 70)
    try:
        conn = connect(s, ETL_ROLE, s.get("LUE_ETL_PASSWORD", ""))
    except psycopg2.OperationalError as exc:
        print(f"  [FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print(" RESULT: FAILED (is PostgreSQL running, and has db_setup.py been run?)")
        return 1
    conn.autocommit = True
    cur = conn.cursor()

    print("Structure (13 dimensions, names from the Phase 1 pack)")
    cur.execute(
        "SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'lue_dw' AND c.relkind = 'r' AND c.relname LIKE 'dim\\_%%'"
    )
    found = dict(cur.fetchall())
    check(
        sorted(found) == sorted(dims) and len(dims) == 13,
        f"lue_dw has exactly the {len(dims)} dimensions of the pack"
        + ("" if sorted(found) == sorted(dims) else f" (missing {sorted(set(dims) - set(found))})"),
    )
    check(set(found.values()) == {ETL_ROLE}, f"every dimension is owned by {ETL_ROLE}")

    cur.execute(
        "SELECT conrelid::regclass::text, contype, array_agg(conname::text) FROM pg_constraint "
        "WHERE connamespace = 'lue_dw'::regnamespace GROUP BY 1, 2"
    )
    cons = {(t.removeprefix("lue_dw."), k): v for t, k, v in cur.fetchall()}
    check(all((d, "p") in cons for d in dims), "every dimension has a primary key")
    check(
        all((d, "u") in cons for d in dims), "every dimension has a unique natural (business) key"
    )

    cur.execute(
        "SELECT table_name, column_name, is_identity, identity_generation "
        "FROM information_schema.columns "
        "WHERE table_schema = 'lue_dw' AND table_name LIKE 'dim\\_%%'"
    )
    colinfo = {}
    for t, c, ident, gen in cur.fetchall():
        colinfo.setdefault(t, {})[c] = (ident, gen)
    want_identity = sorted(set(dims) - SMART_KEY)
    has_identity = sorted(
        d for d in dims if colinfo.get(d, {}).get(dims[d]) == ("YES", "BY DEFAULT")
    )
    check(
        has_identity == want_identity,
        f"{len(want_identity)} surrogate keys are GENERATED BY DEFAULT AS IDENTITY "
        "(dim_date keeps YYYYMMDD)",
    )
    lineage = ("source_system", "batch_id", "loaded_at")
    check(
        all(all(c in colinfo.get(d, {}) for c in lineage) for d in set(dims) - NO_LINEAGE),
        f"{len(set(dims) - NO_LINEAGE)} sourced dimensions have source_system, batch_id, loaded_at",
    )

    print("Special members")
    ok_special = True
    for d, key in sorted(dims.items()):
        cur.execute(f"SELECT array_agg({key} ORDER BY {key}) FROM lue_dw.{d} WHERE {key} < 0")
        got = cur.fetchone()[0] or []
        if got != ([] if d in NO_SPECIAL else [-2, -1]):
            ok_special = False
            print(f"         {d}: special keys {got}")
    check(
        ok_special,
        "-1 (Unknown) and -2 (Not applicable) in 12 dimensions; none in dim_request_flags",
    )
    cur.execute(
        "SELECT tenant_name FROM lue_dw.dim_tenant WHERE tenant_key IN (-1, -2) ORDER BY 1 DESC"
    )
    check(
        [r[0] for r in cur.fetchall()] == ["Unknown", "Not applicable"],
        "special members are labelled Unknown and Not applicable",
    )

    print("First loaded member gets key 1")
    unused = []
    for d in want_identity:
        cur.execute(
            "SELECT pg_sequence_last_value(pg_get_serial_sequence(%s, %s)) IS NULL",
            (f"lue_dw.{d}", dims[d]),
        )
        unused.append(cur.fetchone()[0])
    check(all(unused), f"all {len(want_identity)} identity sequences are unused (next value is 1)")

    conn.autocommit = False
    try:
        sql, p = copy_special_row(
            cur,
            "dim_tenant",
            "tenant_key",
            {
                "tenant_code": "T-TEST",
                "effective_from": "2024-01-01",
                "effective_to": "9999-12-31",
                "is_current": True,
            },
        )
        cur.execute(sql, p)
        check(cur.fetchone()[0] == 1, "a new tenant inserted without a key receives tenant_key 1")

        print("SCD Type 2 rules (unit, tenant, maintenance category, vendor)")
        for d, nk in SCD2.items():
            key = dims[d]
            v1 = {
                nk: "SCD-TEST",
                "effective_from": "2024-01-01",
                "effective_to": "9999-12-31",
                "is_current": True,
            }
            sql, p = copy_special_row(cur, d, key, v1)
            state, _ = violates(cur, sql, p)
            v2 = dict(v1, effective_from="2025-01-01")
            sql2, p2 = copy_special_row(cur, d, key, v2)
            state2, con2 = violates(cur, sql2, p2)
            check(
                state is None and state2 == "23505" and con2 == f"uq_{d}_one_current",
                f"{d}: a second current row for one natural key is rejected ({con2})",
            )
            bad = {
                nk: "SCD-BAD",
                "effective_from": "2025-01-01",
                "effective_to": "2024-01-01",
                "is_current": False,
            }
            sql3, p3 = copy_special_row(cur, d, key, bad)
            state3, con3 = violates(cur, sql3, p3)
            check(
                state3 == "23514" and con3 == f"ck_{d}_effective_range",
                f"{d}: an inverted effective range is rejected ({con3})",
            )
            # The legitimate SCD2 change: expire the old version, insert the new one.
            cur.execute(
                f"UPDATE lue_dw.{d} SET effective_to = '2025-01-01', is_current = false "
                f"WHERE {nk} = 'SCD-TEST'"
            )
            state4, _ = violates(cur, sql2, p2)
            check(state4 is None, f"{d}: expire-and-insert (a valid new version) is accepted")

        print("Other pack constraints")
        sql, p = copy_special_row(
            cur,
            "dim_lease",
            "lease_key",
            {"lease_number": "L-TEST", "start_date": "2025-01-01", "end_date": "2024-01-01"},
        )
        state, con = violates(cur, sql, p)
        check(
            state == "23514" and con == "ck_lease_dates",
            "dim_lease: a lease ending before it starts is rejected (ck_lease_dates)",
        )
        sql, p = copy_special_row(cur, "dim_owner", "owner_key", {"owner_code": "Unknown"})
        state, con = violates(cur, sql, p)
        check(state == "23505", "dim_owner: a duplicate natural key is rejected")
    except psycopg2.Error as exc:
        check(False, f"constraint tests stopped early: {exc}".strip())
    finally:
        conn.rollback()
        conn.autocommit = True
        # A rolled-back insert still advances an identity sequence; put every unused one back to 1.
        for d in want_identity:
            cur.execute(f"SELECT count(*) FROM lue_dw.{d} WHERE {dims[d]} > 0")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)",
                    (f"lue_dw.{d}", dims[d]),
                )

    print("Access")
    try:
        rd = connect(s, READER_ROLE, s.get("LUE_READER_PASSWORD", ""))
        rd.autocommit = True
        with rd.cursor() as rcur:
            try:
                rcur.execute("SELECT count(*) FROM lue_dw.dim_tenant")
                check(False, f"{READER_ROLE} cannot read lue_dw.dim_tenant")
            except psycopg2.Error as exc:
                check(exc.pgcode == "42501", f"{READER_ROLE} cannot read lue_dw.dim_tenant")
        rd.close()
    except psycopg2.OperationalError as exc:
        check(False, f"{READER_ROLE} login: {exc}".strip())

    if not args.no_rerun:
        print("Re-run")
        before = fingerprint(cur)
        run = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("db_deploy.py"))],
            capture_output=True,
            text=True,
        )
        check(run.returncode == 0, "running db_deploy.py a second time succeeds")
        check(
            fingerprint(cur) == before, "the second run changes no table, row, constraint or index"
        )
    conn.close()

    print("=" * 70)
    passed = sum(results)
    print(f" RESULT: {passed}/{len(results)} checks passed" + ("" if all(results) else " - FAILED"))
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
