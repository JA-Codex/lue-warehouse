# US-8.4 Run at full volume and record baseline timings

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e8-pipeline` (one pull request for US-8.1 to US-8.4, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.4/`](../evidence/us-8.4/) |

## Story

As a performance owner, I want a full-volume run with per-step timings, so that we know where time goes and have a
baseline for Phase 3.

## What was done

1. **Generate and run end to end**: `make rebuild PROFILE=full` (reset, generate the full profile, run the pipeline),
   with the duration and the four row counts of every step in `lue_audit.etl_run_log`.
2. **The two slowest steps, and the fix.** The first full run took 598 s; validation alone took 309 s, although the
   same validation run on its own took 32 s. The cause: it ran straight after the bulk ingest, before PostgreSQL had
   statistics on the 467,406 new rows, so the planner chose nested loops. `ANALYZE` first (1.4 s) brings it to 33 s.
   Each layer now refreshes the statistics of what it reads after a bulk load: validation its bronze tables, staging
   its tables when it ends, the dimensions theirs, the fact tests the facts. The same findings come out (6,975 rows
   flagged, 5,636 rejected).
3. **The baseline** (the full profile on the project's build machine; see the evidence for every step):

   | Stage | Seconds | Share |
   |---|---:|---:|
   | generate | 16 | 6% |
   | setup, deploy, reference, source | 1 | 0% |
   | ingest (467,406 rows) | 14 | 5% |
   | validate (109 rules) | 32 | 12% |
   | transform (20 staging tables) | 80 | 31% |
   | dimensions | 0 | 0% |
   | facts (2,264,523 rows) and the 71 fact tests | 118 | 45% |
   | reconcile (194 measure-months) | 0 | 0% |
   | **pipeline** | **279** | |

   The two slowest steps are now the occupancy snapshot (76 s for 1,972,800 rows, set-based, one partition at a time)
   and validation (32 s); neither has an obvious remaining problem. **Target**: a full rebuild in under 10 minutes on a
   laptop; measured here 280 s, the reset included. A rerun on unchanged data takes about 100 s (US-8.3).
4. **Volume**: the six facts hold 2,264,523 rows, 226 times the brief's minimum of 10,000; the occupancy snapshot alone
   1,972,800.

## Files added or changed

- `etl/quality/engine.py`, `etl/staging/run.py`, `etl/dimensions/run.py`, `etl/facts/run.py` (`ANALYZE` after bulk loads)
- `scripts/test_pipeline_contract.py` (22 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **ANALYZE in each layer, not only in the pipeline**: a layer run on its own (`make validate`) gets the same plans.
- **No secondary indexes** were added (D20): the speed-up comes from statistics alone, so the Phase 3 indexing
  baseline (US-12.2) is unchanged.
- The timings are from the build machine; they are the baseline for Phase 3, not a guarantee for every laptop.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Full-volume run completes | Pass: 51 of 51 steps, exit 0, 280 s | `01_` |
| Reconciliation passes | Pass: 194 of 194 measure-months; 71 of 71 fact tests | `01_` (query 4) |
| Fact row counts exceed the brief minimum of 10,000 by a wide margin | Pass: 2,264,523 (226 times) | `01_` (query 3) |
| Evidence: timing table per step | Pass | `01_` (queries 1 and 2) |

## How to re-check it

    make rebuild PROFILE=full                 # about 5 minutes; ends with RESULT: 51/51 steps without failure
    python scripts/test_pipeline_contract.py  # no database: expect 22/22
