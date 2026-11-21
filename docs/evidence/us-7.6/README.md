# Evidence for US-7.6: automated grain, orphan and value checks

Full profile, seed 3004. Staging, the dimensions and all six facts as left by US-7.5.

| File | What it shows |
|---|---|
| `01_fact_tests.txt` | A full run ending with the `fact_tests` step (71 of 71 tests passed, exit code 0), its rows in the run log and in `lue_audit.reconciliation` (per fact: tests, orphan checks, passed, violations), the 71 tests run alone with `psql -f`, and a deliberate failure: one lease event duplicated and committed, the run's test step Failed (exit code 1) naming the grain test, the reconciliation rows that failed, and the next run passing once the duplicate is removed |
| `02_fact_tests.txt` | `scripts/test_fact_load_contract.py` (26 checks, no database) and `scripts/test_fact_load.py` (57 checks; the US-7.6 part: the full run's tests, the audit rows, the special members reported apart, four deliberately corrupted rows each failing exactly its test, a committed corruption failing the run) |
