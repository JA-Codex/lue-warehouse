# US-9.3 Package and GitHub submission

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.x` |
| Evidence | [`../evidence/us-9.3/`](../evidence/us-9.3/) |

## Story

As an assessor, I want to clone the repository and reproduce the full warehouse
in one command, so that I can verify every deliverable without manual steps.

## What was done

1. **README §6 Pipeline** documents `run_pipeline.py` as the one-command rebuild,
   lists all step names with descriptions, shows `--from-step` / `--only` flags,
   and notes that `make rebuild` runs the full pipeline.
2. **Prerequisites and quickstart** in README §2 and §3 (unchanged) cover
   PostgreSQL 16, Python 3.11+, `pip install -r requirements.txt`, `.env` setup
   and `make setup`.
3. **`run_pipeline.py`** wires every ETL stage into one command:
   `python run_pipeline.py --skip-generate` runs the full pipeline on existing
   data; `make rebuild` = `db_reset.py` + pipeline with `--skip-generate`.
4. **`make test`** (CI) includes `pipeline-test` (offline contract checks) and
   is the single gate that must pass on `main`.
5. **`phase2-submission` git tag** marks the commit delivered for assessment.
6. **Fresh-clone test**: the team verified a fresh clone on a second machine
   completes `make setup && make rebuild` without error.

## Files added or changed

- `README.md` (§6 Pipeline, updated §Commands)
- `run_pipeline.py`
- `Makefile` (`rebuild`, `pipeline`, `pipeline-test`)
- `scripts/test_pipeline_contract.py`, `scripts/test_pipeline_timing.py`
- `docs/stories/US-9.3.md`, `docs/evidence/us-9.3/README.md`

## Decisions and deviations

- **Pre-committed PDFs** in `docs/reports/` mean the assessor can read the
  reports without a live PostgreSQL instance.
- **`--skip-generate`** is the default for `make rebuild` because the generated
  data must already be in `data/` (committed or generated once); the flag avoids
  overwriting it accidentally.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| README has prerequisites, setup, pipeline, tests | Pass | README.md |
| `python run_pipeline.py` runs without arguments | Pass | `01_pipeline_run.txt` |
| `make test` passes on main | Pass: CI green | `02_ci_pass.txt` |
| Fresh-clone test passes | Pass: second machine test | `03_fresh_clone.txt` |

## How to re-check it

    git clone https://github.com/JA-Codex/lue-warehouse.git
    cd lue-warehouse
    python -m venv .venv && .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env  # then set PGPASSWORD
    make setup
    make generate PROFILE=small SEED=3004
    make rebuild
    make test
