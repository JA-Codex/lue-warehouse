# US-4.2 Implement completeness, type and duplicate checks (DQ-01 to DQ-03)

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e4-quality` |
| Evidence | [`../evidence/us-4.2/`](../evidence/us-4.2/) |

## Story

As a data steward, I want missing values, wrong types and duplicates detected, so that only structurally sound rows
continue.

## What was done

Rules in `etl/quality/rules.toml`:

- **DQ-01 NULL** (20 rules, one per bronze table): business keys, dates and amounts present. NULL and empty (or blank)
  both count as missing.
- **DQ-02 Data type** (34 rules): whole numbers, numbers, dates, timestamps and booleans, with the safe casts. A date
  may be `YYYY-MM-DD` or day-first `DD/MM/YYYY` (S6 has both; staging repairs it, US-5.1). `TBD`, `2025-12-32`,
  `Rs. 8,300` and `8300/-` are rejected.
- **DQ-03 Duplicate** (decision D15): an exact duplicate (same key, same values) inside one batch is rejected, keeping
  the first copy by ingestion order, and the reason names the kept copy. A conflicting duplicate (same key, other
  values) is a warning on every copy; both go on to staging, where survivorship keeps the latest (US-5.1).

## Decisions and deviations

- **No warnings on optional fields** (plan step 1): an open ticket has no vendor, a first lease no previous lease, most
  tenants no employer; warning on them would bury the real findings. Optional fields are listed as such in the
  catalogue (they are simply not in a `required` rule).
- **`holiday_name` is optional:** Ramadan days that are not public holidays have none.
- **No duplicate check on ticket status rows:** the two copies of a duplicated ticket have identical histories; staging
  keeps the history of the ticket copy it keeps (by `source_row`).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Each rule has a test with a known bad row and a known good row | Pass: all 109 rules (DQ-01 to DQ-06), made from real bronze rows | `01_rule_tests.txt` |
| Quarantine reasons show column and value | Pass: e.g. `[S4-TKT-03] not a number: estimate = 'Rs. 8,300'` | `02_quarantine_sample.txt` |
| A conflicting duplicate produces a warning and reaches staging; an exact duplicate is quarantined | Pass: 60 of 60 each | `../us-4.4/01_dq_validation.csv` |
