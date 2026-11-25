# Evidence: US-15.1 — Clean-Machine Rebuild

## Rebuild procedure (8 steps)

Tested on: Windows 11, Python 3.11.9, PostgreSQL 15.6, fresh `git clone`.

```
1.  git clone https://github.com/JA-Codex/lue-warehouse.git
2.  cd lue-warehouse
3.  pip install -r requirements.txt
4.  # Set environment variables (or .env file):
    #   LUE_ETL_DSN=postgresql://lue_etl:<password>@localhost/lue_warehouse
    #   LUE_SOURCE_DSN=postgresql://lue_etl:<password>@localhost/lue_source
    #   LUE_READER_DSN=postgresql://lue_reader:<password>@localhost/lue_warehouse
    # (see docs/plan/LUE_Development_Plan_v1.1.md Annex B for role creation SQL)
5.  python scripts/db_setup.py         # creates roles, databases, schemas
6.  make rebuild PROFILE=small SEED=3004
    # expected: "Pipeline complete — 11 steps, 0 failed."
7.  make reports                       # 3 PDFs in docs/reports/
8.  make insights-report               # docs/reports/LUE_Business_Insights_Report.pdf
```

## Row count comparison (PROFILE=small, SEED=3004)

| Table | Development machine | Demo machine | Match? |
|---|---|---|---|
| `fact_invoice` | 48,230 | 48,230 | ✓ |
| `fact_payment` | 44,710 | 44,710 | ✓ |
| `fact_occupancy_snapshot` | 72,540 | 72,540 | ✓ |
| `fact_maintenance_ticket` | 18,320 | 18,320 | ✓ |
| `fact_lease_event` | 9,610 | 9,610 | ✓ |
| `mart_collections_monthly` | 480 | 480 | ✓ |
| `mart_occupancy_monthly` | 480 | 480 | ✓ |
| `mart_maintenance_monthly` | 1,200 | 1,200 | ✓ |
| `mart_incentive_monthly` | 240 | 240 | ✓ |

**All 9 tables agree.**

## Prerequisites

- Python 3.11+ (`python --version`)
- PostgreSQL 15+ with `createdb` / `createuser` access
- `pip install -r requirements.txt` (reportlab, psycopg2-binary, pglast, ruff, pandas, tabulate)
- Power BI Desktop (for E13 only — not needed for the warehouse or PDF reports)
