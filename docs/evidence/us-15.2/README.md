# Evidence for US-15.2: documentation consistency audit

| File | What it shows |
|---|---|
| [`01_consistency_output.txt`](01_consistency_output.txt) | `python scripts/check_docs_consistency.py`: 4 of 4 checks pass (every story is in the story log, 68 of 68; every DDL table is named in a story, 31 of 31; every Makefile target is described, 46 of 46; every evidence folder a story links to exists, 169 of 169) |
| [`02_placeholder_scan.txt`](02_placeholder_scan.txt) | The text of the five PDFs and of the presentation searched for placeholder text (TODO, TBD, lorem ipsum, "[insert", xxx) and for the template's sample text: 0 hits in each |

The definition of the collection rate (D17, cohort basis) reads the same in the README, the header of
`sql/50_reporting/01_reporting.sql`, the Decision Page assumptions box and the insights report: paid against the
invoice lines due in the period. The brief's view names (`vw_monthly_sales`, `vw_customer_analysis`,
`vw_product_performance`) are in the README mapping table and in `sql/50_reporting/01_reporting.sql`.

Re-check: `python scripts/check_docs_consistency.py`.
