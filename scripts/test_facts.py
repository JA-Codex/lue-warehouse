#!/usr/bin/env python3
"""Acceptance tests for US-1.3 (fact DDL, foreign keys and partitions).

    python scripts/test_facts.py            run every check
    python scripts/test_facts.py --no-rerun skip the "deploy again, nothing changes" check

Runs as lue_etl. Insert tests run inside a transaction that is rolled back, and the identity
sequences are put back afterwards, so the first real fact row loaded later still gets key 1.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_contract import FROZEN, read_model  # noqa: E402
from db_setup import ETL_ROLE, READER_ROLE, load_settings  # noqa: E402
from test_dimensions import check, connect, fingerprint, results, violates  # noqa: E402

OCC = "fact_unit_occupancy_daily"
PRIMARY_KEYS = {  # US-1.3 step 2
    "fact_rent_invoice_line": ["invoice_line_sk"],
    "fact_payment": ["payment_alloc_sk"],
    OCC: ["snapshot_date_key", "unit_key"],
    "fact_maintenance_request": ["request_sk"],
    "fact_lease_event": ["lease_event_sk"],
    "fact_vacancy_incentive_coverage": ["coverage_date_key", "unit_key", "incentive_key"],
}
SURROGATE = {t: k[0] for t, k in PRIMARY_KEYS.items() if k[0].endswith("_sk")}


def months(first=(2023, 7), count=48):
    y, m = first
    for _ in range(count):
        nxt = (y + (m == 12), m % 12 + 1)
        yield f"{y}_{m:02d}", y * 10000 + m * 100 + 1, nxt[0] * 10000 + nxt[1] * 100 + 1
        y, m = nxt


def fact_row(cur, table, overrides):
    """INSERT filling every column with a valid value: -1 for keys, 1 for counts, else 0 or TEST."""
    cur.execute(
        "SELECT column_name, data_type, is_identity FROM information_schema.columns "
        "WHERE table_schema = 'lue_dw' AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    cols, vals = [], []
    for name, dtype, ident in cur.fetchall():
        if ident == "YES" and name not in overrides:
            continue
        cols.append(name)
        if name in overrides:
            vals.append(overrides[name])
        elif name.endswith("_key"):
            vals.append(-1)
        elif name.endswith("_count"):
            vals.append(1)  # ck_event_count: a factless event row counts 1
        elif dtype.startswith("timestamp"):
            vals.append("2024-01-01 00:00")
        elif dtype in ("character varying", "text", "character"):
            vals.append("TEST")
        elif dtype == "boolean":
            vals.append(False)
        elif dtype == "date":
            vals.append("2024-01-01")
        else:
            vals.append(0)
    marks = ", ".join(["%s"] * len(vals))
    return f"INSERT INTO lue_dw.{table} ({', '.join(cols)}) VALUES ({marks})", vals


def add_date(cur, date_key: int) -> None:
    """dim_date is empty until US-1.4: add one day (a copy of the -1 row) in the transaction."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'lue_dw' "
        "AND table_name = 'dim_date' AND column_name NOT IN ('date_key', 'full_date') "
        "ORDER BY ordinal_position"
    )
    cols = [r[0] for r in cur.fetchall()]
    cur.execute(
        f"INSERT INTO lue_dw.dim_date (date_key, full_date, {', '.join(cols)}) "
        f"SELECT %s, to_date(%s::text, 'YYYYMMDD'), {', '.join(cols)} "
        "FROM lue_dw.dim_date WHERE date_key = -1 ON CONFLICT DO NOTHING",
        (date_key, date_key),
    )


def main() -> int:
    import psycopg2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--no-rerun", action="store_true")
    args = ap.parse_args()
    s = load_settings()
    model = read_model([FROZEN.read_text(encoding="utf-8")])
    facts = sorted(n for n in model["tables"] if n.startswith("fact_"))
    pack_fks = sum(
        "FOREIGN KEY" in c for n in facts for c in model["tables"][n]["constraints"].values()
    )

    print("=" * 70)
    print(" US-1.3 acceptance tests: fact DDL, foreign keys and partitions")
    print("=" * 70)
    try:
        conn = connect(s, ETL_ROLE, s.get("LUE_ETL_PASSWORD", ""))
    except psycopg2.OperationalError as exc:
        print(f"  [FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print(" RESULT: FAILED (is PostgreSQL running, and has db_deploy.py been run?)")
        return 1
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET search_path TO pg_catalog")  # so table names always print as lue_dw.<name>

    print("Structure (6 facts, names from the Phase 1 pack)")
    cur.execute(
        "SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'lue_dw' "
        "AND c.relkind IN ('r', 'p') AND NOT c.relispartition AND c.relname LIKE 'fact\\_%%'"
    )
    found = dict(cur.fetchall())
    check(sorted(found) == facts and len(facts) == 6, f"lue_dw has exactly the {len(facts)} facts")
    check(set(found.values()) == {ETL_ROLE}, f"every fact is owned by {ETL_ROLE}")

    cur.execute(
        "SELECT c.conrelid::regclass::text, array_agg(a.attname::text ORDER BY k.ord) "
        "FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(att, ord) "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.att "
        "WHERE c.contype = 'p' AND c.conparentid = 0 AND c.connamespace = 'lue_dw'::regnamespace "
        "AND c.conrelid::regclass::text LIKE 'lue_dw.fact\\_%%' GROUP BY 1"
    )
    pks = {t.removeprefix("lue_dw."): cols for t, cols in cur.fetchall()}
    check(pks == PRIMARY_KEYS, "primary keys: surrogate on 4 facts, composite on the 2 snapshots")

    cur.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = "
        "'lue_dw' AND table_name LIKE 'fact\\_%%' AND identity_generation = 'BY DEFAULT'"
    )
    check(
        dict(cur.fetchall()) == SURROGATE,
        "the 4 fact surrogate keys are GENERATED BY DEFAULT AS IDENTITY",
    )

    cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE confrelid::regclass::text LIKE 'lue_dw.dim\\_%%') "
        "FROM pg_constraint WHERE contype = 'f' AND connamespace = 'lue_dw'::regnamespace "
        "AND conrelid::regclass::text LIKE 'lue_dw.fact\\_%%' AND conparentid = 0"
    )
    n_fk, n_to_dim = cur.fetchone()
    check(
        n_fk == pack_fks == 41 and n_to_dim == 41,
        f"{n_fk} foreign keys, all to lue_dw dimensions (the pack has {pack_fks})",
    )

    print("Partitions (occupancy snapshot)")
    cur.execute(
        "SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) FROM pg_inherits i "
        "JOIN pg_class c ON c.oid = i.inhrelid WHERE i.inhparent = %s::regclass "
        "AND c.relkind = 'r' ORDER BY 1",
        (f"lue_dw.{OCC}",),
    )
    parts = dict(cur.fetchall())
    want = {
        f"{OCC}_{suffix}": f"FOR VALUES FROM ({lo}) TO ({hi})" for suffix, lo, hi in months()
    }
    monthly = {k: v for k, v in parts.items() if k != f"{OCC}_default"}
    check(monthly == want, "48 monthly partitions, July 2023 to June 2027, no gaps or overlaps")
    check(parts.get(f"{OCC}_default") == "DEFAULT", "a default partition exists")
    cur.execute("SELECT pg_get_partkeydef(%s::regclass)", (f"lue_dw.{OCC}",))
    check(cur.fetchone()[0] == "RANGE (snapshot_date_key)", "partitioned by snapshot_date_key")

    print("Indexes (D20 baseline: primary-key and unique-constraint indexes only)")
    cur.execute(
        "SELECT i.indexrelid::regclass::text FROM pg_index i "
        "JOIN pg_class t ON t.oid = i.indrelid JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE n.nspname = 'lue_dw' AND t.relname LIKE 'fact\\_%%' AND NOT t.relispartition "
        "AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)"
    )
    extra = [r[0] for r in cur.fetchall()]
    check(not extra, "no secondary indexes on the facts" + (f" (found {extra})" if extra else ""))

    print("Behaviour")
    cur.execute(
        "SELECT pg_sequence_last_value(pg_get_serial_sequence('lue_dw.' || t, k)) IS NULL "
        "FROM (VALUES " + ", ".join(f"('{t}', '{k}')" for t, k in SURROGATE.items()) + ") v(t, k)"
    )
    check(all(r[0] for r in cur.fetchall()), "all 4 fact identity sequences are unused (next: 1)")

    conn.autocommit = False
    try:
        sql, vals = fact_row(cur, "fact_lease_event", {})
        state, _ = violates(cur, sql + " RETURNING lease_event_sk", vals)
        check(state is None, "a fact row pointing at the special members (-1) is accepted")
        for table in facts:
            sql, vals = fact_row(cur, table, {"unit_key": 999999})
            state, con = violates(cur, sql, vals)
            check(
                state == "23503",
                f"{table}: a unit_key with no dimension row is rejected ({con})",
            )
        add_date(cur, 20240315)
        add_date(cur, 20300101)
        sql, vals = fact_row(cur, OCC, {"snapshot_date_key": 20240315})
        cur.execute(sql + " RETURNING tableoid::regclass::text", vals)
        got = cur.fetchone()[0]
        check(got == f"lue_dw.{OCC}_2024_03", f"a 2024-03-15 occupancy row lands in {got}")
        sql, vals = fact_row(cur, OCC, {"snapshot_date_key": 20300101})
        cur.execute(sql + " RETURNING tableoid::regclass::text", vals)
        got = cur.fetchone()[0]
        check(got == f"lue_dw.{OCC}_default", f"a 2030-01-01 row lands in the default ({got})")
        cur.execute(
            f"EXPLAIN (COSTS OFF) SELECT * FROM lue_dw.{OCC} "
            "WHERE snapshot_date_key BETWEEN 20240301 AND 20240331"
        )
        plan = "\n".join(r[0] for r in cur.fetchall())
        scanned = sorted(set(re.findall(rf"{OCC}_(\d{{4}}_\d{{2}}|default)(?!_pkey)", plan)))
        check(
            scanned == ["2024_03"],
            f"a one-month query reads 1 of 49 partitions (partition pruning: {scanned})",
        )
        sql, vals = fact_row(cur, "fact_rent_invoice_line", {"net_amount": 5})
        state, con = violates(cur, sql, vals)
        check(state == "23514" and con == "ck_net_amount", "fact_rent_invoice_line: ck_net_amount")
    except psycopg2.Error as exc:
        check(False, f"behaviour tests stopped early: {exc}".strip())
    finally:
        conn.rollback()
        conn.autocommit = True
        for t, k in SURROGATE.items():
            cur.execute(f"SELECT count(*) FROM lue_dw.{t}")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)", (f"lue_dw.{t}", k)
                )

    print("Access")
    try:
        rd = connect(s, READER_ROLE, s.get("LUE_READER_PASSWORD", ""))
        rd.autocommit = True
        with rd.cursor() as rcur:
            try:
                rcur.execute(f"SELECT count(*) FROM lue_dw.{OCC}")
                check(False, f"{READER_ROLE} cannot read the facts")
            except psycopg2.Error as exc:
                check(exc.pgcode == "42501", f"{READER_ROLE} cannot read the facts")
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
        check(fingerprint(cur) == before, "the second run changes no table, row or constraint")
    conn.close()

    print("=" * 70)
    passed = sum(results)
    print(f" RESULT: {passed}/{len(results)} checks passed" + ("" if all(results) else " - FAILED"))
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
