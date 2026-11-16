# Evidence for US-2.6: planted defects, answer key and patterns

| File | What it shows |
|---|---|
| `01_answer_key_summary.txt` | The answer key totals and counts per type, source and table (full profile; small too) |
| `02_defect_tests.txt` | `python scripts/test_defects.py`: 71/71. Every change between the files before and after injection is in the key and the reverse; counts follow the rates; S1 still fits the source ERD; the clean batch is clean; the six patterns hold |
| `03_pattern_check.txt` | `python scripts/check_patterns.py` (pandas) on the clean full profile: 6/6, and on seeds 7, 42 and 99 |
| `04_reproducibility.txt` | Same seed: identical content hash and byte-identical answer key; another seed differs; the clean batch has 0 defects |
| `05_samples.txt` | One answer key row per (type, source, table), `expectations.json`, `planted_patterns.md`, the next-extract tenant files, a conflicting duplicate |
| `06_tests_catch_broken_code.txt` | 19 deliberate code changes: all caught after two weak tests were fixed; the real bug the suite found |
| `07_database_load.txt` | PostgreSQL 16: the defective full load works and SQL finds exactly the key's S1 counts; the clean batch passes every DB suite |
| `08_all_suites.txt` | `make test` on Python 3.11 (what CI runs): every suite passes |

All runs: seed 3004, NumPy 2.4.6, pandas 3.1.1, on 2026-11-16.
