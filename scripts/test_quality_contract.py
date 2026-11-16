#!/usr/bin/env python3
"""E4 checks that need no database (run by CI in make gen-test).

    python scripts/test_quality_contract.py

The rule catalogue (etl/quality/rules.toml) against the bronze DDL and the other contracts: every
rule is well formed, names real tables and columns, and the SQL the engine builds for it parses
(pglast); every bronze table has its NULL checks; the code lists match etl/reference_data.py;
every check the US-2.6 answer key expects has rules; malformed rules are refused.
"""

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl import gen_defects  # noqa: E402
from etl import reference_data as ref  # noqa: E402
from etl.quality import engine  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def bronze_ddl() -> dict[str, list[str]]:
    from pglast import ast, parse_sql

    text = (ROOT / "sql" / "20_staging" / "01_bronze.sql").read_text(encoding="utf-8")
    out = {}
    for raw in parse_sql(text):
        if isinstance(raw.stmt, ast.CreateStmt):
            out[raw.stmt.relation.relname] = [
                e.colname for e in raw.stmt.tableElts if isinstance(e, ast.ColumnDef)
            ]
    return out


def as_runnable(sql: str) -> str:
    """The engine's statement with its parameters filled in, as psycopg2 would send it."""
    sql = sql.replace("%(run)s", "1").replace("%(found)s", "now()")
    sql = sql.replace("%(batches)s", "ARRAY[1]::bigint[]")
    return sql.replace("%%", "%")


def refused(text: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.toml"
        path.write_text(text, encoding="utf-8")
        try:
            engine.load_rules(path)
        except engine.RuleError as exc:
            return str(exc)
    return ""


def main() -> int:
    from pglast import parse_sql

    print("=" * 70)
    print(" E4 contract tests (no database): the rule catalogue")
    print("=" * 70)
    rules = engine.load_rules()
    tables = bronze_ddl()
    print("The catalogue")
    check(len(rules) >= 100 and len({r.id for r in rules}) == len(rules),
          f"{len(rules)} rules, every id unique")  # fmt: skip
    check([r.check for r in rules] == sorted(r.check for r in rules),
          "the engine runs them in the order DQ-01 to DQ-06")
    check({r.check for r in rules} == set(engine.CHECKS),
          "every check DQ-01 to DQ-06 has rules")
    try:
        engine.check_against(rules, tables)
        problem = ""
    except engine.RuleError as exc:
        problem = str(exc)
    check(not problem, "every table and column a rule names exists in the bronze DDL"
          + (f": {problem}" if problem else ""))  # fmt: skip
    nulls = {r.table for r in rules if r.check == "DQ-01" and r.severity == "reject"}
    check(nulls == set(tables), f"all {len(tables)} bronze tables have their NULL check (DQ-01)")
    check(all(r.bad for r in rules if r.type == "condition"),
          "every condition rule carries a bad example for its test")

    print("The SQL the engine builds")
    bad_sql = []
    for r in rules:
        cols = tables[r.table]
        data = [c for c in cols if c not in engine.METADATA]
        order = "source_row" if "source_row" in cols else "row_id"
        for scoped in (False, True):
            try:
                parse_sql(as_runnable(engine.rule_sql(r, data, order, scoped)))
            except Exception as exc:  # noqa: BLE001
                bad_sql.append(f"{r.id}: {exc}")
    check(not bad_sql, f"the statement of each of the {len(rules)} rules parses (scoped to "
          "batches and not)" + (f": {bad_sql[0]}" if bad_sql else ""))  # fmt: skip
    try:
        for t in tables:
            parse_sql(as_runnable(engine.quarantine_sql(t)))
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    check(ok, "the quarantine statement parses for every bronze table")
    sql = engine.rule_sql(next(r for r in rules if r.id == "S1-INL-05"), [], "row_id", True)
    check("NOT EXISTS (SELECT 1 FROM lue_audit.dq_result r WHERE r.run_id = %(run)s" in sql,
          "every statement skips rows an earlier rule rejected in the same run")
    check(engine.literal("it's 100%") == "'it''s 100%%'",
          "texts are quoted safely (an apostrophe, a % that psycopg2 would misread)")

    print("Agreement with the other contracts")
    lists = {r.id: r.values for r in rules if r.type == "in_list"}
    check(lists.get("S1-INL-08") == [c[0] for c in ref.CHARGE_TYPES]
          and lists.get("S1-PAY-07") == [m[0] for m in ref.PAYMENT_METHODS]
          and lists.get("S1-LEV-05") == [e[0] for e in ref.LEASE_EVENT_TYPES],
          "the charge, payment-method and lease-event codes are those of reference_data.py")
    expected = {rule for _h, rule in gen_defects.HANDLING.values() if rule.startswith("DQ-")}
    check(expected <= {r.check for r in rules},
          f"every check the US-2.6 answer key expects ({', '.join(sorted(expected))}) has rules")
    late = [r for r in rules if r.type == "reference" and "tenant" in r.ref_table]
    check(late and all(r.severity == "warn" for r in late),
          "a missing tenant is a warning (inferred member), never a rejection")

    print("Malformed rules are refused")
    head = '[[rule]]\nid = "X-1"\ncheck = "DQ-01"\ntable = "brz_unit"\nseverity = "reject"\n'
    msg = refused(head + 'type = "required"\nmessage = "m"\n')
    check("columns is required" in msg, "a required rule without columns")
    msg = refused(head + 'type = "condition"\nmessage = "m"\nsql = "b.x = 1"\n')
    check("bad example" in msg, "a condition without a bad example")
    msg = refused(head + 'type = "required"\nmessage = "m"\ncolumns = ["a; DROP TABLE x"]\n')
    check("plain lower-case name" in msg, "a column name that is not a plain name")
    msg = refused(head + 'type = "condition"\nmessage = "m"\nsql = "1=1; DELETE FROM x"\n'
                  'bad = { a = "1" }\n')  # fmt: skip
    check("cannot contain ;" in msg, "SQL with a second statement")
    msg = refused(head + 'type = "required"\nmessage = "m"\ncolumns = ["a"]\n' + head
                  + 'type = "required"\nmessage = "m"\ncolumns = ["a"]\n')  # fmt: skip
    check("duplicate id" in msg, "two rules with the same id")
    msg = refused(head + 'type = "required"\nmessage = "m"\ncolumns = ["a"]\ncolour = "red"\n')
    check("unknown field" in msg, "an unknown field (a typo)")
    check(all(re.match(r"^S[1-6]-[A-Z]{3}-\d{2}$", r.id) for r in rules),
          "rule ids follow S<source>-<TABLE>-<nn>")

    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
