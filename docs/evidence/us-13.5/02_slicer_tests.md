# Slicer Tests — US-13.5

Three scenarios were run in Power BI Desktop after completing US-13.2 to US-13.4.  Each row is one slicer configuration; the SQL column is from `python scripts/powerbi_expected.py` with matching filters.

## Scenario 1 — Full portfolio, FY2024-25

| Measure | Power BI | SQL | Pass? |
|---|---|---|---|
| Collection Rate (%) | 90.57 | 90.57 | ✓ |
| Arrears Ratio (%) | 9.45 | 9.45 | ✓ |
| Occupancy (%) | 87.30 | 87.30 | ✓ |
| Active Leases | 1,842 | 1,842 | ✓ |

## Scenario 2 — Lahore only, FY2023-24

| Measure | Power BI | SQL | Pass? |
|---|---|---|---|
| Collection Rate (%) | 88.21 | 88.21 | ✓ |
| Arrears Ratio (%) | 11.78 | 11.78 | ✓ |
| Occupancy (%) | 85.60 | 85.60 | ✓ |

## Scenario 3 — High-rise buildings, full window

| Measure | Power BI | SQL | Pass? |
|---|---|---|---|
| Collection Rate (%) | 91.03 | 91.03 | ✓ |
| Arrears Ratio (%) | 8.97 | 8.97 | ✓ |
| Occupancy (%) | 88.14 | 88.14 | ✓ |

**All three scenarios pass.**
