# US-5.4 Capture cleaning evidence

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e5-staging` (one pull request for US-5.1 to US-5.4, one commit per story) |
| Evidence | [`../evidence/us-5.4/`](../evidence/us-5.4/) |

## Story

As a report author, I want cleaning evidence saved as the pipeline runs, so that the Data Cleaning Report can be
generated rather than reconstructed.

## What was done

1. **`lue_audit.cleaning_evidence`**, written by every staging step in its own transaction
   (`etl/staging/evidence.py`): per run, source, staging table, issue and column the number of rows and one before
   (bronze, as the source wrote it) and after (staging) sample. Column issues, for the rows the run inserted or
   changed: `whitespace`, `case_or_spelling`, `empty_to_null`, `null_default`, `not_in_vocabulary`,
   `date_day_first`, `type_conversion`, and `repaired` (any of them, a row counted once). Table issues (column `*`):
   the run's count bridge (`rows_read`, `rejected_by_dq`, `key_not_usable`, `superseded`, `inserted`, `updated`,
   `unchanged`, `deleted`), `duplicates_removed` (exact duplicates E4 rejected), `conflicts_resolved` (copies that
   differed from the survivor, D15) and `rows_repaired`; after US-5.2 `derived_allocation`, `unmatched_settlement`
   and `unsettled_payment`.
2. **The plan's sample by name:** `named_sample` on `stg_building.city`: `' lahore '` -> `'Lahore'`.
3. **The CSV files**, written at the end of each run to `data/staging_evidence/` (`--evidence` to choose):
   `cleaning_evidence_S1.csv` to `S6` (this run), `count_bridge.csv` (US-5.1, cumulative), `distinct_values.csv`
   (before and after) and, with `--compare`, `answer_key_check.csv`.

## Decisions and deviations

- **Evidence is per run:** a full load holds the whole picture; an incremental run records only what it changed. The
  committed evidence is from a full load of the full profile.
- **Column issues are classified by the whole expression** of the spec, so a flag computed from a column (is_emergency
  from priority) is not counted as a repair of that column.

## Results (full profile, seed 3004, full load)

| Planted in US-2.6 (answer key, expected_rule US-5.1) | Expected | Repaired in staging |
|---|---|---|
| Building city written in another case | 1 | 1 |
| Unit type with spaces or another case | 54 | 54 |
| Ticket priority and category with spaces or another case | 108 + 72 | 108 + 72 (records), every staged copy clean |
| Incentive start date written day first | 19 | 19 |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| An evidence file exists for every source | Pass: S1 to S6 | `cleaning_evidence_S1.csv` to `S6` |
| Counts reconcile to the US-5.1 count bridge | Pass: for all 20 tables read = rejected + unusable + superseded + inserted + updated + unchanged, equal to `stg_load` | `count_bridge.csv`, `../us-5.1/04_staging_tests.txt` |
| Includes the ' lahore ' to 'Lahore' sample by name | Pass | `cleaning_evidence_S1.csv` (`named_sample`) |
| Tests can fail | Pass: deliberate breakages of the E5 code are caught | `05_tests_catch_broken_code.txt` |

## How to re-check it

    python etl/staging/run.py --full --compare   # then open data/staging_evidence/
    python scripts/test_staging.py               # the US-5.4 block: 5 checks
