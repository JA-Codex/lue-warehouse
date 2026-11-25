# Evidence for US-13.2: Page 1, Executive Overview

Built in Power BI Desktop 2.159.883.0 on 25 November 2026 (`docs/powerbi/DASHBOARD_GUIDE.md`, Part 2).
Screenshot: `powerbi/screenshots/02_executive_overview.png`; page 1 of `powerbi/LUE_Dashboard.pdf`.

| Element | Content |
|---|---|
| Slicers (synced to all pages) | Fiscal year, city, building class |
| KPI cards | Cash Received (vs the year before), Collection Rate (billed), Occupancy % (active leases), Arrears (of billed to date) |
| Trends | Cash received by month against the year before; billed and collection rate by month; occupancy by month |
| Ranking | Top 10 buildings by arrears ratio (the drill-through source) |

| Check | Result |
|---|---|
| The four KPIs and the trend | Pass: with no slicer, PKR 5,347,289,709, 94.2%, 84.5%, PKR 329,363,109 (5.8%); the top bar is Gulberg Residency 2 at 21.8% |
| Slicers filter every visual | Pass: see `../us-13.5/README.md` (176/176 values agree for the fiscal year, month and city filters) |
| Page loads quickly | Pass: imported model, 13 visuals on four small marts |
