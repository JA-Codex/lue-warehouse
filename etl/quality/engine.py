"""US-4.1: the data quality engine. Runs the rule catalogue (etl/quality/rules.toml) on bronze.

    rules = load_rules()
    run = Run()                                  # the ingestion framework of US-3.1
    run.step("validate_dq", "bronze", lambda step: validate(step, rules))

For every rule, in catalogue order (DQ-01 to DQ-06, then file order), one SQL statement:

    INSERT INTO lue_audit.dq_result (...) SELECT ... FROM lue_staging.<table> b
    WHERE <the rule fails> AND <the row has no rejection yet in this run>

so a row is rejected by the FIRST rule it fails and later rules skip it; a warning does not stop
later rules. At the end every rejected row is copied, as JSON, into the pack's
lue_audit.quarantine with the check name and the reason (which quotes the column and its value).

Idempotent: before validating, the findings and quarantine rows of the batches in scope are
deleted, so validating twice gives the same result. The whole validation is one transaction (a
step of the US-3.1 framework): if anything fails, nothing of it stays.

The rule types are documented at the top of rules.toml. The SQL for a rule is built from its
fields only (column and table names are checked against the bronze tables first), so a new rule
needs no code. `rule_sql` is also used without a database by scripts/test_quality_contract.py.
"""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / "rules.toml"
CHECKS = {
    "DQ-01": "DQ-01 NULL",
    "DQ-02": "DQ-02 Data type",
    "DQ-03": "DQ-03 Duplicate",
    "DQ-04": "DQ-04 Business rule",
    "DQ-05": "DQ-05 Referential",
    "DQ-06": "DQ-06 Range",
}
COLUMN_TYPES = ("required", "numeric", "integer", "date", "timestamp", "boolean", "in_list",
                "date_range", "number_range")  # fmt: skip
TYPES = (*COLUMN_TYPES, "duplicate_exact", "duplicate_conflict", "reference", "condition")
METADATA = ("batch_id", "source_system", "loaded_at", "source_file", "source_row", "row_hash",
            "row_id")  # fmt: skip
NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class RuleError(ValueError):
    """A rule in the catalogue is not valid."""


@dataclass
class Rule:
    id: str
    check: str
    table: str
    type: str
    severity: str
    message: str
    columns: list[str] = field(default_factory=list)
    key: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    ref_table: str = ""
    ref_columns: list[str] = field(default_factory=list)
    min: object = None
    max: object = None
    abs: bool = False
    sql: str = ""
    show: list[str] = field(default_factory=list)
    where: str = ""
    fixture_where: str = ""
    bad: dict = field(default_factory=dict)
    position: int = 0

    @property
    def check_name(self) -> str:
        return CHECKS[self.check]

    def referenced_columns(self) -> list[str]:
        return [*self.columns, *self.key, *self.show, *self.bad]


def load_rules(path: Path = RULES_FILE) -> list[Rule]:
    """The catalogue, checked and in the order the engine runs it."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RuleError(f"{path.name}: not valid TOML: {exc}") from None
    known = set(Rule.__dataclass_fields__) - {"position"}
    rules, seen = [], set()
    for i, raw in enumerate(data.get("rule", []), start=1):
        where = f"{path.name} rule {i} ({raw.get('id', '?')})"
        extra = set(raw) - known
        if extra:
            raise RuleError(f"{where}: unknown field(s) {', '.join(sorted(extra))}")
        missing = {"id", "check", "table", "type", "severity", "message"} - set(raw)
        if missing:
            raise RuleError(f"{where}: missing field(s) {', '.join(sorted(missing))}")
        rule = Rule(**raw, position=i)
        problems = []
        if rule.id in seen:
            problems.append("duplicate id")
        if len(rule.id) > 40:
            problems.append("id longer than 40 characters")
        if rule.check not in CHECKS:
            problems.append(f"check must be one of {', '.join(CHECKS)}")
        if rule.type not in TYPES:
            problems.append(f"type must be one of {', '.join(TYPES)}")
        if rule.severity not in ("reject", "warn"):
            problems.append("severity must be reject or warn")
        if not NAME.match(rule.table) or not rule.table.startswith("brz_"):
            problems.append("table must be a lue_staging.brz_* table")
        names = [*rule.referenced_columns(), *rule.ref_columns]
        if rule.ref_table and not NAME.match(rule.ref_table):
            problems.append("bad ref_table")
        if any(not NAME.match(c) for c in names):
            problems.append("a column name is not a plain lower-case name")
        if rule.type in COLUMN_TYPES and not rule.columns:
            problems.append("columns is required for this type")
        if rule.type.startswith("duplicate") and not rule.key:
            problems.append("key is required for this type")
        if rule.type == "reference" and (
            not rule.ref_table or len(rule.ref_columns) != len(rule.columns) or not rule.columns
        ):
            problems.append("reference needs columns, ref_table and as many ref_columns")
        if rule.type == "in_list" and not rule.values:
            problems.append("in_list needs values")
        if rule.type in ("date_range", "number_range") and (rule.min is None or rule.max is None):
            problems.append("a range needs min and max")
        if rule.type == "date_range":
            try:
                date.fromisoformat(str(rule.min))
                date.fromisoformat(str(rule.max))
            except ValueError:
                problems.append("date_range min and max must be ISO dates")
        if rule.type == "number_range" and not all(
            isinstance(v, int | float) and not isinstance(v, bool) for v in (rule.min, rule.max)
        ):
            problems.append("number_range min and max must be numbers")
        if rule.type == "condition" and (not rule.sql or not rule.bad):
            problems.append("condition needs sql and a bad example (bad = {...})")
        if ";" in rule.sql or ";" in rule.where or ";" in rule.fixture_where:
            problems.append("sql, where and fixture_where cannot contain ;")
        if problems:
            raise RuleError(f"{where}: {'; '.join(problems)}")
        seen.add(rule.id)
        rules.append(rule)
    order = list(CHECKS)
    return sorted(rules, key=lambda r: (order.index(r.check), r.position))


def check_against(rules: list[Rule], tables: dict[str, list[str]]) -> None:
    """Every table and column a rule names must exist (tables: bronze table -> columns)."""
    for r in rules:
        if r.table not in tables:
            raise RuleError(f"{r.id}: table {r.table} does not exist")
        missing = [c for c in r.referenced_columns() if c not in tables[r.table]]
        if r.type in ("duplicate_exact", "duplicate_conflict") and "source_row" not in tables[
            r.table
        ] and "row_id" not in tables[r.table]:
            missing.append("row_id")
        if r.ref_table:
            if r.ref_table not in tables:
                raise RuleError(f"{r.id}: ref_table {r.ref_table} does not exist")
            missing += [c for c in r.ref_columns if c not in tables[r.ref_table]]
        if missing:
            raise RuleError(f"{r.id}: unknown column(s) {', '.join(missing)} in {r.table}")


# ----------------------------------------------------------------------------- SQL
def esc(text: str) -> str:
    """psycopg2 reads % as a parameter marker: a literal % in the SQL text must be %%."""
    return text.replace("%", "%%")


def literal(value) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, date | datetime):
        value = value.isoformat()
    return "'" + esc(str(value)).replace("'", "''") + "'"


def _nonempty(c: str) -> str:
    return f"(b.{c} IS NOT NULL AND btrim(b.{c}) <> '')"


def _quoted(c: str) -> str:
    return f"coalesce(quote_literal(b.{c}), 'NULL')"


def column_failure(rule: Rule, c: str) -> str:
    """SQL that is TRUE when column c of row b fails a column-type rule."""
    t = rule.type
    if t == "required":
        return f"(b.{c} IS NULL OR btrim(b.{c}) = '')"
    if t == "numeric":
        return f"({_nonempty(c)} AND lue_audit.try_numeric(b.{c}) IS NULL)"
    if t == "integer":
        return f"({_nonempty(c)} AND b.{c} !~ '^\\s*-?[0-9]+\\s*$')"
    if t == "date":
        return f"({_nonempty(c)} AND lue_audit.try_date(b.{c}) IS NULL)"
    if t == "timestamp":
        return f"({_nonempty(c)} AND lue_audit.try_timestamp(b.{c}) IS NULL)"
    if t == "boolean":
        return f"({_nonempty(c)} AND lower(btrim(b.{c})) NOT IN ('true', 'false'))"
    if t == "in_list":
        values = ", ".join(literal(v) for v in rule.values)
        return f"({_nonempty(c)} AND b.{c} NOT IN ({values}))"
    if t == "date_range":
        day = f"coalesce(lue_audit.try_date(b.{c}), lue_audit.try_timestamp(b.{c})::date)"
        return (f"({_nonempty(c)} AND {day} NOT BETWEEN DATE {literal(rule.min)} "
                f"AND DATE {literal(rule.max)})")  # fmt: skip
    if t == "number_range":
        value = f"lue_audit.try_numeric(b.{c})"
        if rule.abs:
            value = f"abs({value})"
        bounds = f"{literal(rule.min)} AND {literal(rule.max)}"
        return f"({_nonempty(c)} AND {value} NOT BETWEEN {bounds})"
    raise RuleError(f"{rule.id}: {t} is not a column type")


def _reason(rule: Rule, detail: str) -> str:
    head = literal(f"[{rule.id}] {rule.message}: ")
    return f"left({head} || {detail}, 200)"


def _filters(rule: Rule, scoped: bool) -> list[str]:
    out = []
    if scoped:
        out.append("b.batch_id = ANY(%(batches)s)")
    if rule.where:
        out.append(f"({esc(rule.where)})")
    out.append(
        "NOT EXISTS (SELECT 1 FROM lue_audit.dq_result r WHERE r.run_id = %(run)s AND "
        f"r.source_table = {literal(rule.table)} AND r.row_id = b.row_id AND "
        "r.severity = 'reject')"
    )
    return out


def _insert(rule: Rule, select_from: str, reason: str, where: list[str]) -> str:
    return (
        "INSERT INTO lue_audit.dq_result (run_id, batch_id, source_system, source_table, row_id, "
        "rule_id, check_name, severity, reason, found_at)\n"
        f"SELECT %(run)s, b.batch_id, b.source_system, {literal(rule.table)}, b.row_id, "
        f"{literal(rule.id)}, {literal(rule.check_name)}, {literal(rule.severity)}, {reason}, "
        f"%(found)s\nFROM {select_from}\nWHERE " + "\n  AND ".join(where)
    )


def rule_sql(rule: Rule, data_columns: list[str], order_column: str, scoped: bool) -> str:
    """The statement that records rule's findings. data_columns: the table's non-metadata
    columns (for the duplicate types); order_column: source_row or row_id."""
    table = f"lue_staging.{rule.table} b"
    filters = _filters(rule, scoped)
    if rule.type in COLUMN_TYPES:
        fails = [column_failure(rule, c) for c in rule.columns]
        detail = "CASE " + " ".join(
            f"WHEN {f} THEN {literal(c + (' is empty' if rule.type == 'required' else ' = '))}"
            + ("" if rule.type == "required" else f" || {_quoted(c)}")
            for f, c in zip(fails, rule.columns, strict=True)
        ) + " END"
        return _insert(rule, table, _reason(rule, detail),
                       [*filters, "(" + " OR ".join(fails) + ")"])  # fmt: skip
    if rule.type == "reference":
        present = " AND ".join(_nonempty(c) for c in rule.columns)
        match = " AND ".join(f"x.{rc} = b.{c}" for c, rc in zip(rule.columns, rule.ref_columns,
                                                                    strict=True))  # fmt: skip
        missing = f"NOT EXISTS (SELECT 1 FROM lue_staging.{rule.ref_table} x WHERE {match})"
        detail = " || ', ' || ".join(
            f"{literal(c + ' = ')} || {_quoted(c)}" for c in rule.columns
        )
        detail += f" || {literal(' not in ' + rule.ref_table)}"
        return _insert(rule, table, _reason(rule, detail), [*filters, present, missing])
    if rule.type == "condition":
        shown = rule.show or rule.columns
        detail = (" || '; ' || ".join(f"{literal(c + ' = ')} || {_quoted(c)}" for c in shown)
                  if shown else "''")  # fmt: skip
        return _insert(rule, table, _reason(rule, detail),
                       [*filters, f"(({esc(rule.sql)}) IS TRUE)"])  # fmt: skip
    data = "md5(row(" + ", ".join(f"b.{c}" for c in data_columns) + ")::text)"
    key = ", ".join(f"b.{k}" for k in rule.key)
    key_text = " || ', ' || ".join(f"{literal(k + ' = ')} || {_quoted(k)}" for k in rule.key)
    if rule.type == "duplicate_exact":
        ranked = (
            f"(SELECT b.*, row_number() OVER w AS dq_n, first_value(b.{order_column}) OVER w "
            f"AS dq_kept FROM lue_staging.{rule.table} b WHERE " + " AND ".join(filters)
            + f" WINDOW w AS (PARTITION BY b.batch_id, {data} ORDER BY b.{order_column}, "
            "b.row_id)) b"
        )
        detail = f"{key_text} || {literal('; the first copy is kept (' + order_column + ' ')} || "
        detail += "b.dq_kept::text || ')'"
        return _insert(rule, ranked, _reason(rule, detail), ["b.dq_n > 1"])
    if rule.type == "duplicate_conflict":
        groups = (
            f"SELECT b.batch_id AS dq_batch, {key} FROM lue_staging.{rule.table} b WHERE "
            + " AND ".join(filters)
            + f" GROUP BY b.batch_id, {key} HAVING count(DISTINCT {data}) > 1"
        )
        match = " AND ".join(f"g.{k} IS NOT DISTINCT FROM b.{k}" for k in rule.key)
        detail = f"{key_text} || {literal('; the copies differ')}"
        return _insert(
            rule, table, _reason(rule, detail),
            [*filters, f"EXISTS (SELECT 1 FROM ({groups}) g WHERE g.dq_batch = b.batch_id AND "
                       f"{match})"],
        )  # fmt: skip
    raise RuleError(f"{rule.id}: unknown type {rule.type}")


def quarantine_sql(table: str) -> str:
    return (
        "INSERT INTO lue_audit.quarantine (run_id, source_system, source_table, batch_id, "
        "record, check_name, rejection_reason, rejected_at)\n"
        "SELECT r.run_id, r.source_system, r.source_table, r.batch_id, to_jsonb(b), "
        "r.check_name, r.reason, r.found_at\n"
        f"FROM lue_audit.dq_result r JOIN lue_staging.{table} b ON b.row_id = r.row_id\n"
        f"WHERE r.run_id = %(run)s AND r.source_table = {literal(table)} AND r.severity = 'reject'"
    )


# ----------------------------------------------------------------------------- running
def bronze_tables(cur) -> dict[str, list[str]]:
    cur.execute(
        "SELECT table_name, array_agg(column_name::text ORDER BY ordinal_position) FROM "
        "information_schema.columns WHERE table_schema = 'lue_staging' AND table_name LIKE "
        "'brz\\_%%' GROUP BY table_name"
    )
    return {t: list(cols) for t, cols in cur.fetchall()}


@dataclass
class Summary:
    run_id: int
    rows_checked: int = 0
    by_rule: dict[str, Counter] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)

    @property
    def rejected(self) -> int:
        return sum(c["reject"] for c in self.by_rule.values())

    @property
    def warned(self) -> int:
        return sum(c["warn"] for c in self.by_rule.values())


def validate(step, rules: list[Rule] | None = None, batches: list[int] | None = None) -> Summary:
    """Run the catalogue on bronze (all batches, or the given ones) inside a framework step."""
    import time

    rules = load_rules() if rules is None else rules
    cur = step.cur
    tables = bronze_tables(cur)
    check_against(rules, tables)
    # Fresh statistics first (US-8.4): just after a bulk ingest the planner knows nothing about the
    # new rows and picks nested loops; with ANALYZE the full validation takes 33 s instead of 315 s.
    for t in sorted({r.table for r in rules}):
        cur.execute(f"ANALYZE lue_staging.{t}")
    cur.execute("SELECT to_regclass('lue_audit.dq_batch') IS NOT NULL")
    if not cur.fetchone()[0]:  # a database deployed before E5
        raise RuleError("lue_audit.dq_batch is missing: run python scripts/db_deploy.py first")
    run_id = step.run.run_id
    found = step.loaded_at
    scoped = batches is not None
    if not scoped:
        batches = []
        for t in sorted(tables):
            cur.execute(f"SELECT DISTINCT batch_id FROM lue_staging.{t}")
            batches += [b for (b,) in cur.fetchall()]
    # Idempotent: forget what earlier validations said about these batches.
    cur.execute("DELETE FROM lue_audit.dq_result WHERE batch_id = ANY(%s)", (batches,))
    cur.execute("DELETE FROM lue_audit.quarantine WHERE batch_id = ANY(%s)", (batches,))
    summary = Summary(run_id)
    for t in sorted({r.table for r in rules}):
        cur.execute(f"SELECT count(*) FROM lue_staging.{t} WHERE batch_id = ANY(%s)", (batches,))
        summary.rows_checked += cur.fetchone()[0]
    params = {"run": run_id, "batches": batches, "found": found}
    for r in rules:
        cols = tables[r.table]
        data = [c for c in cols if c not in METADATA]
        order = "source_row" if "source_row" in cols else "row_id"
        clock = time.monotonic()
        cur.execute(rule_sql(r, data, order, scoped), params)
        summary.by_rule[r.id] = Counter({r.severity: cur.rowcount})
        summary.seconds[r.id] = time.monotonic() - clock
    for t in sorted({r.table for r in rules}):
        cur.execute(quarantine_sql(t), params)
    # E5: record which batches are validated (staging reads only these). In the same transaction,
    # so a failed validation records nothing.
    cur.execute(
        "INSERT INTO lue_audit.dq_batch (batch_id, run_id, validated_at) "
        "SELECT b, %(run)s, %(found)s FROM unnest(%(batches)s::bigint[]) AS b "
        "ON CONFLICT (batch_id) DO UPDATE SET run_id = EXCLUDED.run_id, "
        "validated_at = EXCLUDED.validated_at",
        params,
    )
    step.read(summary.rows_checked)
    step.reject(summary.rejected)
    step.result.rows_written = summary.rejected + summary.warned
    return summary
