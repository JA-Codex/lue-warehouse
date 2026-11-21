# Evidence for US-7.5: fact_lease_event and fact_vacancy_incentive_coverage

Full profile, seed 3004. Staging, the dimensions and the occupancy snapshot as left by US-7.4.

| File | What it shows |
|---|---|
| `01_factless.txt` | The first load (8,781 lease events, 20,177 coverage rows) and a rerun (nothing inserted, updated or deleted), counts by event type against staging (difference 0 for all four), the lease event grain, the coverage row check (624 windows, 20,177 window-days, 20,177 rows, all vacant in the occupancy snapshot), coverage by offer, and the composite primary key refusing a duplicate |
| `02_fact_tests.txt` | `scripts/test_fact_load_contract.py` (23 checks, no database) and `scripts/test_fact_load.py` (49 checks; the US-7.5 part: counts by type, keys of the event date, coverage rows, every coverage day vacant in the snapshot, the primary key, a rerun) |
