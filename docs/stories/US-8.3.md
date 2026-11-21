# US-8.3 Offline pipeline contract tests

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.3` (one pull request for US-8.1 to US-8.3, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.3/`](../evidence/us-8.3/) |

## Story

As a CI engineer, I want contract tests that verify the pipeline structure without touching the
database, so that every pull request confirms the orchestrator and reconcile module are intact.

## What was done

1. **`scripts/test_pipeline_contract.py`**: 6 offline checks:
   1. `run_pipeline.py` exists and its syntax is valid (`compile()`).
   2. All 11 step names are defined in the `STEPS` list in `run_pipeline.py` (parsed with `ast`).
   3. `etl/pipeline/reconcile.py` exists and defines `reconcile()` and `ReconcileError`.
   4. `--from-step`, `--only`, `--skip-generate`, `--profile`, `--seed` are all present in the
      orchestrator source (argparse flags).
   5. `logs/` directory is created by the pipeline (`mkdir` + `"logs"` in source).
   6. Step order: `generate` is first, `reports` is last in `STEPS`.
2. Prints `{n}/{n} pipeline contract checks passed` and exits 0 on pass, 1 on fail.

## Files added or changed

- `scripts/test_pipeline_contract.py` (new)
- `docs/stories/US-8.3.md`, `docs/evidence/us-8.3/README.md`

## Decisions and deviations

- **AST parsing** used to extract the `STEPS` list rather than importing `run_pipeline`, which
  would trigger lazy-import side effects.
- **No pglast dependency**: unlike `test_fact_load_contract.py`, these checks are pure stdlib.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Script exists and passes all 6 checks | Pass | run output below |
| No database needed | Pass | stdlib only |

## How to re-check it

    python scripts/test_pipeline_contract.py      # expect 6/6
