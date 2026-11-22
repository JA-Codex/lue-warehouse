# Evidence for US-12.1: the benchmark harness and the baseline

The recorded run is in [`../us-12.2/`](../us-12.2/) (one run produces the baseline and the after together, interleaved).
Full profile, seed 3004; 9 rounds; `python scripts/benchmark.py --runs 9 --out docs/evidence/us-12.2`.

| File | What it shows |
|---|---|
| [`../us-12.2/baseline.csv`](../us-12.2/baseline.csv) | The baseline (D20): every measurement of every query, 9 rounds: execution and planning time, plan cost, scans, partitions read, indexes used, buffers |
| [`../us-12.2/plans/B2_baseline_as_deployed.txt`](../us-12.2/plans/B2_baseline_as_deployed.txt) | A sample plan: Q1 for one month at the baseline, two sequential scans |
| [`../us-12.2/run.json`](../us-12.2/run.json) | The settings (JIT and parallel workers off), the stated tolerance, the baseline's indexes (primary keys and unique constraints only) and the table sizes |

Stability: every query's interquartile range is within the stated tolerance (60 percent of the median, or 2 ms) in
both states; the per-query ranges are in `summary.csv` and in the report.
