#!/usr/bin/env python3
"""E10 checks that need no database (run by CI in make gen-test).

    python scripts/test_reporting_contract.py

The reporting layer (sql/50_reporting/01_reporting.sql, parsed with pglast): every object the plan
names exists; each is dropped before it is created (safe to re-run); every column of every object
is documented in docs/reporting.md; the aliases are exactly their targets; each mart has a unique
index on its grain and refresh_marts() refreshes all four; the layer reads lue_dw only; deploy and
the pipeline's last stage run it.
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pglast import ast, parse_sql  # noqa: E402

from etl import reporting  # noqa: E402
from etl import run_pipeline as p  # noqa: E402

SQL = ROOT / "sql" / "50_reporting" / "01_reporting.sql"
DOC = ROOT / "docs" / "reporting.md"
VIEWS = ["vw_monthly_collections", "vw_tenant_analysis", "vw_unit_performance"]
ALIASES = {"vw_monthly_sales": "vw_monthly_collections", "vw_customer_analysis": "vw_tenant_analysis",
           "vw_product_performance": "vw_unit_performance"}  # fmt: skip
SLICERS = ["vw_dim_date", "vw_dim_month", "vw_dim_building", "vw_dim_unit", "vw_dim_unit_type", "vw_dim_tenant",
           "vw_dim_owner", "vw_dim_vendor", "vw_dim_maintenance_category", "vw_dim_payment_method"]  # fmt: skip
DASHBOARD = ["vw_tenant_by_building"]  # the dashboard's drill-through from a building to its tenants (US-13.3)
GRAIN = {"mart_collections_monthly": ["month_key", "building_code"],
         "mart_occupancy_monthly": ["month_key", "building_code", "unit_type"],
         "mart_maintenance_monthly": ["month_key", "building_code", "unit_type", "maint_category_key", "vendor_key"],
         "mart_owner_portfolio_monthly": ["month_key", "owner_key"]}  # fmt: skip
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def column(rt) -> str:
    """The output name of a select-list entry."""
    if rt.name:
        return rt.name
    v = rt.val.arg if isinstance(rt.val, ast.TypeCast) else rt.val
    if isinstance(v, ast.ColumnRef):
        f = v.fields[-1]
        return "*" if isinstance(f, ast.A_Star) else f.sval
    return "?"


def objects(text: str) -> dict:
    """{name: (kind, [columns], query)} for every view and materialized view the file creates."""
    out = {}
    for raw in parse_sql(text):
        s = raw.stmt
        if isinstance(s, ast.ViewStmt):
            name, kind, q, alias = s.view.relname, "view", s.query, s.aliases
        elif isinstance(s, ast.CreateTableAsStmt):
            name, kind, q, alias = s.into.rel.relname, "mart", s.query, None
        else:
            continue
        cols = [column(t) for t in q.targetList or []]
        sub = q.fromClause[0] if q.fromClause else None
        if cols == ["*"] and isinstance(sub, ast.RangeSubselect) and sub.alias.colnames:
            cols = [c.sval for c in sub.alias.colnames]  # SELECT * FROM (VALUES ...) AS p (cols)
        out[name] = (kind, [c.sval for c in alias] if alias else cols, q)
    return out


def documented(doc: str, name: str) -> set[str]:
    """The columns in the table under the object's heading in docs/reporting.md."""
    m = re.search(rf"^### `{name}`.*?\n(.*?)(?=^#)", doc + "\n#", re.S | re.M)
    return set(re.findall(r"^\| `(\w+)` \|", m.group(1), re.M)) if m else set()


def main() -> int:
    print("=" * 70)
    print(" E10 contract tests: the reporting layer (no database)")
    print("=" * 70)
    text = SQL.read_text(encoding="utf-8")
    body = "\n".join(line.split("--")[0] for line in text.splitlines())  # without comments
    objs = objects(text)
    doc = DOC.read_text(encoding="utf-8")

    print("US-10.1 The views")
    wanted = [*VIEWS, *ALIASES, *SLICERS, *GRAIN, *DASHBOARD, "vw_reporting_window", "vw_reporting_parameter"]
    check(set(wanted) == set(objs), f"the file creates the brief's 3 views, their 3 aliases (D18), {len(SLICERS)} slicer views, the 4 marts, 2 parameter views and the dashboard's tenant view ({len(objs)} objects)"
          + (f": missing {sorted(set(wanted) - set(objs))}, extra {sorted(set(objs) - set(wanted))}" if set(wanted) != set(objs) else ""))
    plain = {a: (q.targetList and len(q.targetList) == 1 and column(q.targetList[0]) == "*" and not q.whereClause and len(q.fromClause) == 1
                 and q.fromClause[0].relname == ALIASES[a]) for a, (_k, _c, q) in objs.items() if a in ALIASES}  # fmt: skip
    check(len(plain) == 3 and all(plain.values()), "each alias is SELECT * FROM its LUE view, nothing more: " + ", ".join(f"{a} -> {t}" for a, t in ALIASES.items()))
    tech = {n: [c for c in cols if c in ("source_system", "batch_id", "loaded_at")] for n, (_k, cols, _q) in objs.items() if n in SLICERS}
    check(not any(tech.values()), "the slicer views leave out the technical columns (source_system, batch_id, loaded_at)")
    missing = {n: sorted(set(cols) - documented(doc, n)) for n, (_k, cols, _q) in objs.items() if n not in ALIASES}
    missing = {n: c for n, c in missing.items() if c}
    cols = sum(len(c) for n, (_k, c, _q) in objs.items() if n not in ALIASES)
    check(not missing and all(f"`{a}`" in doc for a in ALIASES), f"docs/reporting.md documents every column of every object ({cols} columns) and names the aliases" + (f": undocumented {missing}" if missing else ""))
    d17 = "Payments against the invoice lines **due** in month M, as of the window end, divided by the net amount of the lines due in M"
    check(d17 in doc and "D17 collection rate (cohort): payments against invoice lines due in month M" in text and "collected_cohort / nullif(billed_due, 0)" in body,
          "the collection rate is the cohort definition (D17), stated in the docs and the SQL; cash received is a separate measure")

    print("US-10.2 The marts")
    kinds = {n: k for n, (k, _c, _q) in objs.items()}
    check(all(kinds.get(m) == "mart" for m in GRAIN) and set(GRAIN) == set(reporting.MARTS),
          "the four marts are materialized views; etl/reporting.py knows the same four (lineage)")
    unique = {m: re.search(rf"CREATE UNIQUE INDEX \w+ ON lue_reporting\.{m}\s*\(([^)]*)\)", body) for m in GRAIN}
    check(all(u and [c.strip() for c in u.group(1).split(",")] == GRAIN[m] for m, u in unique.items())
          and all(set(GRAIN[m]) <= set(objs[m][1]) for m in GRAIN),
          "each mart has a unique index on exactly its grain (so it can refresh concurrently): " + "; ".join(f"{m} ({', '.join(g)})" for m, g in GRAIN.items()))
    fn = body.split("CREATE FUNCTION lue_reporting.refresh_marts()")[1].split("$$;")[0] if "CREATE FUNCTION lue_reporting.refresh_marts()" in body else ""
    check(fn and all(f"'{m}'" in fn for m in GRAIN) and "CONCURRENTLY" in fn and "REVOKE ALL ON FUNCTION lue_reporting.refresh_marts() FROM PUBLIC" in body,
          "refresh_marts() refreshes all four (concurrently once populated); nobody but its owner may run it")
    occ = objs["mart_occupancy_monthly"][1]
    check({"unit_days", "occupied_days"} <= set(occ) and "o.occupied_days::numeric / nullif(o.unit_days, 0)" in body
          and "avg(" not in body.split("CREATE MATERIALIZED VIEW lue_reporting.mart_occupancy_monthly")[1].split("CREATE UNIQUE INDEX")[0],
          "occupancy is stored as unit-days and occupied unit-days and rated as their ratio (the average of daily occupancy), never an average of averages")

    print("US-10.3 One schema, read-only reads")
    reads = set(re.findall(r"\b(lue_\w+)\.\w+", body))
    check(reads <= {"lue_dw", "lue_reporting"}, f"the layer reads lue_dw and itself only ({', '.join(sorted(reads))}); never staging or audit")
    created = set(objs) | {"refresh_marts"}
    dropped = set(re.findall(r"lue_reporting\.(\w+)", " ".join(re.findall(r"DROP [A-Z ]+IF EXISTS[^;]+;", body))))
    check(created <= dropped and body.index("DROP VIEW") < body.index("CREATE VIEW"),
          "every object is dropped before the file creates it, so a deploy on a loaded warehouse recreates the layer (safe to re-run)")
    deploy = (ROOT / "scripts" / "db_deploy.py").read_text(encoding="utf-8")
    check('ROOT / "sql" / "50_reporting"' in deploy.split("DDL_DIRS =")[1].split("\n")[0], "scripts/db_deploy.py deploys sql/50_reporting after the DDL and staging")
    check(p.NAMES[-1] == "marts" and "reporting.STEP" in __import__("inspect").getsource(p.layer) and reporting.STEP == "refresh_marts",
          "the pipeline's last stage, marts, refreshes them (step refresh_marts in the run log); no manual step")
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
