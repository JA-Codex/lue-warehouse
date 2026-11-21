# US-6.2 Implement tenant SCD Type 2

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-21 |
| Branch and pull request | `e6-dimensions` (one pull request for US-6.1 to US-6.5, one commit per story) |
| Evidence | [`../evidence/us-6.2/`](../evidence/us-6.2/) |

## Story

As an analyst, I want tenant history preserved, so that a report for a past month reproduces exactly as it was.

## What was done

1. **History, not just the latest row.** Staging keeps one row per tenant (the latest), but bronze keeps every
   version the source sent. The tenant's history is read from bronze (validated batches, rows E4 did not reject) with
   the same cleaning expressions as staging (`etl/dimensions/spec.py`, `TENANT_HISTORY`), each state with the date it
   took effect (`updated_at`).
2. **The SCD2 step** (`etl/dimensions/load.py`): from the history, the versions a member should have are rebuilt
   (`desired_versions`): the first valid from 1900-01-01, then one per change of a Type 2 value, in date order
   (plan step 3); two states the same day, the later wins. Versions the dimension lacks are added in the step's
   transaction (plan step 2): the current version is closed (`effective_to` = change date, `is_current` FALSE) and
   the new one opened (`effective_from` = change date, `effective_to` 9999-12-31). Versions are half-open:
   `effective_from <= d < effective_to`.
3. **Idempotent** (step 4): only versions after the current one are added, so a rerun adds none. A change dated the
   current version's own day is made in place. A stored version is never rewritten; a history that disagrees with
   one is counted (`history_conflicts`, step Warning).
4. **The next extract:** `scripts/db_apply_next_extract.py` applies the generator's later S1 files to `src_pms`
   (`s1/changes/tenants.csv`: 76 tenant changes); the pipeline picks them up like any change.

## Decisions and deviations

- **Tracked attributes follow the frozen data dictionary:** `tenant_type` and `employer_sector` are Type 2;
  `contact_channel` is Type 1 there (the plan lists it as tracked). A contact-channel change is overwritten in place.
  CI checks every column's SCD type against the dictionary.
- The comparison is on the Type 2 values themselves (a tuple), not a stored hash: the values are few and short, and
  the comparison needs no extra column the frozen DDL does not have.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Each planted tenant change produces exactly one new version | Pass: of 76 planted changes, the 36 employer-sector changes give 36 versions, each from its change date; the 40 contact-channel changes (Type 1) overwrite in place | `01_tenant_history.txt` |
| Rerunning creates no rows | Pass: 0 inserted, 0 versions, 0 changed | `01_` |
| A past-month query returns the old attribute value | Pass: T-0040 is Healthcare on 2025-04-01, Construction on 2025-06-01 | `01_` |
