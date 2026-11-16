"""US-3.2: the incremental S1 extract, src_pms (lue_source) into bronze (lue_warehouse).

For each source table: a server-side cursor on lue_source streams the rows (every value cast to
text, so bronze holds exactly what the source holds) in chunks into COPY on lue_warehouse, a
separate connection. Each row's MD5 (row_hash) is compared with the hashes bronze already has:
only rows that are new or changed land. So the first run lands everything, a second run lands
nothing, and changing one source row lands exactly that row (as a new version; bronze only
appends).

Why a row hash and not only the watermark: just two S1 tables have updated_at (units, tenants), and
a change can carry an updated_at older than the newest already loaded (the US-2.6 tenant changes
in s1/changes/ are dated inside the window). A watermark alone would miss those. The watermark is
still kept up to date (lue_audit.etl_watermark, decision O5) for the tables that have updated_at,
and it is only moved after a successful load.

Rows deleted in the source stay in bronze (bronze is append-only); nothing in S1 is deleted.
"""

from __future__ import annotations

import hashlib

from etl.ingest.base import META_COLUMNS, Step, copy_rows

# src_pms table -> bronze table. charge_types and payment_methods are not extracted: their
# dimensions are loaded from etl/reference_data.py (US-1.4), so bronze copies would go unused.
TABLES = {
    "buildings": "brz_building",
    "units": "brz_unit",
    "tenants": "brz_tenant",
    "leases": "brz_lease",
    "lease_events": "brz_lease_event",
    "invoices": "brz_invoice",
    "invoice_lines": "brz_invoice_line",
    "payments": "brz_payment",
    "payment_allocations": "brz_payment_allocation",
}
CHUNK = 10_000
SEPARATOR = "\x1f"  # between values in the hashed text; never in the data


def row_hash(values) -> str:
    text = SEPARATOR.join("\\N" if v is None else v for v in values)
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def source_columns(src_cur, table: str) -> list[str]:
    src_cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'src_pms' "
        "AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in src_cur.fetchall()]


def bronze_columns(cur, table: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'lue_staging' "
        "AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def ingest_s1(step: Step, tables: dict[str, str] | None = None) -> None:
    tables = tables or TABLES
    src = step.run.source_connection()
    try:
        src.set_session(readonly=True)
        with src.cursor() as meta:
            for table, target in tables.items():
                extract_table(step, src, meta, table, target)
    finally:
        src.close()


def extract_table(step: Step, src, meta, table: str, target: str) -> None:
    columns = source_columns(meta, table)
    if not columns:
        raise RuntimeError(f"src_pms.{table} does not exist: run python scripts/db_load_source.py")
    expected = [c for c in bronze_columns(step.cur, target) if c not in
                ("batch_id", "source_system", "loaded_at", "row_hash", "row_id")]  # fmt: skip
    if columns != expected:
        raise RuntimeError(f"src_pms.{table} columns {columns} do not match {target} {expected}")

    step.cur.execute(f"SELECT row_hash FROM lue_staging.{target}")
    known = {r[0] for r in step.cur.fetchall()}
    batch = step.new_batch()
    select = ", ".join(f"{c}::text" for c in columns)
    order = ", ".join(columns[:1])
    has_updated = "updated_at" in columns
    newest = None
    read = landed = 0
    with src.cursor(name=f"lue_extract_{table}") as cur:  # server-side: streams, never all at once
        cur.itersize = CHUNK
        cur.execute(f"SELECT {select} FROM src_pms.{table} ORDER BY {order}")
        while True:
            chunk = cur.fetchmany(CHUNK)
            if not chunk:
                break
            read += len(chunk)
            fresh = []
            for values in chunk:
                h = row_hash(values)
                if h not in known:
                    known.add(h)
                    fresh.append((*values, h))
                if has_updated:
                    stamp = values[columns.index("updated_at")]
                    if stamp is not None and (newest is None or stamp > newest):
                        newest = stamp  # ISO text compares like the timestamp it is
            landed += _land(step, target, columns, fresh, batch)
    step.read(read)
    step.run.log.info(f"step={step.result.step} table=src_pms.{table} target={target} "
                      f"rows_read={read} rows_written={landed} batch_id={batch}")  # fmt: skip

    # Completeness: every row the source has now is in bronze (by its hash).
    step.reconcile(f"{target} rows vs src_pms.{table}", read, read - missing(
        step, src, table, target, columns))  # fmt: skip
    if has_updated and newest is not None:
        step.cur.execute(
            "INSERT INTO lue_audit.etl_watermark (source_system, table_name, last_watermark_value,"
            " updated_at) VALUES ('S1', %s, %s, now()) ON CONFLICT (source_system, table_name) DO "
            "UPDATE SET last_watermark_value = GREATEST(lue_audit.etl_watermark."
            "last_watermark_value, EXCLUDED.last_watermark_value), updated_at = now()",
            (f"src_pms.{table}", newest),
        )
    step.lineage(f"lue_staging.{target}", f"src_pms.{table}", "S1 -> bronze",
                 "copied as text; batch_id, source_system, loaded_at and row_hash added; new or "
                 "changed rows only (row hash)")  # fmt: skip


def _land(step: Step, target: str, columns: list[str], fresh: list, batch: int) -> int:
    """Land (values..., hash) tuples: the hash goes after the three metadata columns."""
    if not fresh:
        return 0
    stamp = (batch, step.source_system, step.loaded_at.isoformat(sep=" "))
    n = copy_rows(
        step.cur,
        target,
        list(columns) + list(META_COLUMNS) + ["row_hash"],
        (tuple(r[:-1]) + stamp + (r[-1],) for r in fresh),
    )
    step.result.rows_written += n
    return n


def missing(step: Step, src, table: str, target: str, columns: list[str]) -> int:
    """Source rows whose hash is not in bronze (0 after a good load)."""
    step.cur.execute(f"SELECT row_hash FROM lue_staging.{target}")
    have = {r[0] for r in step.cur.fetchall()}
    select = ", ".join(f"{c}::text" for c in columns)
    gone = 0
    with src.cursor(name=f"lue_check_{table}") as cur:
        cur.itersize = CHUNK
        cur.execute(f"SELECT {select} FROM src_pms.{table}")
        for values in cur:
            if row_hash(values) not in have:
                gone += 1
    return gone
