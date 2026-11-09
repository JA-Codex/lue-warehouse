#!/usr/bin/env python3
"""Deploy the warehouse DDL (US-1.2 onward).

    python scripts/db_deploy.py

Runs every file in sql/10_ddl/ in name order, as lue_etl in lue_warehouse, so lue_etl owns
every object.
Run scripts/db_setup.py first (US-1.1). Safe to re-run: the files use IF NOT EXISTS and ON CONFLICT.
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

DDL_DIR = ROOT / "sql" / "10_ddl"


def main() -> int:
    try:
        import psycopg2
    except ImportError:
        print("[FAIL] psycopg2 is missing: pip install -r requirements.txt")
        return 1

    s = load_settings()
    files = sorted(DDL_DIR.glob("*.sql"))
    print("=" * 70)
    print(f" LUE Warehouse - deploy {len(files)} DDL file(s) as {ETL_ROLE} to {WAREHOUSE_DB}")
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
        # One transaction for the whole deploy: a failure leaves the database as it was.
        conn.autocommit = False
        for f in files:
            run_sql_file(conn, f)
            print(f"[OK]   {f.relative_to(ROOT).as_posix()}")
        conn.commit()
    except psycopg2.Error as exc:
        conn.rollback()
        print(f"[FAIL] {f.name}: {exc}".rstrip())
        print("       Nothing was changed (the deploy was rolled back).")
        return 1
    finally:
        conn.close()
    print("=" * 70)
    print(" RESULT: DEPLOY COMPLETE. Check it with: python scripts/test_dimensions.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
