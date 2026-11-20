#!/usr/bin/env python3
"""E6 checks that need no database (run by CI in make gen-test).

    python scripts/test_dim_load_contract.py

The dimension spec (etl/dimensions/spec.py) against the frozen design: every dimension, key and
column exists in sql/10_ddl/01_dimensions.sql, every NOT NULL column is filled on insert, the SCD
type of every column is the one in the Phase 1 data dictionary (docs/phase1/tools/model.py),
the source reads only real staging columns, the load order puts independent dimensions first,
and the SQL the loader builds parses (pglast).
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.dimensions import load, spec  # noqa: E402
from etl.staging import spec as staging  # noqa: E402

results: list[bool] = []
TECH = ["source_system", "batch_id", "loaded_at"]
SCD2_COLS = ["effective_from", "effective_to", "is_current"]
LAST = {"dim_unit", "dim_tenant", "dim_lease"}  # plan US-6.1 step 3: loaded after the others


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def ddl() -> dict[str, dict[str, dict]]:
    """table -> column -> {not_null, identity, default}, from sql/10_ddl/01_dimensions.sql."""
    from pglast import ast, parse_sql

    text = (ROOT / "sql" / "10_ddl" / "01_dimensions.sql").read_text(encoding="utf-8")
    out: dict = {}
    for raw in parse_sql(text):
        if not isinstance(raw.stmt, ast.CreateStmt):
            continue
        cols = {}
        for e in raw.stmt.tableElts:
            if isinstance(e, ast.ColumnDef):
                kinds = [c.contype.name for c in (e.constraints or [])]
                cols[e.colname] = {"not_null": "CONSTR_NOTNULL" in kinds,
                                   "identity": "CONSTR_IDENTITY" in kinds,
                                   "default": "CONSTR_DEFAULT" in kinds}  # fmt: skip
        out[raw.stmt.relation.relname] = cols
    return out


def phase1_scd() -> dict[str, dict[str, str]]:
    """table -> column -> SCD type, read from the frozen pack without writing anything to it."""
    sys.dont_write_bytecode = True  # no __pycache__ inside docs/phase1 (MANIFEST check)
    path = ROOT / "docs" / "phase1" / "tools" / "model.py"
    mod_spec = importlib.util.spec_from_file_location("phase1_model", path)
    model = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(model)
    return {d["name"]: {c["name"]: c["scd"] for c in d["cols"]} for d in model.DIMENSIONS}


def parses(sql: str) -> str:
    from pglast import parse_sql

    sql = re.sub(r"%\((\w+)\)s", "NULL", sql)
    try:
        parse_sql(sql)
        return ""
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def main() -> int:
    print("=" * 70)
    print(" E6 contract tests: dimension spec and loader (no database)")
    print("=" * 70)
    tables = ddl()
    scd = phase1_scd()
    print("US-6.1 The spec against the frozen design")
    check(len(tables) == 13 and set(spec.STATIC) <= set(tables),
          f"13 dimensions in the DDL; the {len(spec.STATIC)} static ones of US-1.4 among them")
    missing = [d.name for d in spec.DIMS if d.name not in tables]
    check(not missing and len({d.name for d in spec.DIMS}) == len(spec.DIMS)
          and not set(spec.BY_NAME) & set(spec.STATIC),
          f"every dimension of the spec exists, once, and is not a static one: "
          f"{', '.join(d.name for d in spec.DIMS)}")  # fmt: skip
    bad = []
    for d in spec.DIMS:
        cols = tables.get(d.name, {})
        if not cols.get(d.key, {}).get("identity"):
            bad.append(f"{d.name}.{d.key} is not the identity column")
        for c in [*d.nk, *d.cols, *TECH] + (SCD2_COLS if d.scd2 else []) + (
                ["is_inferred"] if d.inferred else []):  # fmt: skip
            if c not in cols:
                bad.append(f"{d.name}.{c} not in the DDL")
        written = {d.key, *d.nk, *d.cols, *TECH} | (set(SCD2_COLS) if d.scd2 else set()) | (
            {"is_inferred"} if d.inferred else set())  # fmt: skip
        for c, info in cols.items():
            filled = info["default"] or info["identity"]
            if c not in written and info["not_null"] and not filled:
                bad.append(f"{d.name}.{c} is NOT NULL but not filled")
        if d.scd2 != ("is_current" in cols) or d.inferred != ("is_inferred" in cols):
            bad.append(f"{d.name}: scd2/inferred flags do not match the DDL")
    check(not bad, "the surrogate key is the identity column; every column exists; every NOT NULL "
          "column is filled on insert; SCD2 and inferred flags match the DDL"
          + (f": {bad[:4]}" if bad else ""))  # fmt: skip
    wrong = []
    for d in spec.DIMS:
        design = scd.get(d.name, {})
        for c in d.nk:
            if design.get(c) not in ("0", ""):
                wrong.append(f"{d.name}.{c}: natural key but SCD {design.get(c)!r}")
        for c, t in d.cols.items():
            if design.get(c) != str(t):
                wrong.append(f"{d.name}.{c}: spec {t}, data dictionary {design.get(c)!r}")
        if d.scd2 != any(v == "2" for v in design.values()):
            wrong.append(f"{d.name}: SCD2 flag differs from the data dictionary")
    check(not wrong, "every column's SCD type is the data dictionary's (Phase 1 model.py): "
          + ", ".join(f"{d.name} Type 1 {d.type1}, Type 2 {d.type2}" for d in spec.DIMS)
          + (f"; differs: {wrong}" if wrong else ""))  # fmt: skip
    unknown = []
    for d in spec.DIMS:
        for alias, col in re.findall(r"\b([a-z])\.(\w+)", d.source):
            table = re.search(rf"lue_staging\.(\w+) {alias}\b", d.source)
            stg = staging.BY_NAME.get(table.group(1)) if table else None
            cols = (stg.cols + staging.LINEAGE + stg.extra_lineage) if stg else []
            known = {c.name for c in cols}
            if col not in known:
                unknown.append(f"{d.name}: {alias}.{col}")
        if not set(d.staging) <= set(staging.BY_NAME):
            unknown.append(f"{d.name}: staging tables {d.staging}")
    check(not unknown, "every source reads real staging columns (docs/contracts/staging.md)"
          + (f": {unknown}" if unknown else ""))  # fmt: skip
    order = [d.name for d in spec.DIMS]
    first_last = min((order.index(n) for n in LAST if n in order), default=len(order))
    check(all(order.index(n) < first_last for n in order if n not in LAST),
          "load order: the static dimensions (checked first), then the independent ones, then "
          "unit, tenant and lease")  # fmt: skip
    check(all(order.index(dep) < order.index(d.name) for d in spec.DIMS for dep in d.depends
              if dep in order) and all(dep in order or dep in spec.STATIC
                                       for d in spec.DIMS for dep in d.depends),
          "a dimension's dependencies load before it")  # fmt: skip

    print("US-6.1 The loader's SQL")
    errors = []
    for d in spec.DIMS:
        for name, sql in (("source", d.source), ("insert", load.insert_sql(d)),
                          ("type 1", load.type1_sql(d) or "SELECT 1"),
                          ("history", d.history or "SELECT 1")):  # fmt: skip
            if e := parses(sql):
                errors.append(f"{d.name} {name}: {e}")
    check(not errors, "source, history, insert and Type 1 statements parse (pglast)"
          + (f": {errors[:3]}" if errors else ""))  # fmt: skip
    d = spec.BY_NAME["dim_tenant"]
    ins, upd = load.insert_sql(d), load.type1_sql(d)
    check(d.key not in ins.split("SELECT")[0] and "NOT EXISTS" in ins
          and f"'{spec.FIRST_DAY}'" in ins and f"'{spec.OPEN_END}'" in ins,
          "insert: never names the surrogate key (the identity assigns it), only new natural keys, "
          "a first version valid from 1900-01-01 to 9999-12-31")  # fmt: skip
    check(f"x.{d.key} > 0" in upd and "IS DISTINCT FROM" in upd
          and not any(f"{c} = s.{c}" in upd for c in d.type2),
          "Type 1: only when a value differs, never on the special members, never a Type 2 "
          "column")  # fmt: skip
    print("US-6.2 to US-6.5 SCD2 and inferred members (pure rules)")
    d1, d2, d3 = date(2024, 1, 10), date(2024, 6, 1), date(2025, 2, 3)
    v = load.desired_versions([(d1, ("A",)), (d2, ("A",)), (d3, ("B",))])
    check(v == [(load.FIRST, ("A",)), (d3, ("B",))],
          "versions from history: the first from 1900-01-01, a new one only when a Type 2 value changes")
    v = load.desired_versions([(d1, ("A",)), (d3, ("B",)), (d3, ("C",))])
    check(v == [(load.FIRST, ("A",)), (d3, ("C",))], "two changes the same day: the later wins, one version")
    v = load.desired_versions([(d1, ("A",)), (d3, ("B",)), (d3, ("A",))])
    check(v == [(load.FIRST, ("A",))], "a change undone the same day leaves no version")
    v = load.desired_versions([(None, ("A",)), (d2, ("B",)), (d3, ("C",))])
    check(v == [(load.FIRST, ("A",)), (d2, ("B",)), (d3, ("C",))],
          "several changes of one member are versioned in date order (plan US-6.2 step 3)")
    stored = [(load.FIRST, ("A",))]
    check(load.plan_versions(stored, [(load.FIRST, ("A",)), (d2, ("B",)), (d3, ("C",))]) == ([(d2, ("B",)), (d3, ("C",))], None, False)
          and load.plan_versions([(load.FIRST, ("A",)), (d2, ("B",))], [(load.FIRST, ("A",)), (d2, ("B",))]) == ([], None, False),
          "new versions are only those after the current one: a rerun adds none (idempotent)")
    check(load.plan_versions([(load.FIRST, ("B",))], [(load.FIRST, ("A",)), (d2, ("B",))]) == ([(d2, ("B",))], ("A",), False),
          "a member loaded with its latest values before history was known: first version corrected, then versioned")
    check(load.plan_versions([(load.FIRST, ("A",)), (d2, ("X",))], [(load.FIRST, ("A",)), (d2, ("B",))]) == ([], ("B",), False)
          and load.plan_versions([(load.FIRST, ("Z",)), (d2, ("B",))], [(load.FIRST, ("A",)), (d2, ("B",))])[2],
          "a change on the current version's own day is made in place; an older stored version that "
          "disagrees is reported, never rewritten")  # fmt: skip
    missing = [d.name for d in spec.DIMS if d.scd2 and (not d.history or not d.type2 or len(d.nk) != 1
               or any(not re.search(rf"\b{c}\b", d.history) for c in [*d.nk, *d.type2, "change_date", "seq"]))]
    check(not missing, "every SCD2 dimension has a history giving its key, Type 2 columns, change date and order"
          + (f": {missing}" if missing else ""))  # fmt: skip
    refs = [d.name for d in spec.DIMS if d.references and not d.inferred]
    sqls = [q for d in spec.DIMS if d.inferred for q in (load.inferred_sql(d), load.complete_inferred_sql(d)) if q]
    check(not refs and all(load.inferred_sql(d) for d in spec.DIMS if d.inferred and d.references)
          and not any(parses(q) for q in sqls),
          "inferred members only where the DDL has is_inferred (dim_tenant); their SQL parses")
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
