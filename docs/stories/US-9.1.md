# US-9.1 Produce the Data Cleaning Report (PDF)

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-22 |
| Branch and pull request | `e9-reports` (one pull request for US-9.1 to US-9.3) |
| Evidence | [`../reports/LUE_Data_Cleaning_Report.pdf`](../reports/LUE_Data_Cleaning_Report.pdf), [`../evidence/us-9.2/`](../evidence/us-9.2/) |

## Story

As a marker, I want a report showing what was wrong with the data and how it was fixed, so that the cleaning logic is
clearly evidenced.

## What was done

The report (`etl/reports/build.py`, `make reports`) is generated with reportlab from the audit tables
(`etl/reports/facts.py`); it has: the summary; the cleaning process (a diagram); sources and volumes; the issues
found per source with the rule, its handling and an example; the repairs with before and after samples
(`' lahore '` to `'Lahore'`); distinct values before and after; missing values and types; conflicting duplicates and
the survivorship rule; the count bridge from bronze to staging; the derived fields; **the agreement with the run
log** (new); and the answer key check.

Brought up to the pipeline (E8):

1. **The findings of every batch**: a pipeline run validates only new batches (US-8.3), and each batch keeps the
   findings of the run that validated it, so the report reads all of `lue_audit.dq_result` and `lue_audit.quarantine`,
   not only the latest validation run (which after a rerun would have been empty). The answer-key comparison does
   the same (`answer_key.compare(..., None)`).
2. **The run that built staging**: the cleaning evidence is the latest full restage (`make stage FULL=1`), or else
   the first staging run after a reset, the pipeline's first load; before, only a full restage was found, so a
   pipeline-built warehouse gave empty cleaning sections.
3. **Agreement with the run log** (section 9): for every staging table, the rows in the table equal the rows its
   steps inserted according to `lue_audit.etl_run_log`; the rows in quarantine equal the rows the validation runs
   rejected.
4. **No count typed**: the number of rules, sources and tables in the text are computed.
5. `--out` writes the PDFs elsewhere (the test writes to a temporary folder).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Every number is produced by the generator, not typed | Pass: the counts printed are computed; the test checks none is a literal in the generator | `../evidence/us-9.2/01_report_tests.txt` |
| Counts agree with the run log | Pass: 20 of 20 staging tables (rows staged = rows inserted), quarantine 5,636 = 5,636 rejected | the PDF (section 9), the test |
| Evidence: the generated PDF | Pass | `docs/reports/LUE_Data_Cleaning_Report.pdf` |

## How to re-check it

    make rebuild PROFILE=full      # or any loaded warehouse
    make reports                   # rewrites docs/reports/*.pdf
    python scripts/test_reports.py # expect 11/11
