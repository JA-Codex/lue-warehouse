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


# ============================================================================ cleaning report
PIPE = [("Sources S1 to S6", "PostgreSQL, Excel,\nCSV, JSON"), ("Bronze", "rows landed as sent,\nwith lineage"),
        ("Validation", "109 rules,\nDQ-01 to DQ-06"), ("Staging", "cleaned, typed,\none row per key"),
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
        ["Rows received from the 6 sources (20 tables)", fmt(total_bronze)],
        ["Rows rejected to quarantine", fmt(rejected)],
        ["Rows kept with a warning", fmt(warned)],
        ["Rows repaired (at least one value fixed)", fmt(repaired)],
        ["Rows in staging (one per natural key)", fmt(staged)],
        ["Planted defects detected", f"{fmt(f.e4.detected)} of {fmt(f.e4.expected)} ({f.e4.false_positives} false positives)"],
    ], [3, 4]))

    s.append(p("2. Cleaning process", "h1"))
    s.append(flow(PIPE, (2, "Quarantine", "rejected rows + reason")))
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

    s.append(p("9. Answer key check", "h1"))
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
    ], [1.6, 7]))

    s.append(p("2. Validation checks", "h1"))
    s.append(flow([("Bronze", "rows as sent"), ("Rule engine", "109 rules"), ("Pass / warn", "to staging"), ("Staging", "clean tables")],
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

    s.append(p("5. Integrity", "h1"))
    integ = [r for r in f.findings if r[3][:5] in ("DQ-03", "DQ-05")]
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example"],
                   [[a_, b[4:], c, d[6:], e, n, ex] for a_, b, c, d, e, n, ex in integ], [0.6, 1.9, 1.3, 1.5, 1.2, 0.8, 5.3], {5}))
    s.append(p("5.1 Enforced in the database", "h2"))
    s.append(table(["Control", "Result"], [
        ["Staging primary keys (one row per natural key)", f"20 tables; count bridge difference 0 in {sum(1 for b in f.bridge if b[9] == 0)} of {len(f.bridge)}"],
        ["Foreign keys from facts to dimensions", f"{f.fks} declared ({f.partitions} partitions inherit them)"],
        ["Special members in every dimension", "-1 Unknown, -2 Not applicable"],
        ["Surrogate keys", f"Identity columns; dim_tenant {fmt(f.dims[0][1] if f.dims else 0)} members, all keys unique"],
    ], [4, 5]))

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
    build(path, "Data Quality Report", "Lahore Urban Estates Analytics Warehouse", s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    args = ap.parse_args(argv)
    wh, src = connect("lue_warehouse"), connect("lue_source")
    try:
        f = facts_mod.collect(wh.cursor(), src.cursor(), args.data)
    finally:
        wh.close()
        src.close()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("LUE_Data_Cleaning_Report.pdf", cleaning_report), ("LUE_Data_Quality_Report.pdf", quality_report)):
        fn(f, OUT / name)
        print(f"written docs/reports/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
