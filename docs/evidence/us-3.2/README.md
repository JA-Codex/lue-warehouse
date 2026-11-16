# Evidence for US-3.2: S1 incremental extract

| File | What it shows |
|---|---|
| `01_s1_tests.txt` | The S1 checks of `scripts/test_ingest.py`: run 1 lands everything value for value, run 2 lands 0, one changed row lands 1 (also when back-dated), a failed run lands nothing and leaves the watermark |
| `02_run_counts.txt` | Full profile: run 1 (391,870 rows), run 2 (0), one updated unit (1 row, both versions in bronze), the watermark |
