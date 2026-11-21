# US-7.6 Automate grain and orphan checks

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e7-facts` (one pull request for US-7.1 to US-7.6, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-7.6/`](../evidence/us-7.6/) |

## Story

As a quality owner, I want grain, orphan and range checks automated, so that every run proves the facts are
structurally correct.

## What was done

1. **One query per test** in `sql/90_tests/02_fact_tests.sql` (71 tests), each returning its violations (0 when it
   passes), in the format of the dimension tests (US-6.5):
   - **grain**: one test per fact, duplicates of its natural grain;
   - **orphans**: one test per foreign key of the facts (all 41 of the DDL): rows whose key has no dimension row.
     The special members -1 (Unknown) and -2 (Not applicable) are dimension rows, so they are not orphans; the run
     counts the rows on them per key and reports them apart;
   - **impossible values**: negative amounts; net not billed + tax - discount; a receipt not positive or a reversal
     not negative; days past due not paid minus due; a line paid beyond its net; an allocation to an invoice line
     not in the fact; occupancy days outside the window, a day without every unit, a vacant day with a tenant,
     lease, rent or arrears, an occupied day without a tenant or lease; maintenance milestones out of order or
     skipped, a status that does not match its milestones, a vendor before assignment, an SLA flag before
     resolution; an event count not 1; incentive coverage on an occupied day or outside the window.
2. **Wired into the run** (`etl/facts/checks.py`, `etl/facts/run.py`): after the facts, a `fact_tests` step runs the
   file and writes one row per test to `lue_audit.reconciliation` (expected 0, found, passed). The rows are written on
   the run's autocommit audit connection, so they stay when the step then fails; any violation fails the step and the
   run exits 1. It runs after a full run, or with `--tests` after a `--fact` run. E8's pipeline runs it as part of
   the fact load.
3. **CI** (`scripts/test_fact_load_contract.py`) checks the file has an orphan test for every foreign key in the DDL
   and a grain test for every fact, with unique names that fit the audit column.

## Files added or changed

- `sql/90_tests/02_fact_tests.sql`, `etl/facts/checks.py`, `etl/facts/run.py` (the test step, `--tests`, the special
  member report)
- `scripts/test_fact_load_contract.py` (26 checks), `scripts/test_fact_load.py` (57 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **Results in `lue_audit.reconciliation`**: the pack's audit table for checks with an expected and a found value; a
  test is expected 0 and passes at 0, next to the monthly reconciliation rows of the same run.
- **The foreign keys already prevent orphans**; the orphan tests are the second line of defence the plan asks for, and
  matter when constraints are dropped for a bulk load or an indexing experiment (US-12.2).
- **A failing test fails the run**: structural errors are not a Warning.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| All checks return zero violations on a clean run | Pass: 71 of 71, run log Success, 71 passed rows in `lue_audit.reconciliation` | `01_` (queries 1 and 2) |
| A deliberately corrupted row makes the matching check fail | Pass: a duplicated lease event, a negative receipt, a vacant day with rent and a ticket verified before resolved each fail exactly their test; committed, the duplicate fails the run's test step (exit 1) | `01_` (query 3), `02_` |
| Evidence: passing output and a deliberate failure demonstration | Pass | `01_` |

## How to re-check it

    python scripts/test_fact_load_contract.py                # no database: expect 26/26
    python etl/facts/run.py                                  # ends with fact_tests: 71 of 71 tests passed
    psql -d lue_warehouse -f sql/90_tests/02_fact_tests.sql  # the tests alone: every violation 0
    python scripts/test_fact_load.py                         # expect 57/57
