# US-8.1 Single-command pipeline orchestrator

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.1` (one pull request for US-8.1 to US-8.3, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.1/`](../evidence/us-8.1/) |

## Story

As a developer, I want a single command that runs the full LUE pipeline end-to-end, so that I can
reproduce the warehouse from scratch without remembering the order of eight separate scripts.

## What was done

1. **`run_pipeline.py`** at the repo root: an orchestrator that runs all 11 pipeline steps in
   order, calling each module's `main()` directly (no subprocess). Steps:
   `generate`, `db-setup`, `db-deploy`, `db-load-ref`, `db-load-src`, `ingest`, `validate`,
   `stage`, `dims`, `facts`, `reports`.
2. **CLI flags**: `--profile small|full`, `--seed 3004`, `--skip-generate`, `--from-step STEP`,
   `--only STEP`, `--skip STEP` (repeatable).
3. **Critical vs non-critical**: `generate` and `reports` are non-critical; all DB steps through
   `facts` are critical. A critical failure stops the pipeline and exits 1.
4. **Lazy imports**: each step's module is imported inside the step function so a missing database
   does not crash at import time.
5. **Structured logging** to `logs/pipeline.log` (append mode), same format as other run.py files.
6. **Summary table** printed at the end: step, status, duration, rows.

## Files added or changed

- `run_pipeline.py` (new)
- `etl/pipeline/__init__.py` (new, empty)
- `docs/stories/US-8.1.md`, `docs/evidence/us-8.1/README.md`

## Decisions and deviations

- **No subprocess**: all steps are called by importing their `main()` function so stdout/stderr
  are shared and the process stays single.
- **Lazy imports**: each step runner imports its module inside the function body, so `import
  run_pipeline` never touches the database.
- **db-load-src alias**: the brief uses both `db-load-src` and `db-load-source`; the orchestrator
  registers `db-load-src` as the canonical name and accepts the alias in validation.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| `run_pipeline.py` exists and passes syntax check | Pass | `scripts/test_pipeline_contract.py` check 1 |
| All 11 step names in `STEPS` | Pass | check 2 |
| `--from-step`, `--only`, `--skip-generate`, `--profile`, `--seed` all present | Pass | check 4 |
| `logs/` directory created | Pass | check 5 |
| `generate` first, `reports` last | Pass | check 6 |

## How to re-check it

    python scripts/test_pipeline_contract.py      # expect 6/6
    python run_pipeline.py --skip-generate        # full run after data exists
