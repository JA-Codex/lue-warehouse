# US-9.2 Produce the Data Quality Report (PDF)

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-22 |
| Branch and pull request | `e9-reports` (one pull request for US-9.1 to US-9.3) |
| Evidence | [`../reports/LUE_Data_Quality_Report.pdf`](../reports/LUE_Data_Quality_Report.pdf), [`../evidence/us-9.2/`](../evidence/us-9.2/) |

## Story

As a marker, I want a report covering completeness, accuracy and integrity, so that quality validation is
demonstrated end to end.

## What was done

The report is structured on the brief's three dimensions and generated from the audit tables:

1. **Completeness**: missing required values per table (count and share) and their handling.
2. **Accuracy**: the accuracy rules' findings; source against staging by quarter; the allocation checks; and, new,
   **source to warehouse by month (DQ-07, US-8.2)** from `lue_audit.reconciliation`: per measure (billed, paid,
   tickets, lease events) the months, source, warehouse + quarantined and the unexplained rest, then billed and
   paid month by month.
3. **Integrity**: referential and duplicate findings; the constraints in the database; new, **the facts' grain,
   orphan and value tests (US-7.6)** from `lue_audit.reconciliation`, per fact, with the zero-orphan result stated and
   the query behind it quoted from `sql/90_tests/02_fact_tests.sql`; and **SCD Type 2 continuity** from
   `sql/90_tests/01_dimension_tests.sql` (one current version per key, no gap or overlap, first version from
   1900-01-01, the current one open).
4. The rule-by-rule results, the quarantine summary, the answer-key detection rates.
5. New: **the pipeline run** (the latest complete run of `etl/run_pipeline.py`, failed non-critical steps named) and
   **a conclusion on residual risks**.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| All tables are generated from audit tables | Pass: run log, quarantine, findings, reconciliation, cleaning evidence; the SCD tests are the repository's test queries | `docs/reports/LUE_Data_Quality_Report.pdf`, the test |
| The integrity section states the zero-orphan result with the query behind it | Pass: "Fact rows without a matching dimension row: 0 across all 41 foreign keys", with the query; the test runs that query (0) and checks it is in `02_fact_tests.sql` | the PDF (5.2), `../evidence/us-9.2/01_report_tests.txt` |
| Evidence: the generated PDF | Pass | `docs/reports/LUE_Data_Quality_Report.pdf` |

## How to re-check it

    make reports                    # on a loaded warehouse
    python scripts/test_reports.py  # expect 11/11
