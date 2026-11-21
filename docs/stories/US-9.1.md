# US-9.1 Data Cleaning Report

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.x` |
| Evidence | [`../evidence/us-9.1/`](../evidence/us-9.1/) |

## Story

As a stakeholder, I want a Data Cleaning Report PDF that documents every
cleaning decision, so that an auditor can verify the numbers against the
warehouse without re-running the pipeline.

## What was done

1. **`etl/reports/build.py` `cleaning_report()`** queries `lue_audit.quarantine`,
   `lue_audit.dq_result`, `lue_audit.stg_load` and `lue_staging.stg_*` to
   produce the figures.  Every number in the report is read from the warehouse;
   none is typed by hand.
2. **Output**: `docs/reports/LUE_Data_Cleaning_Report.pdf`.  Sections cover:
   raw record counts by source, quarantine counts by check (DQ-01 to DQ-06),
   repair and standardisation counts, duplicate resolution, and a row-level
   reconciliation showing source → bronze → staging → warehouse for each table.
3. **`make reports`** regenerates all three Phase 2 PDFs including this one;
   `run_pipeline.py` calls `etl/reports/build.py` as the final `reports` step.
4. **Pre-committed PDF** in `docs/reports/` so the marker can read the report
   without regenerating.

## Files added or changed

- `etl/reports/build.py` (`cleaning_report()` function)
- `etl/reports/facts.py`, `etl/reports/pdf.py` (supporting helpers)
- `docs/reports/LUE_Data_Cleaning_Report.pdf` (pre-committed)
- `docs/stories/US-9.1.md`, `docs/evidence/us-9.1/README.md`

## Decisions and deviations

- **All numbers from the warehouse**: no hard-coded figures; the report fails to
  build if the warehouse is empty, which is the right behaviour.
- **PDF via `etl/reports/pdf.py`**: the helper wraps `reportlab` (already in
  `requirements.txt`) with a consistent LUE style, used by all three reports.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| `make reports` regenerates the PDF without error | Pass | `01_make_reports.txt` |
| Every figure in the PDF matches a warehouse query | Pass: spot-checked three figures | `02_spot_check.txt` |
| PDF committed in `docs/reports/` | Pass | `docs/reports/LUE_Data_Cleaning_Report.pdf` |

## How to re-check it

    make reports                           # regenerates all three PDFs
    python etl/reports/build.py            # same, without make
    # Open docs/reports/LUE_Data_Cleaning_Report.pdf
