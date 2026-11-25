# Evidence: US-13.2 — Page 1: Executive Overview

## Summary

The Executive Overview page was built in Power BI Desktop following steps 8–10 of `docs/powerbi/README.md`.  It contains four KPI cards, a monthly trend visual and an arrears bar chart, all governed by three page-level slicers (Fiscal Year, City, Building Class).  The page was verified against the SQL outputs from `python scripts/powerbi_expected.py` and confirmed to respond correctly to all three slicers.

## Key checks

| Check | Result |
|---|---|
| Four KPI cards render with correct values (full window, FY2024-25) | Pass — values match `powerbi_expected.py` output |
| Monthly trend (Billed, Collected, Collection Rate) agrees with `vw_monthly_collections` | Pass — 24 months checked |
| Arrears bar chart sorted descending by arrears | Pass — GLB03 appears first (highest arrears building, planted pattern) |
| City slicer filters all visuals | Pass — Lahore-only view changes all four KPI cards |
| Building Class slicer filters all visuals | Pass — High-rise subsets change KPI and trend correctly |
| Fiscal Year slicer filters all visuals | Pass — FY2023-24 vs FY2024-25 changes trend axis |

## Files referenced

- `docs/powerbi/measures.dax` — DAX measures used by KPI cards
- `sql/50_reporting/01_reporting.sql` — `vw_monthly_collections`, `vw_dim_date`, `vw_dim_building`
- `sql/60_analytics/mart/mart_collections_monthly.sql` — arrears bar chart source

## Re-check command

```
python scripts/powerbi_expected.py
python scripts/test_powerbi_contract.py
```
