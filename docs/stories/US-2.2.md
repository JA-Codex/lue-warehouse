# US-2.2 Generate master data

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-14 |
| Branch and pull request | `e2-2.2-master-data` |
| Evidence | [`../evidence/us-2.2/`](../evidence/us-2.2/) |

## Story

As a developer, I want generated master data for buildings, units, tenants, owners, vendors and categories, so that
the transactional generators have stable entities to refer to.

## What was done

1. `etl/gen_master.py`, stage `master_data` (one seeded stream per sub-stage): buildings across up to 4 cities, units
   with type and size, tenants (12% corporate, unique phones, about 5% with no employer sector), owners with an
   ownership register (periods, some units change owner), vendors with trade and rating (some ratings change),
   SLA policy per maintenance subcategory, a holiday register.
2. Outputs: S1 CSVs (`buildings`, `units`, `tenants`, `charge_types`, `payment_methods`) and the S2 workbook (one
   sheet per register: owners, ownership, vendors, sla_policy, holidays).
3. `sql/05_source/01_src_pms_master.sql` and `scripts/db_load_source.py` (`make db-load-source`): create the
   `lue_source.src_pms` tables and load the CSVs in one transaction; a bad file rolls everything back.
4. Tests: `scripts/test_master_data.py` (129 checks, no database) and `scripts/test_source_load.py` (30 checks,
   database). `make gen-test` and `make db-test` run them.
5. `etl/generator_config.py` gained fixed-ratio fields; `etl/reference_data.py` gained trades, subcategories and holidays.
   `etl/generate_data.py` gained workbook writing and content hashing of workbooks.

## Files added or changed

- Added: `etl/gen_master.py`, `scripts/test_master_data.py`, `scripts/test_source_load.py`, `scripts/db_load_source.py`,
  `sql/05_source/01_src_pms_master.sql`, `docs/evidence/us-2.2/`
- Changed: `etl/generate_data.py`, `etl/generator_config.py`, `etl/reference_data.py`, `scripts/test_generator.py`,
  `Makefile`, `requirements-ci.txt` (openpyxl), `README.md`, `docs/stories/README.md`, US-2.1 docs (hash note)

## Decisions and deviations

- **S1 as CSV plus a loader.** The plan leaves the S1 form open; CSV keeps the generator free of database code.
- **`src_pms` has primary keys only, no foreign keys.** US-2.6 must plant orphans and invoices that precede their tenant.
- **Ownership `valid_to` is exclusive**; the current owner has it empty. Periods are contiguous: next `valid_from` equals
  the previous `valid_to`.
- **Vendors** carry `previous_rating` and `rating_changed_on` (about 12% changed); **sla_policy** has 30 base rows from
  2023-01-01 plus about 15% tightened rows inside the window.
- **Holidays are approximate and synthetic.** Lunar dates are not astronomical; `is_public_holiday` and `is_ramadan`
  are columns.
- **Workbooks are hashed by content** (`logical_hash_files` in the manifest), with fixed zip timestamps, so the hash does
  not depend on the openpyxl version.
- **Tenant creation order is a contract for US-2.3**: `tenant_code` T-0001... follows creation time; about 36% of
  tenants exist before the window.
- **Phone numbers are random and unique**, but could coincide with real numbers.
- **New hash:** `--profile small --seed 3004` now gives `7e1030ea...ffbf7089` (US-2.1 alone gave `67c361e8...fd1f68`).
- **DB scripts were verified against PostgreSQL 16 through a psycopg2 stand-in** that shells out to `psql`. Run them once
  with real psycopg2 on your machine.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Counts match the config | Pass (small and full) | `02_acceptance_tests.txt`, `01_database_counts.txt` |
| Every unit belongs to a building and city | Pass | `02_`, `03_database_tests.txt` |
| Ownership periods contiguous, no overlap | Pass | `02_acceptance_tests.txt` |
| Workbook has the expected sheets | Pass | `04_workbook_overview.txt`, `04_workbook_owners_sheet.png` |
| Tests can fail | Pass: 8 mutations caught | `05_tests_catch_broken_data.txt` |

## How to re-check it

    python scripts/test_master_data.py    # expect 129/129
    python scripts/test_generator.py      # expect 39/39
    make db-load-source && python scripts/test_source_load.py   # expect 30/30

## Open items and follow-ups

- The dictionary expects about 4,500 tenant versions; 3,800 tenants plus the 2% change rate (US-2.6) gives about 3,900.
  Raise `tenants` in the full profile if the team wants to match.
- Small-profile volume targets are scaled estimates; revisit after US-2.3 to US-2.5.
- Pinning NumPy/openpyxl in `requirements.txt` is still open.
