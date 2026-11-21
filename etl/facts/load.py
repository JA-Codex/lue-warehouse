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

A periodic snapshot (US-7.3, `period` in the spec) runs steps 1 to 4 once per month of the data
window, so each pass touches one partition; rows outside the window are deleted. Then its last
`refresh_days` days are deleted and re-derived (NFR-08, the one declared exception of D14:
the rows are rewritten, their values stay the same unless a source changed).
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from etl.facts import keys, spec


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
    refreshed: int = 0  # rows deleted and re-derived by the refresh rule (periodic snapshot)
    unchanged: int = 0
    unknown_keys: dict[str, int] = field(default_factory=dict)  # key column -> rows with -1
    months: list[tuple] = field(default_factory=list)  # (month, staging, fact), US-7.2

    @property
    def unknown(self) -> int:
        return sum(self.unknown_keys.values())

    @property
    def months_off(self) -> list[str]:
        return [m for m, s, w in self.months if s != w]


def _match(f: spec.Fact, left: str, right: str) -> str:
    return " AND ".join(f"{left}.{c} = {right}.{c}" for c in f.grain)


def _within(f: spec.Fact) -> str:
    """A periodic snapshot's statements name the month loaded, so they touch one partition."""
    return f" AND x.{f.period} BETWEEN %(first_key)s AND %(last_key)s" if f.period else ""


def delete_sql(f: spec.Fact) -> str:
    """Rows whose grain left the source; for a periodic snapshot only within the month loaded."""
    return (f"DELETE FROM lue_dw.{f.name} x WHERE NOT EXISTS (SELECT 1 FROM _fact_src s WHERE "
            f"{_match(f, 's', 'x')}){_within(f)}")  # fmt: skip


def update_sql(f: spec.Fact) -> str:
    values = [c for c in f.cols if c not in f.grain] + ["source_system"]
    return (f"UPDATE lue_dw.{f.name} x SET {', '.join(f'{c} = s.{c}' for c in values)}, batch_id = %(run)s, "
            f"loaded_at = %(now)s FROM _fact_src s WHERE {_match(f, 'x', 's')}{_within(f)} AND "
            f"({', '.join('x.' + c for c in values)}) IS DISTINCT FROM ({', '.join('s.' + c for c in values)})")  # fmt: skip


def insert_sql(f: spec.Fact) -> str:
    names = [*f.cols, "source_system", "batch_id", "loaded_at"]
    values = [f"s.{c}" for c in f.cols] + ["s.source_system", "%(run)s", "%(now)s"]
    return (f"INSERT INTO lue_dw.{f.name} ({', '.join(names)}) SELECT {', '.join(values)} FROM _fact_src s "
            f"WHERE NOT EXISTS (SELECT 1 FROM lue_dw.{f.name} x WHERE {_match(f, 'x', 's')}{_within(f)}) "
            f"ORDER BY {', '.join('s.' + c for c in f.grain)}")  # fmt: skip


def months(first: str, last: str) -> list[tuple[date, date]]:
    """The calendar months of [first, last], each as (first day, last day)."""
    out, d, end = [], date.fromisoformat(first), date.fromisoformat(last)
    while d <= end:
        nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1)
        out.append((d, min(nxt - timedelta(days=1), end)))
        d = nxt
    return out


def _key(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def _source(cur, f: spec.Fact, out: FactLoad, params: dict) -> None:
    """The source (one period of it) into _fact_src: refuse a grain twice or an unresolved
    primary-key column; drop and count rows missing a required value; count the -1 keys."""
    cur.execute("DROP TABLE IF EXISTS _fact_src")
    cur.execute(f"CREATE TEMP TABLE _fact_src ON COMMIT DROP AS {f.source}", params)
    grain = ", ".join(f.grain)
    cur.execute(f"SELECT count(*), count(DISTINCT ({grain})) FROM _fact_src")
    read, distinct = cur.fetchone()
    out.read += read
    if distinct != read:
        raise FactError(f"{f.name}: {read - distinct} grains appear twice in the source "
                        f"({grain}); the fact's grain must be unique")  # fmt: skip
    for k in f.resolved:
        cur.execute(f"SELECT count(*) FROM _fact_src WHERE {k} = {keys.UNKNOWN}")
        if n := cur.fetchone()[0]:
            raise FactError(f"{f.name}: {n} rows have no {k} (-1), which is part of the primary key; "
                            f"load the dimensions first (python etl/dimensions/run.py)")  # fmt: skip
    if f.required:
        missing = " OR ".join(f"{c} IS NULL" for c in f.required)
        cur.execute(f"DELETE FROM _fact_src WHERE {missing}")
        out.rejected += cur.rowcount
    if f.keys:
        cur.execute("SELECT " + ", ".join(f"count(*) FILTER (WHERE {k} = -1)" for k in f.keys) + " FROM _fact_src")
        for k, n in zip(f.keys, cur.fetchone()):
            if n:
                out.unknown_keys[k] = out.unknown_keys.get(k, 0) + n


def _sync(cur, f: spec.Fact, out: FactLoad, params: dict) -> None:
    cur.execute(delete_sql(f), params)
    out.deleted += cur.rowcount
    cur.execute(update_sql(f), params)
    out.updated += cur.rowcount
    cur.execute(insert_sql(f), params)
    out.inserted += cur.rowcount


def load_fact(cur, f: spec.Fact, run_id: int, now: datetime) -> FactLoad:
    out = FactLoad(f.name)
    for sql in f.prepare:
        cur.execute(sql)
    base = {"run": run_id, "now": now}
    if not f.period:
        _source(cur, f, out, base)
        _sync(cur, f, out, base)
    else:
        first, last = keys.DATA_WINDOW
        cur.execute(f"DELETE FROM lue_dw.{f.name} WHERE {f.period} NOT BETWEEN %s AND %s",
                    (_key(date.fromisoformat(first)), _key(date.fromisoformat(last))))  # fmt: skip
        out.deleted += cur.rowcount
        for a, b in months(first, last):
            params = {**base, "first": a, "last": b, "first_key": _key(a), "last_key": _key(b)}
            _source(cur, f, out, params)
            _sync(cur, f, out, params)
        if f.refresh_days:
            end = date.fromisoformat(last)
            a = max(end - timedelta(days=f.refresh_days - 1), date.fromisoformat(first))
            params = {**base, "first": a, "last": end, "first_key": _key(a), "last_key": _key(end)}
            cur.execute(f"DELETE FROM lue_dw.{f.name} WHERE {f.period} BETWEEN %(first_key)s AND %(last_key)s", params)
            out.refreshed = cur.rowcount
            refresh = FactLoad(f.name)  # the re-derived days were counted in the monthly pass
            _source(cur, f, refresh, params)
            cur.execute(insert_sql(f), params)
            if cur.rowcount != out.refreshed:
                raise FactError(f"{f.name}: the refresh deleted {out.refreshed} rows of the last "
                                f"{f.refresh_days} days but re-derived {cur.rowcount}")  # fmt: skip
    out.unchanged = out.read - out.rejected - out.inserted - out.updated
    cur.execute("DROP TABLE IF EXISTS _fact_src")
    return out


def monthly_sql(f: spec.Fact) -> str:
    """Staging against the fact by month (US-7.2): month, staging amount, fact amount; every month
    either side has (a month missing on one side counts as 0 there)."""
    _label, fact_q, staging_q = f.monthly
    return (f"SELECT coalesce(s.month, w.month) AS month, coalesce(s.amount, 0) AS staging, "
            f"coalesce(w.amount, 0) AS fact FROM ({staging_q}) s FULL JOIN ({fact_q}) w ON w.month = s.month "
            f"ORDER BY 1")  # fmt: skip


def monthly(cur, f: spec.Fact) -> list[tuple]:
    """[(month, staging amount, fact amount)]; empty when the fact declares no reconciliation."""
    if f.monthly is None:
        return []
    cur.execute(monthly_sql(f))
    return cur.fetchall()
