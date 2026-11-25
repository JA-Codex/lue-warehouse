# Evidence: US-13.4 — Page 3: Decision Page

## Summary

The Decision page was built in Power BI Desktop.  It contains three recommendation cards with DAX dynamic text, one supporting mini-visual per recommendation, and an assumptions box.  The key numbers in R1, R2 and R3 were verified against the SQL analytical queries (Q2/Q3 for arrears, Q9 for vendor, Q13 for incentive effect).

## Key checks

| Check | Result |
|---|---|
| R1 building name matches top-arrears building in `mart_collections_monthly` (FY2024-25) | Pass — GLB03 shown; arrears PKR agrees |
| R2 vendor name matches Q9 worst-breach vendor | Pass — vendor ID and breach % agree |
| R3 vacancy reduction matches Q13 `avg_days_to_let` difference | Pass — difference is 8 days (with offer vs without) |
| Assumptions box visible without scrolling on 1280×720 | Pass — box fits at the bottom of the page |
| Dynamic text updates when fiscal year slicer changes | Pass — FY2023-24 shows different building in R1 |

## Files referenced

- `docs/powerbi/measures.dax` — dynamic-text measures `Top Arrears Building`, `Top Breach Vendor`, `Incentive Effect %`
- `sql/60_analytics/analytical.sql` — Q9, Q13 for validation
- `docs/powerbi/README.md` — build guide step 11 (Decision page)

## Re-check command

```
python scripts/powerbi_expected.py
python scripts/test_powerbi_contract.py
```
