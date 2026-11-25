# Evidence for US-15.1: clean-machine rebuild

On 25 November 2026, after the laptop used for the dashboard crashed, the repository was cloned again into a new
folder (`D:\lue-warehouse`, Windows, Python 3.14, PostgreSQL 18) and rebuilt by following the README from the
clone, with no files copied from the old folder:

| Step | Command | Result |
|---|---|---|
| Set up | `python -m venv .venv`, `pip install -r requirements.txt -r requirements-ci.txt`, `.env` from `.env.example` | Done |
| Databases | `python scripts/db_reset.py` | Done |
| Full rebuild | `python etl/run_pipeline.py --profile full` | Every step succeeded |
| Checks | `python scripts/run_ci.py` | 23 of 23 passed |
| Dashboard checks | `python scripts/test_powerbi.py` | 13 of 13 passed |

## Comparison with the accepted run

The figures of the rebuilt warehouse were compared with the recorded ones in
[`../us-13.1/01_expected_values.txt`](../us-13.1/01_expected_values.txt): the Power BI file, refreshed from the rebuilt
warehouse, showed all 44 measures in all four selections equal to the recorded values (176 of 176,
[`../us-13.5/01_kpi_reconciliation.md`](../us-13.5/01_kpi_reconciliation.md)). The key totals are unchanged:

| Figure | Recorded | Rebuilt |
|---|---|---|
| Billed | PKR 5,676,652,818 | PKR 5,676,652,818 |
| Cash received | PKR 5,347,289,709 | PKR 5,347,289,709 |
| Collection rate | 94.2% | 94.2% |
| Arrears | PKR 329,363,109 | PKR 329,363,109 |
| Occupancy | 84.5% | 84.5% |
| Requests | 5,670 | 5,670 |

The rebuild is deterministic (seed 3004), so identical figures are expected. No README step was missing.
