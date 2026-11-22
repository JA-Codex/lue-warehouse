PYTHON ?= python
.DEFAULT_GOAL := help
.PHONY: help setup rebuild pipeline test lint sqlcheck manifest contract gen-test generate patterns weather weather-check ingest validate reports load-sql marts reporting-test db-setup db-deploy db-load-ref db-load-source db-smoke db-test ingest-test quality-test db-reset

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup: ## Set up environment dependencies and test database connection (US-0.4)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) scripts/test_connection.py

rebuild: ## Reset the warehouse, generate the data and run the whole pipeline: make rebuild [PROFILE=full] [SEED=n] (US-8.1)
	$(PYTHON) scripts/db_reset.py
	$(PYTHON) etl/run_pipeline.py --profile $(or $(PROFILE),small) --seed $(or $(SEED),3004)

pipeline: ## Run the whole pipeline on the data already in data/, one run_id (US-8.1); FROM=stage resumes there
	$(PYTHON) etl/run_pipeline.py --skip-generate $(if $(FROM),--from-step $(FROM),)

test: ## Everything CI runs (no make on Windows: python scripts/run_ci.py)
	$(PYTHON) scripts/run_ci.py

lint: ## Ruff on our own Python (docs/ is excluded)
	$(PYTHON) scripts/run_ci.py lint

sqlcheck: ## pglast parse of every .sql file under sql/ and docs/phase1/sql/
	$(PYTHON) scripts/run_ci.py sqlcheck

manifest: ## docs/phase1 must still match MANIFEST.sha256 (frozen baseline)
	$(PYTHON) scripts/run_ci.py manifest

contract: ## sql/10_ddl must match the frozen Phase 1 DDL (US-1.2); the load scripts must match the loaders (US-9.3)
	$(PYTHON) scripts/run_ci.py contract

gen-test: ## Generator and contract tests, no database needed (US-2.1 to US-2.6, E3 to E9)
	$(PYTHON) scripts/run_ci.py gen-test

load-sql: ## Re-export the dimension and fact load scripts from the specs (US-9.3)
	$(PYTHON) scripts/export_load_sql.py

marts: ## Refresh the four reporting marts from the facts, as the pipeline's last stage does (US-10.2)
	$(PYTHON) etl/reporting.py

reporting-test: ## Reporting layer acceptance tests (US-10.1 to US-10.3); needs a loaded warehouse, changes nothing
	$(PYTHON) scripts/test_reporting.py

generate: ## Generate the seeded source data: make generate PROFILE=small SEED=3004 [CLEAN=1] (US-2.1, US-2.6)
	$(PYTHON) etl/generate_data.py --profile $(or $(PROFILE),small) --seed $(or $(SEED),3004) $(if $(CLEAN),--clean)

patterns: ## Measure the six planted patterns in data/ with pandas (US-2.6; use PROFILE=full CLEAN=1 data)
	$(PYTHON) scripts/check_patterns.py

weather: ## Download the S5 weather once into data/weather_cache.json; resumes if stopped (US-2.5)
	$(PYTHON) etl/refresh_weather.py

weather-check: ## Check data/weather_cache.json covers every city and day; no network (US-2.5)
	$(PYTHON) etl/refresh_weather.py --check

db-setup: ## Create databases, roles and schemas; safe to re-run (US-1.1)
	$(PYTHON) scripts/db_setup.py

db-deploy: ## Deploy sql/10_ddl as lue_etl; safe to re-run (US-1.2)
	$(PYTHON) scripts/db_deploy.py

db-load-ref: ## Load dim_date and the static dimensions; safe to re-run (US-1.4)
	$(PYTHON) scripts/db_load_reference.py

db-load-source: ## Load the generated S1 data into lue_source.src_pms; safe to re-run (US-2.2 to US-2.4)
	$(PYTHON) scripts/db_load_source.py

db-test: ## Database acceptance tests (US-1.1 to US-1.5, US-2.2 to US-2.4; load a CLEAN=1 generation)
	$(PYTHON) scripts/test_db_setup.py
	$(PYTHON) scripts/test_dimensions.py
	$(PYTHON) scripts/test_facts.py
	$(PYTHON) scripts/test_source_load.py
	$(PYTHON) scripts/test_reference.py
	$(PYTHON) scripts/test_smoke.py

ingest: ## Land all six sources in bronze: S1 from src_pms, the files from data/ (E3)
	$(PYTHON) etl/ingest/run.py

ingest-test: ## Ingestion acceptance tests (US-3.1 to US-3.4); empties bronze, then refills it
	$(PYTHON) scripts/test_ingest.py

validate: ## Run the quality rules on bronze and compare with the answer key (E4)
	$(PYTHON) etl/quality/run.py --compare

quality-test: ## Data quality acceptance tests (US-4.1 to US-4.4); reloads src_pms and bronze
	$(PYTHON) scripts/test_quality.py

stage: ## Load staging incrementally, record the evidence, compare with the answer key (E5); FULL=1 reloads all
	$(PYTHON) etl/staging/run.py --compare $(if $(FULL),--full,)

staging-test: ## Staging acceptance tests (US-5.1 to US-5.4); reloads src_pms, bronze and staging (about 7 minutes)
	$(PYTHON) scripts/test_staging.py

dims: ## Load the dimensions from staging: new members get surrogate keys, Type 1 overwritten (E6)
	$(PYTHON) etl/dimensions/run.py

dims-test: ## Dimension acceptance tests (US-6.1 to US-6.5); reloads src_pms, bronze, staging and the dimensions
	$(PYTHON) scripts/test_dim_load.py

next-extract: ## Apply the generator's next S1 extract (tenant changes, late tenants) to src_pms (US-6.2, US-6.5)
	$(PYTHON) scripts/db_apply_next_extract.py

facts: ## Load the facts from staging and the dimensions: keys point in time, synced on the grain (E7)
	$(PYTHON) etl/facts/run.py

facts-test: ## Fact acceptance tests (US-7.1 on); needs staging and the dimensions loaded (make stage, make dims)
	$(PYTHON) scripts/test_fact_load.py

reports: ## Build the Phase 2 reports (cleaning, quality) from the loaded warehouse into docs/reports/ (US-9.1, US-9.2)
	$(PYTHON) etl/reports/build.py

db-reset: ## Drop and rebuild the warehouse schemas, reload reference data, smoke test (US-1.5)
	$(PYTHON) scripts/db_reset.py

db-smoke: ## Count the warehouse objects (US-1.5)
	$(PYTHON) scripts/test_smoke.py
