# Evidence for US-6.1: the dimension loader and surrogate keys

Full profile, seed 3004, on a fresh warehouse (`python scripts/db_reset.py`, then ingest, validate and stage).

| File | What it shows |
|---|---|
| `01_dimension_runs.txt` | The first load (3,762 tenants inserted) and a rerun (0 inserted, 0 updated), the run log of both, the business key next to the surrogate key, and key uniqueness |
| `02_dimension_tests.txt` | `scripts/test_dim_load_contract.py` (10 checks, no database) and `scripts/test_dim_load.py` (11 checks: rerun, Type 1 in place, Type 2 left alone, keys never reused, a duplicate source refused) |
