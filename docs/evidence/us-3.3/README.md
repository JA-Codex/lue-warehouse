# Evidence for US-3.3: S2, S3 and S6 files

| File | What it shows |
|---|---|
| `01_file_tests.txt` | The file checks of `scripts/test_ingest.py`: register rows with checksums, exact values, empty cells, rerun 0, edited file as a new batch, renamed column rejected, lost row caught by reconciliation |
| `02_file_load_register.txt` | `lue_audit.file_load` for a first run (files `Loaded`) and a second run (all `Skipped`, unchanged), with sample rows |
| `03_drift_rejection.txt` | The rejection message for a renamed column, a changed sheet header and a cut-off JSON file |
