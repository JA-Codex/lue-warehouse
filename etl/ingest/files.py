"""US-3.3: the file sources S2 (Excel registers), S3 (bank settlement CSVs) and S6 (incentive CSVs).

Every file is landed as it is: every value as text (an empty cell stays an empty text, a missing
Excel cell is NULL), plus batch_id, source_system, loaded_at, the file name and the row's position
in the file (source_row, 1 = the first data row).

Checksum policy (decision D16), per file and target table:

* The file's SHA-256 is computed first. If lue_audit.file_load already has that checksum Loaded
  into the same target, the file is skipped and logged "Skipped, unchanged": nothing lands.
* A new file, or an edited one (new checksum), lands as a new batch. Bronze is appended to, never
  truncated: the earlier version's rows stay (staging picks the latest, E5).
* The column names are checked before anything lands. A file whose structure drifted (a renamed,
  missing or extra column) is rejected with a clear message, recorded as Rejected (that record
  survives a later rollback), and the step ends as Warning; the other files still load.
* lue_audit.file_load gets one row per file and target per attempt: file, checksum, rows, batch.

Reconciliation: for every target, the rows in today's files equal the rows bronze holds for the
batch that loaded each file's checksum (today or on an earlier run).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path

from etl.ingest.base import META_COLUMNS, ROOT, Step, copy_rows, kv, sha256_file

FILE_COLUMNS = ("source_file", "source_row")

# S2: sheet -> (bronze table, columns). The workbook is one file; each sheet is its own target.
S2_SHEETS = {
    "owners": ("brz_owner", ["owner_code", "owner_name", "owner_type"]),
    "ownership": ("brz_ownership",
                  ["building_code", "unit_no", "owner_code", "valid_from", "valid_to"]),
    "vendors": ("brz_vendor", ["vendor_code", "vendor_name", "trade", "rating", "phone",
                               "previous_rating", "rating_changed_on"]),
    "sla_policy": ("brz_sla_policy", ["subcategory_code", "subcategory_name", "category_name",
                                      "default_sla_hours", "valid_from"]),
    "holidays": ("brz_holiday",
                 ["holiday_date", "holiday_name", "is_public_holiday", "is_ramadan"]),
}  # fmt: skip
S3_COLUMNS = ["settlement_id", "payment_reference", "transaction_date", "settlement_date",
              "gross_amount", "fee_amount", "net_amount"]  # fmt: skip
S6_FILES = {
    "offers.csv": ("brz_incentive_offer",
                   ["offer_code", "offer_type", "description", "discount_pct", "rent_free_days"]),
    "incentive_log.csv": ("brz_incentive_log",
                          ["building_code", "unit_no", "offer_code", "start_date", "end_date"]),
}  # fmt: skip


# ----------------------------------------------------------------------------- shared
def relative_name(path: Path, data: Path) -> str:
    """The name recorded for a file: relative to the data folder (or the repository)."""
    for base in (data, ROOT):
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return path.name


def as_text(value) -> str | None:
    """A cell or JSON value as the text it shows: dates ISO, booleans true/false."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def drift(expected: Sequence[str], found: Sequence[str]) -> str:
    """'' when the columns match, else a readable account of what changed."""
    found = [str(c) if c is not None else "" for c in found]
    if list(found) == list(expected):
        return ""
    missing = [c for c in expected if c not in found]
    extra = [c for c in found if c not in expected]
    parts = []
    if missing:
        parts.append("missing " + ", ".join(repr(c) for c in missing))
    if extra:
        parts.append("unexpected " + ", ".join(repr(c) for c in extra))
    if not parts:
        parts.append("columns in a different order")
    return f"structure changed: {'; '.join(parts)} (expected {', '.join(expected)})"


class FileLoader:
    """The checksum policy and the file register, for one step."""

    def __init__(self, step: Step, data: Path):
        self.step = step
        self.data = data
        step.cur.execute(
            "SELECT checksum_sha256, target_table, min(file_name) FROM lue_audit.file_load "
            "WHERE status = 'Loaded' GROUP BY 1, 2"
        )
        self.loaded = {(c, t): f for c, t, f in step.cur.fetchall()}
        self.current: dict[str, list[tuple[str, str, int]]] = defaultdict(list)

    def register(self, name, checksum, target, rows, status, batch=None, message=None, audit=False):
        conn_cur = self.step.run.audit.cursor() if audit else self.step.cur
        try:
            conn_cur.execute(
                "INSERT INTO lue_audit.file_load (run_id, batch_id, source_system, file_name, "
                "checksum_sha256, target_table, rows_landed, status, message, loaded_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (self.step.run.run_id, batch, self.step.source_system, name[:200], checksum,
                 target, rows, status, (message or None) and message[:300], self.step.loaded_at),
            )  # fmt: skip
        finally:
            if audit:
                conn_cur.close()

    def load(self, path: Path, checksum: str, target: str, expected: Sequence[str],
             header: Sequence, rows: Callable[[], Iterable[Sequence]]) -> int:  # fmt: skip
        """Land one file into one target, unless unchanged or drifted. Returns rows landed."""
        name = relative_name(path, self.data)
        log = self.step.run.log
        problem = drift(expected, header)
        if problem:
            self.register(name, checksum, target, 0, "Rejected", message=problem, audit=True)
            self.step.reject()
            self.step.warn(f"{name} rejected before load: {problem}")
            return 0
        body = [tuple(as_text(v) for v in r) for r in rows()]
        self.step.read(len(body))
        self.current[target].append((name, checksum, len(body)))
        if (checksum, target) in self.loaded:
            reason = self.skip_reason(name, checksum, target)
            self.register(name, checksum, target, 0, "Skipped", message=reason)
            log.info(kv(step=self.step.result.step, file=name, target=target,
                        status="Skipped", reason=reason))  # fmt: skip
            return 0
        width = len(expected)
        for i, r in enumerate(body, start=1):
            if len(r) != width:
                raise ValueError(f"{name} row {i}: {len(r)} values, {width} columns expected")
        batch = self.step.new_batch()
        stamp = (batch, self.step.source_system, self.step.loaded_at.isoformat(sep=" "))
        n = copy_rows(
            self.step.cur,
            target,
            list(expected) + list(META_COLUMNS) + list(FILE_COLUMNS),
            (r + stamp + (name, i) for i, r in enumerate(body, start=1)),
        )
        self.step.result.rows_written += n
        self.register(name, checksum, target, n, "Loaded", batch=batch)
        self.loaded[(checksum, target)] = name
        return n

    def skip_reason(self, name: str, checksum: str, target: str) -> str:
        """D16 skips by checksum: the same file again, or another file with the same bytes (two
        empty settlement files, say: nothing would land either way)."""
        first = self.loaded[(checksum, target)]
        return "unchanged" if first == name else f"same content as {first}"

    def reconcile(self, target: str, check: str | None = None) -> None:
        """Rows in today's files = rows bronze holds for each file's loaded checksum."""
        files = self.current.get(target, [])
        cur = self.step.cur
        cur.execute(
            "SELECT DISTINCT ON (checksum_sha256) checksum_sha256, batch_id, file_name "
            "FROM lue_audit.file_load WHERE status = 'Loaded' AND target_table = %s "
            "ORDER BY checksum_sha256, file_load_id DESC",
            (target,),
        )
        loaded_as = {c: (b, f) for c, b, f in cur.fetchall()}
        cur.execute(
            f"SELECT batch_id, source_file, count(*) FROM lue_staging.{target} "
            "GROUP BY batch_id, source_file"
        )
        held = {(b, f): n for b, f, n in cur.fetchall()}
        source = sum(n for _f, _c, n in files)
        landed = sum(held.get(loaded_as.get(c, (None, None)), 0) for _f, c, _n in files)
        self.step.reconcile(check or f"{target} rows vs the files", source, landed)


def lineage(step: Step, target: str, source: str, system: str) -> None:
    step.lineage(f"lue_staging.{target}", source, f"{system} -> bronze",
                 "copied as text; batch_id, source_system, loaded_at, source_file and source_row "
                 "added; checksum policy D16")  # fmt: skip


def need(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing: run python etl/generate_data.py first")
    return path


# ----------------------------------------------------------------------------- S2
def ingest_s2(step: Step, data: Path) -> None:
    import openpyxl

    path = need(data / "s2" / "registers.xlsx")
    checksum = sha256_file(path)
    loader = FileLoader(step, data)
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet, (target, columns) in S2_SHEETS.items():
            if sheet not in book.sheetnames:
                header: list = [f"<no sheet {sheet!r}>"]
                rows: list = []
            else:
                every = [r for r in book[sheet].iter_rows(values_only=True)
                         if any(v is not None for v in r)]  # fmt: skip
                header = list(every[0]) if every else []
                rows = every[1:]
            loader.load(path, checksum, target, columns, header, lambda rows=rows: rows)
            loader.reconcile(target)
            lineage(step, target, f"S2 registers.xlsx sheet {sheet}", "S2")
    finally:
        book.close()


# ----------------------------------------------------------------------------- CSV (S3, S6)
def read_csv(path: Path) -> tuple[list[str], list[tuple]]:
    """pandas with every column as text: '' stays '', nothing is converted."""
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False,
                        encoding="utf-8")  # fmt: skip
    return list(frame.columns), list(frame.itertuples(index=False, name=None))


def ingest_s3(step: Step, data: Path) -> None:
    folder = data / "s3"
    files = sorted(folder.glob("settlement_*.csv")) if folder.is_dir() else []
    if not files:
        raise FileNotFoundError(f"no settlement files in {folder}: run etl/generate_data.py")
    loader = FileLoader(step, data)
    for path in files:
        header, rows = read_csv(path)
        loader.load(path, sha256_file(path), "brz_settlement", S3_COLUMNS, header,
                    lambda rows=rows: rows)  # fmt: skip
    loader.reconcile("brz_settlement")
    lineage(step, "brz_settlement", "S3 s3/settlement_<channel>_<date>.csv", "S3")


def ingest_s6(step: Step, data: Path) -> None:
    loader = FileLoader(step, data)
    for file_name, (target, columns) in S6_FILES.items():
        path = need(data / "s6" / file_name)
        header, rows = read_csv(path)
        loader.load(path, sha256_file(path), target, columns, header, lambda rows=rows: rows)
        loader.reconcile(target)
        lineage(step, target, f"S6 s6/{file_name}", "S6")
