# US-8.1 Build run_pipeline.py with logging and lineage

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e8-pipeline` (one pull request for US-8.1 to US-8.4, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.1/`](../evidence/us-8.1/) |

## Story

As an operator, I want one command that runs the entire pipeline with full logging, so that runs are repeatable and
auditable.

## What was done

1. **Ordered stages, one run** (plan step 1): `etl/run_pipeline.py` runs, in the brief's order, generate, setup,
   deploy, reference, source (the S1 extract into `src_pms`), ingest (E3), validate (E4), transform (E5), dimensions
   (E6) and facts with their tests (E7). Each ETL layer's entry point now takes an optional `run`, so all its steps
   join the pipeline's one `run_id`; used alone, each layer behaves as before. Every step writes a start row and an
   end row to `lue_audit.etl_run_log` with its status and the four counts. Generate, setup, deploy and reference
   create the very audit tables the run writes to, so they run first and their rows are recorded as soon as the run
   exists (`Run.record`).
2. **Options** (step 2): `--profile small|full` and `--seed` for the generation, `--skip-generate` to use the data
   already there, `--from-step STAGE` to resume, `--only STAGE[,STAGE]` to run just those stages (in pipeline order),
   and `--data` for another data folder. An unknown stage, or `--only` with `--from-step`, is refused (exit 2).
3. **Critical steps** (step 3): a Failed step stops the run at its stage, lists the stages not run and prints the
   command to resume; the exit code is 1. The S5 weather is the one non-critical step (it may be cut, D19): its
   failure is reported and the run goes on, the weather keys resolving to -1. Bronze that does not reconcile to its
   source (US-3.4) fails the ingest stage; a layer that cannot start (no data, not ready) is a Failed step, not a crash.
4. **Lineage** (step 4): each layer records its links in `lue_audit.lineage`: each source to its bronze tables, bronze
   to staging, staging to the dimensions and to the facts.
5. **make** (step 5): `make rebuild` resets the warehouse (`scripts/db_reset.py`), then generates and runs the
   pipeline (`PROFILE=full` for the full profile); `make pipeline` runs it on the data already in `data/`
   (`FROM=stage` to resume). The setup scripts' output goes to `logs/pipeline_*.log`.

## Files added or changed

- `etl/run_pipeline.py`; `etl/ingest/base.py` (`Run.record`); `etl/ingest/run.py`, `etl/quality/run.py`,
  `etl/staging/run.py`, `etl/dimensions/run.py`, `etl/facts/run.py` (the optional `run`)
- `scripts/test_pipeline_contract.py` (13 checks, in `make gen-test`), `scripts/test_pipeline.py` (10 checks)
- `Makefile` (`rebuild`, `pipeline`, `gen-test`), `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **One run_id across layers** by passing the run to each layer, rather than one run per layer: the run log of a
  pipeline run is then one query.
- **The setup stages run as scripts** (their own command-line programs, unchanged), the ETL layers in process (their
  counts go straight to the run log). The setup stages have no row counts; their status and duration are logged.
- Marts are not built yet (E10); the stage is added there, before the tests of E10.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| One command takes an empty database to a loaded warehouse | Pass: after `db_reset.py`, `python etl/run_pipeline.py --profile small` loads all 13 dimensions and 6 facts; the 71 fact tests pass | `01_` (queries 1 and 2), `02_` |
| The run log shows every step with counts and a final status | Pass: 49 steps in run 1, each ended, Success or Warning, with rows read, inserted, updated and rejected | `01_` (query 3) |
| Evidence: terminal output of a full small-profile run and the run log rows | Pass | `01_` |

## How to re-check it

    python scripts/test_pipeline_contract.py     # no database: expect 13/13
    make rebuild                                 # or: python scripts/db_reset.py, then python etl/run_pipeline.py
    python scripts/test_pipeline.py              # expect 10/10 (resets the warehouse; leaves the small profile loaded)
