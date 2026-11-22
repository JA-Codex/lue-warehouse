# Evidence for US-12.3: the Indexing Report

| File | What it shows |
|---|---|
| [`../../reports/LUE_Indexing_Report.pdf`](../../reports/LUE_Indexing_Report.pdf) | The report, 7 pages: the comparison table (query, change, time and cost before and after, plan type), the run ranges, the D20 baseline as measured, the method, each experiment with its plans before and after and why it worked or did not, what each index costs, recommendations |

Built by `python etl/reports/indexing.py` from the recorded run in [`../us-12.2/`](../us-12.2/); every number is
read from it. The report states the experiments where indexing did not help (B1, B3, B6) and partitioning did not
speed the query (B4), and why. `scripts/test_benchmark_contract.py` (CI) builds it again from the recorded run.
