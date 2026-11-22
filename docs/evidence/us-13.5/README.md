# Evidence for US-13.5: every KPI against its SQL value

Fill in the **Power BI** columns from the dashboard (cards and the `validation.dax` result) and tick **Match**.
The **SQL** values are the full profile's, from `python scripts/powerbi_expected.py` (lue_reader, the marts), which
`scripts/test_powerbi.py` checks against queries on the facts; all 44 measures are in
[`../us-13.1/expected_measures.csv`](../us-13.1/expected_measures.csv). Power BI shows the same value in the format
of step 5 of the build guide.

| | |
|---|---|
| Power BI Desktop version | (Help, About) |
| Checked by, on | |
| Opened on (two other machines) | (name, machine) and (name, machine) |

## Window (no slicer set)

| Measure | SQL | Power BI | Match |
|---|---|---|---|
| Billed | PKR 5,676,652,818 | | |
| Collected (Cohort) | PKR 5,347,289,709 | | |
| Collection Rate | 94.2% | | |
| Cash Received | PKR 5,347,289,709 | | |
| Cash Received PY | (blank) | | |
| Cash Received YoY % | (blank) | | |
| Arrears | PKR 329,363,109 | | |
| Arrears Ratio | 5.8% | | |
| Occupancy % | 84.5% | | |
| Avg Vacancy Days | 126.9 | | |
| Active Leases | 1,499 | | |
| Avg Days to Resolve | 1.8 | | |
| SLA Breach % | 24.9% | | |
| Maintenance Cost per Unit-Month | PKR 509 | | |
| NOI | PKR 4,092,111,103 | | |
| Tenants | 3,455 | | |
| Chronically Late Tenants | 846 | | |

## FY2024-25 (fiscal year slicer FY2024-25)

| Measure | SQL | Power BI | Match |
|---|---|---|---|
| Billed | PKR 1,889,759,182 | | |
| Collected (Cohort) | PKR 1,775,026,939 | | |
| Collection Rate | 93.9% | | |
| Cash Received | PKR 1,774,998,239 | | |
| Cash Received PY | PKR 1,640,862,798 | | |
| Cash Received YoY % | 8.2% | | |
| Arrears | PKR 207,519,053 | | |
| Arrears Ratio | 5.7% | | |
| Occupancy % | 85.1% | | |
| Avg Vacancy Days | 125.4 | | |
| Active Leases | 1,499 | | |
| Avg Days to Resolve | 1.8 | | |
| SLA Breach % | 25.8% | | |
| Maintenance Cost per Unit-Month | PKR 508 | | |
| NOI | PKR 1,358,087,971 | | |
| Tenants | 3,455 | | |
| Chronically Late Tenants | 846 | | |

## Month 2025-03 (the validation query's Month 2025-03 column)

| Measure | SQL | Power BI | Match |
|---|---|---|---|
| Billed | PKR 157,557,764 | | |
| Collected (Cohort) | PKR 148,326,762 | | |
| Collection Rate | 94.1% | | |
| Cash Received | PKR 149,027,837 | | |
| Cash Received PY | PKR 137,222,923 | | |
| Cash Received YoY % | 8.6% | | |
| Arrears | PKR 181,181,521 | | |
| Arrears Ratio | 5.8% | | |
| Occupancy % | 84.1% | | |
| Avg Vacancy Days | 156.1 | | |
| Active Leases | 1,513 | | |
| Avg Days to Resolve | 1.9 | | |
| SLA Breach % | 27.6% | | |
| Maintenance Cost per Unit-Month | PKR 524 | | |
| NOI | PKR 115,071,598 | | |
| Tenants | 3,455 | | |
| Chronically Late Tenants | 846 | | |

## Lahore (city slicer Lahore)

| Measure | SQL | Power BI | Match |
|---|---|---|---|
| Billed | PKR 2,341,131,218 | | |
| Collected (Cohort) | PKR 2,187,307,068 | | |
| Collection Rate | 93.4% | | |
| Cash Received | PKR 2,187,307,068 | | |
| Cash Received PY | (blank) | | |
| Cash Received YoY % | (blank) | | |
| Arrears | PKR 153,824,150 | | |
| Arrears Ratio | 6.6% | | |
| Occupancy % | 85.8% | | |
| Avg Vacancy Days | 122.9 | | |
| Active Leases | 647 | | |
| Avg Days to Resolve | 1.7 | | |
| SLA Breach % | 24.9% | | |
| Maintenance Cost per Unit-Month | PKR 485 | | |
| NOI | PKR 4,092,111,103 | | |
| Tenants | 1,499 | | |
| Chronically Late Tenants | 381 | | |

## The decision texts

With no slicer set, page 3's three texts must read word for word as the `[Window]` block of
[`../us-13.1/decisions.txt`](../us-13.1/decisions.txt); with FY2024-25 selected, as its `[FY2024-25]` block.

| Text | Matches |
|---|---|
| D1 (arrears) | |
| D2 (vendor) | |
| D3 (occupancy) | |

## Screenshots

In `powerbi/screenshots/`: `01_model.png`, `02_executive_overview.png`, `03_detailed_analysis.png`,
`04_drill_through.png`, `05_decision_page.png`, `06_validation.png` (the `validation.dax` result beside the CSV).
