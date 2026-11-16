# US-5.3 Implement incremental loading with watermarks

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e5-staging` (one pull request for US-5.1 to US-5.4, one commit per story) |
| Evidence | [`../evidence/us-5.3/`](../evidence/us-5.3/) |

## Story

As an operator, I want staging to process only new or changed rows, so that daily runs are fast and repeatable.

## What was done

`etl/staging/load.py`, one transaction per table:

1. **Watermark** (plan step 1): per staging table in `lue_audit.etl_watermark` (source_system `STG`). A run reads the
   bronze rows landed after it: `loaded_at > watermark`, or at the watermark's second from a later batch than the
   last one read (`stg_load.batch_to`), so a batch landed in the same second is not skipped and nothing is read twice.
   The source's `updated_at` decides between versions (survivorship), not what is read: bronze is append-only, so
   every new or changed source row arrives as a new bronze row.
2. **Merge** (step 2): `INSERT ... ON CONFLICT (natural key) DO UPDATE ... WHERE` the incoming version is not older
   than the staged one and a value differs (`IS DISTINCT FROM` over every cleaned column). `RETURNING (xmax = 0)`
   tells inserts from updates; the rest are unchanged.
3. **The watermark moves with the data** (step 3): it is written in the step's transaction, so it advances only when
   the whole step commits. Each step runs in `REPEATABLE READ`: the window, the counts and the merge see one snapshot.
4. **Counts** (step 4): `etl_run_log` gets rows read, inserted, updated and rejected per step (the framework now writes
   `rows_updated`); unchanged, superseded and unusable rows are in `lue_audit.stg_load`, where
   read = rejected + unusable + superseded + inserted + updated + unchanged for every table and run.
5. **Guards:** one staging run at a time (an advisory lock); no start while a bronze batch waits for validation or the
   tables differ from the spec.

## Decisions and deviations

- **The watermark is `loaded_at` plus the batch**, not the source's `updated_at`: S1 tables without `updated_at` and
  the file sources need the same rule, and E3 already finds changed rows by row hash (US-3.2).
- **`stg_ticket_status` has no watermark of its own:** it follows `stg_ticket`, reloading the history of the tickets a
  run inserted or changed and removing entries the surviving copy does not have (`rows_deleted`).
- **The run log has no "unchanged" column** (frozen pack); unchanged rows are in `stg_load` and the evidence.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A second run with no source changes inserts and updates zero rows | Pass: 0 and 0 in every step, derived values included; the run log agrees | `01_incremental_runs.txt` |
| Changing one source row results in exactly one update | Pass: one tenant's phone changed in `src_pms`; ingest, validate, stage: `stage_tenant` rows_updated 1, nothing else | `01_` |
| The watermark advances only after the whole step succeeds | Pass: a failing step (year 99999) leaves watermark and table as they were | `02_staging_tests.txt` |
| An older version never replaces a newer one; a same-second batch is read once; a row landed again unchanged is not an update | Pass | `02_` |

## How to re-check it

    python etl/staging/run.py          # twice: the second run inserts 0, updates 0
    python scripts/test_staging.py     # the US-5.3 block: 6 checks
