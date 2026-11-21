# US-9.2 Data Quality Report

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.x` |
| Evidence | [`../evidence/us-9.2/`](../evidence/us-9.2/) |

## Story

As a stakeholder, I want a Data Quality Report PDF that quantifies completeness,
accuracy and referential integrity, so that the warehouse quality posture is
visible without reading SQL.

## What was done

1. **`etl/reports/build.py` `quality_report()`** queries `lue_audit.dq_result`,
   `lue_audit.reconciliation` and `lue_dw.*` to produce three sections:
   - **Completeness**: not-NULL rates per column per staging table, flagged when
     below 99 %.
   - **Accuracy**: DQ rule pass / fail counts (DQ-01 to DQ-06), overall pass
     rate, quarantine breakdown by check.
   - **Referential integrity**: 41 fact foreign-key orphan counts (from
     `lue_audit.reconciliation` rows written by `sql/90_tests/02_fact_tests.sql`);
     all 71 fact tests listed with their outcome.
2. **Output**: `docs/reports/LUE_Data_Quality_Report.pdf`.
3. **`make reports`** regenerates the PDF; `run_pipeline.py` triggers it as the
   final step.
4. **Pre-committed PDF** in `docs/reports/`.

## Files added or changed

- `etl/reports/build.py` (`quality_report()` function)
- `etl/reports/facts.py`, `etl/reports/pdf.py`
- `docs/reports/LUE_Data_Quality_Report.pdf` (pre-committed)
- `docs/stories/US-9.2.md`, `docs/evidence/us-9.2/README.md`

## Decisions and deviations

- **DQ rule results come from `lue_audit.dq_result`**, populated by E4; the
  report does not re-run the rules, so it is fast.
- **Referential-integrity section** reuses the fact-test rows in
  `lue_audit.reconciliation`; no new queries are added to the report.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| `make reports` regenerates without error | Pass | `01_make_reports.txt` |
| Completeness, accuracy and integrity sections present | Pass | PDF inspection |
| All 71 fact test outcomes listed | Pass: verified in PDF | `02_quality_pdf_check.txt` |

## How to re-check it

    make reports
    python etl/reports/build.py
    # Open docs/reports/LUE_Data_Quality_Report.pdf
