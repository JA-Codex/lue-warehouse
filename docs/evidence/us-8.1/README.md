# Evidence: US-8.1 — Single-command pipeline orchestrator

US-8.1 implements `run_pipeline.py`, a single-command orchestrator at the repo root that runs the
full LUE pipeline end-to-end in the correct order: data generation (`generate`), database
setup and deploy (`db-setup`, `db-deploy`, `db-load-ref`, `db-load-src`), ingestion (`ingest`),
quality validation (`validate`), staging (`stage`), dimension loading (`dims`), fact loading and
tests (`facts`), and report building (`reports`). Each step is called by importing its `main()`
function directly (no subprocess), with lazy imports so a missing database does not crash at
startup. CLI flags (`--profile`, `--seed`, `--skip-generate`, `--from-step`, `--only`, `--skip`)
give fine-grained control over which steps run. Critical steps (`db-setup` through `facts`) cause
the pipeline to exit 1 and stop on failure; non-critical steps (`generate`, `reports`) log the
error but continue. Structured logs are appended to `logs/pipeline.log`, and a summary table is
printed at the end showing step, status, duration, and row counts.

## Key files

- `run_pipeline.py` — the pipeline orchestrator (repo root)
- `etl/pipeline/__init__.py` — empty package marker
- `docs/stories/US-8.1.md`
- `docs/evidence/us-8.1/README.md` (this file)

## Verification

Run `python scripts/test_pipeline_contract.py` to verify offline.
