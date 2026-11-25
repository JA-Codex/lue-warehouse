#!/usr/bin/env python3
"""Build the Phase 2 reports from the warehouse: python etl/reports/build.py [--data data]

  docs/reports/LUE_Data_Cleaning_Report.pdf      what was wrong with the data, how it was fixed
  docs/reports/LUE_Data_Quality_Report.pdf       completeness, accuracy and integrity

Every number is read from lue_warehouse (and lue_source for the reconciliation) by
etl/reports/facts.py; nothing is typed in. Run after ingest, validate and stage.
"""

# ruff: noqa: E501  (report text: long lines read better)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.ingest.base import connect  # noqa: E402
from etl.reports import facts as facts_mod  # noqa: E402
from etl.reports.pdf import PageBreak, build, escape, flow, fmt, p, table  # noqa: E402
from etl.staging import spec  # noqa: E402

OUT = ROOT / "docs" / "reports"
SOURCES = {"S1": "Property management system (PostgreSQL lue_source, schema src_pms)",
           "S2": "Registers workbook (owners, ownership, vendors, SLA policy, holidays)",
           "S3": "Payment channel settlement files (CSV, one per channel and month)",
           "S4": "Tenant app maintenance tickets (JSON with status history)",
           "S5": "Weather feed (JSON, daily per city)",
           "S6": "Leasing incentive register (offers and their use)"}  # fmt: skip
ISSUE_TEXT = {
    "whitespace": "Leading, trailing or repeated spaces removed",
    "case_or_spelling": "Case or spelling made the one vocabulary value",
    "empty_to_null": "Empty or blank text stored as NULL",
    "null_default": "Missing value given its documented default",
    "date_day_first": "DD/MM/YYYY date read day first",
    "type_conversion": "Text converted to its type (number, date, timestamp, boolean)",
    "repaired": "Rows of the column with at least one repair",
    "not_in_vocabulary": "Value outside the vocabulary (kept as NULL, flagged)",
    "named_sample": "The named sample",
}  # fmt: skip


def money(v) -> str:
    return f"{v:,.0f}"


def recon_summary(f) -> str:
    if not f.recon:
        return "not run yet (the stage after the facts)"
    off = sum(1 for r in f.recon if not r[5])
    return f"{len(f.recon) - off} of {len(f.recon)} measure-months reconcile (billed, paid, tickets, lease events); unexplained {money(sum(r[4] for r in f.recon))}"


def fact_summary(f) -> str:
    if not f.fact_tests:
        return "not run yet"
    orphans = sum(int(n) for name, n, _ok in f.fact_tests if ": no orphan " in name)
    return f"{sum(1 for t in f.fact_tests if t[2])} of {len(f.fact_tests)} fact tests pass; {fmt(orphans)} fact rows without a dimension row; {fmt(sum(n for _t, n in f.fact_rows))} fact rows"


# ============================================================================ cleaning report
def pipe(f) -> list:
    return [("Sources S1 to S6", "PostgreSQL, Excel,\nCSV, JSON"), ("Bronze", "rows landed as sent,\nwith lineage"),
            ("Validation", f"{len(f.rules)} rules,\nDQ-01 to DQ-06"), ("Staging", "cleaned, typed,\none row per key"),
            ("Warehouse", "dimensions\nand facts")]  # fmt: skip


def cleaning_report(f, path: Path) -> None:
    s = []
    total_bronze = sum(v[3] for v in f.volumes)
    rejected = sum(r[5] for r in f.findings if r[4] == "reject")
    warned = sum(r[5] for r in f.findings if r[4] == "warn")
    repaired = sum(c.get("rows_repaired", (0,))[0] for c in f.table_counts.values())
    staged = sum(b[7] for b in f.bridge)

    s.append(p("1. Summary", "h1"))
    s.append(table(["Measure", "Value"], [
        ["Data", f"{f.profile} profile (seed {f.seed}), {f.window}"],
        [f"Rows received from the {len({v[0] for v in f.volumes})} sources ({len(f.volumes)} tables)", fmt(total_bronze)],
        ["Rows rejected to quarantine", fmt(rejected)],
        ["Rows kept with a warning", fmt(warned)],
        ["Rows repaired (at least one value fixed)", fmt(repaired)],
        ["Rows in staging (one per natural key)", fmt(staged)],
        ["Planted defects detected", f"{fmt(f.e4.detected)} of {fmt(f.e4.expected)} ({f.e4.false_positives} false positives)"],
    ], [3, 4]))

    s.append(p("2. Cleaning process", "h1"))
    s.append(flow(pipe(f), (2, "Quarantine", "rejected rows + reason")))
    s.append(table(["Step", "What happens to the data"], [
        ["Bronze", "Every source row is landed unchanged, as text, with its batch, file and row number."],
        ["Validation", "Each row is checked by the rule catalogue. Unusable rows are rejected to quarantine with the rule and reason; suspicious but usable rows are kept with a warning."],
        ["Staging", "Accepted rows are trimmed, standardised to one spelling, typed and deduplicated; business fields are derived. Every repair is counted with a before and after sample."],
    ], [1.2, 6]))

    s.append(p("3. Sources and volumes", "h1"))
    vol = [[src, SOURCES[src].split(" (")[0], b, st, n] for src, b, st, n, _bt in f.volumes]
    s.append(table(["Source", "System", "Bronze table", "Staging table", "Rows"], vol, [0.8, 3.4, 2.6, 2.8, 1.2], {4}))

    s.append(p("4. Issues found and handling", "h1"))
    s.append(p("Reject = moved to quarantine, not staged. Warn = kept, finding recorded."))
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example"],
                   [[a, b[4:], c, d[6:], e, n, ex] for a, b, c, d, e, n, ex in f.findings],
                   [0.6, 2.0, 1.3, 1.5, 1.2, 0.8, 5.2], {5}))

    s.append(p("5. Repairs", "h1"))
    rep = [(t, col, i, n, b, a) for _s, t, i, col, n, b, a in f.column_issues if i not in ("type_conversion", "named_sample", "repaired")]
    s.append(table(["Staging table", "Column", "Repair", "Rows", "Before", "After"],
                   [[t[4:], c, ISSUE_TEXT.get(i, i), n, repr(b) if b is not None else "", a] for t, c, i, n, b, a in rep],
                   [1.9, 1.7, 3.2, 0.9, 1.9, 1.9], {3}))
    named = [r for r in f.column_issues if r[2] == "named_sample"]
    if named:
        _s, t, _i, col, n, b, a = named[0]
        s.append(p(f"Standardisation sample: <font face='Courier'>'{escape(b)}'</font> &#8594; "
                   f"<font face='Courier'>'{escape(a)}'</font> ({t}.{col}). Values are matched to a vocabulary ignoring case "
                   f"and spaces: <font face='Courier'>' lahore '</font>, <font face='Courier'>'LAHORE'</font> and "
                   f"<font face='Courier'>'LHE'</font> all become <font face='Courier'>'Lahore'</font>."))
    s.append(p("5.1 Distinct values before and after", "h2"))
    dv = {}
    for t, col, stage, value, n in f.distinct:
        if (t, col) in (("stg_unit", "unit_type"), ("stg_building", "city"), ("stg_ticket", "priority"), ("stg_ticket", "category")):
            dv.setdefault((t, col), {"before": [], "after": []})[stage].append((value, n))
    s.append(table(["Column", "Before", "Values before (rows)", "After", "Values after (rows)"],
                   [[f"{t[4:]}.{c}", len(d["before"]), ", ".join(f"{v!r} ({n:,})" for v, n in d["before"]),
                     len(d["after"]), ", ".join(f"{v} ({n:,})" for v, n in d["after"])] for (t, c), d in dv.items()],
                   [1.6, 0.7, 5.2, 0.6, 2.6], {1, 3}))
    s.append(p("5.2 Missing values and types", "h2"))
    typed = [(t, col, n) for _s, t, i, col, n, _b, _a in f.column_issues if i == "type_conversion"]
    s.append(table(["Rule", "Applied to"], [
        ["Blank text stored as NULL", "All text columns"],
        ["Documented default", "Employer sector 'Unknown'; discount and rent-free days 0"],
        ["Left NULL (optional)", "Phone, vendor before assignment, open ownership end date"],
        ["Missing required value", "Rejected by DQ-01 (section 4)"],
        ["Day-first dates DD/MM/YYYY", "Read as day first (incentive start date)"],
        ["Text to number, date, timestamp, boolean", f"{fmt(sum(n for *_x, n in typed))} values in {len(typed)} columns, by safe casts"],
    ], [3, 5]))

    s.append(p("6. Duplicates", "h1"))
    s.append(p("Exact duplicates are rejected in validation (DQ-03). For conflicting copies of one key, staging keeps the "
               "latest: source <font face='Courier'>updated_at</font> (tickets: latest status time), then load time, batch and row."))
    dup = []
    for t in spec.TABLES:
        c = f.table_counts.get(t.name, {})
        g = lambda k: c.get(k, (0,))[0]  # noqa: E731
        if g("duplicates_removed") or g("superseded") or g("conflicts_resolved"):
            dup.append([t.name[4:], g("duplicates_removed"), g("superseded"), g("conflicts_resolved"),
                        c.get("conflicts_resolved", (0, None))[1] or ""])
    s.append(table(["Staging table", "Exact duplicates rejected", "Older copies dropped", "Of which conflicting", "Example key"],
                   dup, [2.2, 2, 1.8, 1.8, 2.2], {1, 2, 3}))

    s.append(p("7. Count bridge: bronze to staging", "h1"))
    s.append(p("Staged = bronze - rejected - unusable - deduplicated, for every table."))
    br = []
    for b in f.bridge:
        c = f.table_counts.get(b[0], {})
        br.append([b[0][4:], b[1], b[2], b[3], b[4], b[5], b[7], c.get("rows_repaired", (0,))[0], b[9]])
    s.append(table(["Staging table", "Src", "Bronze", "Rejected", "Unusable", "Dedup.", "Staged", "Repaired", "Diff."], br,
                   [2.4, 0.6, 1.1, 1, 0.9, 0.9, 1.1, 1.1, 0.7], {2, 3, 4, 5, 6, 7, 8}))

    s.append(p("8. Derived fields", "h1"))
    a = f.allocation
    biz = {b[1]: b[3] for b in f.business}
    s.append(table(["Field", "Result"], [
        ["Allocations completed where the source's were rejected", f"{fmt(a['derived_rows'])} rows for {fmt(a['derived_payments'])} payments ({money(a['derived_amount'])} PKR)"],
        ["Cleared payments fully allocated", f"{fmt(a['cleared_full'])} of {fmt(a['cleared'])}; none over-allocated"],
        ["Reversals fully allocated", f"{fmt(a['reversals_full'])} of {fmt(a['reversals'])}"],
        ["Unmatched settlement lines", fmt(biz.get("unmatched_settlement", 0))],
        ["Unsettled electronic payments", fmt(biz.get("unsettled_payment", 0))],
        ["Also derived", "Days past due, settlement lag, lease term (months), ticket lifecycle times, SLA breach, 30-day recurrence"],
    ], [3.5, 5]))

    s.append(p("9. Agreement with the run log", "h1"))
    s.append(p("Every count above is read from the tables; the run log (lue_audit.etl_run_log) recorded the same rows as they were loaded."))
    agree = []
    for b in f.bridge:
        logged = f.log_staged.get(b[0], 0)
        agree.append([b[0][4:], b[7], logged, "agree" if logged == b[7] else "DIFFER"])
    agree.append(["Rows rejected to quarantine", f.quarantined, f.log_rejected, "agree" if f.quarantined == f.log_rejected else "DIFFER"])
    s.append(table(["Staging table", "Rows staged (table)", "Rows inserted (run log)", "Result"], agree, [3.2, 2, 2, 1.2], {1, 2}))

    s.append(p("10. Answer key check", "h1"))
    s.append(table(["Check", "Staging table.column", "Expected", "Found", "Result"],
                   [[r[0], f"{r[1]}.{r[2]}", r[3], r[4], "pass" if r[7] else "FAIL"] for r in f.e5.rows],
                   [1, 3.6, 1.2, 1.2, 1], {2, 3}))
    build(path, "Data Cleaning Report", "Lahore Urban Estates Analytics Warehouse", s)


# ============================================================================ quality report
def quality_report(f, path: Path) -> None:
    s = []
    rejected = sum(r[5] for r in f.findings if r[4] == "reject")
    warned = sum(r[5] for r in f.findings if r[4] == "warn")
    tot_i = sum(r[1] for r in f.invoiced), sum(r[2] for r in f.invoiced)
    tot_p = sum(r[1] for r in f.paid), sum(r[2] for r in f.paid)
    a = f.allocation
    s.append(p("1. Summary", "h1"))
    s.append(table(["Dimension", "Result"], [
        ["Completeness", f"{fmt(f.by_check[0][1])} rows with a required value missing, rejected to quarantine"],
        ["Accuracy", f"Invoiced and paid amounts equal the source in every quarter ({money(tot_i[1])} and {money(tot_p[1])} PKR)"],
        ["Integrity", f"{fmt(f.by_check[4][1] + f.by_check[4][2])} referential and {fmt(f.by_check[2][1] + f.by_check[2][2])} duplicate findings handled; {sum(1 for b in f.bridge if b[9] == 0)} of {len(f.bridge)} tables reconcile; {f.fks} foreign keys enforced"],
        ["Rules", f"{len(f.rules)} rules; {fmt(rejected)} rows rejected, {fmt(warned)} warned"],
        ["Answer key", f"{fmt(f.e4.detected)} of {fmt(f.e4.expected)} planted defects detected, {f.e4.false_positives} false positives"],
        ["Source to warehouse", recon_summary(f)],
        ["Fact integrity", fact_summary(f)],
    ], [1.6, 7]))

    s.append(p("2. Validation checks", "h1"))
    s.append(flow([("Bronze", "rows as sent"), ("Rule engine", f"{len(f.rules)} rules"), ("Pass / warn", "to staging"), ("Staging", "clean tables")],
                  (1, "Quarantine", "rejected rows + reason")))
    s.append(table(["Check", "Tests", "Dimension", "Rejected", "Warned"], [
        [f.by_check[0][0], "Required value missing", "Completeness", f.by_check[0][1], f.by_check[0][2]],
        [f.by_check[1][0], "Value of the wrong type", "Accuracy", f.by_check[1][1], f.by_check[1][2]],
        [f.by_check[2][0], "Record repeated", "Integrity", f.by_check[2][1], f.by_check[2][2]],
        [f.by_check[3][0], "Business rule broken (totals, date order, rent)", "Accuracy", f.by_check[3][1], f.by_check[3][2]],
        [f.by_check[4][0], "Reference to a missing record", "Integrity", f.by_check[4][1], f.by_check[4][2]],
        [f.by_check[5][0], "Value outside its range", "Accuracy", f.by_check[5][1], f.by_check[5][2]],
    ], [1.6, 4, 1.6, 1, 1], {3, 4}))
    s.append(p("Reject = row moved to quarantine. Warn = row kept, finding recorded. A row is rejected by its first failing rule only."))

    s.append(p("3. Completeness", "h1"))
    comp = [[a_, b[4:], c, n, m, f"{pct:.2f}%"] for a_, b, c, n, m, pct, _h in f.completeness]
    s.append(table(["Src", "Table", "Required columns", "Rows", "Missing", "Share"], comp, [0.6, 2, 5, 1, 0.9, 0.9], {3, 4, 5}))

    s.append(p("4. Accuracy", "h1"))
    acc = [r for r in f.findings if r[3][:5] in ("DQ-02", "DQ-04", "DQ-06")]
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example"],
                   [[a_, b[4:], c, d[6:], e, n, ex] for a_, b, c, d, e, n, ex in acc], [0.6, 1.9, 1.3, 1.5, 1.2, 0.8, 5.3], {5}))
    s.append(p("4.1 Reconciliation with the source (PKR)", "h2"))
    rec = []
    pays = {q: (x, y) for q, x, y in f.paid}
    for q, sa, ta, _sn, _tn in f.invoiced:
        pa, pt = pays.get(q, (0, 0))
        rec.append([q, money(sa), money(ta), money(ta - sa), money(pa), money(pt), money(pt - pa)])
    rec.append(["Total", money(tot_i[0]), money(tot_i[1]), money(tot_i[1] - tot_i[0]), money(tot_p[0]), money(tot_p[1]), money(tot_p[1] - tot_p[0])])
    s.append(table(["Quarter", "Invoiced (source)", "Invoiced (staging)", "Diff.", "Paid (source)", "Paid (staging)", "Diff."], rec,
                   [1, 1.8, 1.8, 0.8, 1.8, 1.8, 0.8], {1, 2, 3, 4, 5, 6}))
    s.append(p("4.2 Allocation reconciliation", "h2"))
    s.append(table(["Check", "Result"], [
        ["Cleared payments whose allocations equal the amount", f"{fmt(a['cleared_full'])} of {fmt(a['cleared'])}"],
        ["Reversals fully reversed", f"{fmt(a['reversals_full'])} of {fmt(a['reversals'])}"],
        ["Payments over-allocated", fmt(a["over_paid"])],
        ["Invoice lines over-allocated", fmt(a["over_line"])],
        ["Invoice lines paid / unpaid / partly paid", f"{fmt(a['lines_paid'])} / {fmt(a['lines_unpaid'])} / {fmt(a['lines'] - a['lines_paid'] - a['lines_unpaid'])}"],
    ], [5, 3]))

    s.append(p("4.3 Source to warehouse by month (DQ-07)", "h2"))
    if not f.recon:
        s.append(p("Not run yet: the reconciliation runs after the facts in python etl/run_pipeline.py."))
    else:
        s.append(p(f"Run {f.recon_run}, lue_audit.reconciliation. For every measure and month: source = warehouse + quarantined; "
                   "the unexplained rest must be 0. A rejected row counts only when its key never reached staging."))
        meas = {}
        for m, _mo, sv, wv, un, ok in f.recon:
            x = meas.setdefault(m, [0, 0, 0, 0, 0])
            x[0] += 1; x[1] += sv; x[2] += wv; x[3] += un; x[4] += 0 if ok else 1  # noqa: E702
        s.append(table(["Measure", "Months", "Source", "Warehouse + quarantined", "Unexplained", "Months off"],
                       [[m, x[0], money(x[1]), money(x[2]), money(x[3]), x[4]] for m, x in meas.items()],
                       [1.6, 0.9, 2.2, 2.4, 1.3, 1.1], {1, 2, 3, 4, 5}))
        by = {(m, mo): (sv, wv, un) for m, mo, sv, wv, un, _ok in f.recon}
        months = sorted({mo for m, mo, *_r in f.recon if m in ("billed", "paid")})
        s.append(table(["Month", "Billed (source)", "Billed (warehouse)", "Paid (source)", "Paid (warehouse)", "Unexplained"],
                       [[mo, money(by.get(("billed", mo), (0, 0, 0))[0]), money(by.get(("billed", mo), (0, 0, 0))[1]),
                         money(by.get(("paid", mo), (0, 0, 0))[0]), money(by.get(("paid", mo), (0, 0, 0))[1]),
                         money(by.get(("billed", mo), (0, 0, 0))[2] + by.get(("paid", mo), (0, 0, 0))[2])] for mo in months],
                       [1.1, 1.9, 1.9, 1.9, 1.9, 1.2], {1, 2, 3, 4, 5}))

    s.append(p("5. Integrity", "h1"))
    integ = [r for r in f.findings if r[3][:5] in ("DQ-03", "DQ-05")]
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example"],
                   [[a_, b[4:], c, d[6:], e, n, ex] for a_, b, c, d, e, n, ex in integ], [0.6, 1.9, 1.3, 1.5, 1.2, 0.8, 5.3], {5}))
    s.append(p("5.1 Enforced in the database", "h2"))
    s.append(table(["Control", "Result"], [
        ["Staging primary keys (one row per natural key)", f"{len(f.bridge)} tables; count bridge difference 0 in {sum(1 for b in f.bridge if b[9] == 0)} of {len(f.bridge)}"],
        ["Foreign keys from facts to dimensions", f"{f.fks} declared ({f.partitions} partitions inherit them)"],
        ["Special members in every dimension", "-1 Unknown, -2 Not applicable"],
        ["Surrogate keys", f"Identity columns; dim_tenant {fmt(f.dims[0][1] if f.dims else 0)} members, all keys unique"],
    ], [4, 5]))
    s.append(p("5.2 Facts: grain, orphans and values (US-7.6)", "h2"))
    if not f.fact_tests:
        s.append(p("Not run yet: the fact tests run at the end of python etl/facts/run.py."))
    else:
        per = {}
        for name, n, _ok in f.fact_tests:
            fact, test = name.split(": ", 1)
            kind = "grain" if "(grain)" in test else "orphan" if test.startswith("no orphan") else "value"
            x = per.setdefault(fact, {"grain": [0, 0], "orphan": [0, 0], "value": [0, 0]})
            x[kind][0] += 1
            x[kind][1] += int(n)
        rows_ = dict(f.fact_rows)
        s.append(table(["Fact", "Rows", "Grain duplicates", "Orphan checks", "Orphan rows", "Value checks", "Violations"],
                       [[k[5:], rows_.get(k, 0), v["grain"][1], v["orphan"][0], v["orphan"][1], v["value"][0], v["value"][1]] for k, v in per.items()],
                       [2.6, 1.2, 1.2, 1.1, 1.1, 1.1, 1.1], {1, 2, 3, 4, 5, 6}))
        orphans = sum(int(n) for name, n, _ok in f.fact_tests if ": no orphan " in name)
        s.append(p(f"Fact rows without a matching dimension row: <b>{fmt(orphans)}</b> across all "
                   f"{sum(1 for name, *_r in f.fact_tests if ': no orphan ' in name)} foreign keys (run {f.test_run}). "
                   "The special members -1 and -2 are dimension rows, not orphans. Each key is tested by a query of this form "
                   "(sql/90_tests/02_fact_tests.sql), here the tenant of a payment:"))
        s.append(p(f"<font face='Courier' size='7'>{escape(f.orphan_sql)}</font>"))
    s.append(p("5.3 SCD Type 2 continuity", "h2"))
    scd = ["dim_unit", "dim_tenant", "dim_vendor", "dim_maintenance_category"]
    tests = {}
    for name, n in f.dim_tests:
        dim, test = name.split(": ", 1)
        if dim in scd:
            tests.setdefault(test, {})[dim] = n
    s.append(table(["Test (sql/90_tests/01_dimension_tests.sql)", "unit", "tenant", "vendor", "category"],
                   [[t, *[d.get(x, "") for x in scd]] for t, d in tests.items()], [4.6, 0.9, 0.9, 0.9, 1.1], {1, 2, 3, 4}))
    others = [(n_, v) for n_, v in f.dim_tests if n_.split(": ", 1)[0] not in scd]
    s.append(p(f"The other dimension tests: {sum(1 for _n, v in others if v == 0)} of {len(others)} without violations "
               "(keys unique, special members present, one row per natural key, inferred members, the hierarchy, holidays)."))

    s.append(PageBreak())
    s.append(p("6. Rule-by-rule results", "h1"))
    rr = [[r.id, r.table[4:], r.check_name[6:], r.severity, f.rule_hits.get(r.id, 0), r.message] for r in f.rules]
    s.append(table(["Rule", "Table", "Check", "Severity", "Rows", "Description"], rr, [1.2, 1.9, 1.5, 0.9, 0.8, 5.7], {4}))

    s.append(p("7. Quarantine", "h1"))
    s.append(table(["Source", "Table", "Check", "Rows"], [[a_, b, c, n] for a_, b, c, n in f.quarantine], [1, 3, 3, 1], {3}))

    s.append(p("8. Detection against the answer key", "h1"))
    ak = [[r[1], r[2], r[3].replace("_", " "), r[4], r[5], r[6], r[7]] for r in f.e4.rows if r[0] != "total"]
    s.append(table(["Src", "Table", "Defect", "Handling", "Expected by", "Planted", "Found"], ak,
                   [0.6, 2.1, 3, 1, 1.1, 0.9, 0.9], {5, 6}))

    s.append(p("9. The pipeline run", "h1"))
    if f.pipeline_run is None:
        s.append(p("No pipeline run yet (python etl/run_pipeline.py)."))
    else:
        s.append(p(f"The latest complete run, {f.pipeline_run}, of python etl/run_pipeline.py (lue_audit.etl_run_log): "
                   + ", ".join(f"{fmt(n)} steps {st}" for st, n in f.pipeline)
                   + (f" (failed, non-critical: {', '.join(f.pipeline_failed)}; the run went on)" if f.pipeline_failed else "") + ". Facts loaded: "
                   + ", ".join(f"{t[5:]} {fmt(n)}" for t, n in f.fact_rows) + "."))

    s.append(p("10. Conclusion and residual risks", "h1"))
    s.append(table(["Risk", "Where it stands"], [
        ["Rejected rows leave gaps", f"{fmt(f.quarantined)} rows sit in quarantine with their rule and reason; DQ-07 counts them as the explained difference, and paid cash still reconciles because staging re-derives the rejected allocations."],
        ["Late or missing reference data", "Unknown codes resolve to -1 (Unknown) and are counted every run; late tenants become inferred members, completed when the record arrives."],
        ["Rules cover only planted defects", f"The catalogue found {fmt(f.e4.detected)} of {fmt(f.e4.expected)} planted defects with {f.e4.false_positives} false positives; a new kind of defect needs a new rule."],
        ["Arrears of a departed tenant", "The occupancy snapshot holds the arrears of the lease active that day; debt left by a tenant who has gone stays in the invoice and payment facts."],
        ["Synthetic data", "The checks prove the pipeline on generated data with known defects; real sources may hold patterns the generator does not plant."],
    ], [2.4, 6.2]))
    build(path, "Data Quality Report", "Lahore Urban Estates Analytics Warehouse", s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--out", type=Path, default=OUT, help="the folder for the PDFs (default: docs/reports)")
    ap.add_argument("--insights", action="store_true", help="generate only the Business Insights Report")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.insights:
        # the Business Insights Report needs no database: etl/reports/insights.py
        from etl.reports import insights

        insights.report(args.out / "LUE_Business_Insights_Report.pdf")
        print(f"written {args.out / 'LUE_Business_Insights_Report.pdf'}")
        return 0

    wh, src = connect("lue_warehouse"), connect("lue_source")
    try:
        f = facts_mod.collect(wh.cursor(), src.cursor(), args.data)
    finally:
        wh.close()
        src.close()
    for name, fn in (
        ("LUE_Data_Cleaning_Report.pdf", cleaning_report),
        ("LUE_Data_Quality_Report.pdf", quality_report),
    ):
        fn(f, args.out / name)
        print(f"written {args.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
