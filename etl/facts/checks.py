"""US-7.6: the fact tests, run as the last step of every fact run.

sql/90_tests/02_fact_tests.sql holds one query per test (grain, an orphan check for each of the 41
foreign keys, impossible values), each returning its violations. The step writes one row per test
to lue_audit.reconciliation (expected 0, found, passed) and fails when any test has violations,
so a structurally wrong fact never passes a run unnoticed. The special members are not orphans:
how many rows use -1 (Unknown) and -2 (Not applicable) is counted per key and reported apart.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from pathlib import Path

from etl.facts import keys, spec

TESTS_SQL = Path(__file__).resolve().parents[2] / "sql" / "90_tests" / "02_fact_tests.sql"


def run_tests(cur) -> list[tuple[str, int]]:
    """[(test, violations)] in the file's order of names."""
    cur.execute(TESTS_SQL.read_text(encoding="utf-8"))
    return [(name, int(n)) for name, n in cur.fetchall()]


def special_members(cur) -> dict[str, dict[str, tuple[int, int]]]:
    """{fact: {key column: (rows on -1, rows on -2)}}, only the keys that use them."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for f in spec.FACTS:
        sel = ", ".join(f"count(*) FILTER (WHERE {k} = {keys.UNKNOWN}), count(*) FILTER (WHERE {k} = {keys.NOT_APPLICABLE})"
                        for k in f.keys)  # fmt: skip
        cur.execute(f"SELECT {sel} FROM lue_dw.{f.name}")
        row = cur.fetchone()
        used = {k: (row[2 * i], row[2 * i + 1]) for i, k in enumerate(f.keys) if row[2 * i] or row[2 * i + 1]}
        if used:
            out[f.name] = used
    return out


def record(audit_cur, run_id: int, tests: list[tuple[str, int]]) -> None:
    """One row per test in lue_audit.reconciliation, on the run's autocommit audit connection, so
    the results stay even when the step then fails."""
    audit_cur.executemany(
        "INSERT INTO lue_audit.reconciliation (run_id, check_name, source_value, warehouse_value, "
        "difference, passed) VALUES (%s, %s, 0, %s, %s, %s)",
        [(run_id, name[:60], n, n, n == 0) for name, n in tests],
    )
