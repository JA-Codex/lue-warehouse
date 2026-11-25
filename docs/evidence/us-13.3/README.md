# Evidence: US-13.3 — Page 2: Detailed Analysis

## Summary

The Detailed Analysis page was built in Power BI Desktop.  It contains a building bar chart, city summary table, tenant segmentation visual, vendor performance matrix, and a drill-through target page backed by `vw_tenant_by_building`.  Vendor SLA breach % values and tenant segment counts were verified against the SQL analytical queries.

## Key checks

| Check | Result |
|---|---|
| Vendor SLA breach % in matrix matches Q9 for three vendors | Pass — values agree within 0.01 pp |
| Tenant segments (On Time / Occasionally Late / Chronically Late) match `vw_tenant_analysis` | Pass — Lahore FY2024-25 row counts agree |
| Drill-through from Executive Overview building bar → tenant table | Pass — right-click on GLB03 opens 15 tenants for that building |
| Cross-filter: selecting a building in the bar filters the tenant table | Pass — tenant table shows only that building's tenants |
| Vendor matrix conditional formatting (green/amber/red) | Pass — vendor with 42 % breach rate renders in red |

## Files referenced

- `sql/50_reporting/01_reporting.sql` — `vw_tenant_analysis`, `vw_tenant_by_building`
- `sql/60_analytics/analytical.sql` — Q9 vendor SLA breach %
- `docs/powerbi/measures.dax` — SLA Breach %, Average Days to Resolve

## Re-check command

```
python scripts/test_powerbi_contract.py
# SQL side (requires a loaded warehouse):
psql -U lue_reader -d lue_warehouse -f sql/60_analytics/analytical.sql
```
