# Evidence for US-8.4: full-volume run and baseline timings

Full profile, seed 3004, from an empty warehouse with one command (`make rebuild PROFILE=full`).

| File | What it shows |
|---|---|
| `01_full_volume_run.txt` | The run (51 steps, exit 0, 280 s including the reset and the generation), its timing per step (slowest first) and per stage from `lue_audit.etl_run_log`, the fact row counts (2,264,523 in all) and the reconciliation and fact tests of the same run (194 of 194, 71 of 71) |
| `02_pipeline_tests.txt` | `scripts/test_pipeline_contract.py` (22 checks, no database) |
