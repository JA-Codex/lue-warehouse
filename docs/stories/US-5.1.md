# US-5.1 Clean, standardise and deduplicate

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e5-staging` (one pull request for US-5.1 to US-5.4, one commit per story) |
| Evidence | [`../evidence/us-5.1/`](../evidence/us-5.1/) |

## Story

As a data engineer, I want consistent, deduplicated staging tables, so that downstream loads need no further cleanup.

## What was done

1. **One spec for the whole contract:** `etl/staging/spec.py` lists the 20 `stg_` tables: bronze source, natural key,
   survivorship order and, per column, type, the SQL that cleans it from the bronze text, its meaning and its NULL
   rule. `etl/staging/ddl.py` writes from it `sql/20_staging/03_staging_functions.sql`, `04_staging_tables.sql` and
   the contract `docs/contracts/staging.md` (E6 and E7 read only these tables). `ddl.py --check` runs in CI, so the
   files cannot drift from the spec; the loader builds its SQL from the same spec.
2. **Cleaning functions** (plan step 1): `lue_staging.clean_text` (trim, collapse inner spaces, empty or blank to
   NULL) and `lue_staging.std(domain, value)`, which gives the one spelling from the vocabulary, ignoring case and
   spaces: `std('city', ' lahore ') = std('city', 'LAHORE') = 'Lahore'`. Dates (`YYYY-MM-DD` or day-first
   `DD/MM/YYYY`), numbers and timestamps use E4's safe casts (`lue_audit.try_date`, `try_numeric`, `try_timestamp`).
3. **Lookup tables** (step 2): `lue_staging.vocabulary` (17 domains: cities with LHE/KHI/ISB/FSD and Lyallpur, unit
   types, ticket categories, statuses, sectors and others), `lue_staging.city` (city code and region) and
   `lue_staging.payment_method` (names, types, electronic or not, from `etl/reference_data.py`).
4. **NULLs by rule** (step 3), written in the contract per column: a missing employer sector becomes `'Unknown'` (data
   dictionary), a missing discount or rent-free days `0`, optional values stay NULL (phone, vendor until assigned,
   `valid_to` while the ownership lasts). A row whose key is empty after cleaning is not staged and is counted as
   unusable (step Warning).
5. **Deduplication** (step 4, D15): per natural key `ROW_NUMBER()` over the source's `updated_at` descending (units,
   tenants; for tickets the copy's latest status time), then `loaded_at`, `batch_id` and `row_id`. Only rows E4 did
   not reject take part, and only from batches E4 has validated: `etl/quality/engine.py` now records them in
   `lue_audit.dq_batch`, and staging refuses to start while a batch waits for validation.
6. **The tables** (step 5): building, unit, tenant, lease, lease event, invoice, invoice line, payment, allocation,
   settlement, owner, ownership, vendor, maintenance category, holiday, ticket, ticket status, weather, incentive
   offer and incentive log. Each ends with its lineage: `source_system`, `batch_id`, `loaded_at`, `src_row_id` (the
   bronze row that survived), `src_updated_at`, `run_id`, `staged_at`.
7. **The count bridge** per run and table in `lue_audit.stg_load`, and cumulative in `count_bridge.csv`: staged rows =
   bronze rows - rejected by E4 - unusable - deduplicated, with the difference (0) and its explanation.
8. **The runner** `etl/staging/run.py` (`make stage`, `FULL=1` to reload everything): one step per table in the
   pipeline run log, each its own transaction.

## Files added or changed

- Staging: `etl/staging/{spec,ddl,load,business,evidence,answer_key,run}.py`, `sql/20_staging/03_staging_functions.sql`
  and `04_staging_tables.sql` (generated), `docs/contracts/staging.md` (generated).
- Audit: `sql/10_ddl/06_staging_audit.sql` (`dq_batch`, `stg_load`, `cleaning_evidence`); `etl/quality/engine.py`
  (records validated batches); `etl/ingest/base.py` (the run log now gets `rows_updated`, and a step can finish with
  Warning without rejected rows); `scripts/check_contract.py`, `scripts/test_smoke.py` (10 audit tables).
- Tests: `scripts/test_staging_contract.py` (no database, CI), `scripts/test_staging.py` (database);
  `scripts/test_quality.py` empties `dq_batch` with bronze. `Makefile`: `stage`, `staging-test`.

## Decisions and deviations

- **`clean_text` does not change case.** The plan's step 1 puts case in `clean_text`; a blind Title Case would break
  `IT and Software`, `WhatsApp` or `HVAC`. Case and spelling are standardised by `std` through the vocabulary instead,
  and codes are upper-cased. The plan's example holds: ' lahore ' and 'LAHORE' both become 'Lahore'.
- **Tickets have no `updated_at`:** of two copies the one with the latest status time survives (the conflicting
  duplicates of US-2.6). A copy's status entries are those landed from the same file in the same step (same
  `source_file`, `source_row` and `loaded_at`; E3 lands the two tables as two batches). A copy whose Raised entry E4
  rejected is not staged; `stg_ticket_status` holds the history of the surviving copy only.
- **Staging reads only validated batches** (`lue_audit.dq_batch`, new): otherwise a row E4 would reject could reach
  staging before E4 sees it.
- **Re-validation with changed rules** can change which rows are rejected after they were staged. The cumulative
  bridge shows it as a difference; the remedy is `make stage FULL=1`.
- New audit tables (`dq_batch`, `stg_load`, `cleaning_evidence`), not in the pack, like `etl_watermark` and
  `dq_result`; `check_contract.py` allows them.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| No city, unit type or payment method in more than one spelling | Pass: 4 cities, 3 unit types, 6 payment methods, none NULL; no source value outside its vocabulary (15 spellings of unit type before) | `03_distinct_values.csv`, `04_staging_tests.txt` |
| Row counts = bronze - quarantined - deduplicated, the difference explained | Pass: 20 of 20 tables, difference 0 (414 lease events, 4,440 allocations, 361 settlement lines, 390 ticket copies rejected; 60 conflicting ticket copies and 1,614 of their status entries deduplicated) | `02_count_bridge.csv` |
| Survivorship (D15) keeps the latest version | Pass: the 60 planted conflicting ticket pairs; a fixture unit (latest `updated_at` wins whatever the load order) | `04_` |
| Evidence: distinct values before and after; count bridge per table | Pass | `02_`, `03_` |

## How to re-check it

    python scripts/test_staging_contract.py   # no database: expect 36/36
    python etl/staging/run.py --full --compare
    python scripts/test_staging.py            # expect 35/35 (small profile: seconds; full: about 7 minutes)
