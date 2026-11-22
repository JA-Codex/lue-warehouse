-- sql/70_performance/02_indexes.sql: the candidate indexes of the experiments (E12, US-12.2)
-- Runs in: lue_warehouse, as lue_etl. Safe to re-run (IF NOT EXISTS). Not part of the deploy: the warehouse is
-- built with primary-key and unique-constraint indexes only (D20), the baseline the experiments start from.
-- scripts/benchmark.py creates these after the baseline run, measures each one's size, build time and load
-- cost, and drops them again (sql/70_performance/03_drop_indexes.sql) unless told to keep them.
-- Each index is named by the line above it with its purpose and the benchmark query it is for.

-- Purpose: find the invoice lines due in a date range (Q1 by month, B2) without reading every line. Q1 over
--          the whole window (B1) is the control: it reads every line, so the index should not be used.
CREATE INDEX IF NOT EXISTS ix_invoice_line_due_unit ON lue_dw.fact_rent_invoice_line (due_date_key, unit_key);

-- Purpose: the same for the payments against those lines (Q1 by month, B2; control B1).
CREATE INDEX IF NOT EXISTS ix_payment_due_unit ON lue_dw.fact_payment (due_date_key, unit_key);

-- Purpose: one unit's days in a date range (B5), and the per-unit order of the vacancy islands (Q7). The pack's
--          own proposal (docs/phase1/sql/physical_model.sql); on the parent it is created on every partition.
CREATE INDEX IF NOT EXISTS ix_occupancy_unit_date ON lue_dw.fact_unit_occupancy_daily (unit_key, snapshot_date_key);

-- Purpose: the current tenant versions by segment (B6), a partial index on the current SCD2 rows only.
CREATE INDEX IF NOT EXISTS ix_dim_tenant_current_segment ON lue_dw.dim_tenant (tenant_type, employer_sector)
    WHERE is_current;
