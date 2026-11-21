#!/usr/bin/env python3
"""Apply the generator's "next extract" to lue_source.src_pms (US-6.2, US-6.5).

    python scripts/db_apply_next_extract.py [--data data] [--only changes|late]

The generator (US-2.6) writes two S1 files that belong to a later extract than the first load:
  s1/changes/tenants.csv        tenants whose attributes changed (SCD2, US-6.2): each row
                                replaces the tenant's row, with the updated_at of the change
  s1/late_arriving/tenants.csv  tenants referenced by leases and payments before they reached S1
                                (inferred members, US-6.5): inserted
This script applies them to the source system, as the property management system would between
two extracts. The pipeline then picks them up like any change: python etl/ingest/run.py --only S1,
python etl/quality/run.py, python etl/staging/run.py, python etl/dimensions/run.py.

One transaction: all of it or nothing. Safe to re-run: a row already as the file gives is left
alone, so a second run changes nothing. db_load_source.py puts the first extract back.
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_setup import ETL_ROLE, ROOT, SOURCE_DB, load_settings  # noqa: E402

COLUMNS = ["tenant_code", "full_name", "tenant_type", "employer_sector", "phone", "contact_channel",
           "updated_at"]  # fmt: skip
FILES = {"changes": "s1/changes/tenants.csv", "late": "s1/late_arriving/tenants.csv"}


def read(path: Path) -> list[list[str | None]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != COLUMNS:
        raise ValueError(f"{path}: expected the columns {', '.join(COLUMNS)}")
    return [[v if v != "" else None for v in r] for r in rows[1:]]


def apply(cur, kind: str, rows: list) -> tuple[int, int]:
    """Returns (rows changed or inserted, rows already as given)."""
    names = ", ".join(COLUMNS)
    values = ", ".join(["%s"] * len(COLUMNS))
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])
    differs = (f"({', '.join('t.' + c for c in COLUMNS[1:])}) IS DISTINCT FROM "
               f"({', '.join('EXCLUDED.' + c for c in COLUMNS[1:])})")  # fmt: skip
    changed = 0
    for r in rows:
        if kind == "changes":
            cur.execute("SELECT 1 FROM src_pms.tenants WHERE tenant_code = %s", (r[0],))
            if cur.fetchone() is None:
                raise ValueError(f"changes: tenant {r[0]} is not in src_pms.tenants (load the "
                                 "first extract first: python scripts/db_load_source.py)")  # fmt: skip
        cur.execute(f"INSERT INTO src_pms.tenants AS t ({names}) VALUES ({values}) ON CONFLICT "
                    f"(tenant_code) DO UPDATE SET {sets} WHERE {differs}", r)  # fmt: skip
        changed += cur.rowcount
    return changed, len(rows) - changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="folder the generator wrote")
    ap.add_argument("--only", choices=sorted(FILES), help="apply one of the two files")
    args = ap.parse_args(argv)
    import psycopg2

    kinds = [args.only] if args.only else ["late", "changes"]
    try:
        files = {k: read(args.data / FILES[k]) for k in kinds}
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        print("       Generate the data first: python etl/generate_data.py")
        return 1
    s = load_settings()
    try:
        conn = psycopg2.connect(host=s.get("PGHOST", "localhost"),
                                port=int(s.get("PGPORT", "5432")), user=ETL_ROLE,
                                password=s.get("LUE_ETL_PASSWORD", ""), dbname=SOURCE_DB,
                                connect_timeout=10)  # fmt: skip
    except psycopg2.Error as exc:
        print(f"[FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        return 1
    done = {}
    try:
        with conn.cursor() as cur:
            for k in kinds:
                done[k] = apply(cur, k, files[k])
        conn.commit()
    except (psycopg2.Error, ValueError) as exc:
        conn.rollback()
        print(f"[FAIL] {exc}".rstrip())
        print("       Nothing was changed (rolled back).")
        return 1
    finally:
        conn.close()
    print("=" * 70)
    print(f" Next extract applied to {SOURCE_DB}.src_pms.tenants")
    for k, (changed, same) in done.items():
        print(f"  {FILES[k]:30} {changed:>4} applied, {same:>4} already as given")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
