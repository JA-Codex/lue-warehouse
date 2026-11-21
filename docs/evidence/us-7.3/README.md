# Evidence for US-7.3: fact_unit_occupancy_daily

Full profile, seed 3004. Staging, the dimensions and the money facts as left by US-7.2.

| File | What it shows |
|---|---|
| `01_occupancy_load.txt` | The full load (1,972,800 rows in 97 s, from the run log) and a rerun (0 inserted, updated, deleted; 63,000 refreshed), the grain check (1,800 units x 1,096 days, zero duplicates), rows per partition, the monthly unit-day reconciliation (36 of 36), occupancy, rent roll and arrears on quarter-end days, and one unit across a vacancy and a new lease |
| `02_fact_tests.txt` | `scripts/test_fact_load_contract.py` (17 checks, no database), `scripts/test_fact_load.py` (31 checks; the US-7.3 part shows one unit's arrears before and after a late payment and the refresh) and the US-1.3 partition checks with the snapshot loaded |
