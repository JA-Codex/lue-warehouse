#!/usr/bin/env python3
"""Database tests for US-2.2: is the S1 master data in lue_source.src_pms and is it right?

    python scripts/test_source_load.py [--data data]

Run python etl/generate_data.py and python scripts/db_load_source.py first. Connects as lue_etl and
changes nothing. The expected row counts come from data/run_manifest.json (the profile that was
generated), the expected columns and types from the frozen Phase 1 source ERD.
"""

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db_load_source import SOURCE_SCHEMA, TABLES  # noqa: E402
from db_setup import ETL_ROLE, ROOT, SOURCE_DB, load_settings  # noqa: E402
from test_dimensions import check, results  # noqa: E402


def load_model():
    spec = importlib.util.spec_from_file_location(
        "phase1_model", ROOT / "docs" / "phase1" / "tools" / "model.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_type(erd_type: str) -> tuple:
    """(information_schema data_type, length, precision, scale) for a type written as in the ERD."""
    t = erd_type.upper()
    if t.startswith("VARCHAR("):
        return ("character varying", int(t[8:-1]), None, None)
    if t.startswith("CHAR("):
        return ("character", int(t[5:-1]), None, None)
    if t.startswith("NUMERIC("):
        p, s = t[8:-1].split(",")
        return ("numeric", None, int(p), int(s))
    simple = {
        "SMALLINT": "smallint",
        "INT": "integer",
        "BOOLEAN": "boolean",
        "TIMESTAMP": "timestamp without time zone",
        "DATE": "date",
    }
    return (simple[t], None, None, None)


def normal(t) -> tuple:
    """Keep precision and scale only for NUMERIC (integer types report fixed values)."""
    data_type, length, precision, scale = t
    numeric = data_type == "numeric"
    return (data_type, length, precision if numeric else None, scale if numeric else None)


def scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    import psycopg2

    s = load_settings()
    print("=" * 70)
    print(" US-2.2 database tests: S1 master data in lue_source.src_pms")
    print("=" * 70)
    manifest_path = args.data / "run_manifest.json"
    if not manifest_path.is_file():
        print(f"  [FAIL] {manifest_path} not found; run python etl/generate_data.py first")
        print(" RESULT: FAILED")
        return 1
    profile = json.loads(manifest_path.read_text(encoding="utf-8"))["profile"]
    try:
        conn = psycopg2.connect(
            host=s.get("PGHOST", "localhost"),
            port=int(s.get("PGPORT", "5432")),
            user=ETL_ROLE,
            password=s.get("LUE_ETL_PASSWORD", ""),
            dbname=SOURCE_DB,
            connect_timeout=10,
        )
    except psycopg2.OperationalError as exc:
        print(f"  [FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print(" RESULT: FAILED (run python scripts/db_setup.py first)")
        return 1
    conn.autocommit = True
    cur = conn.cursor()
    erd = load_model().SOURCE_ERD
    try:
        print("Tables and columns (the Phase 1 source ERD)")
        for table in TABLES:
            cur.execute(
                "SELECT column_name, data_type, character_maximum_length, numeric_precision, "
                "numeric_scale FROM information_schema.columns "
                f"WHERE table_schema = '{SOURCE_SCHEMA}' AND table_name = '{table}' "
                "ORDER BY ordinal_position"
            )
            actual = [(r[0], normal(r[1:])) for r in cur.fetchall()]
            wanted = [(name, normal(expected_type(typ))) for typ, name, _key in erd[table]]
            check(actual == wanted, f"src_pms.{table}: columns and types equal the ERD")
            cur.execute(
                "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
                "AND a.attnum = ANY(i.indkey) WHERE i.indisprimary "
                f"AND i.indrelid = '{SOURCE_SCHEMA}.{table}'::regclass ORDER BY a.attnum"
            )
            pk = [r[0] for r in cur.fetchall()]
            check(
                pk == [n for _t, n, k in erd[table] if "PK" in k],
                f"src_pms.{table}: the primary key is {', '.join(pk)}",
            )

        print("Row counts match the generated profile")
        n = {t: scalar(cur, f"SELECT count(*) FROM {SOURCE_SCHEMA}.{t}") for t in TABLES}
        check(
            n["buildings"] == profile["buildings"],
            f"{n['buildings']} buildings = {profile['buildings']}",
        )
        check(n["units"] == profile["units"], f"{n['units']} units = {profile['units']}")
        check(n["tenants"] == profile["tenants"], f"{n['tenants']} tenants = {profile['tenants']}")
        check(
            n["charge_types"] == 6 and n["payment_methods"] == 6,
            "6 charge types, 6 payment methods",
        )
        for table in TABLES:
            with (args.data / "s1" / f"{table}.csv").open(encoding="utf-8", newline="") as f:
                rows = sum(1 for _ in csv.reader(f)) - 1
            check(n[table] == rows, f"src_pms.{table} has the {rows} rows of its CSV file")

        print("Units, buildings and cities")
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.units u "
                f"LEFT JOIN {SOURCE_SCHEMA}.buildings b USING (building_code) "
                "WHERE b.building_code IS NULL",
            )
            == 0,
            "every unit belongs to a building (0 units without one)",
        )
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.units u "
                f"JOIN {SOURCE_SCHEMA}.buildings b USING (building_code) "
                "WHERE b.city IS NULL OR b.locality IS NULL",
            )
            == 0,
            "every unit therefore has a city and a locality",
        )
        check(
            scalar(cur, f"SELECT count(DISTINCT city) FROM {SOURCE_SCHEMA}.buildings")
            == profile["cities"],
            f"{profile['cities']} distinct cities",
        )
        check(
            scalar(
                cur,
                "SELECT count(*) FROM (SELECT building_code, unit_no "
                f"FROM {SOURCE_SCHEMA}.units GROUP BY 1, 2 HAVING count(*) > 1) d",
            )
            == 0,
            "(building_code, unit_no) is unique",
        )
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.buildings b WHERE NOT EXISTS "
                f"(SELECT 1 FROM {SOURCE_SCHEMA}.units u WHERE u.building_code = b.building_code)",
            )
            == 0,
            "every building has units",
        )
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.units WHERE area_sqft <= 0 "
                "OR unit_type NOT IN ('Apartment', 'Office', 'Shop') "
                "OR (unit_type = 'Apartment') <> (bedrooms >= 1) OR updated_at IS NULL",
            )
            == 0,
            "area > 0, unit type is one of three, bedrooms fit the type, updated_at is filled",
        )
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.buildings "
                "WHERE building_class NOT IN ('A', 'B', 'C') "
                "OR year_built NOT BETWEEN 1980 AND 2023",
            )
            == 0,
            "building class A, B or C; year built 1980 to 2023",
        )

        print("Tenants and reference tables")
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.tenants WHERE updated_at IS NULL "
                "OR updated_at < TIMESTAMP '2023-06-15' OR phone IS NULL OR full_name IS NULL",
            )
            == 0,
            "every tenant has a name, a phone and a creation time from go-live onwards",
        )
        check(
            scalar(
                cur,
                f"SELECT count(*) FROM {SOURCE_SCHEMA}.tenants "
                "WHERE tenant_type NOT IN ('Individual', 'Corporate') "
                "OR contact_channel NOT IN ('Phone', 'WhatsApp', 'Email')",
            )
            == 0,
            "tenant type and contact channel use the pack's values",
        )
        from etl.reference_data import CHARGE_TYPES, PAYMENT_METHODS

        cur.execute(f"SELECT charge_code, name, category FROM {SOURCE_SCHEMA}.charge_types")
        check(
            sorted(tuple(r) for r in cur.fetchall()) == sorted(CHARGE_TYPES),
            "src_pms.charge_types equals etl/reference_data.py",
        )
        cur.execute(f"SELECT method_code, name FROM {SOURCE_SCHEMA}.payment_methods")
        check(
            sorted(tuple(r) for r in cur.fetchall())
            == sorted((c, nme) for c, nme, _g, _d in PAYMENT_METHODS),
            "src_pms.payment_methods equals etl/reference_data.py",
        )
    finally:
        cur.close()
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
