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
| Data generator (E2): framework, master data, leases, invoices, payments, tickets, incentives, weather, planted defects and patterns | US-2.1 to US-2.6 (Done) |
| Ingestion into bronze (E3): framework, S1 incremental, files with checksums, JSON and weather, reconciliation | US-3.1 to US-3.4 (Done) |
| Data quality and quarantine (E4): rule catalogue and engine, DQ-01 to DQ-06, proof against the answer key | US-4.1 to US-4.4 (Done) |
| Staging (E5): clean, standardise, deduplicate, business fields, incremental merge, cleaning evidence | US-5.1 to US-5.4 (Done) |
| Dimensions (E6): loader and surrogate keys, SCD Type 2, hierarchies, inferred members, dimension tests | US-6.1 to US-6.5 (Done) |
| Facts (E7): loader and point-in-time key mapping, invoice and payment facts with monthly reconciliation, daily occupancy snapshot with arrears and the 35-day refresh, maintenance requests (accumulating snapshot), lease events and incentive coverage (factless): all 6 facts; grain, orphan and value tests every run | US-7.1 to US-7.6 (Done) |
| Pipeline (E8): `etl/run_pipeline.py`, one command and one run_id from an empty warehouse to a loaded one, logging and lineage; source-to-warehouse reconciliation (DQ-07); safe to rerun and resume; full rebuild in about 5 minutes | US-8.1 to US-8.4 (Done) |
| Phase 2 reports and submission (E9): Data Cleaning and Data Quality reports generated from the loaded warehouse, the dimension and fact load scripts as SQL, the deliverables checklist ([docs/phase2_checklist.md](docs/phase2_checklist.md)), a fresh-clone rehearsal; git tag `phase2-submission` | US-9.1 to US-9.3 (Done) |
| Reporting layer (E10): the brief's three views (monthly collections, tenant analysis, unit performance) and their brief-named aliases, 9 slicer views, 4 monthly marts refreshed by the pipeline's last stage, read-only access for Power BI; every column in [docs/reporting.md](docs/reporting.md) | US-10.1 to US-10.3 (Done) |
| Analytical SQL and OLAP (E11): the 14 business questions, window analytics, ROLLUP and CUBE with GROUPING() and their verification, in `sql/60_analytics/`; answers and interpretations in [docs/analytics.md](docs/analytics.md); three results cross-checked with pandas | US-11.1 to US-11.6 (Done) |
| Indexing, Power BI, Phase 3 reports (E12 to E14) | Pending |

## Run it from a fresh clone (Phase 2 submission, US-9.3)

Every Phase 2 deliverable and its files: [docs/phase2_checklist.md](docs/phase2_checklist.md). The steps below
take a machine with PostgreSQL to a loaded, tested warehouse and the two reports. They work the same on Windows
(PowerShell) and Linux or macOS; no `make` is needed (each `make` target is one of these commands).

**Prerequisites.** PostgreSQL 16 or newer, running, with its superuser password; Python 3.11 or newer; Git. About
1 GB of free disk for the small profile, 4 GB for the full one.

1. **Clone** the submission:

       git clone https://github.com/JA-Codex/lue-warehouse.git
       cd lue-warehouse
       git checkout phase2-submission

2. **Python environment** (Windows: `python -m venv .venv` then `.venv\Scripts\Activate.ps1`):

       python3 -m venv .venv
       source .venv/bin/activate
       pip install -r requirements.txt -r requirements-ci.txt

3. **Settings:** copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`) and set `PGPASSWORD`
   to the PostgreSQL superuser's password (and `PGPORT` if it is not 5432). Then check the connection:

       python scripts/test_connection.py

4. **The checks CI runs** (no database; about 3 minutes; ends with `ALL PASSED`):

       python scripts/run_ci.py

5. **Build the warehouse** on the small profile (2 buildings, 3 months; under a minute). The pipeline generates the
   data, creates the databases, roles and schemas, deploys the DDL and loads every layer in one run, ending with the
   source-to-warehouse reconciliation (DQ-07). On a machine that already has an LUE warehouse, reset it first
   (`python scripts/db_reset.py`; together the two are `make rebuild`):

       python etl/run_pipeline.py --profile small

   Every step should say Success; only `ingest_s5_weather` may warn (it is the one non-critical step). For the full
   profile (40 buildings, 36 months, about 5 minutes): `python scripts/db_reset.py`, then
   `python etl/run_pipeline.py --profile full`.

6. **Test the loaded warehouse** (each ends with `RESULT: n/n checks passed`):

       python scripts/test_reports.py     # the reports' numbers against the audit tables (US-9.1, US-9.2)
       python scripts/test_load_sql.py    # the SQL load scripts rebuild the loaded facts (US-9.3)

7. **Build the reports** from the loaded warehouse. The committed PDFs in `docs/reports/` were built from the full
   profile; to build them from the warehouse you just loaded without changing those, write them elsewhere:

       python etl/reports/build.py --out data/reports

   (`python etl/reports/build.py`, or `make reports`, writes `docs/reports/`.)

The rehearsal of these steps on the tagged commit, from an empty PostgreSQL, is in
[docs/evidence/us-9.3/](docs/evidence/us-9.3/).

## Layout

```
docs/phase1/      frozen Phase 1 pack (do not edit; see Change control)
docs/plan/        the development plan for Phases 2 and 3
docs/stories/     story log: what was done in each user story (start at docs/stories/README.md)
docs/contracts/   generated table and key contracts, refreshed weekly
docs/reports/     generated PDFs: cleaning, data quality, indexing, insights
docs/phase2_checklist.md  every Phase 2 deliverable of the brief and its files (plan Appendix B)
docs/reporting.md  the reporting layer: every view, mart and column, and the measure definitions (E10)
docs/analytics.md  the 14 business questions answered, with results and interpretations (E11)
docs/evidence/    screenshots and outputs that prove each story (one folder per story)
sql/              00_setup, 05_source, 10_ddl, 20_staging, 30_dimensions, 40_facts, 50_reporting,
                  60_analytics, 70_performance, 90_tests
etl/              run_pipeline.py, generate_data.py, ingest/, quality/, staging/, dimensions/, facts/,
                  reconcile.py, reporting.py, reports/
data/             generated source files (not committed) and data/weather_cache.json (committed)
powerbi/          PBIX and screenshots
presentation/     final slides
scripts/          run_ci.py (every CI check), database setup and reset, export_load_sql.py, the tests
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

6. **Verify repository quality gates** (needs `requirements-ci.txt`; the same checks as CI, ends with `ALL PASSED`):
   ```bash
   python scripts/run_ci.py
   # Or, where make is installed:
   make test
   ```

## Commands

```
make help        list the targets
make setup       install dependencies and run PostgreSQL connection test (US-0.4)
make test        lint + SQL parse + frozen-pack + DDL contract check + generator tests (what CI runs);
                 without make: python scripts/run_ci.py (groups: lint, sqlcheck, manifest, contract, gen-test)
make db-setup    create databases, roles and schemas (US-1.1); safe to re-run
make db-deploy   deploy sql/10_ddl (the 13 dimensions, 6 facts) as lue_etl (US-1.2)
make db-load-ref load dim_date and the static dimensions as lue_etl; safe to re-run (US-1.4)
make ingest      land all six sources in bronze, with reconciliation (E3)
make ingest-test E3 acceptance tests: 39 PASS lines (empties bronze, then refills it)
make validate     run the 109 quality rules on bronze, compare with the answer key (E4)
make quality-test E4 acceptance tests: 25 PASS lines (reloads src_pms and bronze from data/)
make stage       load the 20 staging tables (incremental; FULL=1 reloads all), evidence CSVs in
                 data/staging_evidence/, compare with the answer key (E5)
make staging-test E5 acceptance tests: 35 PASS lines (reloads src_pms, bronze and staging; about 7 minutes)
make dims        load the dimensions from staging: surrogate keys, SCD2 versions, inferred members (E6)
make next-extract apply the generator's next S1 extract (s1/changes, s1/late_arriving) to src_pms
make dims-test   E6 acceptance tests: 22 PASS lines (reloads src_pms, bronze, staging, dimensions; about 3 minutes)
make facts       load the 6 facts from staging and the dimensions, then the 71 fact tests (sql/90_tests/
                 02_fact_tests.sql; a violation fails the run); about 2 minutes the first time (E7)
make facts-test  E7 acceptance tests: 57 PASS lines (needs make stage and make dims first; about 6 minutes)
make rebuild     reset the warehouse, generate the data and run the whole pipeline (PROFILE=full for the full
                 profile, about 5 minutes): python scripts/db_reset.py, then python etl/run_pipeline.py --profile small
make pipeline    run the whole pipeline on the data in data/ (one run_id; FROM=stage resumes at a stage);
                 options: --profile, --seed, --skip-generate, --from-step, --only, --data (python etl/run_pipeline.py -h)
                 after the facts it reconciles source = warehouse + quarantined by month (DQ-07; alone: python etl/reconcile.py),
                 then refreshes the reporting marts (alone: python etl/reporting.py)
                 E8 acceptance tests: python scripts/test_pipeline.py (21 PASS lines; resets the warehouse)
                 a rerun changes nothing, a failed step is resumed with FROM=stage: see Recovery below
make reports     build the Phase 2 reports from the loaded warehouse (after make rebuild or make pipeline):
                 docs/reports/LUE_Data_Cleaning_Report.pdf and LUE_Data_Quality_Report.pdf (every number read, none
                 typed); E9 tests: python scripts/test_reports.py (11 PASS lines)
make marts       refresh the four reporting marts (the pipeline's last stage; alone: python etl/reporting.py, US-10.2)
make reporting-test  E10 acceptance tests: 18 PASS lines; views and marts against the facts, aliases, lue_reader's
                 access and its denials (python scripts/test_reporting.py; needs a loaded warehouse, changes nothing)
make analytics   run the SQL pack (sql/60_analytics/analytical.sql, olap.sql) query by query: rows, time, a sample
                 (also: psql -d lue_warehouse -f sql/60_analytics/analytical.sql); answers in docs/analytics.md (E11)
make analytics-test  E11 acceptance tests: 22 PASS lines on the full profile (16 on the small): the marts, the planted
                 patterns, the ROLLUP/CUBE verification and three pandas cross-checks (python scripts/test_analytics.py)
make load-sql    re-export sql/30_dimensions/02_dimension_loads.sql and sql/40_facts/01_fact_loads.sql from the
                 loaders' specs (US-9.3; CI fails while they differ); python scripts/test_load_sql.py (6 PASS lines)
                 runs them on the loaded warehouse, rolled back
make db-reset    drop and rebuild the warehouse, reload reference data, smoke test (US-1.5)
make db-smoke    count the warehouse objects: 13 dims, 6 facts, 10 audit tables, 41 FKs, 48 partitions
make generate    generate seeded source data into data/ (US-2.1); PROFILE=small|full SEED=n CLEAN=1 (no defects)
make patterns    measure the six planted patterns in data/ with pandas (US-2.6)
make gen-test    generator acceptance tests, no database needed (US-2.1: 39, US-2.2: 129, US-2.3: 114, US-2.4: 80, US-2.5: 69 + 56, US-2.6: 71, E3 contract: 17, E4 contract: 20, E5 contract: 36, E6 contract: 19, E7 contract: 26, E8 contract: 22, US-9.3 contract: 10, E10 contract: 13, E11 contract: 14)
make weather     download the S5 weather once into data/weather_cache.json (US-2.5; needs internet)
make weather-check  check the weather cache covers every city and day (no internet)
make db-load-source  load data/s1 into lue_source.src_pms as lue_etl; safe to re-run (US-2.2 to US-2.4)
make db-test     database acceptance tests: 22 (US-1.1), 28 (US-1.2), 24 (US-1.3), 32 (US-1.4), 12 (US-1.5) and 66 (US-2.2 to US-2.4) PASS lines;
                 load a clean batch first (make generate CLEAN=1, then make db-load-source)
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

On Windows, `make` is not installed by default. Every target is one Python command (shown above); the checks CI runs
are `python scripts/run_ci.py` (after `pip install -r requirements-ci.txt`).

## Recovery (US-8.3)

The pipeline is safe to rerun and safe to resume.

- **Rerun.** On unchanged inputs a second `python etl/run_pipeline.py --skip-generate` inserts, updates and rejects
  nothing in any step, and every table hashes identically (D14). The one declared exception is the occupancy snapshot:
  every run rewrites its last 35 days (NFR-08), with the same values unless a source changed; the run log shows them as
  `rows_updated` of `fact_unit_occupancy_daily`.
- **A failed step.** Each step is one transaction: a step that fails leaves nothing of itself behind (no partial rows),
  and the steps before it stay committed. A failed critical step stops the run, exit 1; the terminal names the stage and
  prints the command to resume.
- **Resume.** Fix the cause (the message in the run log says what failed), then run the printed command:

      python etl/run_pipeline.py --skip-generate --from-step <stage>

  It starts at that stage and runs the rest; every step is idempotent, so rerunning a stage that half ran is safe. Check
  the run with `SELECT step, status, rows_read, rows_inserted, rows_updated, rows_rejected FROM lue_audit.etl_run_log
  WHERE run_id = <run>` and finish when the last stage, marts, passes.
- **Other generated data.** A warehouse holds one generation of the data (profile, seed, content hash). A run on another
  one stops at `check_generation` before anything changes; to switch, reset first: `python scripts/db_reset.py`, or
  `make rebuild PROFILE=full`.
- **A broken database** (a disk full, a dropped table): `python scripts/db_reset.py`, then
  `python etl/run_pipeline.py --skip-generate` rebuilds everything from the generated data.

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
| `project_reporting` | `lue_reporting` | 4 marts (`mart_*`), the reporting views and 9 slicer views (`vw_dim_*`): [docs/reporting.md](docs/reporting.md) |
| (none) | `lue_audit` | `etl_run_log`, `quarantine`, `reconciliation`, `lineage` |
| (none) | `lue_source.src_pms` | Source system S1; separate database `lue_source` |
| `vw_monthly_sales` | `vw_monthly_collections` | Alias view in `lue_reporting` (D18): `SELECT *` from the LUE view (US-10.1) |
| `vw_customer_analysis` | `vw_tenant_analysis` | Alias view (D18) |
| `vw_product_performance` | `vw_unit_performance` | Alias view (D18) |

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

### Weather data (S5, US-2.5)

`data/weather_cache.json` is real daily weather (maximum temperature, rainfall) for Lahore, Karachi, Islamabad and
Faisalabad, 2023-07-01 to 2026-06-30, from the [Open-Meteo](https://open-meteo.com/) historical API (CC BY 4.0,
"Weather data by Open-Meteo.com"). It is downloaded once with `python etl/refresh_weather.py` and committed
(decision D12): nothing else uses the network, so nobody else needs internet access.

The download makes 16 small requests (4 cities x 4 periods) with a pause between them, retries rate limits and
network errors, keeps finished requests in `data/.weather_parts/` so a stopped run resumes, and writes the cache only
when every part is complete and valid. If your network blocks the API, run `python etl/refresh_weather.py
--print-urls`, save each link from a browser into one folder, then `python etl/refresh_weather.py --import-dir
<folder>`. Check the cache any time with `make weather-check`.

### Ingestion into bronze (E3)

After `make db-deploy` (which now also creates the 20 `lue_staging.brz_*` tables) and `make db-load-source`:

    python etl/ingest/run.py              # or: make ingest. --only S1,S4 for some sources

Each source is one transaction (a failure rolls it back; the others still run) and one row in
`lue_audit.etl_run_log`. S1 lands only new or changed rows (row hash), the files only new or changed files (SHA-256,
recorded in `lue_audit.file_load`); a second run lands nothing. Every run ends with a reconciliation of all 20 bronze
tables in `lue_audit.reconciliation`. The log is in `logs/ingest.log`.

### Data quality and quarantine (E4)

The rules are data: `etl/quality/rules.toml` (109 rules; the field list is at its top). After an ingestion:

    python etl/quality/run.py --compare   # or: make validate

runs them on every bronze batch in the order DQ-01 (NULL) to DQ-06 (range). A row is rejected by the first rule it
fails: it goes to `lue_audit.quarantine` (as JSON, with the check and a reason that quotes the column and value) and
later rules skip it. Warnings (a conflicting duplicate, a tenant that has not arrived yet, a mid-lease rent change)
are findings only. Everything is in `lue_audit.dq_result`; staging keeps the bronze rows without a rejection.
`--compare` checks the findings against the answer key and writes `data/dq_validation.csv`: on the full profile all
6,915 planted defects in scope are found, with no false positive, and a clean control batch gets no finding.

### Reporting layer (E10)

`lue_reporting` is what Power BI and the analysts read; every column and measure is defined in
[docs/reporting.md](docs/reporting.md). `sql/50_reporting/01_reporting.sql` (deployed by `scripts/db_deploy.py`) creates:

| Object | Grain | What it answers |
|---|---|---|
| `vw_monthly_collections` (alias `vw_monthly_sales`) | month | billed, collected and the **cohort collection rate (D17)**, cash received, arrears, growth (LAG) |
| `vw_tenant_analysis` (alias `vw_customer_analysis`) | tenant version | payments, late payments, days past due, collected, arrears, payer segment (Q4) |
| `vw_unit_performance` (alias `vw_product_performance`) | building x unit type | occupancy, vacancy, rent, maintenance cost per unit-month, days to resolve, SLA breaches |
| `mart_collections_monthly` | month x building | the collections measures as additive parts |
| `mart_occupancy_monthly` | month x building x unit type | unit-days, occupied days, vacancy spells, month-end rent roll and arrears |
| `mart_maintenance_monthly` | raised month x building x unit type x category x vendor | requests, resolution, SLA, cost |
| `mart_owner_portfolio_monthly` | month x owner | rent collected, maintenance cost, the 8 percent fee assumption, NOI (Q12) |
| `vw_dim_*` (9) | one row per member or version | the slicers: date, month, building, unit, tenant, owner, vendor, maintenance category, payment method |

The marts are refreshed by the pipeline's last stage (`marts`; alone `python etl/reporting.py`), concurrently so
readers are never blocked. `lue_reader` reads `lue_reporting` only: it cannot read `lue_staging`, `lue_dw` or
`lue_audit`, write, or refresh (`python scripts/test_reporting.py` shows the denials).

### Planted defects, answer key and patterns (US-2.6)

A normal generation plants about 1 to 3 percent of defects (rates in `etl/generator_config.py`) and writes the
answer key into `data/answer_key/`: `defects_answer_key.csv` (every defect: source, table, record, column, type,
expected handling `reject`, `warn`, `repair` or `accept`, and the check that should catch it), `summary.csv`,
`totals.csv`, `expectations.json` (the counts later stories compare with) and `planted_patterns.md`. Two S1 files model
the next extract and are not loaded by `db_load_source.py`: `s1/changes/tenants.csv` (tenant changes for SCD2) and
`s1/late_arriving/tenants.csv` (tenants that arrive late, for inferred members).

`python etl/generate_data.py --clean` (or `make generate CLEAN=1`) is the clean control batch: every rate 0, an empty
answer key. The database tests of US-2.2 to US-2.4 need it. The six business patterns (a high-arrears building, a slow
vendor, summer move-ins, offers that shorten vacancies, leak tickets after rain, renewal churn in Karachi) are in both;
`python scripts/check_patterns.py --data <folder>` measures them (full profile: all six must show their effect).

## Change control for the frozen Phase 1 pack

`docs/phase1/` matches `MANIFEST.sha256`, and CI fails if any file there changes. A design change needs a dated row in
the change log in `docs/phase1/README.md`, a regeneration with `docs/phase1/tools/`, and a new manifest and tag.

Branch rules verified with a test pull request (US-0.3).
