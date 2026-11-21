# Evidence for US-8.3: idempotency and failure recovery

Full profile, seed 3004, on an empty warehouse (`python scripts/db_reset.py`).

| File | What it shows |
|---|---|
| `01_rerun_and_recovery.txt` | A first run, then a second run on unchanged inputs: its run log (49 of 50 steps 0 inserted, 0 updated, 0 rejected; the one other is the declared occupancy refresh, 63,000 rows) and the content hashes of all 62 tables of bronze, staging and the warehouse after each run (identical). Then a crash injected inside the fact_payment step after it wrote 127,210 rows: 0 rows left, the other facts committed, the run stopped with the resume command; the resume with `--from-step facts` (exit 0) and the warehouse after it, as before the crash |
| `02_pipeline_tests.txt` | `scripts/test_pipeline_contract.py` (21 checks, no database) and `scripts/test_pipeline.py` (21 checks; the US-8.3 part: the rerun's counts and hashes, the crash and the resume, another generation refused) |
