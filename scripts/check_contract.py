#!/usr/bin/env python3
"""Contract check: the deployable DDL in sql/10_ddl must match the frozen Phase 1 pack.

    python scripts/check_contract.py

For every table that sql/10_ddl creates, compares it with the same table in
docs/phase1/sql/physical_model.sql: column names and order, types, NOT NULL rules, every named
constraint, and the special-member rows. The only differences allowed are the Phase 2 additions in
the ALLOWED_* lists below, each required by the development plan.
Runs in CI (make test); needs pglast, not a database.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "docs" / "phase1" / "sql" / "physical_model.sql"
DDL_DIR = ROOT / "sql" / "10_ddl"

# Phase 2 additions that may exist in sql/10_ddl but not in the pack (name pattern -> reason).
NOT_NULL_KINDS = ("CONSTR_NOTNULL", "CONSTR_IDENTITY")  # an identity column is always NOT NULL
ALLOWED_EXTRA_TABLES = {
    "etl_watermark": "US-1.5: last loaded value per source table (decision O5)",
}
ALLOWED_EXTRA_CONSTRAINTS = {
    r"ck_dim_\w+_effective_range": "US-1.2: SCD2 range check",
}
# Fact surrogate keys become identity columns (US-1.3); type and NOT NULL are unchanged, so the
# column comparison below already accepts them. Partitions (including the default) are checked by
# scripts/test_facts.py in the database.
ALLOWED_EXTRA_INDEXES = {
    r"uq_dim_\w+_one_current": "US-1.2: one current row per natural key (SCD2)",
}


def strip_meta(text: str) -> str:
    return "\n".join("" if ln.lstrip().startswith("\\") else ln for ln in text.splitlines())


def read_model(texts: list[str]) -> dict:
    """Tables (columns, constraints), special-member rows and indexes, from SQL text."""
    from pglast import ast, parse_sql
    from pglast.stream import RawStream

    def show(node) -> str:
        return RawStream()(node)

    model = {"tables": {}, "rows": {}, "indexes": {}}
    for text in texts:
        for raw in parse_sql(strip_meta(text)):
            stmt = raw.stmt
            if isinstance(stmt, ast.CreateStmt) and stmt.partbound is not None:
                continue  # monthly partitions are checked by count in the database tests
            if isinstance(stmt, ast.CreateStmt):
                name = stmt.relation.relname
                cols, cons = [], {}
                for el in stmt.tableElts:
                    if isinstance(el, ast.ColumnDef):
                        kinds = [c.contype for c in (el.constraints or ())]
                        not_null = any(k.name in NOT_NULL_KINDS for k in kinds)
                        identity = any(k.name == "CONSTR_IDENTITY" for k in kinds)
                        cols.append((el.colname, show(el.typeName), not_null, identity))
                    elif isinstance(el, ast.Constraint):
                        cons[el.conname] = show(el)
                model["tables"][name] = {"columns": cols, "constraints": cons}
            elif isinstance(stmt, ast.InsertStmt):
                stmt.onConflictClause = None
                model["rows"].setdefault(stmt.relation.relname, []).append(show(stmt))
            elif isinstance(stmt, ast.IndexStmt):
                model["indexes"][stmt.idxname] = (stmt.relation.relname, show(stmt))
    return model


def allowed(rules: dict, name: str):
    return next((reason for pattern, reason in rules.items() if re.fullmatch(pattern, name)), None)


def normalise(sql_text: str) -> str:
    """The pack calls key_is_special() unqualified; sql/10_ddl qualifies it with lue_dw."""
    return sql_text.replace("lue_dw.key_is_special(", "key_is_special(")


def main() -> int:
    try:
        import pglast  # noqa: F401
    except ImportError:
        print("FAIL  pglast is not installed (pip install -r requirements-ci.txt)")
        return 1

    from pglast.parser import ParseError

    frozen = read_model([FROZEN.read_text(encoding="utf-8")])
    files = sorted(DDL_DIR.glob("*.sql"))
    for f in files:
        try:
            read_model([f.read_text(encoding="utf-8")])
        except ParseError as exc:
            print(f"FAIL  {f.relative_to(ROOT).as_posix()}: {exc} (fix the SQL syntax first)")
            return 1
    ours = read_model([f.read_text(encoding="utf-8") for f in files])
    problems, notes = [], []

    for name, table in sorted(ours["tables"].items()):
        if name not in frozen["tables"]:
            if name in ALLOWED_EXTRA_TABLES:
                notes.append(f"{name}: extra table allowed ({ALLOWED_EXTRA_TABLES[name]})")
            else:
                problems.append(f"{name}: not in the Phase 1 pack")
            continue
        want = frozen["tables"][name]
        got_cols = [c[:3] for c in table["columns"]]
        want_cols = [c[:3] for c in want["columns"]]
        for i, (g, w) in enumerate(zip(got_cols, want_cols), 1):
            if g != w:
                problems.append(f"{name}: column {i} is {g}, the pack has {w}")
        if len(got_cols) != len(want_cols):
            problems.append(f"{name}: {len(got_cols)} columns, the pack has {len(want_cols)}")
        for con, text in want["constraints"].items():
            if con not in table["constraints"]:
                problems.append(f"{name}: constraint {con} from the pack is missing")
            elif normalise(table["constraints"][con]) != text:
                problems.append(f"{name}: constraint {con} differs from the pack")
        for con in sorted(set(table["constraints"]) - set(want["constraints"])):
            reason = allowed(ALLOWED_EXTRA_CONSTRAINTS, con)
            if reason:
                notes.append(f"{name}: + {con} ({reason})")
            else:
                problems.append(f"{name}: constraint {con} is not in the pack and not allowed")
        if sorted(ours["rows"].get(name, [])) != sorted(frozen["rows"].get(name, [])):
            problems.append(f"{name}: special-member rows differ from the pack")

    for idx, (table, _text) in sorted(ours["indexes"].items()):
        reason = allowed(ALLOWED_EXTRA_INDEXES, idx)
        if reason:
            notes.append(f"{table}: + index {idx} ({reason})")
        elif idx in frozen["indexes"]:
            problems.append(f"{table}: index {idx} is a pack index; D20 keeps it out")
        else:
            problems.append(f"{table}: index {idx} is not allowed in the baseline (D20)")

    pending = sorted(set(frozen["tables"]) - set(ours["tables"]))
    for line in notes:
        print(f"note  {line}")
    for line in problems:
        print(f"FAIL  {line}")
    print(
        f"contract: {len(ours['tables'])} table(s) checked against the pack, "
        f"{len(problems)} problem(s); {len(pending)} pack table(s) not deployed yet"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
