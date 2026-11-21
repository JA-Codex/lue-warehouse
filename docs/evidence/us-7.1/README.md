# Evidence for US-7.1: the fact loader and date-aware key mapping

Full profile, seed 3004. Staging and the dimensions as left by US-6.5 (both S1 extracts applied).

| File | What it shows |
|---|---|
| `01_fact_runs.txt` | The first load of `fact_payment` (127,210 rows) and a rerun (0 inserted, 0 updated, 0 deleted), the run log of both, rows and amount against staging, the key-mapping chain of two payments by tenant T-0115 (one before and one after its sector change on 2024-10-10), and the whole-fact check (0 keys outside their version) |
| `02_fact_tests.txt` | `scripts/test_fact_load_contract.py` (9 checks, no database), `scripts/test_fact_load.py` (10 checks: totals, point-in-time tenant, unit and owner keys, role-playing dates, the mapping chain, rerun, a changed and a removed source row, a duplicate grain refused) and the E1 checks that E6 and E7 touch (fact identity sequences with a fact loaded, holiday flags after US-6.4) |
