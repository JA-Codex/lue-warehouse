#!/usr/bin/env python3
"""Rebuild the warehouse side from scratch (US-1.5).

    python scripts/db_reset.py

Drops the four warehouse schemas (lue_staging, lue_dw, lue_reporting, lue_audit), then runs, in
order: db_setup.py, db_deploy.py, db_load_reference.py and test_smoke.py. It never touches the
source database lue_source or the roles. Use it whenever you want a clean warehouse.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_setup import ROOT, SETUP_DIR, WAREHOUSE_DB, connect, load_settings, run_sql_file  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
FOLLOW_UP = ["db_setup.py", "db_deploy.py", "db_load_reference.py", "test_smoke.py"]


def main() -> int:
    try:
        import psycopg2
    except ImportError:
        print("[FAIL] psycopg2 is missing: pip install -r requirements.txt")
        return 1

    s = load_settings()
    print("=" * 70)
    print(f" LUE Warehouse - reset {WAREHOUSE_DB} (the source database is not touched)")
    print("=" * 70)
    try:
        conn = connect(s, WAREHOUSE_DB)
    except psycopg2.Error as exc:
        print(f"[FAIL] cannot connect as the superuser: {exc}".rstrip())
        print("       Run python scripts/db_setup.py first, and check PGPASSWORD in .env.")
        return 1
    try:
        run_sql_file(conn, SETUP_DIR / "reset.sql")
        print("[OK]   reset.sql: warehouse schemas dropped")
    except psycopg2.Error as exc:
        print(f"[FAIL] reset.sql: {exc}".rstrip())
        return 1
    finally:
        conn.close()

    for name in FOLLOW_UP:
        print(f"--- {name}")
        run = subprocess.run([sys.executable, str(SCRIPTS / name)], cwd=ROOT)
        if run.returncode != 0:
            print(f"[FAIL] {name} failed; the reset stopped here.")
            return 1
    print("=" * 70)
    print(" RESULT: RESET COMPLETE. The warehouse is rebuilt and the smoke test passed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
