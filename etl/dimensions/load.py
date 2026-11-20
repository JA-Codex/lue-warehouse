"""E6: the one loader every dimension goes through, one transaction per dimension.

1. Source: one row per natural key with its current values (spec.Dim.source). A natural key twice,
   or a row without one, is refused: the step fails and nothing changes.
2. New members (US-6.1): INSERT the natural keys not yet in the dimension. The identity column
   assigns the surrogate key (D6): never chosen by hand, never reused; the special members -1 and
   -2 are never touched. An SCD2 member starts with its oldest known state, valid from 1900-01-01.
3. Inferred members completed (US-6.5): a member created from a reference before its record
   arrived gets its real values in place and is_inferred FALSE; no new version.
4. SCD2 versions (US-6.2, US-6.3): from the history (every state with the date it took effect),
   the versions a member should have are rebuilt: the first from 1900-01-01, then one per change
   of a Type 2 value, a day's last state winning. Versions the dimension does not have yet are
   added: the current version is closed (effective_to = the change date, is_current FALSE) and the
   new one opened (effective_from = the change date, effective_to 9999-12-31). A change dated the
   same day as the current version updates it in place. Older versions are never rewritten; a
   history that disagrees with one is counted (history_conflicts) and left as it is.
5. Type 1: overwrite in place, on every version, where a value differs.
6. Inferred members created (US-6.5): a natural key staging references (a lease's or a
   payment's tenant) that is not a member yet becomes one: is_inferred TRUE, the attributes of the
   Unknown member (-1). Key -1 itself is only for a reference with no natural key at all.
Technical columns: source_system from staging ('INFERRED' for an inferred member); batch_id is the
pipeline run that loaded or last changed the row; loaded_at when.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from etl.dimensions import spec

FIRST = date.fromisoformat(spec.FIRST_DAY)


class DimensionError(Exception):
    """A dimension cannot be loaded as its source stands (named, with what to do)."""


@dataclass
class DimLoad:
    dim: str
    read: int = 0
    inserted: int = 0
    updated: int = 0  # rows changed in place by Type 1, all versions counted
    members_updated: int = 0  # natural keys with at least one row changed by Type 1
    versions: int = 0  # new SCD2 versions
    in_place: int = 0  # SCD2 changes dated the same day as the current version
    history_conflicts: int = 0  # members whose history disagrees with a stored version
    inferred_created: int = 0
    inferred_completed: int = 0
    unchanged: int = 0

    @property
    def written(self) -> int:  # rows inserted (members, versions, inferred)
        return self.inserted + self.versions + self.inferred_created

    @property
    def changed(self) -> int:  # rows updated in place
        return self.updated + self.in_place + self.versions + self.inferred_completed


def _nk_match(d: spec.Dim, left: str, right: str) -> str:
    return " AND ".join(f"{left}.{k} = {right}.{k}" for k in d.nk)


def _first_state(d: spec.Dim) -> str:
    """Per natural key, its oldest known Type 2 state (from the history)."""
    k = d.nk[0]
    return (f"SELECT DISTINCT ON (h.{k}) h.{k}, {', '.join('h.' + c for c in d.type2)} FROM _dim_hist h "
            f"ORDER BY h.{k}, h.change_date NULLS FIRST, h.seq")  # fmt: skip


def insert_sql(d: spec.Dim) -> str:
    cols = [*d.nk, *d.cols]
    use_history = d.scd2 and d.history
    values = [f"coalesce(h.{c}, s.{c})" if use_history and c in d.type2 else f"s.{c}" for c in cols]
    names = list(cols)
    if d.inferred:
        names.append("is_inferred")
        values.append("FALSE")
    if d.scd2:
        names += ["effective_from", "effective_to", "is_current"]
        values += [f"DATE '{spec.FIRST_DAY}'", f"DATE '{spec.OPEN_END}'", "TRUE"]
    names += ["source_system", "batch_id", "loaded_at"]
    values += ["s.source_system", "%(run)s", "%(now)s"]
    join = f" LEFT JOIN ({_first_state(d)}) h ON h.{d.nk[0]} = s.{d.nk[0]}" if use_history else ""
    return (f"INSERT INTO lue_dw.{d.name} ({', '.join(names)}) SELECT {', '.join(values)} "
            f"FROM _dim_src s{join} WHERE NOT EXISTS (SELECT 1 FROM lue_dw.{d.name} x WHERE "
            f"{_nk_match(d, 'x', 's')}) ORDER BY {', '.join('s.' + k for k in d.nk)}")  # fmt: skip


def complete_inferred_sql(d: spec.Dim) -> str | None:
    if not d.inferred:
        return None
    use_history = d.scd2 and d.history
    sets = [f"{c} = coalesce(h.{c}, s.{c})" if use_history and c in d.type2 else f"{c} = s.{c}" for c in d.cols]
    sets += ["is_inferred = FALSE", "source_system = s.source_system", "batch_id = %(run)s", "loaded_at = %(now)s"]
    join = f" LEFT JOIN ({_first_state(d)}) h ON h.{d.nk[0]} = s.{d.nk[0]}" if use_history else ""
    return (f"UPDATE lue_dw.{d.name} x SET {', '.join(sets)} FROM _dim_src s{join} WHERE "
            f"{_nk_match(d, 'x', 's')} AND x.is_inferred AND x.{d.key} > 0 "
            f"RETURNING {', '.join('x.' + k for k in d.nk)}")  # fmt: skip


def type1_sql(d: spec.Dim) -> str | None:
    if not d.type1:
        return None
    sets = ", ".join(f"{c} = s.{c}" for c in d.type1)
    return (f"UPDATE lue_dw.{d.name} x SET {sets}, batch_id = %(run)s, loaded_at = %(now)s FROM "
            f"_dim_src s WHERE {_nk_match(d, 'x', 's')} AND x.{d.key} > 0 AND "
            f"({', '.join('x.' + c for c in d.type1)}) IS DISTINCT FROM "
            f"({', '.join('s.' + c for c in d.type1)}) "
            f"RETURNING {', '.join('x.' + k for k in d.nk)}")  # fmt: skip


def inferred_sql(d: spec.Dim) -> str | None:
    """New members for referenced natural keys with no member: the Unknown member's attributes."""
    if not d.inferred or not d.references:
        return None
    k = d.nk[0]
    names = [k, *d.cols, "is_inferred"]
    values = ["r.ref", *(f"u.{c}" for c in d.cols), "TRUE"]
    if d.scd2:
        names += ["effective_from", "effective_to", "is_current"]
        values += [f"DATE '{spec.FIRST_DAY}'", f"DATE '{spec.OPEN_END}'", "TRUE"]
    names += ["source_system", "batch_id", "loaded_at"]
    values += ["'INFERRED'", "%(run)s", "%(now)s"]
    return (f"INSERT INTO lue_dw.{d.name} ({', '.join(names)}) SELECT {', '.join(values)} FROM "
            f"(SELECT DISTINCT x.{k} AS ref FROM ({d.references}) x WHERE x.{k} IS NOT NULL) r "
            f"CROSS JOIN (SELECT * FROM lue_dw.{d.name} WHERE {d.key} = -1) u "
            f"WHERE NOT EXISTS (SELECT 1 FROM lue_dw.{d.name} m WHERE m.{k} = r.ref) ORDER BY r.ref")  # fmt: skip


# ----------------------------------------------------------------------------- SCD2 (US-6.2)
def desired_versions(states: list[tuple]) -> list[tuple]:
    """[(change_date or None, type2 tuple)] oldest first -> [(effective_from, type2 tuple)].

    The first version starts 1900-01-01; a new version only when the Type 2 values change; two
    states the same day: the later wins (and if it equals the version before, that day's version
    disappears). Pure Python, tested without a database.
    """
    out: list[list] = []
    for when, values in states:
        day = when or FIRST
        if not out:
            out.append([FIRST, values])
            continue
        if values == out[-1][1]:
            continue
        if day <= out[-1][0]:
            out[-1][1] = values  # same day (or an older date than the last version): last wins
            if len(out) >= 2 and out[-2][1] == values:
                out.pop()
            continue
        out.append([day, values])
    return [(a, b) for a, b in out]


def plan_versions(stored: list[tuple], desired: list[tuple]) -> tuple[list, tuple | None, bool]:
    """What to do for one member. stored: [(effective_from, type2)] oldest first (the last is current).

    Returns (new versions [(effective_from, type2)] to add after the current one, the type2 values
    to set in place on the current version or None, history conflict?).
    """
    current_from, current_values = stored[-1]
    conflict = False
    for frm, values in stored:  # each stored version must hold the state history gives for its date
        state = None
        for day, v in desired:
            if day <= frm:
                state = v
        if state is not None and state != values and frm != current_from:
            conflict = True
    at_current = None
    for day, v in desired:
        if day <= current_from:
            at_current = v
    in_place = at_current if at_current is not None and at_current != current_values else None
    new = [(day, v) for day, v in desired if day > current_from]
    if new and new[0][1] == (in_place or current_values):
        new = new[1:]
    return new, in_place, conflict


def apply_scd2(cur, d: spec.Dim, run_id: int, now: datetime, out: DimLoad) -> None:
    k, t2 = d.nk[0], d.type2
    cur.execute(f"SELECT h.{k}, h.change_date, {', '.join('h.' + c for c in t2)} FROM _dim_hist h "
                f"WHERE h.{k} IS NOT NULL ORDER BY h.{k}, h.change_date NULLS FIRST, h.seq")  # fmt: skip
    history: dict = {}
    for row in cur.fetchall():
        history.setdefault(row[0], []).append((row[1], tuple(row[2:])))
    inferred = "AND NOT is_inferred" if d.inferred else ""
    cur.execute(f"SELECT {d.key}, {k}, effective_from, {', '.join(t2)} FROM lue_dw.{d.name} WHERE "
                f"{d.key} > 0 {inferred} AND {k} IN (SELECT {k} FROM _dim_src) "
                f"ORDER BY {k}, effective_from")  # fmt: skip
    stored: dict = {}
    keys: dict = {}
    for key, nk, frm, *values in cur.fetchall():
        stored.setdefault(nk, []).append((frm, tuple(values)))
        keys[nk] = key  # the last (current) version's key
    others = [c for c in d.cols if c not in t2]
    copy_cols = [*d.nk, *others] + (["is_inferred"] if d.inferred else [])
    for nk, versions in stored.items():
        new, in_place, conflict = plan_versions(versions, desired_versions(history.get(nk, [])))
        out.history_conflicts += conflict
        if in_place is not None:
            cur.execute(f"UPDATE lue_dw.{d.name} SET {', '.join(c + ' = %s' for c in t2)}, batch_id = %s, "
                        f"loaded_at = %s WHERE {d.key} = %s", [*in_place, run_id, now, keys[nk]])  # fmt: skip
            out.in_place += 1
        for day, values in new:
            cur.execute(f"UPDATE lue_dw.{d.name} SET effective_to = %s, is_current = FALSE, batch_id = %s, "
                        f"loaded_at = %s WHERE {d.key} = %s", (day, run_id, now, keys[nk]))  # fmt: skip
            cur.execute(
                f"INSERT INTO lue_dw.{d.name} ({', '.join(copy_cols + t2)}, effective_from, effective_to, "
                f"is_current, source_system, batch_id, loaded_at) SELECT {', '.join(copy_cols)}, "
                f"{', '.join(['%s'] * len(t2))}, %s, DATE '{spec.OPEN_END}', TRUE, source_system, %s, %s "
                f"FROM lue_dw.{d.name} WHERE {d.key} = %s RETURNING {d.key}",
                [*values, day, run_id, now, keys[nk]],
            )  # fmt: skip
            keys[nk] = cur.fetchone()[0]
            out.versions += 1


# ----------------------------------------------------------------------------- the step
def load_dimension(cur, d: spec.Dim, run_id: int, now: datetime) -> DimLoad:
    out = DimLoad(d.name)
    cur.execute(f"CREATE TEMP TABLE _dim_src ON COMMIT DROP AS {d.source}")
    keys = ", ".join(d.nk)
    cur.execute(f"SELECT count(*), count(DISTINCT ({keys})), count(*) FILTER (WHERE "
                f"{' OR '.join(k + ' IS NULL' for k in d.nk)}) FROM _dim_src")  # fmt: skip
    out.read, distinct, null_keys = cur.fetchone()
    if null_keys:
        raise DimensionError(f"{d.name}: {null_keys} source rows without a natural key")
    if distinct != out.read:
        raise DimensionError(f"{d.name}: {out.read - distinct} natural keys appear twice in the "
                             "source; staging must give one row per key (US-5.1)")  # fmt: skip
    if d.scd2 and d.history:
        if len(d.nk) != 1:
            raise DimensionError(f"{d.name}: SCD2 needs a single-column natural key")
        cur.execute(f"CREATE TEMP TABLE _dim_hist ON COMMIT DROP AS {d.history}")
    params = {"run": run_id, "now": now}
    cur.execute(insert_sql(d), params)
    out.inserted = cur.rowcount
    sql = complete_inferred_sql(d)
    if sql:
        cur.execute(sql, params)
        out.inferred_completed = len(cur.fetchall())
    if d.scd2 and d.history:
        apply_scd2(cur, d, run_id, now, out)
    sql = type1_sql(d)
    if sql:
        cur.execute(sql, params)
        changed = cur.fetchall()
        out.updated = len(changed)
        out.members_updated = len(set(changed))
    sql = inferred_sql(d)
    if sql:
        cur.execute(sql, params)
        out.inferred_created = cur.rowcount
    touched = out.inserted + out.inferred_completed + out.members_updated
    out.unchanged = max(out.read - touched, 0)
    cur.execute("DROP TABLE _dim_src" + ("; DROP TABLE _dim_hist" if d.scd2 and d.history else ""))
    return out


def load_holidays(cur) -> int:
    """US-6.4: the calendar's holiday flags from the S2 register; returns the dates changed."""
    cur.execute(spec.HOLIDAYS)
    return cur.rowcount
