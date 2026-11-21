# US-7.1 Build the fact loading framework and date-aware key mapping

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-21 |
| Branch and pull request | `e7-facts` (one pull request for US-7.1 to US-7.6, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-7.1/`](../evidence/us-7.1/) |

## Story

As a data engineer, I want one tested pattern for turning business keys into surrogate keys, so that every fact
references the correct dimension version.

## What was done

1. **Key mapping, one way for every fact** (`etl/facts/keys.py`, plan step 1):
   - SCD2 dimensions (tenant, unit, vendor, category): `LEFT JOIN dim ON natural_key = business_key AND event_date >=
     effective_from AND event_date < effective_to`, the version valid that day (half-open, as US-6.2 writes them);
   - Type 1 and static dimensions (lease, owner, incentive, payment method, charge type, lease event type): a plain
     join on the natural key;
   - the owner of a unit on a day from the ownership register (`valid_from <= day < valid_to`, an open period has no
     `valid_to`), then `dim_owner`.
2. **Role-playing dates through `dim_date`** (step 2): a date's key is YYYYMMDD inside the calendar
   (2023-07-01 to 2027-06-30); a date outside it or missing is -1. A fact can ask for -2 instead for a milestone not
   reached yet (US-7.4). The loader refuses to start unless `dim_date` holds exactly the 1,461 calendar days, so a
   computed key always exists.
3. **Never drop a row** (step 3): a key that cannot be resolved is -1 (Unknown); the loader counts the -1 keys per
   column, reports them in the run log and makes the step a Warning. A row missing a required measure is counted as
   rejected.
4. **Reruns do not duplicate** (step 4): the facts are data (`etl/facts/spec.py`: grain, columns, one source query
   each) and one loader (`etl/facts/load.py`) makes a fact equal its source, in one transaction per fact: a grain
   twice in the source is refused; then delete the rows whose grain left the source, update in place the rows whose
   values differ, insert the new grains. A rerun inserts, updates and deletes nothing.
5. **The first fact, `fact_payment`**: one row per payment allocation of staging (US-5.2), with the paid and due
   date keys, unit and tenant at the paid date, the lease, the owner on the paid date, the payment method and the
   charge type; reversals stay negative amounts. `etl/facts/run.py` (`make facts`) runs one step per fact in
   `lue_audit.etl_run_log` with lineage. US-7.2 adds the invoice fact and the monthly reconciliation.
6. **The brief's evidence** (step 5): a source payment with its tenant id, the resolved `tenant_key` and the final
   fact row, for a payment before and one after a tenant's change.

## Files added or changed

- `etl/facts/{__init__,keys,spec,load,run}.py`
- `scripts/test_fact_load_contract.py` (no database, in `make gen-test`), `scripts/test_fact_load.py` (database)
- `scripts/test_facts.py` (US-1.3): the identity check allows a loaded fact (its sequence must be past its keys)
- `scripts/test_reference.py` (US-1.4): the holiday flags are either still FALSE or exactly those US-6.4 sets
  from `stg_holiday`; `scripts/test_dim_load.py` (US-6.5) starts the identity sequences again at 1 when it
  empties the dimensions, so `make db-test` also passes after the E6 and E7 tests have run
- `Makefile` (`facts`, `facts-test`, `gen-test`), `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **Sync on the grain instead of `INSERT ... ON CONFLICT`** (plan step 4): the frozen DDL has a unique key on the
  grain of `fact_rent_invoice_line` only; `ON CONFLICT` needs one. Matching on the grain columns in SQL gives the same
  rerun guarantee for every fact, and also removes a row whose source row went away (an allocation moved by a
  late reversal), which `ON CONFLICT` cannot.
- **Staging owns the order of operations**: a fact is rebuilt from staging and the dimensions each run, so a late
  change (a new tenant version, a corrected allocation) reaches the fact on the next run without special cases.
- **A fact row's `batch_id` is the pipeline run** that inserted or last changed it, as for the dimensions.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A payment before a tenant's attribute change maps to the old version; one after maps to the new | Pass: T-0115 changed sector on 2024-10-10; PAY-0025146 (2024-10-05) maps to key 113 (Government), PAY-0027787 (2024-11-10) to 3804 (Healthcare); across the fact, 0 tenant or unit keys outside their version on the paid date | `01_` (queries 4 to 6), `02_` |
| Rerunning inserts zero rows | Pass: 127,210 inserted, then 0 inserted, 0 updated, 0 deleted; the run log agrees | `01_` (runs 1 and 2) |
| Evidence: the key-mapping chain for one payment, and the before and after SCD query | Pass | `01_` (queries 4 and 5) |

## How to re-check it

    python scripts/test_fact_load_contract.py   # no database: expect 9/9
    python etl/facts/run.py                     # twice: the second run inserts 0, updates 0, deletes 0
    python scripts/test_fact_load.py            # expect 10/10 (about a minute)
