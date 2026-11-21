# Evidence: US-8.3 — Offline pipeline contract tests

US-8.3 implements `scripts/test_pipeline_contract.py`, a pure-stdlib test script that verifies the
pipeline's structural contract without requiring a database connection. It performs six checks:
(1) `run_pipeline.py` exists and its Python syntax is valid; (2) all 11 expected step names
(`generate`, `db-setup`, `db-deploy`, `db-load-ref`, `db-load-src`, `ingest`, `validate`,
`stage`, `dims`, `facts`, `reports`) are defined in the `STEPS` list, extracted via `ast.parse`;
(3) `etl/pipeline/reconcile.py` exists and defines both `reconcile()` and `ReconcileError`;
(4) the five CLI flags `--from-step`, `--only`, `--skip-generate`, `--profile`, and `--seed`
are all present in the orchestrator source; (5) `logs/` directory creation is present in the
pipeline source; (6) the step order places `generate` first and `reports` last. The script prints
`{n}/{n} pipeline contract checks passed` and exits 0 on full pass, 1 otherwise.

## Key files

- `scripts/test_pipeline_contract.py` — the offline contract test (6 checks)
- `docs/stories/US-8.3.md`
- `docs/evidence/us-8.3/README.md` (this file)

## Verification

Run `python scripts/test_pipeline_contract.py` to verify offline.
