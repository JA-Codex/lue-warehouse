#!/usr/bin/env python3
"""Create the LUE databases, roles and schemas (US-1.1).

    python scripts/db_setup.py

Runs sql/00_setup/01..05 in order as the admin user from .env (PGUSER, normally postgres),
then sets the passwords of lue_etl and lue_reader from .env. Safe to run any number of times:
a second run changes nothing.

psql is not required. The SQL files also run in psql (each header names the database to use);
this script reproduces psql's \\gexec so 02_databases.sql works the same way here.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP_DIR = ROOT / "sql" / "00_setup"

# Fixed by decisions D1 and D2 and written into the SQL files; .env must agree with them.
SOURCE_DB = "lue_source"
WAREHOUSE_DB = "lue_warehouse"
ETL_ROLE = "lue_etl"
READER_ROLE = "lue_reader"
ROLE_PASSWORDS = ((ETL_ROLE, "LUE_ETL_PASSWORD"), (READER_ROLE, "LUE_READER_PASSWORD"))

STEPS = [
    ("01_roles.sql", "postgres"),
    ("02_databases.sql", "postgres"),
    ("03_database_access.sql", "postgres"),
    ("04_source_schema.sql", SOURCE_DB),
    ("05_warehouse_schemas.sql", WAREHOUSE_DB),
]

GEXEC = re.compile(r"^\s*\\gexec\s*$")


def load_settings() -> dict[str, str]:
    """Values from .env win over variables already set in the shell, so .env is the single truth."""
    values = dict(os.environ)
    env_path = ROOT / ".env"
    if env_path.is_file():
        try:
            from dotenv import dotenv_values
        except ImportError:
            sys.exit("[FAIL] python-dotenv is missing: pip install -r requirements.txt")
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    else:
        print("[WARN] No .env file found; using environment variables only.")
    return values


def check_settings(s: dict[str, str]) -> list[str]:
    problems = []
    expected = {
        "PGDATABASE": WAREHOUSE_DB,
        "PGDATABASE_SOURCE": SOURCE_DB,
        "LUE_ETL_USER": ETL_ROLE,
        "LUE_READER_USER": READER_ROLE,
    }
    for key, value in expected.items():
        if s.get(key, value) != value:
            problems.append(f"{key} must be '{value}' (the SQL uses that name), not '{s[key]}'")
    for key in ("LUE_ETL_PASSWORD", "LUE_READER_PASSWORD"):
        if not s.get(key):
            problems.append(f"{key} is empty; set it in .env")
    return problems


def strip_meta(text: str) -> str:
    """Drop psql meta-command lines; return '' if only comments are left."""
    keep = [ln for ln in text.splitlines() if not ln.lstrip().startswith("\\")]
    code = "\n".join(keep)
    has_code = any(ln.strip() and not ln.strip().startswith("--") for ln in keep)
    return code if has_code else ""


def run_sql_file(conn, path: Path) -> int:
    """Execute a file. A query followed by \\gexec is run, then each value it returns is run."""
    chunks, current = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if GEXEC.match(line):
            chunks.append(("gexec", "\n".join(current)))
            current = []
        else:
            current.append(line)
    chunks.append(("plain", "\n".join(current)))

    generated = 0
    with conn.cursor() as cur:
        for kind, text in chunks:
            sql_text = strip_meta(text)
            if not sql_text:
                continue
            cur.execute(sql_text)
            if kind == "gexec":
                for (statement,) in cur.fetchall():
                    print(f"       running: {statement}")
                    cur.execute(statement)
                    generated += 1
    return generated


def connect(s: dict[str, str], dbname: str):
    import psycopg2

    conn = psycopg2.connect(
        host=s.get("PGHOST", "localhost"),
        port=int(s.get("PGPORT", "5432")),
        user=s.get("PGUSER", "postgres"),
        password=s.get("PGPASSWORD", ""),
        dbname=dbname,
        connect_timeout=10,
    )
    conn.autocommit = True  # CREATE DATABASE cannot run inside a transaction
    return conn


def main() -> int:
    try:
        import psycopg2  # noqa: F401
        from psycopg2 import sql
    except ImportError:
        print("[FAIL] psycopg2 is missing: pip install -r requirements.txt")
        return 1

    s = load_settings()
    problems = check_settings(s)
    if problems:
        for p in problems:
            print(f"[FAIL] {p}")
        return 1

    print("=" * 70)
    print(" LUE Warehouse - create databases, roles and schemas (US-1.1)")
    print("=" * 70)
    try:
        for filename, dbname in STEPS:
            conn = connect(s, dbname)
            try:
                if filename == STEPS[0][0]:
                    with conn.cursor() as cur:
                        cur.execute("SELECT current_user, current_setting('is_superuser')")
                        user, is_super = cur.fetchone()
                    if is_super != "on":
                        print(f"[FAIL] '{user}' is not a superuser; set PGUSER in .env to postgres")
                        return 1
                generated = run_sql_file(conn, SETUP_DIR / filename)
                note = f" ({generated} statement(s) generated)" if generated else ""
                print(f"[OK]   {filename:<28} on database {dbname}{note}")

                if filename == "01_roles.sql":
                    with conn.cursor() as cur:
                        for role, key in ROLE_PASSWORDS:
                            cur.execute(
                                sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier(role)),
                                (s[key],),
                            )
                    print(f"[OK]   {'passwords from .env':<28} {ETL_ROLE}, {READER_ROLE}")
            finally:
                conn.close()
    except psycopg2.Error as exc:
        print(f"\n[FAIL] {exc}".rstrip())
        print("       Check PGHOST, PGPORT, PGUSER, PGPASSWORD in .env and that PostgreSQL runs.")
        return 1

    print("=" * 70)
    print(" RESULT: SETUP COMPLETE. Check it with: python scripts/test_db_setup.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
