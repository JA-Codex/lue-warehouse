#!/usr/bin/env python3
"""Run the analytical SQL pack query by query (E11): python scripts/run_analytics.py

    python scripts/run_analytics.py                        both files, a sample of each result
    python scripts/run_analytics.py --rows 40 --out f.txt  more rows, written to a file
    python scripts/run_analytics.py --only Q1,O3           some queries

Reads sql/60_analytics/analytical.sql and olap.sql, finds each query and its header (the label line
"-- Q1  ...", "-- W1 ...", "-- O1 ..." and the Grain/Tables/Definition lines), and runs it in a
read-only transaction as lue_etl: its rows, the time it took and the first rows. The files also run
as they are in psql (psql -f); this runner is for the evidence and the tests (scripts/test_analytics.py).
Exit 1 when a query fails.
"""

# ruff: noqa: E501  (the result tables: long lines read better)

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FILES = [ROOT / "sql" / "60_analytics" / "analytical.sql", ROOT / "sql" / "60_analytics" / "olap.sql"]
LABEL = re.compile(r"^-- ([QWO]\d+[a-z]?)\s+(.*)$", re.M)


@dataclass
class Query:
    label: str
    title: str
    header: dict[str, str]
    sql: str
    file: str
    rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    seconds: float = 0.0
    error: str = ""


def queries(path: Path) -> list[Query]:
    """Every statement of the file with the header comment just before it."""
    from pglast import parse_sql

    text = path.read_text(encoding="utf-8")
    raw = text.encode("utf-8")  # pglast locations are byte offsets
    out, last = [], 0
    for stmt in parse_sql(text):
        start = stmt.stmt_location
        end = start + (stmt.stmt_len or len(raw) - start)
        before = raw[last:start].decode("utf-8")
        sql = raw[start:end].decode("utf-8").strip()
        last = end
        labels = list(LABEL.finditer(before))
        if not labels:
            raise ValueError(f"{path.name}: a statement without a header label: {sql[:60]}")
        m = labels[-1]
        header, key = {}, None
        for line in before[m.end():].splitlines():
            h = re.match(r"^-- (Grain|Tables|Definition):\s*(.*)$", line)
            c = re.match(r"^--\s{2,}(\S.*)$", line)
            if h:
                key = h.group(1)
                header[key] = h.group(2).strip()
            elif c and key:
                header[key] += " " + c.group(1).strip()
        out.append(Query(m.group(1), m.group(2).strip(), header, sql, path.name))
    return out


def all_queries() -> list[Query]:
    return [q for f in FILES for q in queries(f)]


def run(cur, q: Query) -> Query:
    """Run one query read-only; keep every row."""
    started = time.perf_counter()
    try:
        cur.execute("BEGIN READ ONLY")
        cur.execute(q.sql)
        q.columns = [d[0] for d in cur.description]
        q.rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001  (any database error is the query's result)
        q.error = str(exc).strip().splitlines()[0]
    finally:
        cur.execute("ROLLBACK")
        q.seconds = time.perf_counter() - started
    return q


def table(columns: list, rows: list) -> str:
    cells = [[("" if v is None else str(v)) for v in r] for r in rows]
    width = [max(len(str(h)), *(len(r[i]) for r in cells)) if cells else len(str(h)) for i, h in enumerate(columns)]
    lines = ["  ".join(str(h).ljust(width[i]) for i, h in enumerate(columns)).rstrip(),
             "  ".join("-" * w for w in width)]
    lines += ["  ".join(v.ljust(width[i]) for i, v in enumerate(r)).rstrip() for r in cells]
    return "\n".join(lines)


def report(q: Query, rows: int) -> str:
    head = [f"{'=' * 100}", f"{q.label}  {q.title}", f"{'=' * 100}"]
    head += [f"{k}: {v}" for k, v in q.header.items()]
    if q.error:
        return "\n".join([*head, "", f"ERROR: {q.error}", ""])
    shown = q.rows[:rows]
    note = f"{len(q.rows):,} rows in {q.seconds:.2f} s" + (f"; the first {len(shown)}" if len(q.rows) > len(shown) else "")
    return "\n".join([*head, "", note, "", table(q.columns, shown), ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rows", type=int, default=12, help="rows shown per query (default 12)")
    ap.add_argument("--only", help="labels to run, comma separated (Q1,Q4a,O3)")
    ap.add_argument("--out", type=Path, help="write the report to this file too")
    args = ap.parse_args(argv)
    from etl.ingest.base import IngestError, connect

    try:
        conn = connect("lue_warehouse")
    except IngestError as exc:
        print(f"[FAIL] {exc}")
        return 2
    conn.autocommit = True
    wanted = {x.strip() for x in args.only.split(",")} if args.only else None
    done = []
    try:
        with conn.cursor() as cur:
            for q in all_queries():
                if wanted is None or q.label in wanted:
                    done.append(run(cur, q))
    finally:
        conn.close()
    text = "\n".join(report(q, args.rows) for q in done)
    summary = [f"{'=' * 100}", " Summary", f"{'=' * 100}"]
    summary += [f"  {q.label:5} {q.file:15} {'ERROR' if q.error else f'{len(q.rows):>7,} rows'} {q.seconds:>7.2f} s  {q.title[:70]}" for q in done]
    failed = [q for q in done if q.error]
    summary.append(f" RESULT: {len(done) - len(failed)}/{len(done)} queries ran" + (" - FAILED" if failed else ""))
    text += "\n" + "\n".join(summary) + "\n"
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
