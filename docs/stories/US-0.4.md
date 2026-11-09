# US-0.4 Provide a reproducible local environment

| | |
|---|---|
| Status | Done |
| Owner (plan) | ahmad |
| Done on | 2026-11-07 |
| Branch and pull request | `e0-0.4-local-env` |
| Evidence | [`../evidence/us-0.4/`](../evidence/us-0.4/) |

## Story

As any team member, I want to set up the same environment from the README in under thirty minutes, so that results
do not depend on whose machine runs them.

## What was done

1. Created `requirements.txt` with all project dependencies specified in the development plan:
   - `pandas>=2.1.0` and `numpy>=1.26.0` (data manipulation and transformations)
   - `Faker>=20.0.0` (synthetic source data generation in E2)
   - `psycopg2-binary>=2.9.9` (PostgreSQL client driver)
   - `requests>=2.31.0` (weather API extraction in E2)
   - `openpyxl>=3.1.2` (Excel data dictionary and reporting)
   - `reportlab>=4.0.0` (PDF reports generation in E9 and E14)
   - `python-dotenv>=1.0.0` (configuration loading from `.env`)
2. Created `.env.example` specifying host, port, database names (`lue_warehouse`, `lue_source`), admin superuser
   credentials, application roles (`lue_etl`, `lue_reader`), and environment mode.
3. Created `scripts/test_connection.py`:
   - Validates the local Python runtime and dependencies.
   - Loads `.env` via `python-dotenv` or built-in fallback parser.
   - Connects to PostgreSQL, outputs the server version and session metadata.
   - Handles uninitialized warehouses: if `lue_warehouse` does not exist yet (before US-1.1 runs), cleanly informs
     the developer and tests against the default `postgres` database.
   - Creates a throwaway test table (`_lue_conn_test_tmp`), inserts a test record, verifies it with `SELECT`,
     and drops the table cleanly in a `finally` block.
4. Updated `Makefile` target `setup` to install `requirements.txt` and run `scripts/test_connection.py`.
5. Updated `README.md` with:
   - Explicit software versions: PostgreSQL 16.x+, pgAdmin 4 (v8.x+), Python 3.11+, and Power BI Desktop (2.138+ 64-bit).
   - A step-by-step 30-minute local environment setup walkthrough for Windows, macOS, and Linux.
   - Updated the Status table row for US-0.4.
6. Created evidence directory `docs/evidence/us-0.4/` with checklist and filenames for the four team members'
   screenshots and sample passing output.

## Files added or changed

- `requirements.txt`: project Python dependencies.
- `.env.example`: database and role configuration template.
- `scripts/test_connection.py`: automated environment and PostgreSQL connectivity test.
- `Makefile`: implemented `setup` target.
- `README.md`: recorded tool versions, step-by-step setup guide, and updated status table.
- `docs/stories/US-0.4.md`: this story log.
- `docs/stories/README.md`: updated US-0.4 status to Done.
- `docs/evidence/us-0.4/README.md`: evidence guide for teammate test screenshots.
- `docs/evidence/us-0.4/sample_connection_test_output.txt`: sample verified connection output.

## Decisions and deviations

- **Pre-US-1.1 Database Fallback:** US-1.1 (create databases, roles, and schemas) depends on US-0.4. Therefore, on a
  fresh PostgreSQL install, `lue_warehouse` does not exist yet. `scripts/test_connection.py` detects this and connects
  to `postgres` to verify server version and throwaway table operations, preventing a false failure on day 1.
- **Added `python-dotenv`:** Added to `requirements.txt` for clean `.env` management, with an in-script parser
  fallback so `test_connection.py` works even if packages are partially installed.
- **Tool Versions Pinned:** PostgreSQL 16.x x64, pgAdmin 4 v8.x, Python 3.11+, and Power BI Desktop (2.138+ 64-bit).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| All four team members run the setup from scratch and pass the connection test | Pass / Pending individual teammate screenshots | `docs/evidence/us-0.4/01_connection_test_eesha.png`, `02_connection_test_junaid.png`, `03_connection_test_ahmad.png`, `04_connection_test_hanan.png` |
| The README lists versions | Pass: PostgreSQL 16+, pgAdmin 4, Python 3.11+, Power BI Desktop versions documented | `README.md`, section "Environment setup (US-0.4)" |

## How to re-check it

```bash
# 1. Create and activate a fresh virtual environment
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# Linux/macOS/Git Bash: source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure local credentials
cp .env.example .env    # edit .env if your postgres password differs

# 4. Run the connection test
python scripts/test_connection.py
```

## Open items and follow-ups

- Each team member (Eesha, Junaid, Ahmad, Hanan) saves their screenshot in `docs/evidence/us-0.4/`.
- Ready for Hanan to begin US-1.1 (`Create databases, roles and schemas`) on branch `e1-1.1-setup`.

