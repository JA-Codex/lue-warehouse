# US-1.1 Create databases, roles and schemas

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-09 |
| Branch and pull request | `e1-1.1-setup` |
| Evidence | [`../evidence/us-1.1/`](../evidence/us-1.1/) |

## Story

As a developer, I want the databases, roles and schemas created by an idempotent script, so that any machine gets
the same structure.

## What was done

1. `sql/00_setup/01_roles.sql`: roles `lue_etl` and `lue_reader`, created only if missing, never superusers.
   `lue_reader` sessions start read-only.
2. `sql/00_setup/02_databases.sql`: databases `lue_source` and `lue_warehouse` (decision D1), owned by `lue_etl`.
   A query generates `CREATE DATABASE` only for missing databases and `\gexec` runs it, so a re-run creates nothing.
3. `sql/00_setup/03_database_access.sql`: owners corrected, `PUBLIC` loses `CONNECT`; `lue_reader` may connect to
   `lue_warehouse` only.
4. `sql/00_setup/04_source_schema.sql`: schema `src_pms` in `lue_source`, owned by `lue_etl`.
5. `sql/00_setup/05_warehouse_schemas.sql`: schemas `lue_staging`, `lue_dw`, `lue_reporting`, `lue_audit` (D2), owned
   by `lue_etl`; `lue_reader` gets `USAGE` and `SELECT` on `lue_reporting` only, including future tables and views
   (default privileges); search paths set for both roles.
6. `scripts/db_setup.py`: runs the five files in order on the right database, then sets both role passwords from
   `.env`. It reproduces psql's `\gexec`, so psql is not required.
7. `scripts/test_db_setup.py`: 22 acceptance checks, logging in as each role with its real password.
8. `make db-setup` and `make db-test`; README section "Databases, roles and schemas (US-1.1)".

## Files added or changed

- SQL: `sql/00_setup/01_roles.sql` to `05_warehouse_schemas.sql`
- Python: `scripts/db_setup.py`, `scripts/test_db_setup.py`
- `Makefile` (`db-setup`, `db-test`; the `db-reset` stub now points to US-1.5, which owns the reset script)
- `README.md`, `docs/stories/README.md` (E1 table), this file, `docs/evidence/us-1.1/`

## Decisions and deviations

- **Passwords live only in `.env`.** The repository is public, so the SQL creates roles without passwords and
  `db_setup.py` sets them from `LUE_ETL_PASSWORD` and `LUE_READER_PASSWORD`.
- **`.env` wins over the shell.** `db_setup.py` and the tests prefer `.env` values over variables already set in
  the shell. `test_connection.py` (US-0.4) does the opposite, and a stale `PGPASSWORD` caused a confusing failure.
- **`02_databases.sql` holds one query.** The CI parse check blanks psql meta-commands such as `\gexec`, so any
  statement after it would merge into the query. The owners and grants are therefore in `03_database_access.sql`.
- **Extra hardening beyond the plan:** `lue_reader` sessions are read-only by default, and `PUBLIC` cannot connect to
  either database or create objects in `public`.
- **Tests instead of `\dn` and `\du` screenshots.** The plan's evidence asks for screenshots; the saved test output
  shows the same facts and can be re-run.
- Developed on PostgreSQL 16; the evidence run is on PostgreSQL 18.6. Nothing here needs a version newer than 15.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Running the script twice produces no errors and no duplicates | Pass | `02_setup_second_run.txt`; test "the second run changes no role, database, schema or grant" |
| `lue_reader` can read `lue_reporting` but cannot write anywhere and cannot read `lue_dw`, `lue_staging` or `lue_audit` | Pass | `03_acceptance_tests.txt` (reader section) |
| The four schemas exist with the exact names in D2 | Pass | `03_acceptance_tests.txt` (structure section) |

## How to re-check it

```
python scripts/db_setup.py        # or: make db-setup
python scripts/test_db_setup.py   # or: make db-test; expect "RESULT: 22/22 checks passed"
```

## Open items and follow-ups

- US-1.2 and US-1.3 build `lue_dw` on these schemas, connecting as `lue_etl`. Note for that work: the frozen
  `physical_model.sql` creates `key_is_special()` in `public`, which `lue_etl` cannot do; create it in `lue_dw`.
- US-1.5 (`reset.sql`, `make db-reset`) can call `db_setup.py` after dropping the schemas.
- US-10.1 creates the `vw_dim_*` views in `lue_reporting`; `lue_reader` can read them automatically.
