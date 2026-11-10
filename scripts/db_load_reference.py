#!/usr/bin/env python3
"""Load the calendar and the static reference dimensions (US-1.4).

    python scripts/db_load_reference.py

Runs sql/30_dimensions/01_reference_dimensions.sql as lue_etl in lue_warehouse, in one
transaction: it all loads or nothing does. Run scripts/db_deploy.py first (US-1.2, US-1.3).
Safe to re-run: a second run changes nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_setup import (  # noqa: E402
    ETL_ROLE,
    ROOT,
    WAREHOUSE_DB,
    load_settings,
    run_sql_file,
)

LOAD_FILE = ROOT / "sql" / "30_dimensions" / "01_reference_dimensions.sql"
TABLES = [
    "dim_date",
    "dim_payment_method",
    "dim_charge_type",
    "dim_lease_event_type",
    "dim_request_flags",
]


def main() -> int:
    try:
        import psycopg2
    except ImportError:
        print("[FAIL] psycopg2 is missing: pip install -r requirements.txt")
        return 1

    s = load_settings()
    print("=" * 70)
    print(f" LUE Warehouse - load reference dimensions as {ETL_ROLE} into {WAREHOUSE_DB}")
    print("=" * 70)
    try:
        conn = psycopg2.connect(
            host=s.get("PGHOST", "localhost"),
            port=int(s.get("PGPORT", "5432")),
            user=ETL_ROLE,
            password=s.get("LUE_ETL_PASSWORD", ""),
            dbname=WAREHOUSE_DB,
            connect_timeout=10,
        )
    except psycopg2.Error as exc:
        print(f"[FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print("       Run python scripts/db_setup.py first, and check LUE_ETL_PASSWORD in .env.")
        return 1
    try:
        conn.autocommit = False
        run_sql_file(conn, LOAD_FILE)
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(f"SELECT count(*) FROM lue_dw.{table}")
                print(f"[OK]   {table:<22} {cur.fetchone()[0]:>6} row(s)")
        conn.commit()
    except psycopg2.Error as exc:
        conn.rollback()
        print(f"[FAIL] {LOAD_FILE.name}: {exc}".rstrip())
        print("       Nothing was changed (the load was rolled back).")
        print("       If a table does not exist, run python scripts/db_deploy.py first.")
        return 1
    finally:
        conn.close()
    print("=" * 70)
    print(" RESULT: REFERENCE LOAD COMPLETE. Check it with: python scripts/test_reference.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
