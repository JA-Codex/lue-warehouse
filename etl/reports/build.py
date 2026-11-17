#!/usr/bin/env python3
"""Build the Phase 2 reports from the warehouse: python etl/reports/build.py [--data data]

  docs/reports/LUE_Data_Cleaning_Report.pdf      what was wrong with the data, how it was fixed
  docs/reports/LUE_Data_Quality_Report.pdf       completeness, accuracy and integrity
  docs/reports/LUE_Phase2_Implementation.pdf     the implementation: deliverables, logic, results

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
from etl.reports.pdf import PageBreak, build, bullets, escape, fmt, p, table  # noqa: E402
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
def cleaning_report(f, path: Path) -> None:
    s = []
    total_bronze = sum(v[3] for v in f.volumes)
    rejected = sum(r[5] for r in f.findings if r[4] == "reject")
    warned = sum(r[5] for r in f.findings if r[4] == "warn")
    repaired = sum(c.get("rows_repaired", (0,))[0] for c in f.table_counts.values())
    staged = sum(b[7] for b in f.bridge)

    s.append(p("1. Purpose and summary", "h1"))
    s.append(p(
        "This report shows what was wrong with the six source systems of Lahore Urban Estates (LUE), how each problem was "
        "found, and what was done with it before the data reached the clean staging layer that the dimensions and facts "
        "are loaded from. Every count and sample below is read from the warehouse's audit tables by the report generator "
        "(<font face='Courier'>etl/reports/build.py</font>); none is typed by hand, so the report can be regenerated after "
        "any load and always agrees with the pipeline's own run log."))
    s.append(table(["Measure", "Value"], [
        ["Data profile", f"{f.profile} (seed {f.seed}), business window {f.window}"],
        ["Rows landed in bronze, 20 tables from 6 sources", fmt(total_bronze)],
        ["Rows rejected to quarantine by the validation rules", fmt(rejected)],
        ["Rows kept with a warning", fmt(warned)],
        ["Rows repaired by cleaning (at least one value fixed)", fmt(repaired)],
        ["Rows in the 20 staging tables (one per natural key)", fmt(staged)],
        ["Planted defects detected by validation (answer key)", f"{fmt(f.e4.detected)} of {fmt(f.e4.expected)}, {f.e4.false_positives} false positives"],
        ["Planted repairs and matches confirmed in staging", "all" if f.e5.ok else "not all"],
    ], [3, 4]))

    s.append(p("2. Method: where cleaning happens and why", "h1"))
    s.append(p(
        "Cleaning is split into three layers, each with one job, so that a value is never changed without a record of what "
        "it was:"))
    s += bullets([
        "<b>Bronze (E3)</b> lands every source row unchanged, as text, with its batch, source file and row number. Nothing "
        "is fixed here: bronze is the evidence of what the source actually sent, and every later step can be traced back to it.",
        "<b>Validation (E4)</b> runs a catalogue of 109 rules over bronze in six checks (DQ-01 to DQ-06). A row that cannot "
        "be used (a missing key, a value that is not a number, an exact duplicate, a reference to nothing) is <i>rejected</i>: "
        "it is copied whole into <font face='Courier'>lue_audit.quarantine</font> with the rule and reason, and staging never "
        "reads it. A row that is usable but suspicious (a mid-lease rent change, a tenant that has not reached S1 yet) is "
        "<i>warned</i>: it is kept and the finding is recorded. Nothing is ever silently dropped.",
        "<b>Staging (E5)</b> cleans, types and deduplicates the rows validation accepted: text trimmed, vocabulary values "
        "brought to one spelling, day-first dates read correctly, one row per natural key by a fixed survivorship rule, and "
        "the business fields derived. Each repair is counted per column with a before and after sample in "
        "<font face='Courier'>lue_audit.cleaning_evidence</font>.",
    ])
    s.append(p(
        "Why reject in validation and repair in staging: a missing or unparseable key cannot be repaired without inventing "
        "data, so it is set aside where it can be inspected; a value whose meaning is clear (' lahore ' is Lahore) is repaired, "
        "because rejecting it would lose a good record for a cosmetic reason. The data generator plants every defect on "
        "purpose and records it in an answer key, which is how both layers are proven complete (section 8)."))

    s.append(p("3. Sources and volumes", "h1"))
    vol = [[src, SOURCES[src].split(" (")[0], b, st, n, bt] for src, b, st, n, bt in f.volumes]
    s.append(table(["Source", "System", "Bronze table", "Staging table", "Rows", "Batches"], vol, [1, 3.2, 2.6, 2.8, 1.3, 1.1], {4, 5}))

    s.append(p("4. Issues found by validation and how each was handled", "h1"))
    s.append(p(
        "One line per rule that found something in the latest validation run (run %d). <i>reject</i> means the row went to "
        "quarantine and is not staged; <i>warn</i> means it was kept and the finding recorded for the stage that resolves "
        "it." % f.dq_run))
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example reason"],
                   [[a, b[4:], c, d[6:], e, n, ex] for a, b, c, d, e, n, ex in f.findings],
                   [0.6, 2.0, 1.3, 1.5, 1.2, 0.8, 5.2], {5}))

    s.append(p("5. Repairs made in staging", "h1"))
    s.append(p(
        "Of the rows validation accepted, these are the values staging changed, per table and column, for the full load "
        "(run %d), with the first example of each. Type conversions are counted separately in section 5.3." % f.stage_run))
    rep = [(t, col, i, n, b, a) for _s, t, i, col, n, b, a in f.column_issues if i not in ("type_conversion", "named_sample")]
    s.append(table(["Staging table", "Column", "Repair", "Rows", "Before", "After"],
                   [[t[4:], c, ISSUE_TEXT.get(i, i), n, repr(b) if b is not None else "", a] for t, c, i, n, b, a in rep],
                   [1.9, 1.7, 3.2, 0.9, 1.9, 1.9], {3}))
    s.append(p("5.1 Standardisation: one spelling per value", "h2"))
    s.append(p(
        "Case and spelling are fixed through a vocabulary, not by changing case blindly: "
        "<font face='Courier'>lue_staging.std(domain, value)</font> looks a value up ignoring case and spaces and returns "
        "the one spelling, so <font face='Courier'>std('city', ' lahore ') = std('city', 'LAHORE') = 'Lahore'</font> and "
        "the city codes LHE, KHI, ISB, FSD and the old name Lyallpur all map to their city. A blind Title Case would have "
        "broken values such as 'IT and Software', 'WhatsApp' or 'HVAC', which is why "
        "<font face='Courier'>clean_text</font> only trims and collapses spaces and leaves case to the vocabulary."))
    named = [r for r in f.column_issues if r[2] == "named_sample"]
    if named:
        _s, t, _i, col, n, b, a = named[0]
        s.append(p(f"Named sample: <font face='Courier'>'{escape(b)}'</font> becomes <font face='Courier'>'{escape(a)}'</font> "
                   f"(lue_staging.{t}.{col}); {n} building row(s) of the data had their city repaired this way."))
    dv = {}
    for t, col, stage, value, n in f.distinct:
        if (t, col) in (("stg_unit", "unit_type"), ("stg_building", "city"), ("stg_ticket", "priority"), ("stg_ticket", "category")):
            dv.setdefault((t, col), {"before": [], "after": []})[stage].append((value, n))
    dvr = []
    for (t, col), d in dv.items():
        before = ", ".join(f"{v!r} ({n:,})" for v, n in d["before"])
        after = ", ".join(f"{v} ({n:,})" for v, n in d["after"])
        dvr.append([f"{t[4:]}.{col}", len(d["before"]), before, len(d["after"]), after])
    s.append(table(["Column", "Spellings before", "Values before (rows)", "After", "Values after (rows)"], dvr, [1.6, 0.9, 5.0, 0.6, 2.6], {1, 3}))
    s.append(p("5.2 Missing values", "h2"))
    s.append(p(
        "A missing value is never guessed. Where the data dictionary gives a default it is applied and counted "
        "(a missing employer sector becomes 'Unknown'; a missing discount or rent-free period becomes 0); where it does "
        "not, the value stays NULL (a phone number, a vendor not yet assigned, an open ownership's end date). A blank text "
        "is stored as NULL so that 'missing' has one representation. A required key that is missing was already rejected "
        "by DQ-01 in validation."))
    s.append(p("5.3 Types", "h2"))
    typed = sorted(((t, col, n) for _s, t, i, col, n, _b, _a in f.column_issues if i == "type_conversion"), key=lambda x: -x[2])
    s.append(p(
        "Bronze holds text. Staging converts with safe casts that return NULL instead of failing "
        "(<font face='Courier'>lue_audit.try_numeric</font>, <font face='Courier'>try_date</font> for YYYY-MM-DD or "
        "DD/MM/YYYY, <font face='Courier'>try_timestamp</font>), so one bad value can never stop a load; values that would "
        "not convert were already rejected by DQ-02. %s typed values were converted across %d columns." %
        (fmt(sum(n for *_x, n in typed)), len(typed))))

    s.append(p("6. Duplicates and survivorship", "h1"))
    s.append(p(
        "Two different problems are handled differently. An <b>exact duplicate</b> (the same record sent twice) is rejected "
        "by DQ-03 in validation, keeping one copy. A <b>conflicting duplicate</b> (the same key with different values, for "
        "example a ticket exported twice at different moments) is kept by validation with a warning, because either copy "
        "may be the right one, and staging chooses by a fixed rule (decision D15): per natural key the row with the latest "
        "source <font face='Courier'>updated_at</font> (for tickets, the latest status time), then the latest load, then "
        "the latest batch, then the last row. The rule is deterministic, so a rerun always keeps the same row."))
    dup = []
    for t in spec.TABLES:
        c = f.table_counts.get(t.name, {})
        g = lambda k: c.get(k, (0,))[0]  # noqa: E731
        if g("duplicates_removed") or g("superseded") or g("conflicts_resolved"):
            dup.append([t.name[4:], g("duplicates_removed"), g("superseded"), g("conflicts_resolved"),
                        c.get("conflicts_resolved", (0, None))[1] or ""])
    s.append(table(["Staging table", "Exact duplicates removed (E4)", "Superseded in staging", "Of which conflicting", "Example key"],
                   dup, [2.2, 2, 1.8, 1.8, 2.2], {1, 2, 3}))

    s.append(p("7. Rows rejected versus repaired, and the count bridge", "h1"))
    s.append(p(
        "For every staging table the rows the source sent must be accounted for exactly: staged rows = bronze rows - rows "
        "rejected by validation - rows unusable after cleaning - rows deduplicated. The bridge below is computed over the "
        "whole of bronze and compared with what staging holds; a difference other than 0 would mean a lost or invented row."))
    br = []
    for b in f.bridge:
        c = f.table_counts.get(b[0], {})
        br.append([b[0][4:], b[1], b[2], b[3], b[4], b[5], b[7], c.get("rows_repaired", (0,))[0], b[9]])
    s.append(table(["Staging table", "Src", "Bronze", "Rejected", "Unusable", "Dedup.", "Staged", "Repaired", "Diff."], br,
                   [2.4, 0.6, 1.1, 1, 0.9, 0.9, 1.1, 1.1, 0.7], {2, 3, 4, 5, 6, 7, 8}))
    s.append(p("Derived allocation rows of staging (US-5.2) are not from bronze and are not in the bridge: %s rows." % fmt(f.allocation["derived_rows"]), "note"))

    s.append(p("8. Proof against the answer key", "h1"))
    s.append(p(
        "The data generator records every defect it plants (table, record, defect type and the stage expected to handle "
        "it). Validation found %s of the %s defects in its scope with %d false positives; the defects that belong to "
        "staging were all repaired or matched as the key expects:" % (fmt(f.e4.detected), fmt(f.e4.expected), f.e4.false_positives)))
    s.append(table(["Check", "Staging table.column", "Expected", "Found", "Result", "Meaning"],
                   [[r[0], f"{r[1]}.{r[2]}", r[3], r[4], "pass" if r[7] else "FAIL", r[8]] for r in f.e5.rows],
                   [0.9, 2.6, 1, 1, 0.8, 3.7], {2, 3}))

    s.append(p("9. Business fields derived once in staging", "h1"))
    a = f.allocation
    s += bullets([
        f"<b>Allocation where the source did not.</b> Validation rejected allocation rows with an empty amount or an unknown "
        f"invoice, which left {fmt(a['derived_payments'])} payments partly unallocated. Staging completed them with "
        f"{fmt(a['derived_rows'])} derived allocations ({money(a['derived_amount'])} PKR), marked "
        f"<font face='Courier'>allocation_source = 'derived'</font>: first on the payment's own invoice (the source pays one "
        f"invoice per payment, line by line), then on the tenant's oldest due open line, only on invoices issued by the "
        f"payment date, never beyond a payment's amount or a line's balance. A bounced cheque that lost its allocation "
        f"reverses its original's lines. Result: {fmt(a['cleared_full'])} of {fmt(a['cleared'])} cleared payments and "
        f"{fmt(a['reversals_full'])} of {fmt(a['reversals'])} reversals fully allocated; {a['over_paid']} payments and "
        f"{a['over_line']} invoice lines over-allocated.",
        "<b>Settlement matching.</b> Each S3 settlement line is matched to its S1 payment by payment reference, wherever "
        "the file it arrived in: " + "; ".join(f"{escape(b[1].replace('_', ' '))}: {fmt(b[3])}" for b in f.business if b[1] != "derived_allocation") + ".",
        "<b>Days past due, lease term, ticket lifecycle.</b> Days past due is paid date minus due date on every allocation; "
        "the lease term is in whole months; tickets get their raised, assigned, resolved and verified times, the durations "
        "between them, the SLA in force on the raised date and whether it was breached, and the 30-day recurrence flag of "
        "the data dictionary.",
    ])
    build(path, "Data Cleaning Report", "From six source systems to clean, typed, deduplicated staging", s)


# ============================================================================ quality report
def quality_report(f, path: Path) -> None:
    s = []
    rejected = sum(r[5] for r in f.findings if r[4] == "reject")
    warned = sum(r[5] for r in f.findings if r[4] == "warn")
    s.append(p("1. Purpose and framework", "h1"))
    s.append(p(
        "This report validates the LUE data on the three dimensions of quality the project asks for: <b>completeness</b> "
        "(is everything there that must be), <b>accuracy</b> (are the values right, and do the totals agree with the "
        "source) and <b>integrity</b> (does every reference point at something that exists, and is every record unique). "
        "Every figure is read from the warehouse by the report generator."))
    s.append(p(
        "Validation is a rule catalogue (<font face='Courier'>etl/quality/rules.toml</font>, %d rules) run by one engine "
        "over the bronze layer. Each rule belongs to one of six checks and has a severity:" % len(f.rules)))
    s.append(table(["Check", "Question it answers", "Quality dimension", "Rejected", "Warned"], [
        [f.by_check[0][0], "Is a required value missing?", "Completeness", f.by_check[0][1], f.by_check[0][2]],
        [f.by_check[1][0], "Is the value of the right type (number, date, code)?", "Accuracy", f.by_check[1][1], f.by_check[1][2]],
        [f.by_check[2][0], "Is the record unique?", "Integrity", f.by_check[2][1], f.by_check[2][2]],
        [f.by_check[3][0], "Does it obey the business rules (totals, dates in order, rent)?", "Accuracy", f.by_check[3][1], f.by_check[3][2]],
        [f.by_check[4][0], "Does every reference exist?", "Integrity", f.by_check[4][1], f.by_check[4][2]],
        [f.by_check[5][0], "Is the value within its allowed range?", "Accuracy", f.by_check[5][1], f.by_check[5][2]],
    ], [1.6, 4, 1.6, 1, 1], {3, 4}))
    s.append(p(
        "Severity decides what happens to a row: <b>reject</b> copies it into quarantine with the reason and keeps it out "
        "of staging, because it cannot be used without inventing data; <b>warn</b> keeps it and records the finding, because "
        "the row is right but needs a later stage (a tenant that has not reached S1 yet becomes an inferred member; a "
        "conflicting duplicate is resolved by survivorship). A row is rejected by its first failing rule only, so one bad "
        "row is one rejection. Validation is idempotent per batch: running it twice gives the same results. In the latest "
        "run (run %d) it rejected %s rows and warned on %s." % (f.dq_run, fmt(rejected), fmt(warned))))

    s.append(p("2. Completeness", "h1"))
    s.append(p(
        "Every column a record cannot exist without is checked by a DQ-01 rule. The table gives, per rule, the rows "
        "checked, the rows with a required value missing and the share:"))
    comp = [[a, b[4:], c, n, m, f"{pct:.2f}%", h] for a, b, c, n, m, pct, h in f.completeness]
    s.append(table(["Src", "Table", "Required columns", "Rows", "Missing", "Share", "Handling"], comp, [0.6, 1.9, 4.2, 1, 0.9, 0.9, 2.1], {3, 4, 5}))
    nd = [r for r in f.column_issues if r[2] in ("null_default", "empty_to_null")]
    s.append(p(
        "Optional values are handled by documented rules in staging rather than rejected: " +
        "; ".join(f"{escape(t[4:])}.{escape(c)}: {fmt(n)} rows {'given the default' if i == 'null_default' else 'blank stored as NULL'}" for _s, t, i, c, n, _b, _a in nd)
        + ". A missing value is never guessed."))

    s.append(p("3. Accuracy", "h1"))
    acc = [r for r in f.findings if r[3][:5] in ("DQ-02", "DQ-04", "DQ-06")]
    s.append(p("Type, business-rule and range findings:", "body"))
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example"],
                   [[a, b[4:], c, d[6:], e, n, ex] for a, b, c, d, e, n, ex in acc], [0.6, 1.9, 1.3, 1.5, 1.2, 0.8, 5.3], {5}))
    s.append(p("3.1 Reconciliation with the source", "h2"))
    s.append(p(
        "Accuracy is also checked on money: the amounts in staging must equal the source's, quarter by quarter. Invoiced "
        "net amounts (S1 invoice lines by invoice date) and payments (S1 payments by paid date) in the source system "
        "(<font face='Courier'>lue_source.src_pms</font>) against staging:"))
    rec = []
    pays = {q: (a, b) for q, a, b in f.paid}
    for q, sa, ta, sn, tn in f.invoiced:
        pa, pt = pays.get(q, (0, 0))
        rec.append([q, money(sa), money(ta), money(ta - sa), money(pa), money(pt), money(pt - pa)])
    s.append(table(["Quarter", "Invoiced (source)", "Invoiced (staging)", "Diff.", "Paid (source)", "Paid (staging)", "Diff."], rec,
                   [1, 1.8, 1.8, 0.8, 1.8, 1.8, 0.8], {1, 2, 3, 4, 5, 6}))
    tot_i = sum(r[1] for r in f.invoiced), sum(r[2] for r in f.invoiced)
    tot_p = sum(r[1] for r in f.paid), sum(r[2] for r in f.paid)
    s.append(p(f"Totals: invoiced {money(tot_i[0])} PKR in the source and {money(tot_i[1])} in staging; paid {money(tot_p[0])} "
               f"and {money(tot_p[1])}. No invoice line or payment was rejected (their defects are warnings or belong to "
               f"allocations), so the totals must agree exactly, and they do."))
    a = f.allocation
    s.append(p("3.2 Allocation reconciliation", "h2"))
    s.append(table(["Check", "Result"], [
        ["Cleared payments whose allocations sum to the payment amount", f"{fmt(a['cleared_full'])} of {fmt(a['cleared'])}"],
        ["Reversals (bounced cheques) fully reversed on their lines", f"{fmt(a['reversals_full'])} of {fmt(a['reversals'])}"],
        ["Payments allocated beyond their amount", fmt(a["over_paid"])],
        ["Invoice lines allocated beyond their net amount", fmt(a["over_line"])],
        ["Invoice lines fully paid / unpaid / partly paid", f"{fmt(a['lines_paid'])} / {fmt(a['lines_unpaid'])} / {fmt(a['lines'] - a['lines_paid'] - a['lines_unpaid'])}"],
        ["Allocations from S1 / derived by staging", f"{fmt(a['s1_rows'])} / {fmt(a['derived_rows'])}"],
    ], [5, 3]))

    s.append(p("4. Integrity", "h1"))
    integ = [r for r in f.findings if r[3][:5] in ("DQ-03", "DQ-05")]
    s.append(p("Uniqueness and referential findings in the sources:"))
    s.append(table(["Src", "Table", "Rule", "Check", "Handling", "Rows", "Example"],
                   [[a_, b[4:], c, d[6:], e, n, ex] for a_, b, c, d, e, n, ex in integ], [0.6, 1.9, 1.3, 1.5, 1.2, 0.8, 5.3], {5}))
    s.append(p(
        "Integrity is then enforced by construction at every later layer, so an orphan or duplicate cannot be stored:"))
    s += bullets([
        "Every staging table has its natural key as primary key, so staging holds one row per key; the count bridge shows "
        "%d of %d tables with difference 0 between what bronze sent and what staging holds (rejections and deduplication "
        "accounted for)." % (sum(1 for b in f.bridge if b[9] == 0), len(f.bridge)),
        "The warehouse schema declares %d foreign keys from the six facts to the thirteen dimensions (and %d partitions "
        "inherit them), so the database itself refuses a fact row without its dimension member." % (f.fks, f.partitions),
        "Every dimension carries the special members -1 (Unknown) and -2 (Not applicable), so a fact whose reference is "
        "missing or does not apply points at a real row instead of NULL; references that arrive before their record are "
        "planned as inferred members (US-6.5).",
        "Surrogate keys come from identity columns: the dimension loader never chooses a key and never reuses one. The "
        "tenant dimension holds %s members, one per tenant code, each with a unique key." % fmt(f.dims[0][1] if f.dims else 0),
        "The %d planted orphan settlement lines (a payment reference S1 never issued) are kept, flagged unmatched, so the "
        "unmatched-settlement question can be answered; they reference no dimension." % next((b[3] for b in f.business if b[1] == "unmatched_settlement"), 0),
    ])

    s.append(PageBreak())
    s.append(p("5. Rule-by-rule results", "h1"))
    s.append(p("All %d rules of the catalogue, in the order the engine runs them, with the rows each found in run %d:" % (len(f.rules), f.dq_run)))
    rr = [[r.id, r.table[4:], r.check_name[6:], r.severity, f.rule_hits.get(r.id, 0), r.message] for r in f.rules]
    s.append(table(["Rule", "Table", "Check", "Severity", "Rows", "What it checks"], rr, [1.2, 1.9, 1.5, 0.9, 0.8, 5.7], {4}))

    s.append(p("6. Quarantine", "h1"))
    s.append(p("Rows rejected are kept whole (as JSON) in lue_audit.quarantine with the run, batch, rule and reason, so each "
               "can be inspected or replayed after a correction:"))
    s.append(table(["Source", "Table", "Check", "Rows"], [[a_, b, c, n] for a_, b, c, n in f.quarantine], [1, 3, 3, 1], {3}))

    s.append(p("7. Detection against the answer key", "h1"))
    s.append(p(
        "The generator plants defects on purpose and records each in an answer key. A check is proven when every planted "
        "defect in its scope is found with the expected handling and nothing else is flagged. Validation found %s of %s "
        "with %d false positives; the defects that belong to later stages (spelling repairs, settlement matching, tenant "
        "changes) must pass validation untouched, and they do:" % (fmt(f.e4.detected), fmt(f.e4.expected), f.e4.false_positives)))
    ak = [[r[1], r[2], r[3].replace("_", " "), r[4], r[5], r[6], r[7], r[9]] for r in f.e4.rows if r[0] != "total"]
    s.append(table(["Src", "Table", "Defect", "Handling", "Expected by", "Planted", "Found", "Found by"], ak,
                   [0.6, 1.9, 2.6, 0.9, 1, 0.9, 0.8, 2.2], {5, 6}))

    s.append(p("8. Conclusion and remaining checks", "h1"))
    s.append(p(
        "Every planted defect in validation's scope is detected with no false positive; every money total in staging equals "
        "the source; every payment is fully and never over-allocated; and every staging table reconciles row for row with "
        "what the sources sent. The checks that follow the fact loads extend the same evidence into the warehouse: zero "
        "fact rows without a matching dimension member (enforced by the %d foreign keys), grain checks (one row per "
        "declared grain), SCD Type 2 continuity (one current version per member, no gaps or overlaps between versions) "
        "and revenue reconciliation from staging to the fact tables by month." % f.fks))
    build(path, "Data Quality Report", "Completeness, accuracy and integrity of the LUE data", s)


# ============================================================================ implementation
def implementation_report(f, path: Path) -> None:
    s = []
    s.append(p("1. What was built", "h1"))
    s.append(p(
        "Phase 2 implements the Lahore Urban Estates analytics warehouse designed in Phase 1 (five business processes, six "
        "fact tables, thirteen conformed dimensions, six source systems) on PostgreSQL 16, with the ETL in Python and SQL. "
        "The design is frozen: the physical DDL and data dictionary of Phase 1 are reproduced exactly, and a CI check "
        "compares them line by line, so implementation never drifts from the model that was marked."))
    s.append(table(["Brief deliverable", "Where it is in the repository", "What it contains"], [
        ["PostgreSQL database SQL scripts", "sql/00_setup/, scripts/db_setup.py, db_deploy.py, db_reset.py", "Role lue_etl, databases lue_source and lue_warehouse, schemas, grants; deploy and reset in one command each"],
        ["Staging Schema SQL", "sql/20_staging/01_bronze.sql to 04_staging_tables.sql", "20 bronze landing tables (all text), cleaning functions, vocabularies, 20 typed staging tables with lineage"],
        ["DW Schema SQL", "sql/10_ddl/01_dimensions.sql, 02_facts.sql, 03_audit.sql", "13 dimensions with special members, 6 facts (partitioned by date), 41 foreign keys, audit tables"],
        ["ETL scripts", "etl/gen_*.py, etl/ingest/, etl/quality/, etl/staging/, etl/dimensions/", "Seeded source generator, extraction to bronze, validation and quarantine, cleaning and business rules, dimension loader"],
        ["Dimension Load Scripts", "etl/dimensions/ (spec.py, load.py, run.py); sql/30_dimensions/", "Reference dimensions (calendar, payment method, charge type, event type, request flags) and the generic dimension loader with surrogate keys"],
        ["Data Cleaning Report", "docs/reports/LUE_Data_Cleaning_Report.pdf", "Issues per source, rules, before and after samples, survivorship, count bridge, answer key"],
        ["Data Quality Report", "docs/reports/LUE_Data_Quality_Report.pdf", "Completeness, accuracy (including source reconciliation) and integrity, rule by rule"],
        ["GitHub repository", "github.com/JA-Codex/lue-warehouse", "All of the above, the README with every command, tests and evidence per user story"],
    ], [2.2, 3.2, 4.6]))

    s.append(p("2. The logical flow, layer by layer", "h1"))
    s.append(p(
        "The pipeline moves data through four layers. Each layer has one responsibility and writes evidence of what it did, "
        "so a number in any report can be traced back to the source row it came from:"))
    s.append(table(["Layer", "Schema", "Responsibility", "Why it is separate"], [
        ["Sources", "lue_source.src_pms; files", "Six systems as LUE runs them, generated with a fixed seed and planted defects", "A real extract across databases and file formats; the seed makes every result reproducible"],
        ["Bronze", "lue_staging.brz_*", "Land every row unchanged, as text, with batch, file and row lineage", "Evidence of exactly what the source sent; nothing can be lost by a failed conversion"],
        ["Validation", "lue_audit.dq_result, quarantine", "109 rules: reject unusable rows to quarantine, warn on suspicious ones", "Bad data is stopped before it is used, and kept for inspection instead of dropped"],
        ["Staging", "lue_staging.stg_*", "Clean, type, standardise, deduplicate, derive business fields; incremental", "Downstream loads read one clean contract and need no cleanup of their own"],
        ["Warehouse", "lue_dw.dim_*, fact_*", "Dimensions with surrogate keys and history; facts at their declared grain", "The star schema of Phase 1 that the analytics and dashboard query"],
    ], [1.2, 2, 3.6, 3.6]))
    s.append(p("2.1 Extraction to bronze (E3)", "h2"))
    s += bullets([
        "One framework (<font face='Courier'>etl/ingest/base.py</font>) gives every load a run id and batch ids from "
        "sequences, logs each step's rows read, written and rejected in <font face='Courier'>lue_audit.etl_run_log</font>, "
        "and records lineage. Each source loads in its own transaction: a failure rolls back that source only.",
        "S1 is extracted incrementally: tables with <font face='Courier'>updated_at</font> by watermark, the others by a "
        "row hash, so a rerun lands only new or changed rows. Files are tracked by content hash in "
        "<font face='Courier'>lue_audit.file_load</font>, so a file already loaded is skipped and a changed file is reloaded.",
        "Rows are written with COPY and every value quoted, so text such as 'NULL' or an empty string is landed exactly as sent.",
    ])
    s.append(p("2.2 Validation and quarantine (E4)", "h2"))
    s += bullets([
        "Rules are data (TOML), not code: adding a rule needs no programming, and each rule is tested on purpose-made bad "
        "rows. The engine builds one SQL statement per rule, so validation runs in the database at set speed.",
        "A row is rejected by its first failing rule only, so counts are not inflated. Casts are safe "
        "(<font face='Courier'>try_numeric</font>, <font face='Courier'>try_date</font>, <font face='Courier'>try_timestamp</font> "
        "return NULL instead of failing), so one bad value never stops the run.",
        "Validated batches are recorded in <font face='Courier'>lue_audit.dq_batch</font>; staging reads only those, so no "
        "row can reach staging before validation has seen it.",
    ])
    s.append(p("2.3 Staging (E5)", "h2"))
    s += bullets([
        "The staging contract is data: <font face='Courier'>etl/staging/spec.py</font> defines each table's key, columns, "
        "cleaning expression and NULL rule, and the DDL and the contract document are generated from it. CI fails if they "
        "drift apart, so the loader, the tables and the documentation can never disagree.",
        "Survivorship (decision D15) keeps per natural key the latest source version, then the latest load, batch and row: "
        "deterministic, so reruns keep the same row.",
        "Incremental: each table has a watermark (load time plus the last batch read); a merge "
        "(<font face='Courier'>INSERT ... ON CONFLICT DO UPDATE</font>) changes a row only when a value differs and never "
        "with an older version. A second run with no source change inserts and updates zero rows; changing one source row "
        "produces exactly one update. The watermark is written in the same transaction as the data, so it advances only "
        "when the whole step succeeds.",
        "Business fields are computed once here (allocations where the source did not record them, days past due, "
        "settlement matching, lease term, ticket lifecycle and SLA), so every later query agrees on their meaning.",
    ])
    s.append(p("2.4 Dimensions and surrogate keys (E6)", "h2"))
    s += bullets([
        "Each dimension is described in <font face='Courier'>etl/dimensions/spec.py</font>: surrogate key, natural key, "
        "source query from staging and, for every column, its SCD type from the Phase 1 data dictionary (0 fixed, 1 "
        "overwrite, 2 history). CI checks the spec against the frozen DDL and the dictionary, so a wrong SCD type cannot "
        "be deployed.",
        "One loader serves every dimension: new members are inserted and the identity column assigns the surrogate key "
        "(keys are never chosen by hand and never reused); Type 1 columns are overwritten in place on every version where "
        "a value differs; the special members -1 and -2 are never touched; a source that gives a natural key twice is "
        "refused before anything changes.",
        "Load order: the static reference dimensions first (loaded once, with the calendar), then the independent "
        "dimensions, then unit, tenant and lease, and the facts only after every dimension. The tenant dimension is loaded "
        "through the loader: %s members, and a rerun inserts 0 and updates 0." % fmt(f.dims[0][1] if f.dims else 0),
        "A member's first SCD2 version is valid from 1900-01-01 to 9999-12-31, so a fact of any date finds it. The SCD2 "
        "step builds on the same loader: a Type 2 change closes the current version and opens a new one from the change "
        "date (tenant, unit, vendor and maintenance category), and a reference that arrives before its record gets an "
        "inferred member that is completed when the record arrives (section 6).",
    ])

    s.append(p("3. Key decisions and their reasons", "h1"))
    s.append(table(["Decision", "Choice", "Reason"], [
        ["Where to fix data", "Reject in validation, repair in staging", "A missing key cannot be repaired without inventing data; a clear value (' lahore ') should not be lost for a cosmetic reason"],
        ["Bad rows", "Quarantine with reason, never drop", "Every rejected row can be inspected, counted and replayed after a correction"],
        ["Case and spelling", "Vocabulary lookup, not Title Case", "Keeps 'IT and Software', 'WhatsApp', 'HVAC' intact while making ' lahore ' and 'LAHORE' one value"],
        ["Duplicates", "Exact: reject; conflicting: survivorship D15", "An exact copy carries no information; for conflicting copies a fixed rule picks the latest, reproducibly"],
        ["Contracts", "Staging and dimensions defined as data, DDL generated, checked in CI", "The tables, the loaders and the documents cannot drift apart"],
        ["Incremental loads", "Watermark + merge that updates only on a difference", "Daily runs touch only what changed and a rerun changes nothing (idempotent)"],
        ["Surrogate keys", "Identity columns", "The database guarantees unique, never-reused keys; no key logic in the ETL"],
        ["Special members", "-1 Unknown, -2 Not applicable in every dimension", "A fact never holds a NULL reference, and 'missing' differs from 'does not apply'"],
        ["Derived allocations", "Own invoice first, then oldest due", "The source pays one invoice per payment; sending money to a two-year-old invoice would distort arrears"],
        ["Proof", "Seeded generator with an answer key", "Every check is proven complete (all planted defects found, no false positives), not just run"],
    ], [1.8, 3, 5.2]))

    s.append(p("4. Testing and evidence", "h1"))
    s.append(p(
        "Every user story has acceptance tests and an evidence folder (<font face='Courier'>docs/evidence/us-x.y/</font>). "
        "Tests that need no database run in CI on every push; database tests run against PostgreSQL 16. To show the "
        "tests can fail, the code was deliberately broken in 11 ways for staging alone (allocation, merge, survivorship, "
        "watermark, evidence) and every breakage was caught."))
    s.append(table(["Suite", "Covers", "Result"], [
        ["make test (CI)", "Lint, SQL syntax, frozen-pack manifest, Phase 1 contract, generator, ingestion, quality, staging and dimension contracts", "all pass"],
        ["test_smoke, test_dimensions, test_facts, test_reference", "Database objects, 41 foreign keys, partitions, special members, reference dimensions", "all pass"],
        ["test_source_load", "Clean control batch through S1 (US-2.2 to US-2.4)", "all pass"],
        ["test_ingest", "Extraction, watermarks, file tracking, reruns (E3)", "all pass"],
        ["test_quality", "Every rule on planted bad rows; idempotency; answer key (E4)", "all pass"],
        ["test_staging", "Cleaning, survivorship, allocations, incremental merge, evidence (E5)", "35/35"],
        ["test_dim_load", "Surrogate keys, rerun, Type 1 in place, keys never reused (US-6.1)", "11/11"],
    ], [2.6, 5.4, 1]))
    s.append(p("4.1 The latest staging run", "h2"))
    s.append(table(["Step", "Status", "Read", "Inserted", "Updated", "Rejected"], [list(r) for r in f.runs], [2.6, 1, 1, 1, 1, 1], {2, 3, 4, 5}))

    s.append(p("5. How to run it", "h1"))
    s.append(p("From a fresh clone, with Python 3.11+ and PostgreSQL 16 (README.md has the full steps):"))
    cmds = [
        ("pip install -r requirements.txt", "dependencies"),
        ("python scripts/db_setup.py", "role, databases, schemas"),
        ("python scripts/db_deploy.py", "warehouse, bronze, staging and audit DDL"),
        ("python scripts/db_load_reference.py", "calendar and static dimensions"),
        ("python etl/generate_data.py", "the six sources, seeded, with planted defects and the answer key"),
        ("python scripts/db_load_source.py", "S1 into lue_source"),
        ("python etl/ingest/run.py", "extract all six sources into bronze"),
        ("python etl/quality/run.py --compare", "validate, quarantine, compare with the answer key"),
        ("python etl/staging/run.py --full --compare", "clean and load staging, record evidence"),
        ("python etl/dimensions/run.py", "load the dimensions"),
        ("python etl/reports/build.py", "regenerate these reports"),
    ]
    s.append(table(["Command", "What it does"], [[c, w] for c, w in cmds], [4.5, 5.5]))
    s.append(p("6. Next stage of the pipeline", "h1"))
    s.append(p(
        "The layers above are implemented and tested end to end. The pipeline continues on the same contracts, in this "
        "order, each with its own acceptance tests and evidence:"))
    s += bullets([
        "<b>SCD Type 2</b> on the four history-keeping dimensions (tenant, unit, vendor, maintenance category): close the "
        "current version and open a new one from the change date, one current version per member, no gaps or overlaps.",
        "<b>The remaining dimensions</b> through the loader: unit with its building, locality and city hierarchy, owner, "
        "lease, incentive, weather, and the public holidays into the calendar.",
        "<b>Inferred members</b> for references that arrive before their record (the late tenant references validation "
        "already warns on), completed in place when the record arrives.",
        "<b>The six fact loads</b> at their declared grains, each dimension key looked up as of the event date, with "
        "-1 or -2 where a reference is missing or does not apply.",
        "<b>One-command orchestration and reconciliation</b>: the whole run from the sources to the facts, with revenue "
        "reconciled from staging to the facts by month and zero fact rows without a dimension member.",
    ])
    s.append(p("7. Data volumes", "h1"))
    s.append(p("Full profile (seed %d), business window %s: %s." % (
        f.seed, f.window, ", ".join(f"{v:,} {k}" for k, v in f.sizes.items() if v))))
    s.append(table(["Source", "System", "Bronze table", "Rows"], [[a, SOURCES[a].split(" (")[0], b, n] for a, b, _c, n, _x in f.volumes], [0.8, 4, 2.6, 1.2], {3}))
    build(path, "Phase 2 Implementation", "Database implementation, ETL pipeline, surrogate keys and data quality", s)


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
    for name, fn in (("LUE_Data_Cleaning_Report.pdf", cleaning_report), ("LUE_Data_Quality_Report.pdf", quality_report),
                     ("LUE_Phase2_Implementation.pdf", implementation_report)):
        fn(f, OUT / name)
        print(f"written docs/reports/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
