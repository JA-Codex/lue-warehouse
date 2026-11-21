# US-7.3 Load fact_unit_occupancy_daily

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-21 |
| Branch and pull request | `e7-facts` (one pull request for US-7.1 to US-7.6, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-7.3/`](../evidence/us-7.3/) |

## Story

As an operations analyst, I want one row per unit per day, so that occupancy, vacancy duration and arrears can be
tracked over time.

## What was done

1. **Every unit, every day** (plan step 1): `generate_series` over the days of the data window
   (2023-07-01 to 2026-06-30, the generator's window, fixed: never today's date) for every staged unit, with the
   lease active that day LEFT JOINed (`start_date <= day <= end_date`; `end_date` is the actual end, a termination
   included), so vacant days keep their row.
2. **Keys and measures of the day** (step 2): the unit version valid that day; the lease and the lease's tenant in
   the version valid that day, or -2 (Not applicable) for both when vacant; the unit's owner that day from the
   ownership register; `is_occupied` 1 or 0; `contract_rent` the lease's monthly rent, 0 when vacant.
3. **Arrears without correlated subqueries** (step 3): once per run, per lease, the days its balance changes: a
   line's net amount counts from the day after it is due, a payment against it from the later of that day and the
   paid date (a reversal adds back). `sum() OVER (PARTITION BY lease ORDER BY day)` turns these into balances, each
   valid until the next change (`lead`), so a day's arrears is a range join. `current_lease_arrears` is the open
   overdue balance of the lease active that day, 0 when vacant (the dictionary's definition); semi-additive.
4. **Partition by partition** (step 4): the US-7.1 loader runs once per month of the window, and every statement
   names the month's key range, so each pass touches one partition (pruning). Set-based SQL only; no secondary
   indexes (D20). A unit key of -1 would collide in the primary key, so it is refused, not loaded.
5. **The 35-day refresh** (step 5, NFR-08, D14): after the monthly pass the last 35 days of the window are deleted
   and re-derived every run. The rewritten rows are reported as "refreshed" and in the run log's `rows_updated`,
   never hidden; with no source change their values hash identically.
6. **Duration** (step 6): the full load takes 97 s on the full profile (1,972,800 rows), a rerun 36 s; both are in
   `lue_audit.etl_run_log`. Each run also reconciles unit-days by month (units x days) to `lue_audit.reconciliation`.

## Files added or changed

- `etl/facts/spec.py` (the snapshot: `period`, `refresh_days`, `prepare`, `resolved`), `etl/facts/keys.py`
  (`DATA_WINDOW`), `etl/facts/load.py` (month-by-month loading, the refresh), `etl/facts/run.py` (`--fact`, the
  refreshed column)
- `scripts/test_fact_load_contract.py` (17 checks), `scripts/test_fact_load.py` (31 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **The monthly pass syncs every month each run**, as for the other facts, so a change anywhere in history (a new
  tenant version, a corrected invoice) reaches the snapshot; the 35-day refresh then re-derives the recent days as
  NFR-08 asks. Together they keep the snapshot equal to its sources; a rerun with no change writes only the refresh.
- **JIT is off for this step** (`SET LOCAL jit = off`): compiling each of the 36 month queries cost about 0.8 s and
  saved nothing; the rerun went from 112 s to 36 s.
- **`python etl/facts/run.py --fact NAME`** loads only the named facts (repeatable); the tests use it so the money
  fact checks do not reload the snapshot.
- Arrears belong to the lease active that day, so a departed tenant's debt leaves the snapshot with the lease (the
  Phase 1 limitation); the invoice and payment facts keep it.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Row count equals units times days in the fixed window ending 2026-06-30 | Pass: 1,800 x 1,096 = 1,972,800, zero duplicates, nothing outside the window; 36 of 36 months reconcile | `01_` (queries 3 to 5) |
| Full load duration is recorded and acceptable on a laptop | Pass: 97 s for the full load, 36 s for a rerun, in the run log | `01_` (runs 1 and 2) |
| A late payment backdated within 35 days corrects the arrears after a refresh | Pass: PKR 10,000 paid on 2026-06-20 lowers the lease's arrears from that day (1,735,244.00 to 1,725,244.00), earlier days unchanged | `02_` (US-7.3) |
| A refresh with no changes yields identical values | Pass: 63,000 rows refreshed, content hash identical | `02_` (US-7.3) |
| Evidence: grain check, load duration, before and after refresh arrears for one unit | Pass | `01_`, `02_` |

## How to re-check it

    python scripts/test_fact_load_contract.py                    # no database: expect 17/17
    python etl/facts/run.py --fact fact_unit_occupancy_daily     # about 1.5 minutes the first time
    python scripts/test_fact_load.py                             # expect 31/31 (about 6 minutes)
