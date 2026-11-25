# Appendix B checklist, ticked against the repository

## Phase 2 (40 marks)

| Brief deliverable | Format | File | Done |
|---|---|---|---|
| PostgreSQL database SQL scripts | SQL | `sql/00_setup/`, `sql/10_ddl/` | [x] |
| Staging Schema SQL | SQL | `sql/10_ddl/`, `sql/20_staging/` (schema `lue_staging`, tables `brz_*` and `stg_*`) | [x] |
| DW Schema SQL | SQL | `sql/10_ddl/` (schema `lue_dw`) | [x] |
| ETL scripts | SQL and Python | `etl/`, `etl/run_pipeline.py` | [x] |
| Data Cleaning Report | PDF | `docs/reports/LUE_Data_Cleaning_Report.pdf` | [x] |
| Dimension Load Scripts | SQL | `sql/30_dimensions/`, `etl/dimensions/` | [x] |
| Fact Load Scripts | SQL | `sql/40_facts/`, `etl/facts/` | [x] |
| Data Quality Report | PDF | `docs/reports/LUE_Data_Quality_Report.pdf` | [x] |
| GitHub repository link | URL | https://github.com/JA-Codex/lue-warehouse | [x] |

## Phase 3 (30 marks)

| Brief deliverable | Format | File | Done |
|---|---|---|---|
| Analytical SQL queries | SQL | `sql/60_analytics/analytical.sql` (Q1 to Q14 with SUM, AVG, COUNT; monthly revenue with growth; W1 to W4) | [x] |
| OLAP queries (ROLLUP, CUBE) | SQL | `sql/60_analytics/olap.sql` (O1 ROLLUP region, city, building; O2 CUBE city by payment channel; O3 checks) | [x] |
| Reporting views (including brief-named aliases) | SQL | `sql/50_reporting/01_reporting.sql` (`vw_monthly_sales`, `vw_customer_analysis`, `vw_product_performance`) | [x] |
| Indexing Report | PDF | `docs/reports/LUE_Indexing_Report.pdf` | [x] |
| Power BI dashboard | PBIX | `powerbi/LUE_Dashboard.pbix` (Executive Overview, Detailed Analysis, Decision Page) | [x] |
| Dashboard screenshots | PDF | Submission zip: `06_Dashboard_Screenshots/LUE_Dashboard_Screenshots.pdf` (every page with a caption, the drill-through, the model and the validation); the Power BI export `powerbi/LUE_Dashboard.pdf` | [x] |
| Business Insights Report | PDF | Submission zip: `07_Business_Insights_Report/` (built by `etl/reports/insights.py`) | [x] |
| Final presentation | PPT | Submission zip: `08_Final_Presentation/LUE_Final_Presentation.pptx` | [x] |

The PBIX opens in Power BI Desktop 2.159.883.0 and refreshes from `lue_warehouse` (US-13.5).
The Phase 3 zip holds the eight brief deliverables in folders 01 to 08; `python scripts/package_submission.py` checks the repository side.
