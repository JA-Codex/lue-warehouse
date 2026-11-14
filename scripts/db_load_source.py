#!/usr/bin/env python3
"""Create the S1 tables and load the generated master data into lue_source.src_pms (US-2.2).

    python etl/generate_data.py
    python scripts/db_load_source.py [--data data]

Runs sql/05_source/*.sql as lue_etl in lue_source, then replaces the contents of the S1 tables
the generator has files for (data/s1/*.csv) with those files. It all happens in one transaction,
so it loads completely or not at all. Safe to re-run: a second run gives the same rows.
Run scripts/db_setup.py first (US-1.1).

Later stories add their tables to TABLES (leases, invoices, payments) in load order.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_setup import (  # noqa: E402
    ETL_ROLE,
    ROOT,
    SOURCE_DB,
    load_settings,
    run_sql_file,
)

SOURCE_SCHEMA = "src_pms"
DDL_DIR = ROOT / "sql" / "05_source"
# Tables loaded from data/s1/<table>.csv, in load order (parents before children).
TABLES = ["buildings", "units", "tenants", "charge_types", "payment_methods"]


def truncate_sql(tables: list[str]) -> str:
    """One statement that empties every listed table, so no reload ever doubles rows."""
    names = ", ".join(f'{SOURCE_SCHEMA}."{t}"' for t in tables)
    return f"TRUNCATE {names}"


def copy_sql(table: str, columns: list[str]) -> str:
    """The COPY statement that reads a header-first CSV from standard input."""
    cols = ", ".join(f'"{c}"' for c in columns)
    return (
        f'COPY {SOURCE_SCHEMA}."{table}" ({cols}) FROM STDIN '
        "WITH (FORMAT csv, HEADER true, NULL '')"
    )


def csv_columns(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="folder the generator wrote")
    args = ap.parse_args()

    try:
        import psycopg2
    except ImportError:
        print("[FAIL] psycopg2 is missing: pip install -r requirements.txt")
        return 1

    folder = args.data / "s1"
    missing = [t for t in TABLES if not (folder / f"{t}.csv").is_file()]
    if missing:
        print(f"[FAIL] no CSV for {', '.join(missing)} in {folder}")
        print("       Generate the data first: python etl/generate_data.py")
        return 1

    s = load_settings()
    print("=" * 70)
    print(f" LUE Warehouse - load S1 master data into {SOURCE_DB}.{SOURCE_SCHEMA} as {ETL_ROLE}")
    print("=" * 70)
    try:
        conn = psycopg2.connect(
            host=s.get("PGHOST", "localhost"),
            port=int(s.get("PGPORT", "5432")),
            user=ETL_ROLE,
            password=s.get("LUE_ETL_PASSWORD", ""),
            dbname=SOURCE_DB,
            connect_timeout=10,
        )
    except psycopg2.Error as exc:
        print(f"[FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print("       Run python scripts/db_setup.py first, and check LUE_ETL_PASSWORD in .env.")
        return 1
    try:
        conn.autocommit = False  # one transaction: all of it or none of it
        for f in sorted(DDL_DIR.glob("*.sql")):
            run_sql_file(conn, f)
            print(f"[OK]   {f.relative_to(ROOT).as_posix()}")
        with conn.cursor() as cur:
            cur.execute(truncate_sql(TABLES))
            for table in TABLES:
                path = folder / f"{table}.csv"
                with path.open(encoding="utf-8", newline="") as fh:
                    cur.copy_expert(copy_sql(table, csv_columns(path)), fh)
            counts = []
            for table in TABLES:
                cur.execute(f'SELECT count(*) FROM {SOURCE_SCHEMA}."{table}"')
                counts.append((table, cur.fetchone()[0]))
        conn.commit()
    except (psycopg2.Error, OSError, StopIteration) as exc:
        conn.rollback()
        print(f"[FAIL] {exc}".rstrip())
        print("       Nothing was changed (the load was rolled back).")
        return 1
    finally:
        conn.close()
    for table, n in counts:
        print(f"[OK]   {SOURCE_SCHEMA}.{table:<16} {n:>6} rows")
    print("=" * 70)
    print(" RESULT: S1 MASTER DATA LOADED. Check it with: python scripts/test_source_load.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
