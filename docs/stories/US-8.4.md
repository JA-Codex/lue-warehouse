# US-8.4 Pipeline timing: per-step summary table

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by team) |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.x` (one pull request for US-8.1 to US-8.4) |
| Evidence | [`../evidence/us-8.4/`](../evidence/us-8.4/) |

## Story

As a developer, I want `run_pipeline.py` to record and display per-step timing,
so that I can see which step is slow and diagnose regressions.

## What was done

1. **Per-step timing** in `run_pipeline.py`: each step records `time.monotonic()`
   before and after the call; the elapsed seconds are stored in a `StepResult`
   dataclass alongside the step name, status, and any row counts returned by
   the module's `main()`.
2. **Summary table** printed at the end of every run, showing step name, status
   (`OK` / `SKIP` / `FAIL`), duration in seconds, and row count where available.
3. **Full-profile evidence**: a `make rebuild PROFILE=full` run on the small
   development machine generates > 10 000 fact rows; timing baseline is captured
   for each step and committed to `docs/evidence/us-8.4/`.
4. **`make rebuild`** wires everything together: `db_reset.py` then
   `run_pipeline.py --skip-generate`; the full profile is
   `make rebuild PROFILE=full`.
5. **Offline contract test** `scripts/test_pipeline_timing.py` verifies the
   timing infrastructure exists without a database.

## Files added or changed

- `run_pipeline.py` (timing mechanism, summary table)
- `scripts/test_pipeline_timing.py` (US-8.4 offline contract)
- `Makefile` (`rebuild`, `pipeline`, `pipeline-test` targets)
- `README.md` (§6 Pipeline)
- `docs/stories/US-8.4.md`, `docs/evidence/us-8.4/README.md`

## Decisions and deviations

- **`time.monotonic()` over `datetime.now()`**: monotonic clock is unaffected
  by system-clock adjustments and is the right tool for elapsed-time measurement.
- **Row counts are best-effort**: each module's `main()` may return an integer
  row count or `None`; `run_pipeline.py` displays it when present.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Each step prints its elapsed time | Pass: summary table shown at run end | `01_run_output.txt` |
| Full profile generates > 10 000 fact rows | Pass: fact row count in summary table | `02_full_profile_summary.txt` |
| `make rebuild` completes without error | Pass: exit 0, all critical steps green | `03_make_rebuild.txt` |
| Offline timing contract passes | Pass: 13/13 timing contract checks passed | `04_timing_contract.txt` |

## How to re-check it

    python scripts/test_pipeline_timing.py          # offline: expect 13/13
    python run_pipeline.py --skip-generate          # small profile pipeline
    make rebuild                                    # db-reset + pipeline (small)
    make rebuild PROFILE=full                       # full profile (~10 000+ rows)
