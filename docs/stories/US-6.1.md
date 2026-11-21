# US-6.1 Build the dimension loader pattern and surrogate keys

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-17 |
| Branch and pull request | `e6-dimensions` (one pull request for US-6.1 to US-6.5, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-6.1/`](../evidence/us-6.1/) |

## Story

As a data engineer, I want one reusable loader pattern with surrogate key generation, so that every dimension loads the
same way.

## What was done

1. **The dimensions as data:** `etl/dimensions/spec.py` lists each dimension with its surrogate key, natural key, the
   SQL that gives one row per natural key from the staging contract (`docs/contracts/staging.md`), and each column's
   SCD type from the Phase 1 data dictionary (0 identity, 1 overwrite, 2 history). CI checks the spec against the
   frozen DDL and the dictionary (`scripts/test_dim_load_contract.py`), so a wrong SCD type cannot slip in.
2. **One loader** (`etl/dimensions/load.py`), one transaction per dimension (plan steps 1 and 2):
   - new members: `INSERT ... SELECT ... WHERE NOT EXISTS` (natural key not yet in the dimension); the identity
     column assigns the surrogate key (D6), so keys are never chosen by hand and never reused;
   - Type 1: `UPDATE` the overwrite columns in place where a value differs, on every version of the member;
     Type 2 columns are left to the SCD2 step (US-6.2, US-6.3); the special members -1 and -2 are never touched;
   - a source that gives a natural key twice, or a row without one, is refused: the step fails, nothing changes.
3. **Load order** (step 3): the static dimensions of US-1.4 first (checked, not reloaded), then the independent ones
   (owner, vendor, category, incentive, weather: US-6.3, US-6.4), then unit, tenant and lease. This story loads
   `dim_tenant`; the others join the list in their stories.
4. **Counts in the run log** (step 4): `etl/dimensions/run.py` (`make dims`), one step per dimension in
   `lue_audit.etl_run_log` (rows read, inserted, updated), lineage in `lue_audit.lineage`.
5. **The brief's evidence** (step 5): the tenant business key next to its surrogate key.

## Files added or changed

- `etl/dimensions/{__init__,spec,load,run}.py`
- `scripts/test_dim_load_contract.py` (no database, in `make gen-test`), `scripts/test_dim_load.py` (database)
- `Makefile` (`dims`, `dims-test`), `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **A member's first SCD2 version is valid from 1900-01-01** (to 9999-12-31): a fact of any date finds it. The
  dictionary's "set to load date" applies to the versions a change creates (US-6.2).
- **`batch_id` on a dimension row is the pipeline run** that loaded or last changed it (the dictionary's meaning),
  not a bronze batch.
- **Missing values become 'Unknown'** in the dimension's NOT NULL columns (staging already gives 'Unknown' for a
  missing employer sector, as the dictionary asks).
- Generated SQL from a spec, as in staging (E5), rather than one SQL function per dimension: the same pattern, and the
  spec is checked in CI.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Re-running inserts zero new members | Pass: 3,762 inserted, then 0 inserted and 0 updated; the run log agrees | `01_dimension_runs.txt` |
| Surrogate keys are unique and never reused | Pass: 3,762 unique positive keys from 1; a deleted member comes back with a new key | `01_`, `02_dimension_tests.txt` |
| Evidence: business key versus surrogate key | Pass | `01_` (query 3) |

## How to re-check it

    python scripts/test_dim_load_contract.py   # no database: expect 10/10
    python etl/dimensions/run.py               # twice: the second run inserts 0, updates 0
    python scripts/test_dim_load.py            # expect 11/11 (seconds)
