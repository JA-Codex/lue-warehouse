# Evidence for US-13.4: Page 3, Decision Page

Built in Power BI Desktop 2.159.883.0 on 25 November 2026 (`docs/powerbi/DASHBOARD_GUIDE.md`, Part 4).
Screenshot: `powerbi/screenshots/05_decision_page.png`; page 3 of `powerbi/LUE_Dashboard.pdf`.

Three recommendations, each a DAX measure (`D1 Text` to `D3 Text`) beside its evidence chart, an assumptions box and
the data window. With no slicer set, the texts on the page read word for word as the `[Window]` block of
[`../us-13.1/decisions.txt`](../us-13.1/decisions.txt) (computed from SQL and checked against the facts by
`scripts/test_powerbi.py`):

| # | Figure | Action | Owner | Expected effect |
|---|---|---|---|---|
| 1 | Gulberg Residency 2 (GLB03): arrears ratio 21.8% against 5.8%; collection rate 78.2%, 16.0 points under the portfolio | Weekly call list and payment plans for its chronically late tenants | Finance head (credit control) | Recovering half its PKR 64,267,854 arrears cuts portfolio arrears by 10% |
| 2 | Sheikh Plumbing Works (V-001): 3.1 days a request, 2.3 times its trade's 1.4; SLA breached on 86.5% of jobs (24.9% overall) | Give its urgent jobs to Hussain Plumbing Associates (V-006), review its contract | Maintenance manager | About 76 fewer days of waiting on its 37 requests |
| 3 | Karachi apartments: occupancy 78.2% against 84.5%; a vacancy lasts 133 days | A vacancy incentive marketed before the summer peak | Leasing manager | About 23 more units let, about PKR 1,775,190 of rent a month |

| Check | Result |
|---|---|
| Each recommendation cites a figure and names an action, an owner and an expected effect | Pass: as above |
| The texts follow the slicers | Pass: with FY2023-24 the page showed GLB03 at 17.0% against 5.4%, Gondal Plumbing Services (V-020) and Karachi apartments at 76.8% |
