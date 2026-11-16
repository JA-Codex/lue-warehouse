# US-3.1 Build the ingestion framework

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-16 |
| Branch and pull request | `e3-ingestion` (one pull request for US-3.1 to US-3.4, one commit per story) |
| Evidence | [`../evidence/us-3.1/`](../evidence/us-3.1/) |

## Story

As a developer, I want a shared ingestion framework, so that every source loads consistently with logging and error
handling.

## What was done

1. `etl/ingest/base.py`: `Run` (one `run_id` per run from `lue_audit.seq_run_id`) and `Run.step(...)` (one source):
   writes its `etl_run_log` row, gives the ingestor a `Step` with a cursor in the source's transaction, commits the
   source at once or rolls it back. Connections from `.env`, always as `lue_etl`; S1 is read from `lue_source` on a
   separate connection.
2. `Step.land(...)` stamps every row with `batch_id` (from `lue_audit.seq_batch_id`, one per source table or file),
   `source_system` and `loaded_at`, and bulk-loads with `COPY` (`copy_dataframe` does the same for a DataFrame).
3. **Failure handling:** the run log is written on its own autocommit connection, so it survives a rollback. On any
   error the source is rolled back (no partial rows), the step is marked `Failed` with the error logged, and the next
   source still runs.
4. **Structured logging** (`key=value`) to the console and `logs/ingest.log` (ignored by git): step, source, status,
   rows read, written, rejected, seconds.
5. `Step.reconcile(...)` and `Step.lineage(...)` write `lue_audit.reconciliation` and `lue_audit.lineage` (used by
   US-3.2 to US-3.4).
6. DDL: `sql/10_ddl/04_ingest_audit.sql` (the two sequences and `lue_audit.file_load`, see US-3.3) and
   `sql/20_staging/01_bronze.sql` (the 20 bronze tables); `scripts/db_deploy.py` now also runs `sql/20_staging/`.

## Decisions and deviations

- **Bronze is all text.** Every source value is kept as `TEXT` exactly as given (NULL when missing; an empty CSV cell
  stays an empty text). Nothing can fail to land, and DQ-02 (E4) judges the raw value. Bronze only appends.
- **`run_id` per run, `batch_id` per source table or file.** `etl_run_log` has `run_id` and `step`; the quarantine has
  both ids, so both exist.
- **Status `Running`** is written when a step starts and replaced by `Success`, `Warning` (a file rejected, US-3.3) or
  `Failed`. Only a killed process can leave `Running`.
- **Walkthrough (plan step 5):** not held as a meeting; the module docstrings and this file are the hand-over.
- `scripts/check_contract.py` allows the new `lue_audit.file_load`; `scripts/test_smoke.py` now counts 6 audit tables.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A failed load leaves no partial rows in bronze and records the failure | Pass: 5 rows written, 0 kept; run log `Failed` with counts and end time; the next source still runs | `01_framework_tests.txt`, `02_run_log.txt` |
| Every landed row carries the three metadata columns | Pass: NOT NULL in all 20 tables, checked on every row | `01_`, `../us-3.4/01_json_weather_tests.txt` |
| Evidence: run log rows for a success and a forced failure | Pass | `02_run_log.txt`, `03_structured_log.txt` |

## How to re-check it

    python scripts/db_deploy.py
    python scripts/test_ingest.py        # expect 39/39 (all of E3)
