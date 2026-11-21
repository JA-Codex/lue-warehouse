# Evidence for US-9.3: the Phase 2 submission

| File | What it shows |
|---|---|
| [`../../phase2_checklist.md`](../../phase2_checklist.md) | The plan's Appendix B for Phase 2: every deliverable ticked with its files (CI checks each path exists) |
| `01_fresh_clone_run.txt` | The fresh-clone rehearsal: the README's "Run it from a fresh clone" steps, word for word, on commit `a1030e9` |

## The rehearsal

Started from an **empty PostgreSQL 16** (both LUE databases and both roles dropped first: "LUE databases: 0, LUE
roles: 0"), a fresh clone of the `e9-reports` branch at `a1030e9` (a local copy of the commit pushed to GitHub), a new
virtual environment and a `.env` made from `.env.example` with only `PGPASSWORD` and `PGPORT` set. Linux, Python 3.11.

| Step | Command | Result |
|---|---|---|
| 1-3 | clone, `pip install -r requirements.txt -r requirements-ci.txt`, `.env`, `python scripts/test_connection.py` | connected |
| 4 | `python scripts/run_ci.py` | `ALL PASSED: 19 checks in 148s` (every test's RESULT line is in the log) |
| 5 | `python etl/run_pipeline.py --profile small` | run 1: 51/51 steps without failure in 7 s; reconciliation passed |
| 6 | `python scripts/test_reports.py`, `python scripts/test_load_sql.py` | 11/11, 6/6 |
| 7 | `python etl/reports/build.py --out data/reports` | both PDFs written |
| after | `git status --short` | working tree clean: the run changes no tracked file |

The `validate` stage's Warning is expected: 25 planted defects rejected into quarantine (the small profile's share
of the answer key; all 32 planted defects found, 0 false positives).

The only change after `a1030e9` is documentation: this folder, the story log, and one word in the README
(the small profile builds in "under a minute", not "about a minute").
The tag `phase2-submission` is set on the merge commit of the E9 pull request, whose files equal the branch's.

To run it again on your own machine: the README, **Run it from a fresh clone**.
