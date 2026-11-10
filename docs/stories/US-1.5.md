# US-1.5 Deploy the audit tables, the watermark table and the reset command

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha |
| Done on | 2026-11-10 |
| Branch and pull request | `e1-1.5-audit-reset` |
| Evidence | [`../evidence/us-1.5/`](../evidence/us-1.5/) |

## Story

As a developer, I want the audit tables and a one-command reset, so that I can rebuild the warehouse at any time and
every later run can log, quarantine, reconcile and resume.

## What was done

1. `sql/10_ddl/03_audit.sql`: the 4 audit tables from the Phase 1 pack (`etl_run_log`, `quarantine`, `reconciliation`,
   `lineage`) plus `lue_audit.etl_watermark` (decision O5). `db_deploy.py` runs it with the other DDL files.
2. `sql/00_setup/reset.sql` drops `lue_staging`, `lue_dw`, `lue_reporting` and `lue_audit`.
3. `scripts/db_reset.py` runs `reset.sql` as the superuser, then `db_setup.py`, `db_deploy.py`,
   `db_load_reference.py` and `test_smoke.py`, in that order, and stops at the first failure.
4. `scripts/test_smoke.py` (12 checks): 13 dimensions, 6 facts, 5 audit tables, 41 foreign keys, 48 partitions
   (plus a default), the reference row counts and the watermark columns.
5. `scripts/check_contract.py` gets `ALLOWED_EXTRA_TABLES` so `etl_watermark` (not in the pack) is accepted.
6. `Makefile`: `db-reset` (was a stub) and `db-smoke`; `db-test` also runs the smoke test. README updated.

## Files added or changed

- Added: `sql/10_ddl/03_audit.sql`, `sql/00_setup/reset.sql`, `scripts/db_reset.py`, `scripts/test_smoke.py`
- Changed: `scripts/check_contract.py`, `Makefile`, `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **`quarantine_id` is an identity column.** The pack has a plain `BIGINT NOT NULL`. Type and NOT NULL are unchanged, so
  the contract check still passes; the quarantine engine (US-4.1) no longer has to invent ids.
- **`etl_watermark` columns:** `source_system`, `table_name`, `last_watermark_value` (timestamp, default 1900-01-01 =
  nothing loaded yet), `updated_at`; primary key (`source_system`, `table_name`).
- **The data dictionary is not changed.** Plan O5 says to record the table in the README and the dictionary. The
  dictionary is part of the frozen Phase 1 pack, so changing it needs the change-control steps. Recorded here and in the
  README only; ask the team whether to raise a change request.
- **`db-reset` never touches `lue_source`** or the roles; it rebuilds the warehouse side only.
- Only `fact_unit_occupancy_daily` is partitioned (48 monthly partitions + default), so the smoke test counts those.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| The four audit tables and the watermark table exist after a fresh deploy | Pass | `02_smoke_test.txt` |
| `make db-reset` returns the warehouse to a clean deployed state in one command | Pass | `01_reset.txt` |
| The smoke test confirms the object counts | Pass | `02_smoke_test.txt` |

## How to re-check it

    python scripts/db_reset.py        # ends with "RESET COMPLETE"
    python scripts/test_smoke.py      # expect "RESULT: 12/12 checks passed"
    python scripts/check_contract.py  # expect "24 table(s) checked ... 0 problem(s)"

## Open items and follow-ups

- Decision D16 says `lue_audit.lineage` records file checksums, but the pack's table has no checksum column. US-3.3 will
  need one; raise it with the team.
- Change request for the data dictionary (watermark table), if the team wants it.
