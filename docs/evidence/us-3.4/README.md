# Evidence for US-3.4: JSON, weather and reconciliation (and E3 as a whole)

| File | What it shows |
|---|---|
| `01_json_weather_tests.txt` | Ticket and status rows equal the file, duplicated tickets keep their own histories, defects arrive untouched, weather with its NULLs, the full run of all six sources (20/20 reconciliation, lineage, metadata) |
| `02_full_ingest.txt` | `python etl/ingest/run.py` on the full profile, then a second run that lands nothing |
| `03_reconciliation.txt` | `lue_audit.reconciliation` for all 20 bronze tables (difference 0) and `lue_audit.lineage` |
| `04_tests_catch_broken_code.txt` | 11 deliberate breakages of the E3 code: all caught after one test fix |
| `05_all_suites.txt` | `make test` (CI) and every database suite, all passing |
