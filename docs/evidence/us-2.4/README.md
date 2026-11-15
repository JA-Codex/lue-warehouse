# Evidence for US-2.4: payments and settlements

| File | What it shows |
|---|---|
| `01_hash_comparison.txt` | Same seed gives identical hashes (S1 and all S3 files), another seed differs; earlier files unchanged except invoice status |
| `02_acceptance_tests.txt` | `python scripts/test_payments.py`: 80/80 |
| `03_database_tests.txt` | `python scripts/test_source_load.py`: 66/66 on PostgreSQL 16.2 with real psycopg2 |
| `04_behaviour_profiles.txt` | Late-day distribution, arrears and unpaid share per behaviour; methods; collection; settlement lag by channel; unmatched share |
| `05_settlement_and_payment_samples.txt` | Real rows: S3 files, a payment split across lines, a bounced cheque and its reversal |
| `06_tests_catch_broken_data.txt` | Eleven deliberately broken datasets fail the tests |

Content hash for `--profile small --seed 3004`:
`cbdb041c1a01ee87ac3d69ab7f07b3a8abbd0c935377ac5143908c44acb7872f`.
