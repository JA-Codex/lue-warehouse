"""US-6.1: the one loader every dimension goes through, one transaction per dimension.

1. Read the dimension's source (one row per natural key from staging). A natural key twice in the
   source is refused: the step fails and nothing changes.
2. New members: INSERT the rows whose natural key is not yet in the dimension. The identity
   column assigns the surrogate key (D6), so a key is never chosen by hand, never reused (an
   identity does not go back) and the special members -1 and -2 are never touched. An SCD2
   dimension's first version runs from 1900-01-01 to 9999-12-31, current.
3. Type 1: UPDATE the type 1 columns in place where a value differs, on every version of the
   member (a correction applies to all history). Type 2 columns are left to the SCD2 step
   (US-6.2, US-6.3).
4. Counts: rows read, members inserted, rows updated, unchanged (read - inserted - members
   updated); the run log gets read, inserted and updated.
Technical columns: source_system from staging; batch_id is the pipeline run that loaded or last
changed the row (data dictionary); loaded_at is when.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from etl.dimensions import spec


class DimensionError(Exception):
    """A dimension cannot be loaded as its source stands (named, with what to do)."""


@dataclass
class DimLoad:
    dim: str
    read: int = 0
    inserted: int = 0
    updated: int = 0  # rows changed in place (Type 1), all versions counted
    members_updated: int = 0  # natural keys with at least one row changed
    unchanged: int = 0


def _nk_match(d: spec.Dim, left: str, right: str) -> str:
    return " AND ".join(f"{left}.{k} = {right}.{k}" for k in d.nk)


def insert_sql(d: spec.Dim) -> str:
    cols = [*d.nk, *d.cols]
    names = [*cols]
    values = [f"s.{c}" for c in cols]
    if d.inferred:
        names.append("is_inferred")
        values.append("FALSE")
    if d.scd2:
        names += ["effective_from", "effective_to", "is_current"]
        values += [f"DATE '{spec.FIRST_DAY}'", f"DATE '{spec.OPEN_END}'", "TRUE"]
    names += ["source_system", "batch_id", "loaded_at"]
    values += ["s.source_system", "%(run)s", "%(now)s"]
    return (f"INSERT INTO lue_dw.{d.name} ({', '.join(names)}) SELECT {', '.join(values)} "
            f"FROM _dim_src s WHERE NOT EXISTS (SELECT 1 FROM lue_dw.{d.name} x WHERE "
            f"{_nk_match(d, 'x', 's')}) ORDER BY {', '.join('s.' + k for k in d.nk)}")  # fmt: skip


def type1_sql(d: spec.Dim) -> str | None:
    if not d.type1:
        return None
    sets = ", ".join(f"{c} = s.{c}" for c in d.type1)
    return (f"UPDATE lue_dw.{d.name} x SET {sets}, batch_id = %(run)s, loaded_at = %(now)s FROM "
            f"_dim_src s WHERE {_nk_match(d, 'x', 's')} AND x.{d.key} > 0 AND "
            f"({', '.join('x.' + c for c in d.type1)}) IS DISTINCT FROM "
            f"({', '.join('s.' + c for c in d.type1)}) "
            f"RETURNING {', '.join('x.' + k for k in d.nk)}")  # fmt: skip


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
    params = {"run": run_id, "now": now}
    cur.execute(insert_sql(d), params)
    out.inserted = cur.rowcount
    sql = type1_sql(d)
    if sql:
        cur.execute(sql, params)
        changed = cur.fetchall()
        out.updated = len(changed)
        out.members_updated = len(set(changed))
    out.unchanged = out.read - out.inserted - out.members_updated
    cur.execute("DROP TABLE _dim_src")
    return out
