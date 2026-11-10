# Evidence for US-1.4: date dimension and static reference dimensions

| File | What it shows |
|---|---|
| `01_load.txt` | `python scripts/db_load_reference.py`: the five tables loaded as `lue_etl` |
| `02_load_second_run.txt` | The same command again: same row counts (nothing changes) |
| `03_acceptance_tests.txt` | `python scripts/test_reference.py`: 32 PASS lines, including 1,461 days, no gaps, the fiscal boundary between 30 June 2026 and 1 July 2026, the exact static members, and a re-run that changes nothing |
