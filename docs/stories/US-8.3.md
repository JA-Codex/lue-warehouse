# US-8.3 Test idempotency and failure recovery

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e8-pipeline` (one pull request for US-8.1 to US-8.4, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.3/`](../evidence/us-8.3/) |

## Story

As an operator, I want to know the pipeline is safe to rerun and safe to resume, so that failures are never
catastrophic.

## What was done

1. **A rerun changes nothing (D14).** Two full runs on unchanged inputs: in the second, every step reports 0 inserted,
   0 updated and 0 rejected, except the declared occupancy refresh (its last 35 days rewritten: units x 35 rows); the
   content of all 62 tables of bronze, staging and the warehouse hashes identically before and after (each row as JSON,
   without `batch_id`, `loaded_at`, `run_id` and `staged_at`, which say when and by which run, not what).
   Getting there needed one change: the pipeline now validates only the bronze batches not validated yet
   (`quality.unvalidated`). Before, every run validated every batch again and reported its rejected rows again. The
   rules judge a row within its own batch or against whole bronze tables, so the findings are the same;
   `make validate` alone still checks everything, for the answer-key comparison.
2. **A failure leaves no partial rows.** A crash injected inside the `fact_payment` step, after it wrote its rows and
   before its transaction committed: the step rolls back (0 rows), the facts before and after it stay committed, the
   run stops at the facts stage (exit 1) and prints the command to resume.
3. **Resume with `--from-step`.** `python etl/run_pipeline.py --skip-generate --from-step facts` completes, the fact tests
   and the reconciliation pass, and the warehouse is what an uninterrupted run gives (same hashes, the reloaded
   payments' surrogate keys aside: a rolled-back insert uses up identity values).
4. **One warehouse, one generation.** Running the pipeline on other generated data (another profile or seed) on top
   of a loaded warehouse would mix two datasets in bronze. The pipeline records the generation it loaded (the run
   manifest's content hash, profile and seed, in `lue_audit.file_load` as source `GEN`) and stops at
   `check_generation`, before the source or bronze changes, when the data folder holds another one; the message says to
   reset first.
5. **The recovery procedure** is in the README (Recovery).

## Files added or changed

- `etl/run_pipeline.py` (validation of new batches only, the generation check and record), `etl/quality/run.py`
  (`unvalidated`)
- `scripts/test_pipeline_contract.py` (21 checks), `scripts/test_pipeline.py` (21 checks)
- `README.md` (Recovery), `docs/stories/README.md`

## Decisions and deviations

- **The hash leaves out the run-stamp columns** (`batch_id`, `loaded_at`, `run_id`, `staged_at`): the refresh rewrites
  rows with a new run's stamp, D14 asks for identical values.
- **The failure is injected in the test** (a wrapper around the fact loader), not by an option of the pipeline: the
  production code has no way to crash on purpose.
- **The generation record uses `lue_audit.file_load`** (one row per loaded file and checksum): the run manifest is the
  file that names the generation; no table is added.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Second run changes no data (hash-identical) | Pass: 62 tables, 0 differ | `01_` (query 2) |
| It reports zero rows for every step except the declared occupancy refresh | Pass: 49 of 50 steps 0/0/0; fact_unit_occupancy_daily updated 63,000 = 1,800 units x 35 days | `01_` (query 2) |
| A resumed run completes and passes all tests | Pass: the crash left 0 rows of fact_payment; `--from-step facts` exit 0, fact tests and reconciliation passed, 127,210 rows and PKR 5,347,289,709 as staging | `01_` (queries 3 and 4), `02_` |
| Evidence: counts and hashes of the second run; the recovery run log | Pass | `01_` |

## How to re-check it

    python scripts/test_pipeline_contract.py      # no database: expect 21/21
    python etl/run_pipeline.py --skip-generate    # twice: the second run's steps are all 0, but the occupancy refresh
    python scripts/test_pipeline.py               # expect 21/21 (resets the warehouse; leaves the small profile loaded)
