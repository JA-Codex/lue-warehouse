"""US-5.1 and US-5.3: load one staging table from bronze, incrementally.

For a table of etl/staging/spec.py, in one transaction (one step of the run):

1. The window: the bronze rows landed after the table's watermark (lue_audit.etl_watermark,
   source_system STG), from batches E4 has validated (lue_audit.dq_batch). The watermark is the
   loaded_at of the last rows read plus their batch (lue_audit.stg_load.batch_to), so a batch
   landed in the same second as the last one read is still read, and nothing is read twice.
2. Rows E4 rejected (lue_audit.dq_result, severity reject) and rows the table's own filter
   leaves out are counted as rejected; the rest are cleaned and typed by the spec's expressions.
   A row with a key column that is empty after cleaning is unusable (counted, not staged).
3. Survivorship (D15): per natural key the row with the latest source updated_at (where the
   source has one), then loaded_at, then batch_id, then row_id. The others are superseded.
4. Merge: INSERT ... ON CONFLICT (key) DO UPDATE, only when the incoming version is not older
   than the staged one and a value differs. RETURNING (xmax = 0) tells inserts from updates;
   the rest are unchanged.
5. The watermark and the stg_load row are written in the same transaction, so they move only
   when the whole step commits.

stg_ticket_status is driven by stg_ticket: it reloads the status history of the tickets this run
inserted or changed, from the copy that survived, and removes the entries that copy does not have.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from etl.staging import spec

EPOCH = datetime(1900, 1, 1)  # etl_watermark's default: nothing read yet


@dataclass
class Load:
    table: str
    read: int = 0
    rejected: int = 0
    duplicates: int = 0  # of the rejected: exact duplicates E4 removed (DQ-03)
    unusable: int = 0
    superseded: int = 0
    conflicts: int = 0  # of the superseded: copies whose values differ from the survivor's (D15)
    conflict_sample: str | None = None  # the key of one of them
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    watermark_from: datetime = EPOCH
    watermark_to: datetime = EPOCH
    batch_from: int = 0
    batch_to: int = 0

    @property
    def balanced(self) -> bool:
        return self.read == (self.rejected + self.unusable + self.superseded + self.inserted
                             + self.updated + self.unchanged)  # fmt: skip


def _one(cur, sql: str, params=None):
    cur.execute(sql, params)
    return cur.fetchone()


def watermark(cur, table: str) -> tuple[datetime, int]:
    """(loaded_at, batch) of the last rows read; (1900-01-01, 0) before the first load."""
    row = _one(cur, "SELECT last_watermark_value FROM lue_audit.etl_watermark WHERE "
                    "source_system = 'STG' AND table_name = %s", (table,))  # fmt: skip
    if row is None:
        return EPOCH, 0
    batch = _one(cur, "SELECT batch_to FROM lue_audit.stg_load WHERE stg_table = %s AND "
                      "watermark_to = %s ORDER BY run_id DESC LIMIT 1", (table, row[0]))  # fmt: skip
    # Without the batch (stg_load emptied by hand) the rows at the watermark are read again:
    # safe, the merge leaves them unchanged.
    return row[0], (batch[0] if batch else 0)


def _rejected(alias: str, bronze: str) -> str:
    return (f"EXISTS (SELECT 1 FROM lue_audit.dq_result r WHERE r.source_table = '{bronze}' "
            f"AND r.row_id = {alias}.row_id AND r.severity = 'reject')")  # fmt: skip


def _window(t: spec.Table, wm: datetime, wm_batch: int, run_id: int) -> tuple[str, dict]:
    """SQL creating _win (row_id, batch_id, loaded_at, excluded) for the table's window."""
    params = {"wm": wm, "wm_batch": wm_batch, "run": run_id}
    excluded = _rejected("b", t.bronze)
    if t.where:
        excluded = f"({excluded} OR NOT ({t.where}))"
    if t.name == "stg_ticket_status":
        # The status rows of the surviving copy of each ticket this run inserted or changed.
        scope = ("(b.loaded_at, b.source_file, b.source_row) IN (SELECT k.loaded_at, k.src_file, "
                 "k.src_row FROM lue_staging.stg_ticket k WHERE k.run_id = %(run)s)")  # fmt: skip
    else:
        scope = ("(b.loaded_at > %(wm)s OR (b.loaded_at = %(wm)s AND b.batch_id > %(wm_batch)s))"
                 " AND b.batch_id IN (SELECT d.batch_id FROM lue_audit.dq_batch d)")  # fmt: skip
    sql = (f"CREATE TEMP TABLE _win ON COMMIT DROP AS SELECT b.row_id, b.batch_id, b.loaded_at, "
           f"{excluded} AS excluded FROM lue_staging.{t.bronze} b WHERE {scope}")  # fmt: skip
    return sql, params


def _source_select(t: spec.Table) -> str:
    """The cleaned, typed rows of _win that are not excluded, with lineage and the rank."""
    cols = [f"{c.expr} AS {c.name}" for c in t.loaded]
    cols += [f"{c.expr} AS {c.name}" for c in t.extra_lineage]
    cols += ["b.source_system", "b.batch_id", "b.loaded_at", "b.row_id AS src_row_id",
             f"{t.updated or 'NULL::timestamp'} AS src_updated_at"]  # fmt: skip
    return (f"SELECT {', '.join(cols)} FROM lue_staging.{t.bronze} b JOIN _win w ON w.row_id = "
            f"b.row_id WHERE NOT w.excluded")  # fmt: skip


def _version(alias: str) -> str:
    return (f"(coalesce({alias}.src_updated_at, '-infinity'::timestamp), {alias}.loaded_at, "
            f"{alias}.batch_id, {alias}.src_row_id)")  # fmt: skip


def merge_sql(t: spec.Table) -> str:
    """INSERT ... ON CONFLICT DO UPDATE from _src (the ranked rows); RETURNING inserted?"""
    compared = [c.name for c in t.loaded] + [c.name for c in t.extra_lineage]
    lineage = ["source_system", "batch_id", "loaded_at", "src_row_id", "src_updated_at"]
    names = compared + lineage + ["run_id", "staged_at"]
    values = compared + lineage + ["%(run)s", "%(now)s"]
    sets = ", ".join(f"{n} = EXCLUDED.{n}" for n in compared + lineage + ["run_id", "staged_at"])
    keys = ", ".join(t.key)
    changed = (f"({', '.join('s.' + n for n in compared)}) IS DISTINCT FROM "
               f"({', '.join('EXCLUDED.' + n for n in compared)})")  # fmt: skip
    # Never replace a version with an older one. stg_ticket_status follows its ticket's copy,
    # which is decided by stg_ticket, so there the newer copy always wins.
    # A row staging derived itself (US-5.2: an allocation, no bronze row) gives way to the source.
    newer = ("" if t.name == "stg_ticket_status" else
             f"(s.src_row_id IS NULL OR {_version('EXCLUDED')} >= {_version('s')}) AND ")
    return (f"INSERT INTO lue_staging.{t.name} AS s ({', '.join(names)}) SELECT "
            f"{', '.join(values)} FROM _src WHERE rn = 1 "
            f"ON CONFLICT ({keys}) DO UPDATE SET {sets} WHERE {newer}{changed} "
            f"RETURNING (xmax = 0) AS inserted")  # fmt: skip


def load_table(cur, t: spec.Table, run_id: int, now: datetime) -> Load:
    wm, wm_batch = watermark(cur, t.name)
    out = Load(t.name, watermark_from=wm, watermark_to=wm, batch_from=wm_batch, batch_to=wm_batch)
    sql, params = _window(t, wm, wm_batch, run_id)
    params["now"] = now
    cur.execute(sql, params)
    out.read, out.rejected = _one(cur, "SELECT count(*), count(*) FILTER (WHERE excluded) FROM _win")
    out.duplicates = _one(cur, "SELECT count(*) FROM _win w WHERE EXISTS (SELECT 1 FROM "
                               "lue_audit.dq_result r WHERE r.source_table = %s AND r.row_id = "
                               "w.row_id AND r.severity = 'reject' AND r.check_name LIKE 'DQ-03%%')",
                          (t.bronze,))[0]  # fmt: skip
    keys_present = " AND ".join(f"{k} IS NOT NULL" for k in t.key)
    order = "src_updated_at DESC NULLS LAST, loaded_at DESC, batch_id DESC, src_row_id DESC"
    cur.execute(
        f"CREATE TEMP TABLE _src ON COMMIT DROP AS SELECT x.*, CASE WHEN {keys_present} THEN "
        f"row_number() OVER (PARTITION BY {', '.join(t.key)} ORDER BY {order}) END AS rn "
        f"FROM ({_source_select(t)}) x"
    )
    out.unusable, out.superseded = _one(cur, "SELECT count(*) FILTER (WHERE rn IS NULL), "
                                             "count(*) FILTER (WHERE rn > 1) FROM _src")  # fmt: skip
    values = [c.name for c in t.loaded] + [c.name for c in t.extra_lineage]
    on_key = " AND ".join(f"x.{k} = w.{k}" for k in t.key)
    out.conflicts, out.conflict_sample = _one(
        cur,
        f"SELECT count(*), min(concat_ws('|', {', '.join('x.' + k for k in t.key)})) FROM _src x "
        f"JOIN _src w ON {on_key} AND w.rn = 1 WHERE x.rn > 1 AND "
        f"({', '.join('x.' + c for c in values)}) IS DISTINCT FROM "
        f"({', '.join('w.' + c for c in values)})",
    )  # fmt: skip
    cur.execute(merge_sql(t), params)
    flags = [r[0] for r in cur.fetchall()]
    out.inserted = sum(flags)
    out.updated = len(flags) - out.inserted
    out.unchanged = out.read - out.rejected - out.unusable - out.superseded - len(flags)
    if t.name == "stg_ticket_status":
        # A ticket whose surviving copy changed: drop the entries the new copy does not have.
        cur.execute(
            "DELETE FROM lue_staging.stg_ticket_status s USING lue_staging.stg_ticket k WHERE "
            "k.ticket_id = s.ticket_id AND k.run_id = %(run)s AND NOT EXISTS (SELECT 1 FROM _src "
            "x WHERE x.rn = 1 AND x.ticket_id = s.ticket_id AND x.status_seq = s.status_seq)",
            params,
        )
        out.deleted = cur.rowcount
    else:
        top = _one(cur, "SELECT max(loaded_at) FROM _win")[0]
        if top is not None:
            out.watermark_to = top
            out.batch_to = _one(cur, "SELECT max(batch_id) FROM _win WHERE loaded_at = %s",
                                (top,))[0]  # fmt: skip
            cur.execute(
                "INSERT INTO lue_audit.etl_watermark (source_system, table_name, "
                "last_watermark_value, updated_at) VALUES ('STG', %s, %s, %s) ON CONFLICT "
                "(source_system, table_name) DO UPDATE SET last_watermark_value = "
                "EXCLUDED.last_watermark_value, updated_at = EXCLUDED.updated_at",
                (t.name, top, now),
            )
    cur.execute(
        "INSERT INTO lue_audit.stg_load (run_id, stg_table, bronze_rows_read, rows_rejected, "
        "rows_unusable, rows_superseded, rows_inserted, rows_updated, rows_unchanged, "
        "rows_deleted, watermark_from, watermark_to, batch_to) VALUES (%s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s, %s, %s)",
        (run_id, t.name, out.read, out.rejected, out.unusable, out.superseded, out.inserted,
         out.updated, out.unchanged, out.deleted, out.watermark_from, out.watermark_to,
         out.batch_to),
    )  # fmt: skip
    cur.execute("DROP TABLE _win; DROP TABLE _src")
    return out
