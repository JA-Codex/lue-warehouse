# Evidence: US-13.5 — Validate, finish and export the dashboard

## Summary

The finished `LUE_Dashboard.pbix` was validated against the SQL outputs, tested with three slicer scenarios, confirmed to open on a second machine, and exported to PDF.  All 24 measures agree with their SQL equivalents; all slicer tests pass.

## Key checks

| Check | Result |
|---|---|
| KPI reconciliation: 24 measures vs SQL | 24 / 24 agree (< 0.01 pp difference) |
| Slicer test 1: full portfolio, FY2024-25 | Pass |
| Slicer test 2: Lahore only, FY2023-24 | Pass |
| Slicer test 3: High-rise buildings, full window | Pass |
| Drill-through: Executive Overview → Detailed Analysis | Pass |
| PBIX opens on second machine (fresh install + lue_reader credentials) | Pass — all 15 tables loaded, no refresh errors |
| PDF export saved | `LUE_Dashboard_Export.pdf` in this folder |

## Files referenced

- `docs/powerbi/LUE_Dashboard.pbix` — the finished file
- `docs/powerbi/README.md` — build and open instructions
- `docs/evidence/us-13.5/01_kpi_reconciliation.md` — full reconciliation table
- `docs/evidence/us-13.5/02_slicer_tests.md` — per-scenario slicer results

## Re-check command

```
python scripts/powerbi_expected.py
python scripts/test_powerbi_contract.py
# Then open docs/powerbi/LUE_Dashboard.pbix in Power BI Desktop
```
