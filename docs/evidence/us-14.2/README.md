# Evidence: US-14.2 — Business Insights Report

## Summary

`insights_report()` was added to `etl/reports/build.py` and the `main()` loop updated.  The function generates `docs/reports/LUE_Business_Insights_Report.pdf` with five sections (one per insight) and a summary table.  The report runs offline (no database connection) with `--insights --data data`, using the same `build()` / `p()` / `table()` helpers as the other two reports.

## Key checks

| Check | Result |
|---|---|
| `python etl/reports/build.py --insights --data data` exits 0 | Pass |
| PDF written to `docs/reports/LUE_Business_Insights_Report.pdf` | Pass |
| `make insights-report` exits 0 | Pass |
| `python -m ruff check etl/reports/build.py` — 0 errors | Pass |
| PDF has five insight sections with correct Q-number references | Pass (I1→Q2/Q3, I2→Q9, I3→Q6/Q8, I4→Q13, I5→Q11/Q14) |

## Re-check command

```
python etl/reports/build.py --insights --data data
make insights-report
python -m ruff check etl/reports/build.py
```
