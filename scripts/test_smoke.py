#!/usr/bin/env python3
"""Smoke test (US-1.5): does the warehouse have everything Phase 1 and Phase 2 setup promise?

    python scripts/test_smoke.py

Counts the objects in lue_dw and lue_audit and the reference rows. Runs as lue_etl, changes nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_setup import ETL_ROLE, load_settings  # noqa: E402
from test_dimensions import check, connect, results  # noqa: E402


def scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> int:
    import psycopg2

    s = load_settings()
    print("=" * 70)
    print(" US-1.5 smoke test: is the whole warehouse in place?")
    print("=" * 70)
    try:
        conn = connect(s, ETL_ROLE, s.get("LUE_ETL_PASSWORD", ""))
    except psycopg2.OperationalError as exc:
        print(f"  [FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print(" RESULT: FAILED (run python scripts/db_setup.py first)")
        return 1
    conn.autocommit = True
    cur = conn.cursor()
    try:
        tables = (
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = '{}' AND c.relkind IN ('r', 'p') AND NOT c.relispartition"
        )
        dims = scalar(
            cur, "SELECT count(*) " + tables.format("lue_dw") + " AND c.relname LIKE 'dim\\_%'"
        )
        facts = scalar(
            cur, "SELECT count(*) " + tables.format("lue_dw") + " AND c.relname LIKE 'fact\\_%'"
        )
        audit = scalar(cur, "SELECT count(*) " + tables.format("lue_audit"))
        fks = scalar(
            cur,
            "SELECT count(*) FROM pg_constraint k JOIN pg_namespace n ON n.oid = k.connamespace "
            "WHERE n.nspname = 'lue_dw' AND k.contype = 'f' AND k.conparentid = 0",
        )
        parts = scalar(
            cur,
            "SELECT count(*) FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "JOIN pg_class p ON p.oid = i.inhparent JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'lue_dw' AND p.relname = 'fact_unit_occupancy_daily' "
            "AND c.relkind = 'r' AND c.relname NOT LIKE '%\\_default'",
        )
        print("Objects")
        check(dims == 13, f"13 dimension tables in lue_dw (found {dims})")
        check(facts == 6, f"6 fact tables in lue_dw (found {facts})")
        check(audit == 5, f"5 tables in lue_audit: 4 audit tables + etl_watermark (found {audit})")
        check(fks == 41, f"41 foreign keys from the facts to the dimensions (found {fks})")
        check(
            parts == 48,
            f"48 monthly partitions of fact_unit_occupancy_daily (plus a default) (found {parts})",
        )
        print("Reference data")
        check(
            scalar(cur, "SELECT count(*) FROM lue_dw.dim_date WHERE date_key > 0") == 1461,
            "dim_date has 1,461 days",
        )
        check(
            scalar(
                cur, "SELECT count(*) FROM lue_dw.dim_payment_method WHERE payment_method_key > 0"
            )
            == 6,
            "6 payment methods",
        )
        check(
            scalar(cur, "SELECT count(*) FROM lue_dw.dim_charge_type WHERE charge_type_key > 0")
            == 6,
            "6 charge types",
        )
        check(
            scalar(
                cur,
                "SELECT count(*) FROM lue_dw.dim_lease_event_type WHERE lease_event_type_key > 0",
            )
            == 4,
            "4 lease event types",
        )
        check(
            scalar(cur, "SELECT count(*) FROM lue_dw.dim_request_flags") == 8,
            "8 request-flag combinations",
        )
        print("Audit tables")
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'lue_audit' AND table_name = 'etl_watermark' "
            "ORDER BY ordinal_position"
        )
        check(
            [r[0] for r in cur.fetchall()]
            == ["source_system", "table_name", "last_watermark_value", "updated_at"],
            "etl_watermark has its 4 columns",
        )
        cur.execute(
            "SELECT is_identity FROM information_schema.columns WHERE table_schema = 'lue_audit' "
            "AND table_name = 'quarantine' AND column_name = 'quarantine_id'"
        )
        check(cur.fetchone()[0] == "YES", "quarantine_id is generated automatically")
    except psycopg2.Error as exc:
        check(False, f"a query failed: {exc}".strip())
    finally:
        conn.close()
    print("=" * 70)
    print(
        f" RESULT: {sum(results)}/{len(results)} checks passed"
        + ("" if results and all(results) else " - FAILED")
    )
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
