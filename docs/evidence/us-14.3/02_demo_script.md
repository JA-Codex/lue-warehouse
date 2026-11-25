# Demo script (about 4 minutes, small profile)

1. **Rebuild live** (PowerShell, in the repository folder, the virtual environment active):

       python scripts/db_reset.py
       python etl/run_pipeline.py --profile small

   Point at the step list as it runs: ingest, validate, stage, dimensions, facts, marts, checks.

2. **A quarantined row and why** (pgAdmin or `psql -d lue_warehouse`):

       SELECT check_name, source_table, rejection_reason, record FROM lue_audit.quarantine LIMIT 5;

3. **An SCD2 history** (full-profile result shown from `docs/evidence/us-6.2/01_tenant_history.txt`: T-0040,
   Healthcare until 2025-05-03, then Construction).

4. **EXPLAIN ANALYZE before and after**: open `docs/evidence/us-12.2/plans/`, B5 before (17.5 ms, a scan of every
   partition) and after (0.97 ms, `ix_occupancy_unit_date`).

5. **The dashboard**: open `powerbi/LUE_Dashboard.pbix`; on the Executive Overview pick FY2024-25 (cash received
   PKR 1,774,998,239, up 8.2%); right-click Gulberg Residency 2, Drill through, Detailed Analysis; then the Decision
   Page, where the three texts change with the slicers.
