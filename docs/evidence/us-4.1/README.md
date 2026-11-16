# Evidence for US-4.1: rule catalogue and engine

| File | What it shows |
|---|---|
| `../../../etl/quality/rules.toml` | The catalogue itself (109 rules) |
| `01_engine_tests.txt` | Idempotent runs, one rejection per row, the run log, a quarantine row, a rule added with no code change, a failed validation rolled back, malformed rules refused |
| `02_two_runs.txt` | Two validations in a row: identical summaries |
