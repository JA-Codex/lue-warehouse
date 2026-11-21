# Phase 2 deliverables checklist (plan Appendix B, US-9.3)

Every Phase 2 deliverable of the brief, with the files that hold it. Repository:
<https://github.com/JA-Codex/lue-warehouse>, tag `phase2-submission`. Every path below is checked by
`scripts/test_submission_contract.py` (CI): a path that does not exist fails the build.

To verify it all from a fresh clone, follow **Run it from a fresh clone** in the [README](../README.md).

| Brief deliverable | Format | Produced by | Files | Done |
|---|---|---|---|---|
| PostgreSQL database SQL scripts | SQL | US-1.1 to US-1.5 | `sql/00_setup/01_roles.sql`, `sql/00_setup/02_databases.sql`, `sql/00_setup/03_database_access.sql`, `sql/00_setup/04_source_schema.sql`, `sql/00_setup/05_warehouse_schemas.sql`, `sql/00_setup/reset.sql`; the source system S1: `sql/05_source/01_src_pms_master.sql`, `sql/05_source/02_src_pms_leases.sql`, `sql/05_source/03_src_pms_payments.sql` | [x] |
| Staging Schema SQL | SQL | US-3.x, US-5.x | `sql/20_staging/01_bronze.sql` (bronze, as landed), `sql/20_staging/02_bronze_row_id.sql`, `sql/20_staging/03_staging_functions.sql` (cleaning functions), `sql/20_staging/04_staging_tables.sql` (silver, cleaned); their audit tables `sql/10_ddl/04_ingest_audit.sql`, `sql/10_ddl/05_quality.sql`, `sql/10_ddl/06_staging_audit.sql` | [x] |
| DW Schema SQL | SQL | US-1.2, US-1.3 | `sql/10_ddl/01_dimensions.sql` (13 dimensions), `sql/10_ddl/02_facts.sql` (6 facts), `sql/10_ddl/03_audit.sql`; checked against the frozen pack by `scripts/check_contract.py` | [x] |
| ETL scripts | SQL and Python | US-3.x to US-8.x | `etl/run_pipeline.py` (the whole pipeline, one run_id); `etl/ingest/` (E3), `etl/quality/` with `etl/quality/rules.toml` (E4), `etl/staging/` (E5), `etl/dimensions/` (E6), `etl/facts/` (E7), `etl/reconcile.py` (DQ-07); the data generator `etl/generate_data.py` | [x] |
| Data Cleaning Report | PDF | US-9.1 | `docs/reports/LUE_Data_Cleaning_Report.pdf` (built by `etl/reports/build.py`) | [x] |
| Dimension Load Scripts | SQL | US-6.x | `sql/30_dimensions/01_reference_dimensions.sql` (static dimensions), `sql/30_dimensions/02_dimension_loads.sql` (the other 8, as the loader runs them); loader `etl/dimensions/`; tests `sql/90_tests/01_dimension_tests.sql` | [x] |
| Fact Load Scripts | SQL | US-7.x | `sql/40_facts/01_fact_loads.sql` (all 6 facts, as the loader runs them); loader `etl/facts/`; tests `sql/90_tests/02_fact_tests.sql` | [x] |
| Data Quality Report | PDF | US-9.2 | `docs/reports/LUE_Data_Quality_Report.pdf` (built by `etl/reports/build.py`) | [x] |
| GitHub repository link | URL | US-0.3, US-9.3 | <https://github.com/JA-Codex/lue-warehouse> (tag `phase2-submission`); `README.md` | [x] |

## Notes

- **Load scripts and loaders are one thing.** The pipeline loads through `etl/dimensions/load.py` and
  `etl/facts/load.py`, which build each statement from `etl/dimensions/spec.py` and `etl/facts/spec.py`.
  `scripts/export_load_sql.py` writes those same statements to the two SQL files, and CI fails if the files and the
  loaders ever differ. `python scripts/test_load_sql.py` runs the files on a loaded warehouse (rolled back): the
  fact script on empty facts rebuilds every fact row the loader built, and both change nothing on a rerun.
- **What the SQL files leave to Python**, as their headers say: the SCD Type 2 version planning (US-6.2), the
  refusals (a natural key or grain twice), the counts in `lue_audit.etl_run_log`, the lineage and the monthly
  reconciliation.
- **Brief names.** The warehouse uses LUE names (`lue_staging`, `lue_dw`, `lue_reporting`, `lue_audit`); the
  mapping to the brief's `project_*` names is in the README (**Names**). The brief-named alias views
  (`vw_monthly_sales`, `vw_customer_analysis`, `vw_product_performance`, D18) belong to the reporting views of
  Phase 3 (US-10.1).
- **Evidence.** The fresh-clone rehearsal of this submission: `docs/evidence/us-9.3/`.
