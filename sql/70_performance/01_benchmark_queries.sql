-- sql/70_performance/01_benchmark_queries.sql: the benchmark workload beyond Q1 and Q7 (E12, US-12.1)
-- Runs in: lue_warehouse, as lue_etl; read-only. scripts/benchmark.py measures these together with Q1 and Q7
-- exactly as they stand in sql/60_analytics/analytical.sql (the whole-window answers), so the questions measured
-- are the questions answered. These four are the selective and date-bounded shapes a dashboard sends: one
-- month, one quarter, one unit. Dates are fixed keys (the last month and quarter of the data window), so every
-- run measures the same work; they hold on both profiles (both windows end on 2026-06-30).
-- "Change" names what the experiment varies; "Baseline" the table measured before, when it is not the same.

-- ==========================================================================================================
-- B2  Collection rate by building for one month (Q1 drilled to June 2026)
-- Grain:      building, due month 2026-06
-- Tables:     fact_rent_invoice_line, fact_payment, dim_unit
-- Definition: Q1 (D17, cohort basis) restricted to the lines due in one month: a dashboard's month filter.
-- Change:     indexes ix_invoice_line_due_unit and ix_payment_due_unit, (due_date_key, unit_key)
-- ==========================================================================================================
WITH billed AS (
    SELECT u.building_code, sum(f.net_amount) AS billed
    FROM lue_dw.fact_rent_invoice_line f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    WHERE f.due_date_key BETWEEN 20260601 AND 20260630
    GROUP BY 1),
collected AS (
    SELECT u.building_code, sum(p.payment_amount) AS collected
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_unit u ON u.unit_key = p.unit_key
    WHERE p.due_date_key BETWEEN 20260601 AND 20260630 AND p.paid_date_key BETWEEN 1 AND 20260630
    GROUP BY 1)
SELECT b.building_code, b.billed, coalesce(c.collected, 0) AS collected,
       round(coalesce(c.collected, 0) / nullif(b.billed, 0), 4) AS collection_rate
FROM billed b
LEFT JOIN collected c ON c.building_code = b.building_code
ORDER BY b.building_code;

-- ==========================================================================================================
-- B4  Occupancy by city for one quarter (a large occupancy aggregate, date-bounded)
-- Grain:      city, the quarter April to June 2026
-- Tables:     fact_unit_occupancy_daily, dim_unit
-- Definition: occupied unit-days / unit-days in the quarter, by the unit version's city.
-- Change:     monthly range partitioning on snapshot_date_key (partition pruning)
-- Baseline:   lue_dw.bench_occupancy_unpartitioned (the same rows and primary key in one table)
-- ==========================================================================================================
SELECT u.city, count(*) AS unit_days, sum(f.is_occupied) AS occupied_days,
       round(sum(f.is_occupied)::numeric / count(*), 4) AS occupancy_rate
FROM lue_dw.fact_unit_occupancy_daily f
JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
WHERE f.snapshot_date_key BETWEEN 20260401 AND 20260630
GROUP BY u.city
ORDER BY u.city;

-- ==========================================================================================================
-- B5  One unit's occupancy, rent and arrears over a fiscal year (a drill-through to one unit)
-- Grain:      month, FY2025-26, the first unit of the first building (every version of it)
-- Tables:     fact_unit_occupancy_daily, dim_unit
-- Definition: per month: occupied days, the average contract rent while let, arrears on the last day.
-- Change:     index ix_occupancy_unit_date, (unit_key, snapshot_date_key), on every partition
-- ==========================================================================================================
SELECT f.snapshot_date_key / 100 AS year_month, count(*) AS days, sum(f.is_occupied) AS occupied_days,
       round(avg(f.contract_rent) FILTER (WHERE f.is_occupied = 1), 2) AS avg_rent_while_let,
       (array_agg(f.current_lease_arrears ORDER BY f.snapshot_date_key DESC))[1] AS arrears_month_end
FROM lue_dw.fact_unit_occupancy_daily f
WHERE f.unit_key IN (SELECT u.unit_key FROM lue_dw.dim_unit u
                     WHERE u.unit_nk = (SELECT min(unit_nk) FROM lue_dw.dim_unit WHERE unit_key > 0))
  AND f.snapshot_date_key BETWEEN 20250701 AND 20260630
GROUP BY 1
ORDER BY 1;

-- ==========================================================================================================
-- B6  Current tenants by segment (a slicer list from the current SCD2 rows)
-- Grain:      tenant type x employer sector, current versions
-- Tables:     dim_tenant
-- Definition: the current version of every tenant, counted by segment.
-- Change:     partial index ix_dim_tenant_current_segment, (tenant_type, employer_sector) WHERE is_current
-- ==========================================================================================================
SELECT tenant_type, employer_sector, count(*) AS tenants
FROM lue_dw.dim_tenant
WHERE is_current
GROUP BY tenant_type, employer_sector
ORDER BY tenant_type, employer_sector;
