# Evidence for US-10.2: the four gold marts

| File | What it shows |
|---|---|
| `01_refresh_log.txt` | The refresh log entry of the pipeline run (`refresh_marts`, after `fact_tests` and `reconcile_dq07`), each mart with its unique grain index and rows, and the marts' lineage |
| [`../../../sql/50_reporting/01_reporting.sql`](../../../sql/50_reporting/01_reporting.sql) | The mart definitions |
| [`../us-10.1/01_reporting_tests.txt`](../us-10.1/01_reporting_tests.txt) | Every mart equal to the facts in every month |
