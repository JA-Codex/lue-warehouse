# US-9.3 Package scripts, README and the GitHub submission

| | |
|---|---|
| Status | Done |
| Owner (plan) | Whole team (carried out by Hanan) |
| Done on | 2026-11-22 |
| Branch and pull request | `e9-reports` (one pull request for US-9.1 to US-9.3); tag `phase2-submission` |
| Evidence | [`../phase2_checklist.md`](../phase2_checklist.md), [`../evidence/us-9.3/`](../evidence/us-9.3/) |

## Story

As a marker, I want the repository to match the brief's deliverable list and run from the README, so that I can
verify everything quickly.

## What was done

1. **The brief's list mapped to files**: [`docs/phase2_checklist.md`](../phase2_checklist.md), the plan's Appendix B
   with every Phase 2 deliverable ticked and its files named. `scripts/test_submission_contract.py` (CI) fails if a
   named path does not exist, a row is not ticked, or the list differs from the plan's.
2. **Dimension and fact load scripts as SQL.** The loaders build their statements from specs, so the brief's
   "Dimension Load Scripts" and "Fact Load Scripts" had no SQL file of their own. `scripts/export_load_sql.py`
   writes the statements the loaders run to `sql/30_dimensions/02_dimension_loads.sql` and
   `sql/40_facts/01_fact_loads.sql` (runnable with `psql -f`, one transaction each; the parameters become session
   settings). CI fails while a file and its loader differ. `scripts/test_load_sql.py` proves the files on the
   warehouse, rolled back: the fact script on empty facts rebuilds every fact row the loader built (2,264,523 on
   the full profile, every column equal); both change nothing on a loaded warehouse but the declared occupancy
   refresh; the dimension script re-creates deleted members and restores corrupted Type 1 values. Each file's header
   says what stays in Python (SCD2 version planning, the refusals, the counts and lineage).
3. **README completed**: a "Run it from a fresh clone" section (prerequisites, clone and tag, environment, `.env`,
   the CI checks, the warehouse build, the tests, the reports), the layout and commands updated, the brief-name
   mapping with the alias views placed in Phase 3 (US-10.1, D18).
4. **No `make` needed**: `scripts/run_ci.py` runs everything CI runs on any operating system; `make test` and the
   other check targets call it, so the list of checks lives in one place. (Found on Windows, where `make` is missing;
   the same session fixed the tests that kept files open, which Windows cannot delete.)
5. **Rehearsal**: from an empty PostgreSQL, a fresh clone followed the README word for word; every step passed
   ([evidence](../evidence/us-9.3/)).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| The fresh-clone run passes | Pass: CI checks 19/19, pipeline 51/51 steps (run 1, from empty databases), report tests 11/11, load-script tests 6/6, both PDFs, tree clean | `../evidence/us-9.3/01_fresh_clone_run.txt` |
| Every Phase 2 deliverable maps to a file or folder | Pass: 9 of 9, 38 paths, each checked by CI | `../phase2_checklist.md` |
| Evidence: Appendix B checklist with file paths; fresh-clone run log | Pass | both above |

## How to re-check it

    python scripts/run_ci.py                    # includes test_submission_contract.py (10 checks)
    python etl/run_pipeline.py --profile small  # after python scripts/db_reset.py on an existing warehouse
    python scripts/test_load_sql.py             # expect 6/6
