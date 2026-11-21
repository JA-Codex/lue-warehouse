#!/usr/bin/env python3
"""E7 checks that need no database (run by CI in make gen-test).

    python scripts/test_fact_load_contract.py

The fact spec (etl/facts/spec.py) against the frozen DDL (sql/10_ddl/02_facts.sql): every fact and
column exists, every NOT NULL column is filled, the grain columns are written (and are the DDL's
UNIQUE key where it has one); the key lookups are point in time with half-open versions; every
statement the loader builds parses (pglast); the money facts reconcile to staging by month; the
occupancy snapshot covers the generator's window month by month and refreshes its last 35 days.
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.facts import keys, load, spec  # noqa: E402

results: list[bool] = []
TECH = ["source_system", "batch_id", "loaded_at"]


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


UNIQUE: dict[str, list[list[str]]] = {}  # fact -> its UNIQUE constraints' columns (filled by ddl())


def ddl() -> dict[str, dict[str, dict]]:
    from pglast import ast, parse_sql

    text = (ROOT / "sql" / "10_ddl" / "02_facts.sql").read_text(encoding="utf-8")
    out: dict = {}
    for raw in parse_sql(text):
        s = raw.stmt
        if isinstance(s, ast.CreateStmt) and not s.partbound:
            cols = {}
            for e in s.tableElts:
                if isinstance(e, ast.Constraint) and e.contype.name == "CONSTR_UNIQUE":
                    UNIQUE.setdefault(s.relation.relname, []).append([k.sval for k in e.keys])
                if isinstance(e, ast.ColumnDef):
                    kinds = [c.contype.name for c in (e.constraints or [])]
                    cols[e.colname] = {"not_null": "CONSTR_NOTNULL" in kinds, "identity": "CONSTR_IDENTITY" in kinds}
            out[s.relation.relname] = cols
    return out


def parses(sql: str) -> str:
    from pglast import parse_sql

    try:
        parse_sql(re.sub(r"%\((\w+)\)s", "NULL", sql))
        return ""
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def main() -> int:
    print("=" * 70)
    print(" E7 contract tests: fact spec, key lookups and loader (no database)")
    print("=" * 70)
    tables = ddl()
    print("US-7.1 The spec against the frozen design")
    check(len(tables) == 6, f"6 facts in the DDL: {', '.join(sorted(tables))}")
    bad = []
    for f in spec.FACTS:
        cols = tables.get(f.name)
        if cols is None:
            bad.append(f"{f.name} not in the DDL")
            continue
        for c in [*f.cols, *TECH]:
            if c not in cols:
                bad.append(f"{f.name}.{c} not in the DDL")
        for c, info in cols.items():
            if info["not_null"] and not info["identity"] and c not in [*f.cols, *TECH]:
                bad.append(f"{f.name}.{c} is NOT NULL but not written")
        if not set(f.grain) <= set(f.cols):
            bad.append(f"{f.name}: grain {f.grain} not all written")
        if len(set(f.cols)) != len(f.cols):
            bad.append(f"{f.name}: a column twice")
        if not set(f.required) <= set(f.cols):
            bad.append(f"{f.name}: required {f.required} not all written")
    check(not bad, "every fact and column exists; every NOT NULL column is written; grain and required columns are written columns"
          + (f": {bad[:4]}" if bad else ""))
    missing = [f"{f.name}.{c}" for f in spec.FACTS for c in f.cols if not re.search(rf"\bAS {c}\b|\.{c}\b", f.source)]
    check(not missing, "the source query gives every column the fact writes" + (f": {missing}" if missing else ""))

    wrong = [f"{f.name}: grain {f.grain}, unique {u}" for f in spec.FACTS for u in UNIQUE.get(f.name, []) if sorted(u) != sorted(f.grain)]
    check(not wrong and UNIQUE.get("fact_rent_invoice_line") == [["invoice_number", "invoice_line_no"]],
          "a fact with a UNIQUE constraint in the DDL has it on exactly its grain (uq_invoice_line: invoice_number, invoice_line_no)"
          + (f": {wrong}" if wrong else ""))

    print("US-7.1 Key lookups")
    j = keys.scd2("dim_tenant", "dt", "p.tenant_code", "p.paid_at")
    check("dt.tenant_code = p.tenant_code" in j and ">= dt.effective_from" in j and "< dt.effective_to" in j and "<= dt.effective_to" not in j,
          "SCD2 lookup: natural key and the version valid that day, half-open [effective_from, effective_to)")
    o = keys.owner("dw", "su.building_code", "su.unit_no", "p.paid_at")
    check("valid_from <= (p.paid_at)::date" in o and "(p.paid_at)::date < dw_r.valid_to" in o and "valid_to IS NULL" in o,
          "owner lookup: the ownership period holding that day (valid_from <= day < valid_to, open period)")
    dk = keys.date_key("x")
    check(f"DATE '{keys.CALENDAR[0]}'" in dk and "'YYYYMMDD'" in dk and "THEN -1" in dk and keys.date_key("x", -2).count("THEN -2") == 1,
          "date keys: YYYYMMDD inside the calendar, -1 outside or unknown, -2 when given for 'not yet'")
    check(keys.key("du", "unit_key") == "coalesce(du.unit_key, -1)", "an unresolved key is -1 (Unknown), never a dropped row")

    print("US-7.1 The loader's SQL")
    errors = []
    for f in spec.FACTS:
        stmts = [("source", f.source), ("delete", load.delete_sql(f)), ("update", load.update_sql(f)), ("insert", load.insert_sql(f))]
        stmts += [(f"prepare {i + 1}", s) for i, s in enumerate(f.prepare)]
        if f.monthly:
            stmts.append(("monthly reconciliation", load.monthly_sql(f)))
        for name, sql in stmts:
            if e := parses(sql):
                errors.append(f"{f.name} {name}: {e}")
    check(not errors, "source, delete, update, insert and reconciliation statements parse (pglast)" + (f": {errors[:3]}" if errors else ""))
    f = spec.FACTS[0]
    u, i = load.update_sql(f), load.insert_sql(f)
    check("IS DISTINCT FROM" in u and all(f"x.{g} = s.{g}" in u for g in f.grain) and "NOT EXISTS" in i
          and not any(c.endswith("_sk") for c in f.cols),
          "sync on the grain: update only on a difference, insert only new grains, the surrogate *_sk left to the identity")

    print("US-7.2 Monthly reconciliation")
    names = [f.name for f in spec.FACTS]
    check(names[:2] == ["fact_rent_invoice_line", "fact_payment"] and all(spec.BY_NAME[n].monthly for n in names[:2]),
          "the invoice and payment facts load first and both declare a monthly reconciliation to staging")
    long = [f"{f.name} 2026-06 {f.monthly[0]}" for f in spec.FACTS if f.monthly and len(f"{f.name} 2026-06 {f.monthly[0]}") > 60]
    check(not long, "every reconciliation check name fits lue_audit.reconciliation.check_name (60)" + (f": {long}" if long else ""))

    print("US-7.3 The periodic snapshot")
    from etl.generator_config import WINDOW_END, WINDOW_START

    occ = spec.BY_NAME.get("fact_unit_occupancy_daily")
    check(keys.DATA_WINDOW == (WINDOW_START.isoformat(), WINDOW_END.isoformat()),
          f"the snapshot window {keys.DATA_WINDOW[0]} to {keys.DATA_WINDOW[1]} is the generator's data window (fixed, never today)")
    check(occ is not None and occ.period == "snapshot_date_key" and occ.grain == ["snapshot_date_key", "unit_key"]
          and occ.refresh_days == 35 and occ.resolved == ["unit_key"] and occ.monthly is not None,
          "fact_unit_occupancy_daily: grain = its primary key (snapshot day, unit), loaded by month, last 35 days refreshed, unit never -1, unit-days reconciled")
    within = "BETWEEN %(first_key)s AND %(last_key)s"
    check(occ is not None and all(within in s for s in (load.delete_sql(occ), load.update_sql(occ), load.insert_sql(occ)))
          and within not in load.update_sql(spec.BY_NAME["fact_payment"]),
          "a periodic snapshot's delete, update and insert name the month loaded (one partition each); other facts are not restricted")
    ms = load.months(*keys.DATA_WINDOW)
    check(len(ms) == 36 and ms[0][0].isoformat() == keys.DATA_WINDOW[0] and ms[-1][1].isoformat() == keys.DATA_WINDOW[1]
          and all((b - a).days >= 27 and (ms[i + 1][0] - b).days == 1 for i, (a, b) in enumerate(ms[:-1])),
          f"the window splits into {len(ms)} whole, contiguous months")
    src = occ.source if occ else ""
    check("generate_series" in src and "LEFT JOIN lue_staging.stg_lease" in src and "THEN -2" in src and "OVER w" in " ".join(occ.prepare if occ else []),
          "every unit and day from generate_series, the lease LEFT JOINed (vacant days stay, -2), arrears by window sums")
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
