# Presentation outline (21 slides, about 18 minutes)

| # | Slide | Message | Figures from |
|---|---|---|---|
| 1 | Lahore Urban Estates | Title | |
| 2 | The business at a glance | 94.2% collected, PKR 329M unpaid, 84.5% occupied, 24.9% of repairs late | `docs/evidence/us-13.1/01_expected_values.txt` |
| 3 | Who needs answers | Finance, leasing, repairs, owners and their questions | `docs/phase1/02_Business_Requirements_Document.pdf` |
| 4 | Six business processes, six fact tables | Fact type and grain of each | `sql/10_ddl/02_facts.sql` |
| 5 | One star: the rent invoice line | The fact and its six dimensions | `docs/phase1/diagrams/` |
| 6 | From six sources to one warehouse | The layered architecture | `docs/reports/figures/f0_architecture.png` |
| 7 | Data quality, measured | 109 rules; 6,915 of 6,915 planted errors; 0 orphan facts; 194 of 194 monthly totals | `docs/reports/LUE_Data_Quality_Report.pdf` |
| 8 | Making the data trustworthy | Cleaning, surrogate keys, SCD2 history (T-0040) | `docs/evidence/us-6.2/01_tenant_history.txt` |
| 9 | 14 business questions (1 of 2) | Q1 to Q7 and their answers | `docs/analytics.md` |
| 10 | 14 business questions (2 of 2) | Q8 to Q14 and their answers | `docs/analytics.md` |
| 11 | Revenue grew every year | Monthly revenue with growth; the brief's views | W2, W3 in `docs/evidence/us-11.1/01_analytics_output.txt` |
| 12 | ROLLUP: from building to grand total | Building, city, region, total | O1 in the same file |
| 13 | CUBE: city by payment channel | Channel shares | O2 in the same file |
| 14 | One building holds a fifth of all arrears | GLB03 21.8%; 86% of overdue debt over 90 days | Q2, Q3 |
| 15 | Karachi tenants leave at renewal | 17.9% renew; incentives cut vacancy 134 to 58 days | Q8, Q13 |
| 16 | Slow vendors and rain drive repair delays | V-001 86.5% SLA breach; 6.3 times more leaks after rain | Q9, Q14 |
| 17 | Making it fast: EXPLAIN ANALYZE | 17.5 ms to 0.97 ms; partition pruning | `docs/reports/LUE_Indexing_Report.pdf` |
| 18 | The dashboard: overview and detail | Pages 1 and 2 | `powerbi/screenshots/` |
| 19 | The dashboard: the Decision Page | Page 3; 176 of 176 values match SQL | `docs/evidence/us-13.5/` |
| 20 | What management should do | PKR 32M recoverable, 76 days saved, PKR 21M a year | `docs/evidence/us-13.1/decisions.txt` |
| 21 | Thank you | Repository link; the data is synthetic | |
