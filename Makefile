PYTHON ?= python
.DEFAULT_GOAL := help
.PHONY: help setup rebuild test lint sqlcheck manifest contract gen-test generate reports db-setup db-deploy db-load-ref db-smoke db-test db-reset

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup: ## Set up environment dependencies and test database connection (US-0.4)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) scripts/test_connection.py

rebuild: ## Stub: full rebuild of databases, data, pipeline and marts (E9)
	@echo "rebuild: not implemented yet (grows with each epic; must always pass on main)"

test: lint sqlcheck manifest contract gen-test ## Everything CI runs

lint: ## Ruff on our own Python (docs/ is excluded)
	ruff check etl scripts

sqlcheck: ## pglast parse of every .sql file under sql/ and docs/phase1/sql/
	$(PYTHON) scripts/ci_checks.py --sql

manifest: ## docs/phase1 must still match MANIFEST.sha256 (frozen baseline)
	$(PYTHON) scripts/ci_checks.py --manifest

contract: ## sql/10_ddl must match the frozen Phase 1 DDL (US-1.2)
	$(PYTHON) scripts/check_contract.py

gen-test: ## Generator acceptance tests, no database needed (US-2.1)
	$(PYTHON) scripts/test_generator.py

generate: ## Generate the seeded source data: make generate PROFILE=small SEED=3004 (US-2.1)
	$(PYTHON) etl/generate_data.py --profile $(or $(PROFILE),small) --seed $(or $(SEED),3004)

reports: ## Stub: generate the report PDFs (E9, E14)
	@echo "reports: not implemented yet"

db-setup: ## Create databases, roles and schemas; safe to re-run (US-1.1)
	$(PYTHON) scripts/db_setup.py

db-deploy: ## Deploy sql/10_ddl as lue_etl; safe to re-run (US-1.2)
	$(PYTHON) scripts/db_deploy.py

db-load-ref: ## Load dim_date and the static dimensions; safe to re-run (US-1.4)
	$(PYTHON) scripts/db_load_reference.py

db-test: ## Database acceptance tests (US-1.1 to US-1.5)
	$(PYTHON) scripts/test_db_setup.py
	$(PYTHON) scripts/test_dimensions.py
	$(PYTHON) scripts/test_facts.py
	$(PYTHON) scripts/test_reference.py
	$(PYTHON) scripts/test_smoke.py

db-reset: ## Drop and rebuild the warehouse schemas, reload reference data, smoke test (US-1.5)
	$(PYTHON) scripts/db_reset.py

db-smoke: ## Count the warehouse objects (US-1.5)
	$(PYTHON) scripts/test_smoke.py
