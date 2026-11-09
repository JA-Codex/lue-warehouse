#!/usr/bin/env python3
"""Acceptance tests for US-1.1 (databases, roles and schemas).

    python scripts/test_db_setup.py            run every check
    python scripts/test_db_setup.py --no-rerun skip the "run setup again, nothing changes" check

Logs in as each role with its real password from .env, so it also proves the passwords work.
Every check prints PASS or FAIL; the exit code is 0 only if all pass. Leaves nothing behind.
"""

import argparse
import subprocess
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_setup import (  # noqa: E402
    ETL_ROLE,
    READER_ROLE,
    SOURCE_DB,
    WAREHOUSE_DB,
    load_settings,
)

SCHEMAS = ["lue_audit", "lue_dw", "lue_reporting", "lue_staging"]
PROBE = "_us11_probe"
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def connect(s, user, password, dbname):
    import psycopg2

    conn = psycopg2.connect(
        host=s.get("PGHOST", "localhost"),
        port=int(s.get("PGPORT", "5432")),
        user=user,
        password=password,
        dbname=dbname,
        connect_timeout=10,
    )
    conn.autocommit = True
    return conn


def admin(s, dbname):
    return connect(s, s.get("PGUSER", "postgres"), s.get("PGPASSWORD", ""), dbname)


def fails_with(conn, statement, sqlstate) -> bool:
    """True if the statement fails with the given SQLSTATE (42501 = insufficient privilege)."""
    import psycopg2

    try:
        with conn.cursor() as cur:
            cur.execute(statement)
    except psycopg2.Error as exc:
        return exc.pgcode == sqlstate
    return False


def fingerprint(s) -> list:
    """Everything US-1.1 creates, as comparable rows: roles, databases, schemas, ACLs, settings."""
    rows = []
    with closing(admin(s, "postgres")) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT rolname, rolsuper, rolcanlogin, rolcreatedb, rolcreaterole FROM pg_roles "
            "WHERE rolname IN (%s, %s) ORDER BY 1",
            (ETL_ROLE, READER_ROLE),
        )
        rows += cur.fetchall()
        cur.execute(
            "SELECT datname, pg_get_userbyid(datdba), datacl::text FROM pg_database "
            "WHERE datname IN (%s, %s) ORDER BY 1",
            (SOURCE_DB, WAREHOUSE_DB),
        )
        rows += cur.fetchall()
        cur.execute(
            "SELECT coalesce(d.datname, '*'), r.rolname, s.setconfig::text "
            "FROM pg_db_role_setting s "
            "JOIN pg_roles r ON r.oid = s.setrole LEFT JOIN pg_database d ON d.oid = s.setdatabase "
            "WHERE r.rolname IN (%s, %s) ORDER BY 1, 2",
            (ETL_ROLE, READER_ROLE),
        )
        rows += cur.fetchall()
    for db in (SOURCE_DB, WAREHOUSE_DB):
        with closing(admin(s, db)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT nspname, pg_get_userbyid(nspowner), nspacl::text FROM pg_namespace "
                "WHERE nspname NOT LIKE 'pg\\_%%' AND nspname <> 'information_schema' ORDER BY 1"
            )
            rows += [(db, *r) for r in cur.fetchall()]
            cur.execute("SELECT defaclrole::regrole::text, defaclacl::text FROM pg_default_acl")
            rows += [(db, *r) for r in cur.fetchall()]
    return rows


def main() -> int:
    import psycopg2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--no-rerun", action="store_true")
    args = ap.parse_args()
    s = load_settings()
    etl_pw, reader_pw = s.get("LUE_ETL_PASSWORD", ""), s.get("LUE_READER_PASSWORD", "")

    print("=" * 70)
    print(" US-1.1 acceptance tests: databases, roles and schemas")
    print("=" * 70)

    print("Structure")
    with closing(admin(s, "postgres")) as conn, conn.cursor() as cur:
        for role in (ETL_ROLE, READER_ROLE):
            cur.execute(
                "SELECT count(*), bool_or(rolsuper) FROM pg_roles WHERE rolname = %s", (role,)
            )
            n, is_super = cur.fetchone()
            check(n == 1 and not is_super, f"role {role} exists once and is not a superuser")
        for db in (SOURCE_DB, WAREHOUSE_DB):
            cur.execute(
                "SELECT count(*), max(pg_get_userbyid(datdba)) FROM pg_database WHERE datname = %s",
                (db,),
            )
            n, owner = cur.fetchone()
            check(n == 1 and owner == ETL_ROLE, f"database {db} exists once, owned by {ETL_ROLE}")
    with closing(admin(s, WAREHOUSE_DB)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace "
            "WHERE nspname LIKE 'lue\\_%%' ORDER BY 1"
        )
        found = cur.fetchall()
        check(
            found == [(n, ETL_ROLE) for n in SCHEMAS],
            f"lue_warehouse has exactly the schemas {', '.join(SCHEMAS)}, owned by {ETL_ROLE}"
            + ("" if found == [(n, ETL_ROLE) for n in SCHEMAS] else f" (found {found})"),
        )
    with closing(admin(s, SOURCE_DB)) as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'src_pms'")
        row = cur.fetchone()
        check(row == (ETL_ROLE,), f"lue_source has schema src_pms, owned by {ETL_ROLE}")

    print(f"{ETL_ROLE} (pipeline)")
    etl = None
    try:
        etl = connect(s, ETL_ROLE, etl_pw, WAREHOUSE_DB)
        check(True, f"{ETL_ROLE} logs in to {WAREHOUSE_DB} with the password from .env")
        with etl.cursor() as cur:
            for schema in SCHEMAS:
                cur.execute(f"DROP TABLE IF EXISTS {schema}.{PROBE}")
                cur.execute(f"CREATE TABLE {schema}.{PROBE} (id int)")
                cur.execute(f"INSERT INTO {schema}.{PROBE} VALUES (1)")
            check(True, f"{ETL_ROLE} can create and write tables in all four schemas")
            cur.execute("SHOW search_path")
            path = cur.fetchone()[0]
            check(path.startswith("lue_dw"), f"{ETL_ROLE} search_path starts with lue_dw")
        src = connect(s, ETL_ROLE, etl_pw, SOURCE_DB)
        with src.cursor() as cur:
            cur.execute(f"CREATE TABLE src_pms.{PROBE} (id int)")
            cur.execute(f"DROP TABLE src_pms.{PROBE}")
        src.close()
        check(True, f"{ETL_ROLE} can create tables in {SOURCE_DB}.src_pms")
    except psycopg2.Error as exc:
        check(False, f"{ETL_ROLE} setup checks: {exc}".strip())

    print(f"{READER_ROLE} (Power BI)")
    try:
        rd = connect(s, READER_ROLE, reader_pw, WAREHOUSE_DB)
        check(True, f"{READER_ROLE} logs in to {WAREHOUSE_DB} with the password from .env")
        with rd.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM lue_reporting.{PROBE}")
            check(cur.fetchone()[0] == 1, f"{READER_ROLE} can read a new lue_reporting table")
            cur.execute("SHOW default_transaction_read_only")
            check(cur.fetchone()[0] == "on", f"{READER_ROLE} sessions start read-only")
            cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE")
        # Read-only mode switched off above, so these prove the privileges themselves block writes.
        check(fails_with(rd, f"INSERT INTO lue_reporting.{PROBE} VALUES (2)", "42501"),
              f"{READER_ROLE} cannot insert into lue_reporting (permission denied)")
        check(fails_with(rd, "CREATE TABLE lue_reporting.x_reader (id int)", "42501"),
              f"{READER_ROLE} cannot create tables in lue_reporting")
        check(fails_with(rd, "CREATE TABLE public.x_reader (id int)", "42501"),
              f"{READER_ROLE} cannot create tables in public")
        for schema in ("lue_dw", "lue_staging", "lue_audit"):
            check(fails_with(rd, f"SELECT * FROM {schema}.{PROBE}", "42501"),
                  f"{READER_ROLE} cannot read {schema}")
        rd.close()
    except psycopg2.Error as exc:
        check(False, f"{READER_ROLE} checks: {exc}".strip())
    try:
        connect(s, READER_ROLE, reader_pw, SOURCE_DB).close()
        check(False, f"{READER_ROLE} cannot connect to {SOURCE_DB}")
    except psycopg2.OperationalError as exc:
        check("permission denied" in str(exc), f"{READER_ROLE} cannot connect to {SOURCE_DB}")

    if etl is not None:
        with etl.cursor() as cur:
            for schema in SCHEMAS:
                cur.execute(f"DROP TABLE IF EXISTS {schema}.{PROBE}")
        etl.close()

    if not args.no_rerun:
        print("Re-run")
        before = fingerprint(s)
        run = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("db_setup.py"))],
            capture_output=True,
            text=True,
        )
        check(run.returncode == 0, "running db_setup.py a second time succeeds")
        check(fingerprint(s) == before, "the second run changes no role, database, schema or grant")

    passed = sum(results)
    print("=" * 70)
    print(f" RESULT: {passed}/{len(results)} checks passed" + ("" if all(results) else " - FAILED"))
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
