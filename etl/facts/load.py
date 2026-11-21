"""US-7.1: the one loader the transaction, accumulating and factless facts go through.

A fact is a function of staging and the dimensions, so a load makes the fact equal its source,
in one transaction per fact:
  1. Source: the fact's query into a temp table. A grain twice is refused (the step fails,
     nothing changes). A row missing a required value is counted as rejected and not loaded.
  2. Delete the fact rows whose grain is no longer in the source (an allocation staging moved).
  3. Update, in place, the rows whose grain is there but whose values differ (a ticket that
     reached its next milestone: the accumulating snapshot, US-7.4).
  4. Insert the grains not in the fact yet.
Matching is on the grain columns (the fact's natural key), so a rerun inserts, updates and
deletes nothing. Unresolved keys (-1) are counted per key column and reported. Technical
columns: source_system from the source, batch_id the pipeline run, loaded_at when.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from etl.facts import spec


class FactError(Exception):
    """A fact cannot be loaded as its source stands (named, with what to do)."""


@dataclass
class FactLoad:
    fact: str
    read: int = 0
    rejected: int = 0  # source rows missing a required value
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    unknown_keys: dict[str, int] = field(default_factory=dict)  # key column -> rows with -1

    @property
    def unknown(self) -> int:
        return sum(self.unknown_keys.values())


def _match(f: spec.Fact, left: str, right: str) -> str:
    return " AND ".join(f"{left}.{c} = {right}.{c}" for c in f.grain)


def delete_sql(f: spec.Fact) -> str:
    return (f"DELETE FROM lue_dw.{f.name} x WHERE NOT EXISTS (SELECT 1 FROM _fact_src s WHERE "
            f"{_match(f, 's', 'x')})")  # fmt: skip


def update_sql(f: spec.Fact) -> str:
    values = [c for c in f.cols if c not in f.grain] + ["source_system"]
    return (f"UPDATE lue_dw.{f.name} x SET {', '.join(f'{c} = s.{c}' for c in values)}, batch_id = %(run)s, "
            f"loaded_at = %(now)s FROM _fact_src s WHERE {_match(f, 'x', 's')} AND "
            f"({', '.join('x.' + c for c in values)}) IS DISTINCT FROM ({', '.join('s.' + c for c in values)})")  # fmt: skip


def insert_sql(f: spec.Fact) -> str:
    names = [*f.cols, "source_system", "batch_id", "loaded_at"]
    values = [f"s.{c}" for c in f.cols] + ["s.source_system", "%(run)s", "%(now)s"]
    return (f"INSERT INTO lue_dw.{f.name} ({', '.join(names)}) SELECT {', '.join(values)} FROM _fact_src s "
            f"WHERE NOT EXISTS (SELECT 1 FROM lue_dw.{f.name} x WHERE {_match(f, 'x', 's')}) "
            f"ORDER BY {', '.join('s.' + c for c in f.grain)}")  # fmt: skip


def load_fact(cur, f: spec.Fact, run_id: int, now: datetime) -> FactLoad:
    out = FactLoad(f.name)
    cur.execute(f"CREATE TEMP TABLE _fact_src ON COMMIT DROP AS {f.source}")
    grain = ", ".join(f.grain)
    cur.execute(f"SELECT count(*), count(DISTINCT ({grain})) FROM _fact_src")
    out.read, distinct = cur.fetchone()
    if distinct != out.read:
        raise FactError(f"{f.name}: {out.read - distinct} grains appear twice in the source "
                        f"({grain}); the fact's grain must be unique")  # fmt: skip
    if f.required:
        missing = " OR ".join(f"{c} IS NULL" for c in f.required)
        cur.execute(f"DELETE FROM _fact_src WHERE {missing}")
        out.rejected = cur.rowcount
    if f.keys:
        cur.execute("SELECT " + ", ".join(f"count(*) FILTER (WHERE {k} = -1)" for k in f.keys) + " FROM _fact_src")
        out.unknown_keys = {k: n for k, n in zip(f.keys, cur.fetchone()) if n}
    params = {"run": run_id, "now": now}
    cur.execute(delete_sql(f))
    out.deleted = cur.rowcount
    cur.execute(update_sql(f), params)
    out.updated = cur.rowcount
    cur.execute(insert_sql(f), params)
    out.inserted = cur.rowcount
    out.unchanged = out.read - out.rejected - out.inserted - out.updated
    cur.execute("DROP TABLE _fact_src")
    return out
