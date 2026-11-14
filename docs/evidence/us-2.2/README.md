# Evidence for US-2.2: master data and registers

| File | What it shows |
|---|---|
| `01_database_counts.txt` | Row counts of the five `src_pms` tables after loading |
| `02_acceptance_tests.txt` | `python scripts/test_master_data.py`: 129/129 |
| `03_database_tests.txt` | `python scripts/test_source_load.py`: 30/30 (run through a psql-backed psycopg2 stand-in on PostgreSQL 16) |
| `04_workbook_overview.txt`, `04_workbook_owners_sheet.png` | The S2 workbook: sheets, rows, and the owners sheet rendered |
| `05_tests_catch_broken_data.txt` | Eight deliberately broken datasets fail the tests |

Content hash for `--profile small --seed 3004`:
`7e1030ea22c78fc1b4954f2b35627f82960a8df24fcc78c419efb859ffbf7089`.
