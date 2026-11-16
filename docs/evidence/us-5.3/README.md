# Evidence for US-5.3: incremental loading with watermarks

| File | What it shows |
|---|---|
| `01_incremental_runs.txt` | A rerun with no source change (0 inserted, 0 updated, run log too), then one changed tenant in `src_pms`: exactly one update |
| `02_staging_tests.txt` | The US-5.3 block of `scripts/test_staging.py`: failed step keeps its watermark, same-second batch, older version |
