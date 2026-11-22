-- sql/70_performance/03_drop_indexes.sql: back to the D20 baseline (E12, US-12.2)
-- Runs in: lue_warehouse, as lue_etl. Drops the candidate indexes of 02_indexes.sql and the benchmark's
-- unpartitioned copy of the occupancy fact; safe to re-run. Primary-key and unique-constraint indexes stay.

DROP INDEX IF EXISTS lue_dw.ix_invoice_line_due_unit;
DROP INDEX IF EXISTS lue_dw.ix_payment_due_unit;
DROP INDEX IF EXISTS lue_dw.ix_occupancy_unit_date;
DROP INDEX IF EXISTS lue_dw.ix_dim_tenant_current_segment;
DROP TABLE IF EXISTS lue_dw.bench_occupancy_unpartitioned;
