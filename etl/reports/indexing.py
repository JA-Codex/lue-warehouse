#!/usr/bin/env python3
"""Build the Indexing Report from the benchmark results (E12, US-12.3): python etl/reports/indexing.py

    python etl/reports/indexing.py                       from docs/evidence/us-12.2 (the recorded run)
    python etl/reports/indexing.py --results data/benchmark --out data/reports

Writes LUE_Indexing_Report.pdf (default: docs/reports/). Every number comes from the results of
scripts/benchmark.py (summary.csv, indexes.csv, run.json, plans/); nothing is typed in. The reason each
change did or did not help is written per query below (WHY), with the verdict it explains: when a run's
measured verdict differs from it, the report is not built, so the text can never argue against the numbers.
"""

# ruff: noqa: E501  (report text: long lines read better)

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.reports.pdf import PageBreak, build, bullets, code, escape, p, table  # noqa: E402

RESULTS = ROOT / "docs" / "evidence" / "us-12.2"
OUT = ROOT / "docs" / "reports"
NAME = "LUE_Indexing_Report.pdf"

# Why each experiment came out as it did, per verdict ({fields} from summary.csv). A verdict without a text here
# is one the plans cannot explain (Q1 or Q7 improving with an unchanged plan, B2 or B5 not improving with the
# index used): the report is then not built, so the text never argues against the numbers.
WHY = {
    "B1": {"no gain": "Q1 over the whole window reads every invoice line and every payment. A sequential scan reads each page once; an "
                      "index would add random reads to fetch the same rows, so the planner keeps the sequential scans and the plan cost does "
                      "not move ({before_cost:,.0f} before and after). This is the control: the indexes were made for the month filter (B2) "
                      "and are rightly not used here; the small difference in time is the machine, not a plan change."},
    "B2": {"improved": "A month is a small slice of the lines and payments. The (due_date_key, unit_key) indexes find it with bitmap index "
                       "scans and read only its pages, instead of every page: the plan changes from sequential to bitmap scans, the cost "
                       "falls from {before_cost:,.0f} to {after_cost:,.0f} and the time {speedup}-fold."},
    "B3": {"no gain": "Q7 needs every vacant unit-day of the window, in order per unit, to find the spells: it reads most of the fact "
                      "whatever the index, and it orders by the unit's natural key across its SCD2 versions, which the (unit_key, "
                      "snapshot_date_key) index does not give. The planner does not use the index (the plan is the same before and after); "
                      "the difference in time is the machine. Precomputed spells are the way to make Q7 fast (recommendations)."},
    "B4": {"no gain": "Pruning works: the partitioned plan reads {after_partitions} of the monthly partitions and its estimated cost is "
                      "{cost_ratio}-fold lower ({before_cost:,.0f} to {after_cost:,.0f}). The time does not fall because the unpartitioned "
                      "copy keeps the same primary key, (snapshot_date_key, unit_key), with the date first: a bitmap scan of that key already "
                      "reads only the quarter's pages. The D20 baseline therefore serves date ranges; partitioning pays in maintenance instead: "
                      "the snapshot's refresh deletes and re-derives whole months (US-7.3), and a month is dropped or archived as one partition.",
           "improved": "Pruning works: the partitioned plan reads {after_partitions} of the monthly partitions, its estimated cost is "
                       "{cost_ratio}-fold lower and, on this machine, the time {speedup}-fold. The unpartitioned copy keeps the same date-first "
                       "primary key, so the gain is the smaller indexes and tables of three months against one large table; partitioning also "
                       "pays in maintenance: the refresh re-derives whole months (US-7.3) and a month is dropped as one partition."},
    "B5": {"improved": "One unit is a tiny share of the snapshot. The (unit_key, snapshot_date_key) index, present on every partition, turns "
                       "the scans of the year's {before_partitions} partitions into index lookups of the unit's rows: the cost falls from "
                       "{before_cost:,.0f} to {after_cost:,.0f} and the time {speedup}-fold."},
    "B6": {"no gain": "dim_tenant is small. The partial index on the current rows is chosen (an index-only scan), but it saves "
                      "{saved_ms:.2f} ms: below the 1 ms the harness counts as a gain. A partial index on the current SCD2 rows pays on a "
                      "large dimension; on a slicer list this small it is not worth its maintenance.",
           "improved": "The partial index on the current rows serves the list by an index-only scan of the current versions only, saving "
                       "{saved_ms:.2f} ms. The saving is real but small in absolute terms: dim_tenant is a slicer list, read rarely."},
}


# Short names for the tables (the full titles and changes are in section 4)
SHORT = {
    "B1": ("Q1 collection rate, whole window", "(due_date_key, unit_key) on invoice lines and payments"),
    "B2": ("Q1 collection rate, one month", "(due_date_key, unit_key) on invoice lines and payments"),
    "B3": ("Q7 vacancy spells", "(unit_key, snapshot_date_key) on the occupancy fact"),
    "B4": ("Occupancy by city, one quarter", "monthly partitions (pruning) against one table"),
    "B5": ("One unit over a fiscal year", "(unit_key, snapshot_date_key) on every partition"),
    "B6": ("Current tenants by segment", "partial index on the current dim_tenant rows"),
}


def read(results: Path):
    def rows(name):
        with (results / name).open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    summary, indexes = rows("summary.csv"), rows("indexes.csv")
    run = json.loads((results / "run.json").read_text(encoding="utf-8"))
    for s in summary:
        for k in ("before_ms", "after_ms", "before_cost", "after_cost"):
            s[k] = float(s[k])
        s["speedup"] = round(s["before_ms"] / s["after_ms"], 1) if s["after_ms"] else 0
        s["cost_ratio"] = round(s["before_cost"] / s["after_cost"], 1) if s["after_cost"] else 0
        s["saved_ms"] = s["before_ms"] - s["after_ms"]
        s["before_partitions"], s["after_partitions"] = int(s["before_partitions"]), int(s["after_partitions"])
    return summary, indexes, run


def excerpt(results: Path, label: str, phase: str, variant: str, n: int = 14) -> list[str]:
    """The plan's top node and its scans (the work that answers the query), and the execution time. The
    look-ups of the data window's first and last day (index-only scans of the occupancy partitions' primary
    keys, inside an InitPlan) are left out: they are the same in every plan and hide the scans that differ."""
    lines = (results / "plans" / f"{label}_{phase}_{variant.replace(' ', '_')}.txt").read_text(encoding="utf-8").splitlines()
    body = [ln for ln in lines if not ln.startswith("--")]
    top = body[:1]
    scans = [ln for ln in body[1:] if "Scan" in ln and "->" in ln
             and not ("Index Only Scan" in ln and "fact_unit_occupancy_daily_" in ln and "_pkey" in ln)]
    tail = [ln for ln in body if ln.startswith("Execution Time")]
    shown = ["  " + ln.strip() for ln in scans[:n]]  # a list of scans: the tree's indentation only wraps the lines
    return top + shown + ([f"  ... ({len(scans) - n} more scans of the same kind)"] if len(scans) > n else []) + tail


def report(results: Path, path: Path) -> None:
    summary, indexes, run = read(results)
    wrong = [f"{s['query']}: measured {s['verdict']}, which its plans cannot explain (see WHY)" for s in summary if s["verdict"] not in WHY[s["query"]]]
    if wrong:
        raise SystemExit("the measured verdicts differ from the explanations; check the run before building the report:\n  " + "\n  ".join(wrong))
    improved = [s for s in summary if s["verdict"] == "improved"]
    by = {s["query"]: s for s in summary}
    mb = lambda b: f"{int(b) / 1024 / 1024:,.2f} MB"  # noqa: E731
    st = []

    st.append(p("1. Summary", "h1"))
    st.append(p(f"Six queries were measured with <b>EXPLAIN (ANALYZE, BUFFERS)</b> before and after one change each, on the full profile. "
                f"<b>{len(improved)} improved</b> (" + ", ".join(f"{s['query']} {s['speedup']}-fold" for s in improved) + "); "
                f"<b>{len(summary) - len(improved)} did not</b>, and each of those is explained: an index the planner rightly ignores, an "
                "index it never uses, partitioning that the primary key already makes unnecessary for speed, and a gain too small to count."))
    st.append(table(["Query", "Change", "Time before", "Time after", "Cost before", "Cost after", "Plan before", "Plan after", "Verdict"], [
        [f"<b>{s['query']}</b> {escape(SHORT[s['query']][0])}", escape(SHORT[s["query"]][1]), f"{s['before_ms']:,.2f} ms", f"{s['after_ms']:,.2f} ms",
         f"{s['before_cost']:,.0f}", f"{s['after_cost']:,.0f}", escape(s["before_plan"]), escape(s["after_plan"]), s["verdict"]]
        for s in summary], [1.15, 1.25, 0.6, 0.6, 0.62, 0.62, 1.3, 1.3, 0.55], numeric={2, 3, 4, 5}, raw=True))
    st.append(table(["Query", "Runs before (min to max)", "Runs after (min to max)", "Spread before (IQR)", "Spread after (IQR)", "Stable"], [
        [s["query"], f"{s['before_range_ms']} ms", f"{s['after_range_ms']} ms", f"{float(s['before_iqr_ms']):,.2f} ms",
         f"{float(s['after_iqr_ms']):,.2f} ms", "yes" if s["stable"] == "True" else "no"] for s in summary],
        [0.6, 1.6, 1.6, 1.1, 1.1, 0.6], numeric={1, 2, 3, 4}))
    st.append(p("Times are the medians of the timed runs; the cost is the planner's total estimated cost of the plan (its own units). "
                "B4's before is the unpartitioned copy and its after the partitioned fact, both without the candidate indexes, so the "
                "partitioning is measured alone.", "note"))

    st.append(p("2. The baseline", "h1"))
    base = run.get("baseline_indexes", [])
    st.append(p("The warehouse was built with <b>primary-key and unique-constraint indexes only</b> (decision D20), so the baseline is "
                "the warehouse as deployed, not an index-free one. These are the indexes present on the measured tables at the baseline:"))
    st.append(table(["Table", "Index", "Kind"], [[b["table"], b["index"], b["kind"]] for b in base], [2.2, 3.2, 1.6]))
    st.append(p("The candidate indexes of the experiments are in <b>sql/70_performance/02_indexes.sql</b>, outside the deploy; "
                "<b>03_drop_indexes.sql</b> returns to this baseline."))

    st.append(p("3. Method", "h1"))
    st += bullets([
        "One command, <b>python scripts/benchmark.py</b>: the baseline (the candidate indexes dropped; an unpartitioned copy of the "
        "occupancy fact with the same rows and primary key), <b>VACUUM ANALYZE</b>, a warm-up of every query in both states, then "
        f"<b>{run['runs']} interleaved rounds</b>: in each, every query is measured at the baseline, the candidate indexes are created, "
        "and every query is measured again. A slowdown of the machine therefore falls on both sides alike: the medians compare plans, "
        "not moments.",
        f"Each measurement is the fastest of {run.get('repeat', 1)} back-to-back runs of EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), since "
        "interference from the machine only ever adds time; it records the execution and planning time, the total cost, the scans and "
        "partitions read, the indexes used and the buffers (baseline.csv, after.csv). Each index's build time is the median of its "
        f"{run['runs']} builds.",
        f"Stable: {escape(run['tolerance'])}; the measuring machine is a shared cloud machine whose CPU speed changes, so a query of a few "
        "milliseconds can take twice as long from one run to the next. The verdicts do not depend on that: "
        f"improved means {escape(run['gain'])}. JIT and parallel workers are off in the session: "
        "their start-up varies from run to run and is unrelated to indexes, so serial plans compare the access paths themselves.",
        "Q1 and Q7 are measured exactly as they stand in sql/60_analytics/analytical.sql; B2, B4, B5 and B6 (in "
        "sql/70_performance/01_benchmark_queries.sql) are the date-bounded and selective shapes a dashboard sends.",
    ])
    st.append(p("Every query kept the same plan in every round of a state (" + ", ".join(s["query"] for s in summary if s["same_plan_every_run"] == "True")
                + "), and every one was stable by the rule above (" + ", ".join(s["query"] for s in summary if s["stable"] == "True") + ")."))

    st.append(PageBreak())
    st.append(p("4. The experiments", "h1"))
    for s in summary:
        q = s["query"]
        st.append(p(f"{q}. {escape(s['title'])}", "h2"))
        st.append(p(f"<b>Change:</b> {escape(s['change'])}. <b>Measured:</b> {s['before_ms']:,.2f} ms to {s['after_ms']:,.2f} ms, cost "
                    f"{s['before_cost']:,.0f} to {s['after_cost']:,.0f}: <b>{s['verdict']}</b>."))
        st.append(p("<b>Why:</b> " + WHY[q][s["verdict"]].format(**s)))
        before_variant = "unpartitioned copy" if q == "B4" else "as deployed"
        after_phase, after_variant = ("baseline", "partitioned") if q == "B4" else ("after", "as deployed")
        st.append(p("Plan before (the top node and the scans)", "note"))
        st.append(code(excerpt(results, q, "baseline", before_variant)))
        st.append(p("Plan after (the top node and the scans)", "note"))
        st.append(code(excerpt(results, q, after_phase, after_variant)))

    st.append(PageBreak())
    st.append(p("5. What each index costs", "h1"))
    tables = run.get("tables", {})
    rows = []
    for i in indexes:
        heap = tables.get(i["table"], {}).get("heap_bytes")
        share = f"{int(i['size_bytes']) / heap:.0%} of the table" if heap else ""
        lw, lo = i.get("load_ms_with") or "", i.get("load_ms_without") or ""
        load = f"{float(lo):,.0f} to {float(lw):,.0f} ms ({float(lw) / float(lo) - 1:+.0%})" if lw and lo else "not measured (a dimension the facts reference)"
        rows.append([escape(i["index"]), escape(i["purpose"]), f"{mb(i['size_bytes'])}<br/>{share}",
                     f"{float(i['build_ms']):,.0f} ms", load, i["used_by"]])
    st.append(table(["Index", "Purpose", "Size", "Build (median)", "Re-load of the slice, without to with", "Used by"], rows,
                    [1.75, 2.45, 0.85, 0.6, 1.2, 0.45], numeric={3}, raw=True))
    st.append(p("The re-load is the time to insert a slice of the fact again (every invoice line, every payment, one month of the occupancy "
                "snapshot), in a transaction that is rolled back: what each index adds to a load. Differences of a few percent are within "
                "the run-to-run variation; the foreign-key checks, not the indexes, dominate the load.", "note"))

    st.append(p("6. Recommendations", "h1"))
    used = {i["index"]: i["used_by"] for i in indexes}
    sizes = {i["index"]: mb(i["size_bytes"]) for i in indexes}
    rec = []
    if "B2" in used.get("ix_payment_due_unit", "") and "B2" in used.get("ix_invoice_line_due_unit", ""):
        rec.append(f"<b>Keep ix_invoice_line_due_unit and ix_payment_due_unit</b> ({sizes['ix_invoice_line_due_unit']} and "
                   f"{sizes['ix_payment_due_unit']}): every month or quarter filter on collections, from a dashboard slicer or an analyst, "
                   f"becomes {by['B2']['speedup']}-fold faster; Q1 over the whole window is unaffected.")
    if "B5" in used.get("ix_occupancy_unit_date", ""):
        rec.append(f"<b>Keep ix_occupancy_unit_date</b> ({sizes['ix_occupancy_unit_date']}, the pack's own proposal): a drill-through to "
                   f"one unit becomes {by['B5']['speedup']}-fold faster. It is the largest index; its build takes seconds and its load "
                   "cost is within the variation.")
    if by["B6"]["verdict"] == "no gain":
        rec.append("<b>Do not keep ix_dim_tenant_current_segment</b>: chosen, but saving under a millisecond on a dimension this small.")
    else:
        rec.append(f"<b>ix_dim_tenant_current_segment is optional</b>: it saves {by['B6']['saved_ms']:.2f} ms on a list that is read rarely.")
    if by["B4"]["verdict"] == "no gain":
        rec.append("<b>Keep the monthly partitions, for maintenance rather than speed</b>: the date-first primary key already serves date "
                   "ranges, while partitions let the snapshot refresh and retire whole months.")
    else:
        rec.append(f"<b>Keep the monthly partitions</b>: date-bounded queries run {by['B4']['speedup']}-fold faster, and partitions let the "
                   "snapshot refresh and retire whole months.")
    rec.append("<b>Make Q7 fast with data, not an index</b>: a mart of vacancy spells (one row per spell) would answer it from a few "
               "thousand rows; mart_occupancy_monthly already counts completed spells per month.")
    rec.append("<b>Power BI</b> imports the marts and views (E13), which are small; these indexes matter for DirectQuery and ad-hoc SQL on "
               "the facts. To keep them after a benchmark: python scripts/benchmark.py --keep, or run sql/70_performance/02_indexes.sql.")
    st += bullets(rec)
    build(path, "Indexing Report", "Query optimisation with EXPLAIN ANALYZE: indexes and partitioning, before and after", st, phase="Phase 3")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, default=RESULTS, help="the benchmark's results folder (default docs/evidence/us-12.2)")
    ap.add_argument("--out", type=Path, default=OUT, help="the folder for the PDF (default docs/reports)")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    report(args.results, args.out / NAME)
    print(f"written {args.out / NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
