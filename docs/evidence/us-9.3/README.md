# Evidence: US-9.3 — Package and GitHub submission

## Summary

US-9.3 wraps Phase 2 into a submission-ready package.  `run_pipeline.py` wires
all ETL stages into one command; `make rebuild` runs `db_reset.py` then the
pipeline with `--skip-generate`.  The README has a full quickstart (prerequisites,
environment setup, `make rebuild`, `make test`, report generation).  `make test`
(CI) includes the offline pipeline contract tests (`pipeline-test`).  The
`phase2-submission` git tag marks the delivered commit.  A fresh-clone test on
a second machine verified that `make setup && make rebuild` completes without
error.

## Key files

| File | Purpose |
|---|---|
| `README.md` | Quickstart, commands, §6 Pipeline |
| `run_pipeline.py` | One-command pipeline orchestrator |
| `Makefile` | `rebuild`, `pipeline`, `pipeline-test` targets |
| `scripts/test_pipeline_contract.py` | Offline contract (US-8.3) |
| `scripts/test_pipeline_timing.py` | Offline timing contract (US-8.4) |
| `docs/reports/` | Pre-committed PDFs |

## How to re-verify offline

    python scripts/test_pipeline_timing.py      # expect 13/13
    python scripts/test_pipeline_contract.py    # expect 6/6
    make test                                   # full CI gate

## Evidence files

| File | Description |
|---|---|
| `01_pipeline_run.txt` | stdout of `python run_pipeline.py --skip-generate` |
| `02_ci_pass.txt` | stdout of `make test` (all checks pass) |
| `03_fresh_clone.txt` | Log of fresh-clone test on second machine |
