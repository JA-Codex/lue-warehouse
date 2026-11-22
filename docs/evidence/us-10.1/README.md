# Evidence for US-10.1 and US-10.3: the reporting views, their validation and access

Full profile, seed 3004, the warehouse built by `make rebuild PROFILE=full` (the pipeline's last stage refreshed the
marts).

| File | What it shows |
|---|---|
| `01_reporting_tests.txt` | `scripts/test_reporting.py` (18 checks): every mart against the facts in every month (zero variance), unique grains, every view's totals against the facts, the aliases identical to their targets, the 9 slicer views; then `lue_reader`: reads all 19 objects of `lue_reporting`, and PostgreSQL's denials for `lue_dw`, `lue_staging`, `lue_audit`, writing, creating and refreshing (US-10.3) |
| `02_views_sample_and_reconciliation.txt` | Per view: sample rows and a reconciliation query against the facts with its result; the aliases (0 rows differ) |

The column definitions: [`../../reporting.md`](../../reporting.md).
