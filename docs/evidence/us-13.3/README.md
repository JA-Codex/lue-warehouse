# Evidence for US-13.3: Page 2, Detailed Analysis

Built in Power BI Desktop 2.159.883.0 on 25 November 2026 (`docs/powerbi/DASHBOARD_GUIDE.md`, Part 3).
Screenshots: `powerbi/screenshots/03_detailed_analysis.png`, `04_drill_through.png`; page 2 of `powerbi/LUE_Dashboard.pdf`.

| Section | Visuals |
|---|---|
| Buildings and unit types (product-style) | Matrix: city then building, with occupancy, collection rate, arrears ratio, vacancy days, maintenance per unit-month (colour-scaled); occupancy by unit type |
| Cities (regional) | Collection rate and occupancy by city |
| Tenant segmentation | Tenants by payer segment (donut); tenants by arrears (table, from `vw_tenant_by_building`) |
| Vendors | Vendors slowest against their trade (20 or more resolved requests) |

| Check | Result |
|---|---|
| The three required sections | Pass: as above |
| Drill-through works | Pass: the page is the drill-through target on `building_name`; right-click a building on page 1, Drill through, Detailed Analysis opens it filtered (`04_drill_through.png`) |
| Values | The measures on this page are among the 44 validated in `../us-13.5/01_kpi_reconciliation.md` (tenants 3,455, chronically late 846, late payment share 30.4%) |
