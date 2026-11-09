PYTHON ?= python
.DEFAULT_GOAL := help
.PHONY: help setup rebuild test lint sqlcheck manifest reports db-setup db-test db-reset

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup: ## Set up environment dependencies and test database connection (US-0.4)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) scripts/test_connection.py

rebuild: ## Stub: full rebuild of databases, data, pipeline and marts (E9)
	@echo "rebuild: not implemented yet (grows with each epic; must always pass on main)"

test: lint sqlcheck manifest ## Everything CI runs

lint: ## Ruff on our own Python (docs/ is excluded)
	ruff check etl scripts

sqlcheck: ## pglast parse of every .sql file under sql/ and docs/phase1/sql/
	$(PYTHON) scripts/ci_checks.py --sql

manifest: ## docs/phase1 must still match MANIFEST.sha256 (frozen baseline)
	$(PYTHON) scripts/ci_checks.py --manifest

reports: ## Stub: generate the report PDFs (E9, E14)
	@echo "reports: not implemented yet"

db-setup: ## Create databases, roles and schemas; safe to re-run (US-1.1)
	$(PYTHON) scripts/db_setup.py

db-test: ## Acceptance tests for the databases, roles and schemas (US-1.1)
	$(PYTHON) scripts/test_db_setup.py

db-reset: ## Stub: drop and recreate the warehouse schemas and redeploy (US-1.5)
	@echo "db-reset: not implemented yet (US-1.5)"
