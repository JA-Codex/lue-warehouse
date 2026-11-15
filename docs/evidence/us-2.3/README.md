# Evidence for US-2.3: leases, lease events and invoices

| File | What it shows |
|---|---|
| `01_hash_comparison.txt` | Same seed gives identical hashes, another seed differs; US-2.1 and US-2.2 files unchanged |
| `02_acceptance_tests.txt` | `python scripts/test_leases.py`: 114/114 |
| `03_database_tests.txt` | `python scripts/test_source_load.py`: 54/54 on PostgreSQL 16.2 with real psycopg2 |
| `04_overlap_check_and_counts.txt` | The overlap query (0 pairs), row counts, lease mix, events, active leases over time |
| `05_monthly_lease_starts.txt` | Monthly move-ins and renewals, and the June to August seasonal peak |
| `06_tests_catch_broken_data.txt` | Eleven deliberately broken datasets fail the tests |

Content hash for `--profile small --seed 3004`:
`a9cac42af9703345859100dc241cc7c3c06d214e055f87b92900bdbc5ec811db`.
