# Evidence for US-5.4: cleaning evidence (and E5 as a whole)

| File | What it shows |
|---|---|
| `cleaning_evidence_S1.csv` to `S6.csv` | Per source, table, issue and column: rows and a before/after sample, plus the run's count bridge per table (column `*`); `named_sample` holds ' lahore ' -> 'Lahore' |
| `count_bridge.csv` | The cumulative count bridge the evidence reconciles with (same as `../us-5.1/02_count_bridge.csv`) |
| `05_tests_catch_broken_code.txt` | Deliberate breakages of the E5 code: each caught by a test |
| `06_all_suites.txt` | `make test` (CI) and every database suite |
