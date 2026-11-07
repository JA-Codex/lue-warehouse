#!/usr/bin/env python3
"""PostgreSQL connection and throwaway table test script for US-0.4.

Verifies the local environment for any team member:
1. Validates Python environment and dependencies.
2. Reads configuration from .env or environment variables.
3. Connects to PostgreSQL and queries the server version.
4. Creates a throwaway test table, inserts a test row, verifies it, and drops it.

Usage:
    python scripts/test_connection.py
    python scripts/test_connection.py --help
"""

import argparse
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse KEY=VALUE pairs from a .env file if python-dotenv is not available."""
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            values[key] = val
    return values


def load_environment(env_file_arg: str | None = None) -> Path | None:
    """Load environment variables from .env file (via dotenv or manual parser)."""
    env_path = Path(env_file_arg).resolve() if env_file_arg else ROOT / ".env"

    if env_path.is_file():
        try:
            import dotenv

            dotenv.load_dotenv(dotenv_path=env_path, override=False)
        except ImportError:
            # Fallback manual parsing if python-dotenv is not installed yet
            parsed = parse_env_file(env_path)
            for k, v in parsed.items():
                if k not in os.environ:
                    os.environ[k] = v
        return env_path
    return None


def run_test(
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
    table_name: str = "_lue_conn_test_tmp",
) -> int:
    """Run connection test, server version check, and throwaway table operations."""
    try:
        import psycopg2
        from psycopg2 import errorcodes
    except ImportError:
        print("[FAIL] psycopg2 is not installed.")
        print("       Install required packages using: pip install -r requirements.txt")
        return 1

    print("=" * 70)
    print(" LUE Warehouse - Local Environment & PostgreSQL Connection Test (US-0.4)")
    print("=" * 70)
    print(f"Timestamp:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Operating System:{platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python Version:  {platform.python_version()} ({sys.executable})")
    print(f"psycopg2 Version:{psycopg2.__version__}")
    print("-" * 70)
    print("Target Connection Parameters:")
    print(f"  Host:          {host}")
    print(f"  Port:          {port}")
    print(f"  User:          {user}")
    print("  Password:      " + ("*" * len(password) if password else "(empty)"))
    print(f"  Database:      {dbname}")
    print("-" * 70)

    conn = None
    connected_db = dbname

    # Step 1: Connect to the requested database, or fallback to 'postgres'
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=10,
        )
    except psycopg2.OperationalError as exc:
        err_msg = str(exc)
        # Check if database does not exist (catalog error 3D000)
        is_missing_db = (
            getattr(exc, "pgcode", None) == errorcodes.INVALID_CATALOG_NAME
            or f'database "{dbname}" does not exist' in err_msg
        )
        if is_missing_db and dbname != "postgres":
            print(
                f"[INFO] Target database '{dbname}' does not exist yet (expected prior to US-1.1)."
            )
            print("[INFO] Connecting to default maintenance database 'postgres' instead...")
            try:
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    dbname="postgres",
                    connect_timeout=10,
                )
                connected_db = "postgres"
            except Exception as fallback_exc:
                print(f"\n[FAIL] Could not connect to fallback database 'postgres': {fallback_exc}")
                print_troubleshooting(host, port, user)
                return 1
        else:
            print(f"\n[FAIL] Connection failed: {exc}")
            print_troubleshooting(host, port, user)
            return 1

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Step 2: Query and display PostgreSQL server version
            cur.execute("SELECT version();")
            pg_version = cur.fetchone()[0]
            print(f"[PASS] Connected successfully to database: '{connected_db}'")
            print(f"[PASS] Server Version:\n       {pg_version}")

            cur.execute(
                """
                SELECT current_database(),
                       current_user,
                       inet_server_addr(),
                       inet_server_port();
                """
            )
            curr_db, curr_user, srv_addr, srv_port = cur.fetchone()
            print(
                f"[INFO] Session: database='{curr_db}', user='{curr_user}', "
                f"server_addr='{srv_addr}:{srv_port}'"
            )
            print("-" * 70)

            # Step 3: Create throwaway table
            print(f"Testing throwaway table operations: table '{table_name}'...")
            cur.execute(f"DROP TABLE IF EXISTS {table_name};")
            cur.execute(
                f"""
                CREATE TABLE {table_name} (
                    test_id SERIAL PRIMARY KEY,
                    test_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    test_marker VARCHAR(50) NOT NULL
                );
                """
            )
            print(f"  [PASS] CREATE TABLE {table_name} succeeded.")

            # Step 4: Insert test row
            cur.execute(
                f"INSERT INTO {table_name} (test_marker) VALUES (%s) RETURNING test_id, test_time;",
                ("US-0.4 local environment check",),
            )
            test_id, test_time = cur.fetchone()
            print(f"  [PASS] INSERT INTO {table_name} succeeded (id={test_id}, time={test_time}).")

            # Step 5: Read and verify test row
            cur.execute(
                f"SELECT test_id, test_marker FROM {table_name} WHERE test_id = %s;",
                (test_id,),
            )
            row = cur.fetchone()
            if row and row[1] == "US-0.4 local environment check":
                print(f"  [PASS] SELECT verification passed (read back marker: '{row[1]}').")
            else:
                print(f"  [FAIL] SELECT verification failed: unexpected row {row}")
                return 1

            # Step 6: Drop throwaway table
            cur.execute(f"DROP TABLE IF EXISTS {table_name};")
            print(f"  [PASS] DROP TABLE {table_name} clean-up succeeded.")

    except Exception as exc:
        print(f"\n[FAIL] Database operation failed: {exc}")
        return 1
    finally:
        # Final cleanup attempt in case of error
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table_name};")
        except Exception:
            pass
        conn.close()

    print("=" * 70)
    print(" RESULT: ALL LOCAL ENVIRONMENT CHECKS PASSED (US-0.4)")
    print("=" * 70)
    return 0


def print_troubleshooting(host: str, port: int, user: str) -> None:
    """Print troubleshooting suggestions on connection failure."""
    print("\nTroubleshooting checklist:")
    print("  1. Is PostgreSQL installed and the service running?")
    print("     - Windows: Check Services (services.msc) for 'postgresql-x64-16'.")
    print("     - Linux/macOS: Run 'sudo systemctl status postgresql' or 'brew services list'.")
    print(f"  2. Is PostgreSQL listening on host '{host}' and port {port}?")
    print(f"  3. Are the credentials for user '{user}' in your .env file correct?")
    print("  4. If .env does not exist yet, copy .env.example to .env and set PGPASSWORD.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to custom .env file (default: root .env)",
    )
    parser.add_argument("--host", type=str, default=None, help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=None, help="PostgreSQL port")
    parser.add_argument("--user", type=str, default=None, help="PostgreSQL user")
    parser.add_argument("--password", type=str, default=None, help="PostgreSQL password")
    parser.add_argument("--dbname", type=str, default=None, help="Database name to connect to")
    parser.add_argument(
        "--table-name",
        type=str,
        default="_lue_conn_test_tmp",
        help="Throwaway table name",
    )

    args = parser.parse_args()

    loaded_env_path = load_environment(args.env_file)
    if loaded_env_path:
        print(f"[INFO] Loaded environment from {loaded_env_path}")
    else:
        print("[INFO] No .env file found; using environment variables or defaults.")

    host = args.host or os.getenv("PGHOST", "localhost")
    port = args.port or int(os.getenv("PGPORT", "5432"))
    user = args.user or os.getenv("PGUSER", "postgres")
    password = args.password if args.password is not None else os.getenv("PGPASSWORD", "postgres")
    dbname = args.dbname or os.getenv("PGDATABASE", "lue_warehouse")

    return run_test(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        table_name=args.table_name,
    )


if __name__ == "__main__":
    sys.exit(main())

