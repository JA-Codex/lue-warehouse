# Evidence: US-8.4 — Pipeline timing

## Summary

US-8.4 adds per-step timing to `run_pipeline.py`.  After each step completes,
the elapsed wall-clock time (measured with `time.monotonic()`) is stored in a
`StepResult` record.  At the end of the run, a summary table is printed to
stdout and written to `logs/pipeline.log`, showing every step name, its status
(`OK` / `SKIP` / `FAIL`), duration in seconds, and row count where the step
returned one.  The offline contract test `scripts/test_pipeline_timing.py`
verifies this infrastructure exists without a database.

## Key files

| File | Purpose |
|---|---|
| `run_pipeline.py` | Pipeline orchestrator with timing |
| `scripts/test_pipeline_timing.py` | Offline contract test (13 checks) |
| `Makefile` | `rebuild`, `pipeline`, `pipeline-test` targets |
| `logs/pipeline.log` | Append-mode run log (not committed) |

## How to re-verify offline

    python scripts/test_pipeline_timing.py
    # Expected: 13/13 timing contract checks passed

## Evidence files

| File | Description |
|---|---|
| `01_run_output.txt` | stdout of a small-profile pipeline run showing the summary table |
| `02_full_profile_summary.txt` | Summary table from a full-profile run (> 10 000 fact rows) |
| `03_make_rebuild.txt` | Output of `make rebuild` (exit 0) |
| `04_timing_contract.txt` | Output of `python scripts/test_pipeline_timing.py` |
