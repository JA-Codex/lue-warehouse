# Evidence for US-5.1: clean, standardise and deduplicate

Full profile, seed 3004, a full staging load (`python etl/staging/run.py --full --compare`).

| File | What it shows |
|---|---|
| `01_staging_full_run.txt` | The full load: per table rows read, rejected by E4, unusable, superseded, inserted; the business step; the count bridge; the answer key |
| `02_count_bridge.csv` | Per table: bronze rows - rejected - unusable - deduplicated = staged rows, difference 0, explained |
| `03_distinct_values.csv` | Distinct values before (bronze) and after (staging) of every vocabulary column and the payment method |
| `04_staging_tests.txt` | `scripts/test_staging.py` (35 checks, all of E5) and `scripts/test_staging_contract.py` (36 checks, no database) |
