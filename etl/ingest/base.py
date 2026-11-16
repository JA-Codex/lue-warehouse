"""US-3.1: the shared ingestion framework. Every source ingestor (US-3.2 to US-3.4) runs through it.

    run = Run()                                    # a run_id from lue_audit.seq_run_id
    run.step("ingest_s3", "S3", load_settlements)  # one source, one transaction, one run log row
    run.close()

What a step does:

1. Writes its row in lue_audit.etl_run_log (status Running) on a separate autocommit connection,
   so the log survives whatever happens to the data.
2. Calls the ingestor with a Step: it reads its source and lands rows with `step.land(...)`, which
   stamps every row with batch_id, source_system and loaded_at and bulk-loads it with COPY.
3. Commits the whole source at once, then marks the step Success (or Warning when a file was
   rejected). On any error it rolls the source back (no partial rows in bronze), marks the step
   Failed and logs the error; the next source still runs.

Logging is structured (key=value) to the console and to logs/ingest.log:
    step=ingest_s3 source=S3 status=Success rows_read=1234 rows_written=1234 rows_rejected=0

Connections come from .env (the same settings as scripts/db_setup.py), always as lue_etl: S1 is read
from lue_source, everything is written to lue_warehouse.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DB = "lue_source"
WAREHOUSE_DB = "lue_warehouse"
ETL_ROLE = "lue_etl"
LOG_FILE = ROOT / "logs" / "ingest.log"
BRONZE = "lue_staging"
META_COLUMNS = ("batch_id", "source_system", "loaded_at")
NULL = "\\N"  # how COPY is told a value is missing (an empty text stays an empty text)


class IngestError(Exception):
    """A problem the ingestor reports on purpose (bad structure, missing file)."""


# ----------------------------------------------------------------------------- settings
def settings() -> dict[str, str]:
    """Values from .env win over the shell's, as in scripts/db_setup.py."""
    values = dict(os.environ)
    env_path = ROOT / ".env"
    if env_path.is_file():
        try:
            from dotenv import dotenv_values
        except ImportError:
            raise IngestError("python-dotenv is missing: pip install -r requirements.txt") from None
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    return values


def connect(dbname: str, s: dict[str, str] | None = None):
    """A psycopg2 connection as lue_etl."""
    try:
        import psycopg2
    except ImportError:
        raise IngestError("psycopg2 is missing: pip install -r requirements.txt") from None
    s = s or settings()
    try:
        return psycopg2.connect(
            host=s.get("PGHOST", "localhost"),
            port=int(s.get("PGPORT", "5432")),
            user=ETL_ROLE,
            password=s.get("LUE_ETL_PASSWORD", ""),
            dbname=dbname,
            connect_timeout=10,
            application_name="lue_ingest",
        )
    except psycopg2.Error as exc:
        raise IngestError(
            f"cannot connect to {dbname} as {ETL_ROLE}: {str(exc).strip()}. Run "
            "python scripts/db_setup.py and python scripts/db_deploy.py first, and check .env."
        ) from None


# ----------------------------------------------------------------------------- logging
def get_logger() -> logging.Logger:
    log = logging.getLogger("lue.ingest")
    if not log.handlers:
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        log.addHandler(console)
        LOG_FILE.parent.mkdir(exist_ok=True)
        file = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file.setFormatter(fmt)
        log.addHandler(file)
        log.propagate = False
    return log


def kv(**fields) -> str:
    """step=ingest_s1 source=S1 rows_read=10 (values with spaces are quoted)."""
    out = []
    for k, v in fields.items():
        text = str(v)
        out.append(f'{k}="{text}"' if (" " in text or not text) else f"{k}={text}")
    return " ".join(out)


# ----------------------------------------------------------------------------- COPY
def copy_text(value) -> str:
    """One value for COPY ... (FORMAT csv, NULL '\\N'): always quoted, so '' stays ''."""
    if value is None:
        return NULL
    return '"' + str(value).replace('"', '""') + '"'


def copy_rows(cur, table: str, columns: Sequence[str], rows: Iterable[Sequence]) -> int:
    """Bulk-load rows (sequences of text or None) into BRONZE.table with COPY. Returns the count."""
    buffer = io.StringIO()
    n = 0
    width = len(columns)
    for row in rows:
        if len(row) != width:
            raise IngestError(f"{table}: a row has {len(row)} values, {width} columns expected")
        buffer.write(",".join(copy_text(v) for v in row))
        buffer.write("\n")
        n += 1
    if n:
        buffer.seek(0)
        cols = ", ".join(columns)
        cur.copy_expert(
            f"COPY {BRONZE}.{table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer
        )
    return n


def copy_dataframe(cur, table: str, frame, extra: dict | None = None) -> int:
    """The plan's "bulk-load a DataFrame using COPY": every column as text, NaN as NULL."""
    columns = list(frame.columns) + list(extra or {})
    tail = tuple((extra or {}).values())
    rows = (
        tuple(None if v != v else v for v in values) + tail  # v != v: NaN
        for values in frame.itertuples(index=False, name=None)
    )
    return copy_rows(cur, table, columns, rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ----------------------------------------------------------------------------- run and step
@dataclass
class StepResult:
    step: str
    source_system: str
    status: str = "Running"
    rows_read: int = 0
    rows_written: int = 0
    rows_updated: int = 0  # staging (US-5.3): rows changed in place; 0 for ingestion
    rows_rejected: int = 0
    message: str = ""
    seconds: float = 0.0
    rejects_warn: bool = True  # staging: rows E4 rejected are expected, not a reason for Warning
    warning: bool = False  # set by a step that finished but needs a look (status Warning)
    batches: list[int] = field(default_factory=list)


class Step:
    """What an ingestor gets: a cursor in the source's transaction and the landing helpers."""

    def __init__(self, run: Run, result: StepResult):
        self.run = run
        self.result = result
        self.cur = run.data.cursor()
        self.loaded_at = datetime.now().replace(microsecond=0)

    @property
    def source_system(self) -> str:
        return self.result.source_system

    def new_batch(self) -> int:
        batch = self.run.next_value("lue_audit.seq_batch_id")
        self.result.batches.append(batch)
        return batch

    def land(self, table: str, columns: Sequence[str], rows: Iterable[Sequence], batch: int,
             extra: dict | None = None) -> int:  # fmt: skip
        """Land rows as they are, plus the metadata columns and any extra ones (the file)."""
        stamp = (batch, self.source_system, self.loaded_at.isoformat(sep=" "))
        tail = tuple((extra or {}).values())
        n = copy_rows(
            self.cur,
            table,
            list(columns) + list(META_COLUMNS) + list(extra or {}),
            (tuple(r) + stamp + tail for r in rows),
        )
        self.result.rows_written += n
        return n

    def read(self, n: int) -> None:
        self.result.rows_read += n

    def reject(self, n: int = 1) -> None:
        self.result.rows_rejected += n

    def warn(self, text: str) -> None:
        self.result.message = (self.result.message + "; " if self.result.message else "") + text
        self.run.log.warning(kv(step=self.result.step, source=self.source_system, warning=text))

    def reconcile(self, check: str, source_value: int, warehouse_value: int) -> bool:
        """One row in lue_audit.reconciliation (inside the step's transaction)."""
        passed = source_value == warehouse_value
        self.cur.execute(
            "INSERT INTO lue_audit.reconciliation (run_id, check_name, source_value, "
            "warehouse_value, difference, passed) VALUES (%s, %s, %s, %s, %s, %s)",
            (self.run.run_id, check[:60], source_value, warehouse_value,
             warehouse_value - source_value, passed),
        )  # fmt: skip
        return passed

    def lineage(self, target: str, source: str, layer_path: str, transformation: str) -> None:
        """The pack's lineage table: one row per (target table, source table)."""
        self.cur.execute(
            "INSERT INTO lue_audit.lineage (target_table, source_table, layer_path, "
            "transformation) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (target_table, source_table) DO UPDATE SET "
            "layer_path = EXCLUDED.layer_path, transformation = EXCLUDED.transformation",
            (target, source, layer_path, transformation),
        )


class Run:
    """One pipeline run: a run_id, an audit connection (autocommit) and a data connection."""

    def __init__(self, s: dict[str, str] | None = None):
        self.settings = s or settings()
        self.log = get_logger()
        self.audit = connect(WAREHOUSE_DB, self.settings)
        self.audit.autocommit = True
        self.data = connect(WAREHOUSE_DB, self.settings)
        self.data.autocommit = False
        self.run_id = self.next_value("lue_audit.seq_run_id")
        self.results: list[StepResult] = []
        self.log.info(kv(event="run_start", run_id=self.run_id))

    def next_value(self, sequence: str) -> int:
        with self.audit.cursor() as cur:
            cur.execute("SELECT nextval(%s)", (sequence,))
            return int(cur.fetchone()[0])

    def source_connection(self):
        return connect(SOURCE_DB, self.settings)

    def _log_row(self, r: StepResult, started: datetime, ended: datetime | None) -> None:
        with self.audit.cursor() as cur:
            cur.execute(
                "INSERT INTO lue_audit.etl_run_log (run_id, step, started_at, ended_at, rows_read, "
                "rows_inserted, rows_updated, rows_rejected, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (run_id, step) DO UPDATE SET ended_at = EXCLUDED.ended_at, "
                "rows_read = EXCLUDED.rows_read, rows_inserted = EXCLUDED.rows_inserted, "
                "rows_updated = EXCLUDED.rows_updated, rows_rejected = EXCLUDED.rows_rejected, "
                "status = EXCLUDED.status",
                (self.run_id, r.step[:40], started, ended, r.rows_read, r.rows_written,
                 r.rows_updated, r.rows_rejected, r.status),
            )  # fmt: skip

    def step(self, name: str, source_system: str, ingest: Callable[[Step], None]) -> StepResult:
        result = StepResult(name, source_system)
        started = datetime.now().replace(microsecond=0)
        clock = time.monotonic()
        self._log_row(result, started, None)
        step = Step(self, result)
        try:
            ingest(step)
            self.data.commit()
            warn = result.warning or (result.rows_rejected and result.rejects_warn)
            result.status = "Warning" if warn else "Success"
        except Exception as exc:  # noqa: BLE001  any failure: roll the source back, log, go on
            self.data.rollback()
            result.status = "Failed"
            result.message = f"{type(exc).__name__}: {exc}".strip()[:300]
            result.rows_written = 0  # nothing of this source stayed in bronze
            result.rows_updated = 0
            self.log.error(kv(step=name, source=source_system, status="Failed",
                              error=result.message))  # fmt: skip
        finally:
            step.cur.close()
        result.seconds = time.monotonic() - clock
        self._log_row(result, started, datetime.now().replace(microsecond=0))
        self.log.info(
            kv(step=name, source=source_system, status=result.status, rows_read=result.rows_read,
               rows_written=result.rows_written, rows_rejected=result.rows_rejected,
               seconds=f"{result.seconds:.1f}")
        )  # fmt: skip
        self.results.append(result)
        return result

    def close(self) -> None:
        failed = sum(r.status == "Failed" for r in self.results)
        self.log.info(kv(event="run_end", run_id=self.run_id, steps=len(self.results),
                         failed=failed))  # fmt: skip
        for conn in (self.data, self.audit):
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
