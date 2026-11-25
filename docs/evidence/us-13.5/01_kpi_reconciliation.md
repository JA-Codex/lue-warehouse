# Every measure in Power BI against SQL (US-13.5)

`validation.dax` run in Power BI Desktop 2.159.883.0 (DAX query view) on the team's PBIX, 25 November 2026; its result is
[`02_powerbi_validation.tsv`](02_powerbi_validation.tsv). The SQL side is
[`../us-13.1/expected_measures.csv`](../us-13.1/expected_measures.csv) (`python scripts/powerbi_expected.py`, full profile),
which `scripts/test_powerbi.py` checks against queries on the facts.

**Result: 176 of 176 values agree** (44 measures x 4 selections); the largest difference is 0.0000005, the last decimal
of a double. Blank in both where the measure is blank by design (the year before outside the data; the trade measures
need one vendor). Screenshot: `powerbi/screenshots/06_validation.png`.

| Measure | Window | Month 2025-03 | FY2024-25 | Lahore | Match |
|---|---|---|---|---|---|
| Invoice Lines | 129,885 | 3,569 | 43,416 | 55,810 | Yes |
| Billed | PKR 5,676,652,818 | PKR 157,557,764 | PKR 1,889,759,182 | PKR 2,341,131,218 | Yes |
| Collected (Cohort) | PKR 5,347,289,709 | PKR 148,326,762 | PKR 1,775,026,939 | PKR 2,187,307,068 | Yes |
| Collection Rate | 94.2% | 94.1% | 93.9% | 93.4% | Yes |
| Cash Received | PKR 5,347,289,709 | PKR 149,027,837 | PKR 1,774,998,239 | PKR 2,187,307,068 | Yes |
| Cash Received PY | (blank) | PKR 137,222,923 | PKR 1,640,862,798 | (blank) | Yes |
| Cash Received YoY % | (blank) | 8.6% | 8.2% | (blank) | Yes |
| Arrears | PKR 329,363,109 | PKR 181,181,521 | PKR 207,519,053 | PKR 153,824,150 | Yes |
| Billed to Date | PKR 5,676,652,818 | PKR 3,143,400,476 | PKR 3,623,380,090 | PKR 2,341,131,218 | Yes |
| Arrears Ratio | 5.8% | 5.8% | 5.7% | 6.6% | Yes |
| Unit Days | 1,972,800 | 55,800 | 657,000 | 824,192 | Yes |
| Occupied Days | 1,667,578 | 46,903 | 558,818 | 706,960 | Yes |
| Occupancy % | 84.5% | 84.1% | 85.1% | 85.8% | Yes |
| Avg Vacancy Days | 126.9 | 156.1 | 125.4 | 122.9 | Yes |
| Active Leases | 1,499 | 1,513 | 1,499 | 647 | Yes |
| Units | 1,800 | 1,800 | 1,800 | 752 | Yes |
| Occupied Units | 1,499 | 1,513 | 1,499 | 647 | Yes |
| Rent Roll | PKR 140,589,000 | PKR 127,207,500 | PKR 128,291,000 | PKR 58,959,500 | Yes |
| Avg Contract Rent | PKR 93,789 | PKR 84,076 | PKR 85,584 | PKR 91,128 | Yes |
| Requests | 5,670 | 152 | 1,889 | 2,232 | Yes |
| Resolved Requests | 5,659 | 152 | 1,889 | 2,226 | Yes |
| Avg Days to Resolve | 1.8 | 1.9 | 1.8 | 1.7 | Yes |
| SLA Breaches | 1,411 | 42 | 488 | 555 | Yes |
| SLA Breach % | 24.9% | 27.6% | 25.8% | 24.9% | Yes |
| Maintenance Cost | PKR 32,984,300 | PKR 943,750 | PKR 10,965,500 | PKR 13,142,500 | Yes |
| Maintenance Cost per Unit-Month | PKR 509 | PKR 524 | PKR 508 | PKR 485 | Yes |
| Rent Collected | PKR 4,483,799,351 | PKR 126,103,639 | PKR 1,488,101,599 | PKR 4,483,799,351 | Yes |
| Management Fee | PKR 358,703,948 | PKR 10,088,291 | PKR 119,048,128 | PKR 358,703,948 | Yes |
| NOI | PKR 4,092,111,103 | PKR 115,071,598 | PKR 1,358,087,971 | PKR 4,092,111,103 | Yes |
| Tenants | 3,455 | 3,455 | 3,455 | 1,499 | Yes |
| Chronically Late Tenants | 846 | 846 | 846 | 381 | Yes |
| Tenant Billed | PKR 5,676,652,818 | PKR 5,676,652,818 | PKR 5,676,652,818 | PKR 2,341,131,218 | Yes |
| Tenant Collected | PKR 5,347,289,709 | PKR 5,347,289,709 | PKR 5,347,289,709 | PKR 2,187,307,068 | Yes |
| Tenant Arrears | PKR 329,363,109 | PKR 329,363,109 | PKR 329,363,109 | PKR 153,824,150 | Yes |
| Tenant Arrears Ratio | 5.8% | 5.8% | 5.8% | 6.6% | Yes |
| Late Payment Share | 30.4% | 30.4% | 30.4% | 31.3% | Yes |
| Collection Rate (Portfolio) | 94.2% | 94.1% | 93.9% | 94.2% | Yes |
| Arrears (Portfolio) | PKR 329,363,109 | PKR 181,181,521 | PKR 207,519,053 | PKR 329,363,109 | Yes |
| Arrears Ratio (Portfolio) | 5.8% | 5.8% | 5.7% | 5.8% | Yes |
| Occupancy % (Portfolio) | 84.5% | 84.1% | 85.1% | 84.5% | Yes |
| Avg Days to Resolve (Portfolio) | 1.8 | 1.9 | 1.8 | 1.8 | Yes |
| SLA Breach % (Portfolio) | 24.9% | 27.6% | 25.8% | 24.9% | Yes |
| Trade Avg Days to Resolve | (blank) | (blank) | (blank) | (blank) | Yes |
| Days vs Trade | (blank) | (blank) | (blank) | (blank) | Yes |
