# Evidence for US-3.1: the ingestion framework

| File | What it shows |
|---|---|
| `01_framework_tests.txt` | The framework checks of `scripts/test_ingest.py`: 20 bronze tables with the metadata columns; a forced failure leaves 0 of its 5 rows, is logged `Failed`, and the next source still runs; a wrong password gives a clear message |
| `02_run_log.txt` | `lue_audit.etl_run_log` rows for the forced failure and for a successful run of all six sources |
| `03_structured_log.txt` | The `key=value` lines in `logs/ingest.log` |
