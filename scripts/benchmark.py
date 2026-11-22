#!/usr/bin/env python3
"""The benchmark harness (E12, US-12.1 and US-12.2): python scripts/benchmark.py

    python scripts/benchmark.py                   baseline and after, interleaved; results in data/benchmark/
    python scripts/benchmark.py --out DIR         results elsewhere (docs/evidence/us-12.2 for the record)
    python scripts/benchmark.py --runs 9 --keep   more rounds; keep the candidate indexes afterwards

One command:
  1. The baseline (D20): only primary-key and unique-constraint indexes (sql/70_performance/03_drop_indexes.sql),
     and an unpartitioned copy of the occupancy fact, lue_dw.bench_occupancy_unpartitioned (the same rows and
     primary key), for the partitioning comparison. VACUUM ANALYZE. A warm-up run of every query.
  2. --runs rounds (default 7), each: the candidate indexes dropped, every query measured once (the baseline);
     then the indexes created (sql/70_performance/02_indexes.sql, each build timed), every query measured once
     (after). Interleaving the two states puts any slowdown of the machine on both sides alike, so the
     medians compare the plans, not the moment. A measurement is the fastest of 3 back-to-back
     EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) runs (interference only ever adds time), recording:
     execution and planning time, total plan cost, the scans (sequential, index, bitmap; partitions read),
     the indexes used, buffers.
  3. The load cost of each fact, in 3 interleaved rounds: one slice deleted and re-inserted, rolled back,
     timed without and with its index.
  4. Back to the baseline: the copy is always dropped; the indexes too, unless --keep.
The workload: Q1 and Q7 exactly as in sql/60_analytics/analytical.sql (B1, B3), and B2, B4, B5, B6 from
sql/70_performance/01_benchmark_queries.sql. JIT and parallel workers are off in the session: JIT's compile
time and the workers' start-up vary from run to run and are unrelated to indexes, so serial plans compare the
access paths themselves. Results: baseline.csv and after.csv (every measurement), summary.csv (each query
before and after, with the verdict), indexes.csv (size, build time, load cost, the queries that use it),
run.json (the settings, the baseline's indexes, the table sizes), plans/ (text plans).
A query is improved when every run after is faster than every run before (no overlap: no noise explains
that), its median time falls by at least 20 percent and 1 ms, and its plan cost falls. The runs are stable
when their interquartile range (the middle half) is within 60 percent of the median or 2 ms: a shared cloud
machine switches CPU speed, so a query of a few milliseconds can take twice as long from one run to the next;
the no-overlap rule keeps the verdicts independent of that.
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_analytics as ra  # noqa: E402

PERF = ROOT / "sql" / "70_performance"
COPY = "lue_dw.bench_occupancy_unpartitioned"
OCC = "lue_dw.fact_unit_occupancy_daily"
TOLERANCE, TOLERANCE_MS, GAIN, GAIN_MS = 0.60, 2.0, 0.20, 1.0
# the facts whose load cost is measured: (table, the slice deleted and re-inserted)
LOADS = {
    "lue_dw.fact_rent_invoice_line": "TRUE",
    "lue_dw.fact_payment": "TRUE",
    OCC: "snapshot_date_key BETWEEN 20260601 AND 20260630",
}
VACUUM = ["lue_dw.fact_rent_invoice_line", "lue_dw.fact_payment", OCC, "lue_dw.dim_unit", "lue_dw.dim_tenant",
          "lue_dw.dim_date"]  # fmt: skip


@dataclass
class Work:
    label: str
    title: str
    sql: str
    change: str
    source: str
    partitioning: bool = False  # before: the unpartitioned copy; after: the partitioned fact


def workload() -> list[Work]:
    analytical = {q.label: q for q in ra.queries(ROOT / "sql" / "60_analytics" / "analytical.sql")}
    bench = {q.label: q for q in ra.queries(PERF / "01_benchmark_queries.sql")}
    out = [Work("B1", f"Q1 {analytical['Q1'].title} (the whole window)", analytical["Q1"].sql,
                "indexes ix_invoice_line_due_unit and ix_payment_due_unit, (due_date_key, unit_key): the control, it reads every row", "analytical.sql Q1"),
           Work("B3", f"Q7 {analytical['Q7'].title}", analytical["Q7"].sql,
                "index ix_occupancy_unit_date, (unit_key, snapshot_date_key)", "analytical.sql Q7")]
    for label in ("B2", "B4", "B5", "B6"):
        q = bench[label]
        out.append(Work(label, q.title, q.sql, q.header["Change"], f"01_benchmark_queries.sql {label}", "Baseline" in q.header))
    return sorted(out, key=lambda w: w.label)


def statements(path: Path) -> list[str]:
    from pglast import parse_sql

    text = path.read_text(encoding="utf-8")
    raw = text.encode("utf-8")
    return [raw[s.stmt_location:s.stmt_location + (s.stmt_len or len(raw) - s.stmt_location)].decode("utf-8").strip()
            for s in parse_sql(text)]  # fmt: skip


def walk(node: dict, out: list[dict]) -> list[dict]:
    """Every node of the plan's main work. InitPlans and SubPlans are left out: they are side lookups run once
    (the data window's first and last day, the unit to drill into), not the scans that answer the query."""
    out.append(node)
    for child in node.get("Plans", []):
        if child.get("Parent Relationship") not in ("InitPlan", "SubPlan"):
            walk(child, out)
    return out


PART = re.compile(r"^fact_unit_occupancy_daily_(\d{4}_\d{2}|default)$")


def normalise(name: str) -> tuple[str, str]:
    """A relation or index name with an occupancy partition folded into its parent: (name, partition).
    PostgreSQL names a partition's index itself and shortens long names (fact_unit_occupancy_daily_2025_1_
    unit_key_snapshot_date_key_idx is the 2025_10 partition's), so indexes are matched by what they index."""
    m = PART.match(name)
    if m:
        return "fact_unit_occupancy_daily", m.group(1)
    if name.startswith("fact_unit_occupancy_daily_") and "unit_key_snapshot" in name:
        return "ix_occupancy_unit_date", ""
    if name.startswith("fact_unit_occupancy_daily_") and name.endswith("_pkey"):
        return "fact_unit_occupancy_daily_pkey", ""
    return name, ""


def describe(plan: dict) -> tuple[str, int, list[str]]:
    """The plan's scans of the facts, the copy and dim_tenant (node type and relation or index), how many
    occupancy partitions it read, and the indexes it used."""
    scans: dict[str, int] = {}
    parts, indexes = set(), set()
    for n in walk(plan, []):
        kind = n.get("Node Type", "")
        if "Scan" not in kind:
            continue
        rel, rpart = normalise(n.get("Relation Name", ""))
        idx, ipart = normalise(n.get("Index Name", ""))
        if not any(x.startswith(("fact_", "bench_", "dim_tenant", "ix_")) for x in (rel, idx)):
            continue
        parts |= {x for x in (rpart, ipart) if x}
        if idx:
            indexes.add(idx)
        key = f"{kind} {idx}" if kind in ("Index Scan", "Index Only Scan", "Bitmap Index Scan") else f"{kind} {rel}"
        scans[key] = scans.get(key, 0) + 1
    text = "; ".join(k + (f" x{v}" if v > 1 else "") for k, v in sorted(scans.items()))
    return text, len(parts), sorted(indexes)


def variants(w: Work, state: str) -> list[str]:
    """What a query is measured on: B4 (partitioning) on the copy and the partitioned fact at the baseline."""
    if w.partitioning:
        return ["unpartitioned copy", "partitioned"] if state == "baseline" else ["partitioned"]
    return ["as deployed"]


def sql_for(w: Work, variant: str) -> str:
    return w.sql.replace(OCC, COPY) if variant == "unpartitioned copy" else w.sql


REPEAT = 3  # back-to-back runs per measurement; the fastest is kept (interference only ever adds time)


def measure(cur, w: Work, phase: str, variant: str, run: int) -> dict:
    """The fastest of REPEAT back-to-back EXPLAIN (ANALYZE, BUFFERS) runs of the query, as a row."""
    docs = []
    for _ in range(REPEAT):
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql_for(w, variant)}")
        d = cur.fetchone()[0]
        docs.append(d[0] if isinstance(d, list) else json.loads(d)[0])
    doc = min(docs, key=lambda d: d["Execution Time"])
    plan = doc["Plan"]
    scans, parts, indexes = describe(plan)
    return {"phase": phase, "query": w.label, "variant": variant, "run": run,
            "execution_ms": round(doc["Execution Time"], 3), "planning_ms": round(doc["Planning Time"], 3),
            "total_cost": round(plan["Total Cost"], 2), "plan_rows": plan.get("Plan Rows"), "actual_rows": plan.get("Actual Rows"),
            "scans": scans, "occupancy_partitions_read": parts, "indexes_used": " ".join(indexes),
            "shared_hit_blocks": plan.get("Shared Hit Blocks", 0), "shared_read_blocks": plan.get("Shared Read Blocks", 0)}  # fmt: skip


def save_plan(cur, w: Work, phase: str, variant: str, plans: Path) -> None:
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql_for(w, variant)}")
    (plans / f"{w.label}_{phase}_{variant.replace(' ', '_')}.txt").write_text(
        f"-- {w.label} {w.title}\n-- {phase}, {variant}\n" + "\n".join(r[0] for r in cur.fetchall()) + "\n", encoding="utf-8")


def reload_ms(conn, table: str, where: str) -> float:
    """ms to re-insert a fact's slice (deleted first), in a transaction rolled back."""
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TEMP TABLE _keep ON COMMIT DROP AS SELECT * FROM {table} WHERE {where}")
            cur.execute(f"DELETE FROM {table} WHERE {where}")
            started = time.perf_counter()
            cur.execute(f"INSERT INTO {table} SELECT * FROM _keep")
            return (time.perf_counter() - started) * 1000
    finally:
        conn.rollback()
        conn.autocommit = True


def index_size(cur, name: str) -> int:
    """Bytes of an index; a partitioned index is the sum of its partitions' indexes (pg_partition_tree lists
    nothing for an ordinary index, so that one is sized directly)."""
    cur.execute("SELECT coalesce((SELECT sum(pg_relation_size(relid)) FROM pg_partition_tree(%s::regclass)), "
                "pg_relation_size(%s::regclass))", (f"lue_dw.{name}", f"lue_dw.{name}"))  # fmt: skip
    return int(cur.fetchone()[0])


def vacuum(cur, extra: list[str]) -> None:
    for t in VACUUM + extra:
        cur.execute(f"VACUUM ANALYZE {t}")


def iqr(times: list[float]) -> float:
    """The interquartile range: the spread of the middle half of the runs (robust to a slow outlier)."""
    if len(times) < 4:
        return max(times) - min(times)
    q1, _q2, q3 = statistics.quantiles(times, n=4, method="inclusive")
    return q3 - q1


def stable(times: list[float]) -> bool:
    """The middle half of the runs lies within the tolerance: 25 percent of the median, or 2 ms."""
    spread = iqr(times)
    return spread <= TOLERANCE * statistics.median(times) or spread <= TOLERANCE_MS


def summarise(rows: list[dict], works: list[Work]) -> list[dict]:
    def pick(phase, label, variant):
        return [r for r in rows if r["phase"] == phase and r["query"] == label and r["variant"] == variant]

    out = []
    for w in works:
        if w.partitioning:  # the partitioning alone: the copy and the partitioned fact, both without the candidate indexes
            before, after = pick("baseline", w.label, "unpartitioned copy"), pick("baseline", w.label, "partitioned")
        else:
            before, after = pick("baseline", w.label, "as deployed"), pick("after", w.label, "as deployed")
        tb, ta = [r["execution_ms"] for r in before], [r["execution_ms"] for r in after]
        mb, ma = statistics.median(tb), statistics.median(ta)
        cb, ca = before[0]["total_cost"], after[0]["total_cost"]
        apart = max(ta) < min(tb)  # the slowest run after is faster than the fastest before: no noise explains that
        improved = apart and ma <= (1 - GAIN) * mb and mb - ma >= GAIN_MS and ca < cb
        out.append({"query": w.label, "title": w.title, "source": w.source, "change": w.change,
                    "before_variant": before[0]["variant"] if w.partitioning else "baseline (D20)",
                    "after_variant": after[0]["variant"] if w.partitioning else "with the candidate indexes",
                    "before_ms": round(mb, 3), "after_ms": round(ma, 3), "speedup": round(mb / ma, 2) if ma else None,
                    "before_cost": cb, "after_cost": ca,
                    "before_plan": before[0]["scans"], "after_plan": after[0]["scans"],
                    "before_partitions": before[0]["occupancy_partitions_read"], "after_partitions": after[0]["occupancy_partitions_read"],
                    "after_indexes_used": after[0]["indexes_used"],
                    "same_plan_every_run": len({r["scans"] for r in before}) == 1 and len({r["scans"] for r in after}) == 1,
                    "runs_apart": apart, "verdict": "improved" if improved else "no gain",
                    "stable": stable(tb) and stable(ta), "before_iqr_ms": round(iqr(tb), 3), "after_iqr_ms": round(iqr(ta), 3),
                    "before_range_ms": f"{min(tb):.2f} to {max(tb):.2f}", "after_range_ms": f"{min(ta):.2f} to {max(ta):.2f}"})  # fmt: skip
    return out


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "benchmark")
    ap.add_argument("--runs", type=int, default=7, help="rounds of baseline and after measurements (default 7)")
    ap.add_argument("--keep", action="store_true", help="keep the candidate indexes afterwards")
    args = ap.parse_args(argv)
    from etl.ingest.base import IngestError, connect

    try:
        conn = connect("lue_warehouse")
    except IngestError as exc:
        print(f"[FAIL] {exc}")
        return 2
    conn.autocommit = True
    plans = args.out / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    works = workload()
    creates = statements(PERF / "02_indexes.sql")
    drop_indexes = [s for s in statements(PERF / "03_drop_indexes.sql") if s.startswith("DROP INDEX")]
    drop_all = statements(PERF / "03_drop_indexes.sql")
    names = [(m.group(1), m.group(2)) for m in (re.search(r"IF NOT EXISTS (\w+) ON (\S+)", s) for s in creates)]
    rows: list[dict] = []
    builds: dict[str, list[float]] = {n: [] for n, _t in names}
    loads: dict[tuple[str, str], list[float]] = {}
    started = time.perf_counter()

    def create(cur) -> None:
        for s, (name, _table) in zip(creates, names, strict=True):
            t0 = time.perf_counter()
            cur.execute(s)
            builds[name].append((time.perf_counter() - t0) * 1000)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM lue_dw.fact_payment")
            if not cur.fetchone()[0]:
                print("[FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
                return 1
            cur.execute("SET jit = off")
            cur.execute("SET max_parallel_workers_per_gather = 0")
            print("1. The baseline (D20) and the unpartitioned copy; VACUUM ANALYZE; a warm-up of every query")
            for s in drop_all:
                cur.execute(s)
            cur.execute(f"CREATE TABLE {COPY} (LIKE {OCC} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)")
            cur.execute(f"INSERT INTO {COPY} SELECT * FROM {OCC}")
            vacuum(cur, [COPY])
            # the D20 baseline as measured: every index on the workload's tables, and each table's size
            cur.execute("""SELECT t.relname, i.relname, coalesce(c.contype::text, CASE WHEN x.indisunique THEN 'i' END)
                           FROM pg_index x JOIN pg_class t ON t.oid = x.indrelid
                           JOIN pg_class i ON i.oid = x.indexrelid JOIN pg_namespace n ON n.oid = t.relnamespace
                           LEFT JOIN pg_constraint c ON c.conindid = x.indexrelid AND c.conrelid = x.indrelid AND c.contype IN ('p', 'u')
                           WHERE n.nspname = 'lue_dw' AND NOT t.relispartition
                             AND t.relname IN ('fact_rent_invoice_line', 'fact_payment', 'fact_unit_occupancy_daily', 'dim_unit', 'dim_tenant', 'dim_date')
                           ORDER BY 1, 2""")  # fmt: skip
            kinds = {"p": "primary key", "u": "unique constraint", "i": "unique index (one current row per member, US-1.2)"}
            baseline_indexes = [{"table": a, "index": b, "kind": kinds.get(k, "other (not allowed by D20)")} for a, b, k in cur.fetchall()]
            sizes = {}
            for table in ("lue_dw.fact_rent_invoice_line", "lue_dw.fact_payment", OCC, "lue_dw.dim_tenant"):
                cur.execute("SELECT coalesce((SELECT sum(pg_relation_size(relid)) FROM pg_partition_tree(%s::regclass)), "
                            "pg_relation_size(%s::regclass)), (SELECT count(*) FROM " + table + ")", (table, table))  # fmt: skip
                b, n = cur.fetchone()
                sizes[table] = {"heap_bytes": int(b), "rows": int(n)}
            for state in ("baseline", "after"):
                if state == "after":
                    create(cur)
                for w in works:
                    for v in variants(w, state):
                        cur.execute(sql_for(w, v))
                        cur.fetchall()
            print(f"2. {args.runs} rounds: the baseline, then the candidate indexes")
            for run in range(1, args.runs + 1):
                for s in drop_indexes:
                    cur.execute(s)
                for w in works:
                    for v in variants(w, "baseline"):
                        rows.append(measure(cur, w, "baseline", v, run))
                create(cur)
                for w in works:
                    for v in variants(w, "after"):
                        rows.append(measure(cur, w, "after", v, run))
                done = {w.label: [r["execution_ms"] for r in rows[-len(works) * 2 - 1:] if r["query"] == w.label] for w in works}
                print(f"   round {run}: " + "  ".join(f"{k} {'/'.join(f'{x:.1f}' for x in v)}" for k, v in done.items()))
            index_bytes = {n: index_size(cur, n) for n, _t in names}
            for w in works:  # the text plans, with the indexes present ...
                for v in variants(w, "after"):
                    save_plan(cur, w, "after", v, plans)
            for s in drop_indexes:  # ... and at the baseline
                cur.execute(s)
            for w in works:
                for v in variants(w, "baseline"):
                    save_plan(cur, w, "baseline", v, plans)
            print("3. The load cost: each fact's slice re-inserted, without and with its index, 3 rounds")
            for _ in range(3):
                for s in drop_indexes:
                    cur.execute(s)
                for table, where in LOADS.items():
                    loads.setdefault((table, "without"), []).append(reload_ms(conn, table, where))
                create(cur)
                for table, where in LOADS.items():
                    loads.setdefault((table, "with"), []).append(reload_ms(conn, table, where))
    finally:
        with conn.cursor() as cur:
            for s in drop_all if not args.keep else [d for d in drop_all if "DROP TABLE" in d]:
                cur.execute(s)
            if args.keep:
                create(cur)
        conn.close()
    summary = summarise(rows, works)
    text = re.sub(r"\n--\s{2,}(?=\S)", " ", (PERF / "02_indexes.sql").read_text(encoding="utf-8"))  # join the indented continuation lines
    purposes = {m.group(2): m.group(1).strip() for m in re.finditer(r"-- Purpose: (.*?)\nCREATE INDEX IF NOT EXISTS (\w+)", text)}
    built = []
    for name, table in names:
        used = sorted({r["query"] for r in rows if r["phase"] == "after" and name in r["indexes_used"].split()})
        lo, lw = loads.get((table, "without")), loads.get((table, "with"))
        built.append({"index": name, "table": table, "purpose": purposes.get(name, ""),
                      "definition": next(" ".join(s.split()) for s in creates if f" {name} " in s),
                      "size_bytes": index_bytes[name], "build_ms": round(statistics.median(builds[name]), 1),
                      "used_by": " ".join(used) or "none",
                      "load_ms_without": round(statistics.median(lo), 1) if lo else None,
                      "load_ms_with": round(statistics.median(lw), 1) if lw else None,
                      "load_slice": LOADS.get(table, "not measured: a dimension referenced by the facts")})  # fmt: skip
    write(args.out / "baseline.csv", [r for r in rows if r["phase"] == "baseline"])
    write(args.out / "after.csv", [r for r in rows if r["phase"] == "after"])
    write(args.out / "summary.csv", summary)
    write(args.out / "indexes.csv", built)
    (args.out / "run.json").write_text(json.dumps({
        "baseline_indexes": baseline_indexes, "tables": sizes, "runs": args.runs, "repeat": REPEAT,
        "design": f"interleaved rounds: baseline then after, every round; each measurement the fastest of {REPEAT} back-to-back runs",
        "kept_indexes": args.keep, "seconds": round(time.perf_counter() - started, 1),
        "tolerance": f"the interquartile range of the runs within {TOLERANCE:.0%} of the median or {TOLERANCE_MS} ms",
        "gain": f"every run after faster than every run before, the median at least {GAIN:.0%} and {GAIN_MS} ms lower, and the plan cost lower",
        "jit": "off", "parallel_workers": "off (max_parallel_workers_per_gather = 0)"}, indent=2), encoding="utf-8")  # fmt: skip
    print("4. Back to the baseline" + (" (indexes kept)" if args.keep else ""))
    print("=" * 100)
    for s in summary:
        print(f"  {s['query']} {s['before_ms']:>10.2f} ms -> {s['after_ms']:>9.2f} ms  cost {s['before_cost']:>11,.0f} -> {s['after_cost']:>11,.0f}  {s['verdict']:9} {'stable' if s['stable'] else 'UNSTABLE':8} {s['title'][:50]}")
    improved = sum(1 for s in summary if s["verdict"] == "improved")
    print(f" RESULT: {improved} of {len(summary)} queries improved, {len(summary) - improved} no gain; results in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
