#!/usr/bin/env python3
"""US-9.3 acceptance tests: the exported load scripts reproduce the warehouse. Needs a loaded
warehouse (python etl/run_pipeline.py); every test runs in a transaction that is rolled back, and
the identity sequences are put back, so the warehouse is left exactly as it was.

    python scripts/test_load_sql.py

  facts       sql/40_facts/01_fact_loads.sql on empty facts gives the facts the loader built,
              row for row (every column but the surrogate key, batch_id and loaded_at); run again
              on the loaded facts it changes nothing but the declared occupancy refresh (D14)
  dimensions  sql/30_dimensions/02_dimension_loads.sql re-creates deleted members with their
              values, puts back corrupted Type 1 values, and on a loaded warehouse changes nothing
  both        the committed files equal what the loaders run (scripts/export_load_sql.py --check)
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import export_load_sql as export  # noqa: E402

from etl.dimensions import spec as dspec  # noqa: E402
from etl.facts import spec as fspec  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def body(path: Path) -> str:
    """The file's statements without its own BEGIN and COMMIT: the test holds the transaction."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if line not in ("BEGIN;", "COMMIT;"))


def columns(cur, table: str, leave_out: set[str], identity: bool = True) -> list[str]:
    """The table's columns but leave_out; identity=False also leaves out its identity (surrogate) key."""
    cur.execute("SELECT column_name, is_identity FROM information_schema.columns WHERE table_schema = 'lue_dw' "
                "AND table_name = %s ORDER BY ordinal_position", (table,))  # fmt: skip
    return [c for c, ident in cur.fetchall() if c not in leave_out and (identity or ident != "YES")]


def differ(cur, table: str, cols: list[str], before: str) -> int:
    """Rows in one of the table and its copy but not the other (as multisets)."""
    c = ", ".join(cols)
    return scalar(cur, f"SELECT (SELECT count(*) FROM (SELECT {c} FROM lue_dw.{table} EXCEPT ALL SELECT {c} FROM {before}) a) "
                       f"+ (SELECT count(*) FROM (SELECT {c} FROM {before} EXCEPT ALL SELECT {c} FROM lue_dw.{table}) b)")  # fmt: skip


def sequences(cur) -> list[tuple]:
    """Every lue_dw identity sequence with its position, to put back after a rolled-back test."""
    cur.execute("SELECT s.schemaname || '.' || s.sequencename, s.last_value FROM pg_sequences s WHERE s.schemaname = 'lue_dw'")
    return cur.fetchall()


def restore(cur, seqs: list[tuple]) -> None:
    for name, last in seqs:
        if last is None:
            cur.execute("SELECT setval(%s, 1, false)", (name,))
        else:
            cur.execute("SELECT setval(%s, %s, true)", (name, last))


def main() -> int:
    print("=" * 70)
    print(" US-9.3 acceptance tests: the dimension and fact load scripts (database)")
    print("=" * 70)
    print("The files")
    check(export.main(["--check"]) == 0, "both files equal what the loaders run (re-exported from the specs)")
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    seq_cur = wh.cursor()
    wh.autocommit = True
    if not scalar(seq_cur, "SELECT count(*) FROM lue_dw.fact_payment"):
        print("  [FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
        return 1
    seqs = sequences(seq_cur)
    wh.autocommit = False
    cur = wh.cursor()
    facts_sql, dims_sql = body(export.FACT_FILE), body(export.DIM_FILE)
    try:
        print("Facts: sql/40_facts/01_fact_loads.sql")
        keep = {}
        for f in fspec.FACTS:
            keep[f.name] = columns(cur, f.name, {"batch_id", "loaded_at"}, identity=False)
            cur.execute(f"CREATE TEMP TABLE _was_{f.name} AS SELECT {', '.join(keep[f.name])} FROM lue_dw.{f.name}")
        cur.execute("TRUNCATE " + ", ".join(f"lue_dw.{f.name}" for f in fspec.FACTS))
        cur.execute(facts_sql)
        run = scalar(cur, "SELECT current_setting('lue.run_id')::bigint")
        off = {f.name: differ(cur, f.name, keep[f.name], f"_was_{f.name}") for f in fspec.FACTS}
        total = sum(scalar(cur, f"SELECT count(*) FROM _was_{f.name}") for f in fspec.FACTS)
        stamped = all(scalar(cur, f"SELECT count(*) FROM lue_dw.{f.name} WHERE batch_id <> %s", (run,)) == 0 for f in fspec.FACTS)
        check(not any(off.values()) and total > 0 and stamped,
              f"on empty facts it builds the {len(off)} facts the loader built: {total:,} rows, every column equal"
              + (f"; differ {[k for k, v in off.items() if v]}" if any(off.values()) else ""))
        wh.rollback()

        cur.execute(facts_sql)
        run = scalar(cur, "SELECT current_setting('lue.run_id')::bigint")
        occ = fspec.BY_NAME["fact_unit_occupancy_daily"]
        touched = {f.name: scalar(cur, f"SELECT count(*) FROM lue_dw.{f.name} WHERE batch_id = %s", (run,)) for f in fspec.FACTS}
        refreshed = touched.pop(occ.name)
        units = scalar(cur, "SELECT count(*) FROM lue_staging.stg_unit")
        check(not any(touched.values()) and refreshed == units * occ.refresh_days,
              f"run on the loaded facts it changes nothing (D14) but the occupancy refresh: {units:,} units x {occ.refresh_days} days = {refreshed:,} rows"
              + (f"; changed {touched}" if any(touched.values()) else ""))
        wh.rollback()

        print("Dimensions: sql/30_dimensions/02_dimension_loads.sql")
        cur.execute(dims_sql)
        run = scalar(cur, "SELECT current_setting('lue.run_id')::bigint")
        touched = {d.name: scalar(cur, f"SELECT count(*) FROM lue_dw.{d.name} WHERE batch_id = %s", (run,)) for d in dspec.DIMS}
        check(not any(touched.values()), f"run on the loaded dimensions it changes nothing ({len(touched)} dimensions, 0 rows)"
              + (f"; changed {touched}" if any(touched.values()) else ""))
        wh.rollback()

        plain = [d for d in dspec.DIMS if not d.scd2]
        cur.execute("TRUNCATE " + ", ".join(f"lue_dw.{f.name}" for f in fspec.FACTS))
        dkeep = {}
        for d in plain:
            dkeep[d.name] = columns(cur, d.name, {d.key, "batch_id", "loaded_at"})
            cur.execute(f"CREATE TEMP TABLE _was_{d.name} AS SELECT {', '.join(dkeep[d.name])} FROM lue_dw.{d.name}")
            cur.execute(f"DELETE FROM lue_dw.{d.name} WHERE {d.key} > 0")
        corrupted = {}
        for d in [d for d in dspec.DIMS if d.scd2]:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'lue_dw' AND table_name = %s "
                        "AND data_type = 'character varying' AND column_name = ANY(%s) ORDER BY ordinal_position LIMIT 1", (d.name, d.type1))  # fmt: skip
            col = (cur.fetchone() or [None])[0]
            if col:
                dkeep[d.name] = columns(cur, d.name, {"batch_id", "loaded_at"})
                cur.execute(f"CREATE TEMP TABLE _was_{d.name} AS SELECT {', '.join(dkeep[d.name])} FROM lue_dw.{d.name}")
                cur.execute(f"UPDATE lue_dw.{d.name} SET {col} = left({col}, 1) || '#' WHERE {d.key} IN "
                            f"(SELECT {d.key} FROM lue_dw.{d.name} WHERE {d.key} > 0 AND NOT {col} LIKE '_#' ORDER BY {d.key} LIMIT 5)")  # fmt: skip
                corrupted[f"{d.name}.{col}"] = cur.rowcount
        deleted = sum(scalar(cur, f"SELECT count(*) FROM _was_{d.name}") for d in plain)
        cur.execute(dims_sql)
        off = {d: differ(cur, d, dkeep[d], f"_was_{d}") for d in dkeep}
        check(not any(off.values()) and deleted > 0,
              f"it re-creates the members of {', '.join(d.name for d in plain)} with their values ({deleted:,} rows, new surrogate keys)"
              + (f"; differ {[k for k, v in off.items() if v and k in {d.name for d in plain}]}" if any(off.values()) else ""))
        check(corrupted and all(n == 5 for n in corrupted.values()) and not any(off[k.split('.')[0]] for k in corrupted),
              f"it puts back corrupted Type 1 values ({', '.join(corrupted)}: 5 rows each), every version left as it was")
        wh.rollback()
    finally:
        wh.rollback()
        wh.autocommit = True
        restore(seq_cur, seqs)
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
