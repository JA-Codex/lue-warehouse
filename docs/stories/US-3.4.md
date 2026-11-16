# US-3.4 Ingest JSON and weather, and reconcile bronze

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-16 |
| Branch and pull request | `e3-ingestion` |
| Evidence | [`../evidence/us-3.4/`](../evidence/us-3.4/) |

## Story

As a data engineer, I want the JSON tickets and the weather cache landed and every bronze table reconciled to its
source, so that nothing is lost before validation.

## What was done

1. `etl/ingest/json_weather.py`: `s4/tickets.json` flattened into `brz_ticket` (one row per ticket object, in file
   order) and `brz_ticket_status` (one row per `status_history` entry, `status_seq` 1, 2, ...). Same checksum policy
   and structure check as US-3.3 (a cut-off or reshaped file is rejected).
2. `data/weather_cache.json` into `brz_weather` (city, date, maximum temperature, rainfall).
3. **Reconciliation** in `lue_audit.reconciliation` for all 20 bronze tables every run: source rows (in the source
   now, or in today's files) against the rows bronze holds for them, with the difference and pass or fail.
4. `etl/ingest/run.py` (`make ingest`) runs all six sources and prints the steps and the reconciliation.
5. **Tests:** `scripts/test_ingest.py` (39 checks, the database, all of E3; `make ingest-test`) and
   `scripts/test_ingest_contract.py` (17 checks, no database, in `make gen-test` so CI runs it: the generator's
   files, the ingestors and the bronze DDL agree; the text rules).

## Decisions and deviations

- **A ticket's copies stay apart.** A ticket can be in the file twice (US-2.6 duplicates). `brz_ticket_status` keeps
  `source_row` (the ticket object's position), so each copy keeps its own history; the ticket id alone would mix them.
- **JSON values as text:** null is NULL, `true`/`false`, numbers as their digits, and a planted text such as
  `Rs. 8,300` stays that text (DQ-02's job).
- **Rejected files are not part of the reconciliation** (they are in `file_load` as `Rejected`).
- The pandas `json_normalize` of the Phase 1 sheet is not needed: the two levels are flattened directly.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| All bronze tables show zero difference between source and landed rows | Pass: 20 of 20 on the full profile | `03_reconciliation.txt`, `02_full_ingest.txt` |
| Status history rows equal the sum of the array lengths | Pass: 24,080 | `01_json_weather_tests.txt` |
| Tests can fail | Pass: 11 deliberate breakages, all caught | `04_tests_catch_broken_code.txt` |

## How to re-check it

    python etl/ingest/run.py              # 20/20 reconciliation checks
    python scripts/test_ingest.py         # expect 39/39
    python scripts/test_ingest_contract.py  # expect 17/17
