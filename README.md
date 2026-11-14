# LUE Warehouse

Lahore Urban Estates analytics warehouse. DL3004 Data Warehousing and Business Intelligence, final project
(FAST-NU Lahore). PostgreSQL star schema, Python ETL and a Power BI dashboard.

Team: Junaid Minhas, Ahmad Waqar, Hanan Tiwana, Eesha Khurram.

## Status

| Item | State |
|---|---|
| Phase 1 design pack | Frozen as v2.1 in `docs/phase1/` (git tag `phase1-v2.1-final`) |
| Repository, branch rules, CI | US-0.3 (Done) |
| Local environment and `.env.example` | US-0.4 (Done) |
| Database (E1): schemas, 13 dimensions, 6 facts, audit tables, reference data | US-1.1 to US-1.5 (Done) |
| Data generator framework (E2) | US-2.1 (Done); US-2.2 to US-2.6 pending |
| Ingestion, staging, dimensions, facts, marts, reports | Phase 2 and 3, pending |

## Layout

```
docs/phase1/      frozen Phase 1 pack (do not edit; see Change control)
docs/plan/        the development plan for Phases 2 and 3
docs/stories/     story log: what was done in each user story (start at docs/stories/README.md)
docs/contracts/   generated table and key contracts, refreshed weekly
docs/reports/     generated PDFs: cleaning, data quality, indexing, insights
docs/evidence/    screenshots and outputs that prove each story (one folder per story)
sql/              00_setup, 10_ddl, 20_staging, 30_dimensions, 40_facts, 50_reporting,
                  60_analytics, 70_performance, 90_tests
etl/              generate_data.py, refresh_weather.py, ingest/, run_pipeline.py, reports/
data/             generated source files (not committed) and data/weather_cache.json (committed)
powerbi/          PBIX and screenshots
presentation/     final slides
scripts/          ci_checks.py (CI quality gates), test_connection.py (connection test)
```

Two small additions to the plan's layout, recorded here as deviations: `scripts/` holds the CI checks, and
`docs/evidence/` holds story evidence (plan A10 says evidence lives under `docs/`).

## Environment setup (US-0.4)

### Software versions

| Component | Minimum / Pinned Version | Notes |
|---|---|---|
| PostgreSQL | 16.x or newer (64-bit) | Database engine; default superuser `postgres` |
| pgAdmin | 4 (v8.x or newer) | Database GUI management |
| Python | 3.11 or newer (tested on 3.11, 3.12, 3.13) | Pipeline and analytics runtime |
| Power BI Desktop | 2.138+ (64-bit, Nov 2024 or later) | Dashboard interface (E13) |
| Git | 2.40+ | Version control |

### 30-Minute quickstart

1. **Clone the repository and switch to the active branch:**
   ```bash
   git clone https://github.com/JA-Codex/lue-warehouse.git
   cd lue-warehouse
   ```

2. **Create and activate a Python virtual environment:**
   ```bash
   # Windows PowerShell:
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS / Git Bash:
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install project dependencies:**
   ```bash
   pip install -r requirements.txt

   # Optional: install CI and quality check tools (ruff, pglast)
   pip install -r requirements-ci.txt
   ```

4. **Configure your local `.env` file:**
   ```bash
   # Windows Command Prompt:
   copy .env.example .env

   # PowerShell:
   Copy-Item .env.example .env

   # Linux / macOS / Git Bash:
   cp .env.example .env
   ```
   Open `.env` and set `PGPASSWORD` to match your local PostgreSQL superuser password. Never commit `.env`.

5. **Run the connection test:**
   ```bash
   python scripts/test_connection.py
   # Or using make:
   make setup
   ```
   The script verifies your Python version, connects to PostgreSQL, displays the server version, creates a throwaway table `_lue_conn_test_tmp`, inserts a test record, verifies it, and drops it.

6. **Verify repository quality gates:**
   ```bash
   ruff check etl scripts
   python scripts/ci_checks.py --manifest --allow-missing-pglast
   # Or if pglast is installed:
   make test
   ```

## Commands

```
make help        list the targets
make setup       install dependencies and run PostgreSQL connection test (US-0.4)
make test        lint + SQL parse + frozen-pack + DDL contract check + generator tests (what CI runs)
make rebuild     stub until the pipeline exists; must always pass on main
make reports     stub
make db-setup    create databases, roles and schemas (US-1.1); safe to re-run
make db-deploy   deploy sql/10_ddl (the 13 dimensions, 6 facts) as lue_etl (US-1.2)
make db-load-ref load dim_date and the static dimensions as lue_etl; safe to re-run (US-1.4)
make db-reset    drop and rebuild the warehouse, reload reference data, smoke test (US-1.5)
make db-smoke    count the warehouse objects: 13 dims, 6 facts, 5 audit tables, 41 FKs, 48 partitions
make generate    generate seeded source data into data/ (US-2.1); PROFILE=small|full SEED=n
make gen-test    generator acceptance tests, no database needed (US-2.1)
make db-test     database acceptance tests: 22 (US-1.1), 28 (US-1.2), 24 (US-1.3), 32 (US-1.4) and 12 (US-1.5) PASS lines
```

Generator without `make`: `python etl/generate_data.py --profile small --seed 3004 --out data`. The command
prints a content hash; two runs with the same seed and profile must print the same one. The rules every generator
stage follows (seeded streams only, `ctx.write_text`) are at the top of `etl/generate_data.py`.

Without `make`: `python scripts/db_setup.py`, `python scripts/db_deploy.py`, `python scripts/db_load_reference.py`,
then `python scripts/test_db_setup.py`, `test_dimensions.py`, `test_facts.py`, `test_reference.py` and
`test_smoke.py` (all in `scripts/`). To start again from nothing: `python scripts/db_reset.py`.

### Databases, roles and schemas (US-1.1)

| Object | Name | Notes |
|---|---|---|
| Databases | `lue_source`, `lue_warehouse` | Both owned by `lue_etl`. `lue_source` holds schema `src_pms` (S1) |
| Pipeline role | `lue_etl` | Owns all schemas; not a superuser |
| Power BI role | `lue_reader` | Connects to `lue_warehouse` only; reads `lue_reporting` only; sessions start read-only |
| Warehouse schemas | `lue_staging`, `lue_dw`, `lue_reporting`, `lue_audit` | Decision D2 |

The SQL is in `sql/00_setup/01` to `05` (each file names the database it runs in, so it also works in psql).
Role passwords come from `.env` (`LUE_ETL_PASSWORD`, `LUE_READER_PASSWORD`) and are never committed.
`scripts/db_setup.py` reads `.env` first, so a `PGPASSWORD` left in the shell cannot override it.

On Windows, `make` is not installed by default. Either run the checks directly
(`pip install -r requirements-ci.txt`, then `ruff check etl scripts` and `python scripts/ci_checks.py`)
or use Git Bash with `make` installed.

## How we work

- `main` is always runnable. Nobody pushes to it: every change is a pull request, and the `ci` check must pass
  before it can merge. A teammate review is optional and not enforced by the ruleset.
- Branch names are `epic-story`, for example `e6-6.2-tenant-scd2`.
- Reviews are optional. If one is wanted, the rotation is: Junaid reviews Hanan, Hanan reviews Ahmad Waqar,
  Ahmad Waqar reviews Eesha, Eesha reviews Junaid.
- The pull request template carries the Definition of Done. Evidence goes under `docs/evidence/<story>/`.
- Never commit credentials. `.env` is ignored; only `.env.example` is committed.

## Names: brief names against LUE names

The briefs use `project_*` names. We use LUE names; this mapping is **pending instructor confirmation (O4)**.

| Brief name | LUE name | Notes |
|---|---|---|
| `project_staging` | `lue_staging` | Bronze tables `brz_*`, Silver tables `stg_*` |
| `project_dw` | `lue_dw` | 13 dimensions and 6 facts |
| `project_reporting` | `lue_reporting` | Gold marts and views, including `vw_dim_*` |
| (none) | `lue_audit` | `etl_run_log`, `quarantine`, `reconciliation`, `lineage` |
| (none) | `lue_source.src_pms` | Source system S1; separate database `lue_source` |
| `vw_monthly_sales`, `vw_customer_analysis`, `vw_product_performance` | alias views in `lue_reporting` | Planned (US-10.1) |

The warehouse database is `lue_warehouse`.

### Warehouse DDL (US-1.2 onward)

`sql/10_ddl/` holds the deployable DDL. It is copied from the frozen `docs/phase1/sql/physical_model.sql`, and
`scripts/check_contract.py` (part of `make test`, so CI runs it) fails if any table, column, type, NULL rule,
constraint or special member differs from the pack. The only allowed differences are these Phase 2 additions
from the development plan:

| Addition | Why | Story |
|---|---|---|
| Surrogate keys `GENERATED BY DEFAULT AS IDENTITY` (12 dimensions; `dim_date` keeps its `YYYYMMDD` key) | D6: keys are assigned by the database, special members -1 and -2 can still be inserted, the first loaded member gets key 1 | US-1.2 |
| `ck_<dim>_effective_range` and partial unique index `uq_<dim>_one_current` on the four SCD2 dimensions | US-1.2: an inverted date range or two current versions of one member are rejected | US-1.2 |
| `key_is_special()` created in `lue_dw`, not `public` | `lue_etl` cannot create objects in `public` | US-1.2 |
| `IF NOT EXISTS` and `ON CONFLICT DO NOTHING` | Safe to re-run | US-1.2 |

The partial unique indexes enforce uniqueness, like the primary keys, so they belong to the D20 baseline; the pack's
38 foreign-key and filter indexes are left out of the baseline and are added in the Phase 3 indexing experiments
(US-12.2). `dim_request_flags` has no special members, as in the pack: all 8 flag combinations always exist.

### Reference data (US-1.4)

`python scripts/db_load_reference.py` (or `make db-load-ref`) runs `sql/30_dimensions/01_reference_dimensions.sql` as `lue_etl`. It is separate from `sql/10_ddl/` on purpose: that folder is structure only and is compared with the frozen pack row for row. Safe to re-run: a second run changes nothing and uses no extra key numbers.

| Table | Rows loaded | Notes |
|---|---|---|
| `dim_date` | 1,461 (2023-07-01 to 2027-06-30) | `date_key` is YYYYMMDD; fiscal year runs July to June (`FY2025-26`); holiday and Ramadan flags start FALSE and are filled in US-6.4 |
| `dim_payment_method` | 6 | `CASH`, `CHEQUE`, `BANK`, `RAAST`, `JAZZ`, `EASY`; keys 1 to 6 |
| `dim_charge_type` | 6 | `RENT`, `SERVICE`, `LATEFEE`, `UTILITY`, `CREDIT`, `DEPADJ`; keys 1 to 6 |
| `dim_lease_event_type` | 4 | `SIGN`, `RENEW`, `NOTICE`, `TERM`; keys 1 to 4 |
| `dim_request_flags` | 8 | every combination of the three flags; no special members (as in the pack) |

The same members are in `etl/reference_data.py`, which the data generator uses for the source system S1 codes. `scripts/test_reference.py` fails if the two ever differ.

## Change control for the frozen Phase 1 pack

`docs/phase1/` matches `MANIFEST.sha256`, and CI fails if any file there changes. A design change needs a dated row in
the change log in `docs/phase1/README.md`, a regeneration with `docs/phase1/tools/`, and a new manifest and tag.

Branch rules verified with a test pull request (US-0.3).
