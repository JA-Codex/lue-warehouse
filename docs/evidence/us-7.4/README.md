# Evidence for US-7.4: fact_maintenance_request

Full profile, seed 3004. Staging and the dimensions as left by US-6.5.

| File | What it shows |
|---|---|
| `01_lifecycle.txt` | The first load (5,670 requests) and a rerun (nothing inserted, updated or deleted), the run log, one row per request, the lifecycle stages with their -2 milestone keys, the SLA breach rate by category and SLA version, and the same ticket (MR-2026-00944) at two lifecycle stages: assigned in run A, verified in run B, the same row (request_sk 5659) updated in place |
| `02_fact_tests.txt` | `scripts/test_fact_load_contract.py` (20 checks, no database) and `scripts/test_fact_load.py` (41 checks; the US-7.4 part: milestones, durations recomputed from the timestamps, SLA, every key against staging, a rerun hash-identical, a ticket progressing between two runs) |
