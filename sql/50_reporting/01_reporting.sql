-- sql/50_reporting/01_reporting.sql: the reporting layer in lue_reporting (E10, US-10.1 to US-10.3)
-- Runs in: lue_warehouse, as lue_etl (scripts/db_deploy.py, the pipeline's deploy stage). Safe to re-run:
-- every object is derived from lue_dw, so the layer is dropped and created again from this file, and
-- the marts are filled at once from the facts as they stand. The pipeline's marts stage refreshes
-- them after every load (lue_reporting.refresh_marts()).
--
-- Objects (every column is described in docs/reporting.md):
--   parameters    vw_reporting_window (the data window: the occupancy snapshot's first and last day),
--                 vw_reporting_parameter (the stated assumptions: management fee, late-payer bands)
--   slicers       vw_dim_date, vw_dim_month, vw_dim_building, vw_dim_unit, vw_dim_unit_type, vw_dim_tenant,
--                 vw_dim_owner, vw_dim_vendor, vw_dim_maintenance_category, vw_dim_payment_method (no technical
--                 columns)
--   marts         mart_collections_monthly      month x building
--                 mart_occupancy_monthly        month x building x unit type
--                 mart_maintenance_monthly      raised month x building x unit type x category x vendor
--                 mart_owner_portfolio_monthly  month x owner
--                 Each stores additive parts only (sums and counts; month-end values are semi-additive:
--                 sum across buildings, never across months), so a rate is a ratio of sums at any level.
--   views         vw_monthly_collections, vw_tenant_analysis, vw_unit_performance (the brief's three
--                 reporting views, LUE names) and their brief-named aliases vw_monthly_sales,
--                 vw_customer_analysis, vw_product_performance (D18); vw_tenant_by_building, the tenant
--                 analysis by building (the dashboard's drill-through from a building to its tenants, US-13.3)
--
-- Definitions:
--   D17 collection rate (cohort): payments against invoice lines due in month M / net amount of the lines
--       due in M, as of the window end. Cash received: payments with a paid date in M (a separate measure).
--   Arrears on day D: the open balance of the lines past due on D: net amount of lines due before D minus
--       the payments against them made by D (a payment before the due date counts from the day after it);
--       the rule of fact_unit_occupancy_daily.current_lease_arrears (US-7.3).
--   Occupancy: occupied unit-days / unit-days (the average of daily occupied units over units).
--   Average vacancy days (pack KPI): vacant unit-days / completed vacancy spells (a spell is completed when
--       the unit is let again inside the window).
--   Maintenance cost per unit-month (pack KPI): actual cost / unit-months (units at each month end).
--   NOI per owner (Q12): rent collected (charge type RENT, paid month) - actual maintenance cost (raised
--       month) - the management fee (rent collected x management_fee_rate).
-- Access: lue_reader reads every object here (default privileges, sql/00_setup/05_warehouse_schemas.sql)
-- and nothing in lue_staging, lue_dw or lue_audit; it cannot write, and cannot run refresh_marts().

DROP VIEW IF EXISTS lue_reporting.vw_monthly_sales, lue_reporting.vw_customer_analysis,
    lue_reporting.vw_product_performance CASCADE;
DROP VIEW IF EXISTS lue_reporting.vw_tenant_by_building, lue_reporting.vw_monthly_collections,
    lue_reporting.vw_tenant_analysis, lue_reporting.vw_unit_performance CASCADE;
DROP FUNCTION IF EXISTS lue_reporting.refresh_marts();
DROP MATERIALIZED VIEW IF EXISTS lue_reporting.mart_collections_monthly, lue_reporting.mart_occupancy_monthly,
    lue_reporting.mart_maintenance_monthly, lue_reporting.mart_owner_portfolio_monthly CASCADE;
DROP VIEW IF EXISTS lue_reporting.vw_dim_date, lue_reporting.vw_dim_month, lue_reporting.vw_dim_building,
    lue_reporting.vw_dim_unit, lue_reporting.vw_dim_unit_type, lue_reporting.vw_dim_tenant, lue_reporting.vw_dim_owner,
    lue_reporting.vw_dim_vendor, lue_reporting.vw_dim_maintenance_category, lue_reporting.vw_dim_payment_method,
    lue_reporting.vw_reporting_parameter, lue_reporting.vw_reporting_window CASCADE;

-- ---------------------------------------------------------------------------------------------------------
-- Parameters
-- ---------------------------------------------------------------------------------------------------------
CREATE VIEW lue_reporting.vw_reporting_window AS
SELECT d0.full_date AS window_start, d1.full_date AS window_end
FROM (SELECT min(snapshot_date_key) AS first_key, max(snapshot_date_key) AS last_key
      FROM lue_dw.fact_unit_occupancy_daily) w
JOIN lue_dw.dim_date d0 ON d0.date_key = w.first_key
JOIN lue_dw.dim_date d1 ON d1.date_key = w.last_key;

CREATE VIEW lue_reporting.vw_reporting_parameter AS
SELECT * FROM (VALUES
    ('management_fee_rate', 0.08,
     'LUE management fee: 8 percent of the rent collected (an assumption; Q12, mart_owner_portfolio_monthly)'),
    ('occasionally_late_from', 0.00,
     'Payer band: a tenant with any late payment is at least occasionally late (vw_tenant_analysis)'),
    ('chronically_late_from', 0.50,
     'Payer band: chronically late when half or more of a tenant''s payments were late (vw_tenant_analysis)')
) AS p (parameter, value, note);

-- ---------------------------------------------------------------------------------------------------------
-- Slicer views (US-10.1 step 5): the dimensions without their technical columns
-- ---------------------------------------------------------------------------------------------------------
CREATE VIEW lue_reporting.vw_dim_date AS
SELECT date_key, full_date, day_of_month, day_name, is_weekend, week_of_year, month_no, month_name, quarter_no,
       year_no, to_char(full_date, 'YYYY-MM') AS year_month, fiscal_month_no, fiscal_quarter_no, fiscal_year_label,
       is_public_holiday, holiday_name, is_ramadan
FROM lue_dw.dim_date;

CREATE VIEW lue_reporting.vw_dim_month AS
SELECT d.date_key AS month_key, d.full_date AS month_start,
       least((d.full_date + interval '1 month' - interval '1 day')::date, w.window_end) AS month_end,
       to_char(d.full_date, 'YYYY-MM') AS year_month, d.month_no, d.month_name, d.quarter_no, d.year_no,
       d.fiscal_month_no, d.fiscal_quarter_no, d.fiscal_year_label
FROM lue_dw.dim_date d
CROSS JOIN lue_reporting.vw_reporting_window w
WHERE d.date_key > 0 AND d.day_of_month = 1
  AND d.full_date BETWEEN date_trunc('month', w.window_start)::date AND w.window_end;

CREATE VIEW lue_reporting.vw_dim_building AS
SELECT DISTINCT ON (building_code) building_code, building_name, building_class, building_age_band, locality, city,
       region
FROM lue_dw.dim_unit
ORDER BY building_code, is_current DESC, effective_from DESC;

CREATE VIEW lue_reporting.vw_dim_unit AS
SELECT unit_key, unit_nk, building_code, unit_no, unit_type, bedrooms, area_sqft, furnished_flag, floor_no,
       building_name, building_class, building_age_band, locality, city, region, effective_from, effective_to,
       is_current
FROM lue_dw.dim_unit;

-- the unit types, so one slicer filters the occupancy and maintenance marts together
CREATE VIEW lue_reporting.vw_dim_unit_type AS
SELECT unit_type, count(*) FILTER (WHERE is_current AND unit_key > 0)::int AS current_units
FROM lue_dw.dim_unit
GROUP BY unit_type;

CREATE VIEW lue_reporting.vw_dim_tenant AS
SELECT tenant_key, tenant_code, tenant_name, tenant_type, employer_sector, contact_channel, is_inferred,
       effective_from, effective_to, is_current
FROM lue_dw.dim_tenant;

CREATE VIEW lue_reporting.vw_dim_owner AS
SELECT owner_key, owner_code, owner_name, owner_type, portfolio_size_band
FROM lue_dw.dim_owner;

CREATE VIEW lue_reporting.vw_dim_vendor AS
SELECT vendor_key, vendor_code, vendor_name, trade, rating_band, phone, effective_from, effective_to, is_current
FROM lue_dw.dim_vendor;

CREATE VIEW lue_reporting.vw_dim_maintenance_category AS
SELECT maint_category_key, subcategory_code, subcategory_name, category_name, default_sla_hours, effective_from,
       effective_to, is_current
FROM lue_dw.dim_maintenance_category;

CREATE VIEW lue_reporting.vw_dim_payment_method AS
SELECT payment_method_key, method_code, method_name, channel_group, typical_settlement_days
FROM lue_dw.dim_payment_method;

-- ---------------------------------------------------------------------------------------------------------
-- mart_collections_monthly: one row per month and building (US-10.2)
-- ---------------------------------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW lue_reporting.mart_collections_monthly AS
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
line AS (
    SELECT u.building_code, d.full_date AS due_date, f.net_amount
    FROM lue_dw.fact_rent_invoice_line f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key
    WHERE f.due_date_key > 0),
pay AS (
    SELECT u.building_code, dd.full_date AS due_date, pd.full_date AS paid_date, f.payment_amount
    FROM lue_dw.fact_payment f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date dd ON dd.date_key = f.due_date_key
    JOIN lue_dw.dim_date pd ON pd.date_key = f.paid_date_key
    WHERE f.due_date_key > 0 AND f.paid_date_key > 0),
billed AS (SELECT building_code, date_trunc('month', due_date)::date AS month_start, count(*) AS lines,
                  sum(net_amount) AS amount FROM line GROUP BY 1, 2),
cohort AS (SELECT p.building_code, date_trunc('month', p.due_date)::date AS month_start, sum(p.payment_amount) AS amount
           FROM pay p CROSS JOIN w WHERE p.paid_date <= w.window_end GROUP BY 1, 2),
cash AS (SELECT building_code, date_trunc('month', paid_date)::date AS month_start, sum(payment_amount) AS amount
         FROM pay GROUP BY 1, 2),
-- a line is past due from the day after its due date; a payment reduces it from then, or from its paid date
moves AS MATERIALIZED (
    SELECT building_code, month_start, sum(amount) AS amount FROM (
        SELECT building_code, date_trunc('month', due_date + 1)::date AS month_start, net_amount AS amount FROM line
        UNION ALL
        SELECT building_code, date_trunc('month', greatest(due_date + 1, paid_date))::date, -payment_amount FROM pay
    ) x GROUP BY 1, 2),
opening AS (SELECT x.building_code, sum(x.amount) AS amount FROM moves x
            WHERE x.month_start < (SELECT min(month_start) FROM lue_reporting.vw_dim_month) GROUP BY 1),
buildings AS (SELECT building_code FROM lue_dw.dim_unit WHERE unit_key > 0
              UNION SELECT building_code FROM line UNION SELECT building_code FROM pay),
grid AS (
    SELECT m.month_key, m.month_start, b.building_code,
           coalesce(bl.lines, 0) AS invoice_lines, coalesce(bl.amount, 0) AS billed_due,
           coalesce(co.amount, 0) AS collected_cohort, coalesce(ca.amount, 0) AS cash_received,
           coalesce(op.amount, 0) AS opening, coalesce(mv.amount, 0) AS moved
    FROM lue_reporting.vw_dim_month m
    CROSS JOIN buildings b
    LEFT JOIN billed bl ON bl.building_code = b.building_code AND bl.month_start = m.month_start
    LEFT JOIN cohort co ON co.building_code = b.building_code AND co.month_start = m.month_start
    LEFT JOIN cash ca ON ca.building_code = b.building_code AND ca.month_start = m.month_start
    LEFT JOIN moves mv ON mv.building_code = b.building_code AND mv.month_start = m.month_start
    LEFT JOIN opening op ON op.building_code = b.building_code)
SELECT month_key, month_start, building_code, invoice_lines::int, billed_due::numeric(14,2),
       collected_cohort::numeric(14,2), cash_received::numeric(14,2),
       (opening + sum(moved) OVER (PARTITION BY building_code ORDER BY month_start))::numeric(14,2)
           AS arrears_month_end
FROM grid;

CREATE UNIQUE INDEX uq_mart_collections_monthly ON lue_reporting.mart_collections_monthly (month_key, building_code);

-- ---------------------------------------------------------------------------------------------------------
-- mart_occupancy_monthly: one row per month, building and unit type (US-10.2)
-- ---------------------------------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW lue_reporting.mart_occupancy_monthly AS
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
daily AS (
    SELECT m.month_key, u.building_code, u.unit_type, d.full_date = m.month_end AS month_end_day,
           f.is_occupied, f.lease_key, f.contract_rent, f.current_lease_arrears
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    JOIN lue_reporting.vw_dim_month m ON m.month_start = date_trunc('month', d.full_date)::date),
agg AS (
    SELECT month_key, building_code, unit_type,
           count(*) AS unit_days,
           sum(is_occupied) AS occupied_days,
           count(DISTINCT lease_key) FILTER (WHERE is_occupied = 1) AS active_leases,
           count(*) FILTER (WHERE month_end_day) AS units_month_end,
           coalesce(sum(is_occupied) FILTER (WHERE month_end_day), 0) AS occupied_units_month_end,
           coalesce(sum(contract_rent) FILTER (WHERE month_end_day), 0) AS rent_roll_month_end,
           coalesce(sum(current_lease_arrears) FILTER (WHERE month_end_day), 0) AS arrears_month_end
    FROM daily GROUP BY 1, 2, 3),
vacant AS (
    SELECT u.unit_nk, d.full_date,
           d.full_date - (row_number() OVER (PARTITION BY u.unit_nk ORDER BY d.full_date))::int AS island
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    WHERE f.is_occupied = 0),
spell AS (SELECT unit_nk, max(full_date) AS last_day FROM vacant GROUP BY unit_nk, island),
completed AS (
    SELECT m.month_key, u.building_code, u.unit_type, count(*) AS completed_vacancy_spells
    FROM spell s
    CROSS JOIN w
    JOIN lue_dw.dim_unit u ON u.unit_nk = s.unit_nk AND s.last_day >= u.effective_from AND s.last_day < u.effective_to
    JOIN lue_reporting.vw_dim_month m ON m.month_start = date_trunc('month', s.last_day)::date
    WHERE s.last_day < w.window_end  -- let again the next day, inside the window
    GROUP BY 1, 2, 3)
SELECT a.month_key, m.month_start, a.building_code, a.unit_type,
       a.unit_days::int, a.occupied_days::int, (a.unit_days - a.occupied_days)::int AS vacant_days,
       coalesce(c.completed_vacancy_spells, 0)::int AS completed_vacancy_spells,
       a.active_leases::int, a.units_month_end::int, a.occupied_units_month_end::int,
       a.rent_roll_month_end::numeric(14,2), a.arrears_month_end::numeric(14,2)
FROM agg a
JOIN lue_reporting.vw_dim_month m ON m.month_key = a.month_key
LEFT JOIN completed c ON c.month_key = a.month_key AND c.building_code = a.building_code AND c.unit_type = a.unit_type;

CREATE UNIQUE INDEX uq_mart_occupancy_monthly ON lue_reporting.mart_occupancy_monthly (month_key, building_code, unit_type);

-- ---------------------------------------------------------------------------------------------------------
-- mart_maintenance_monthly: one row per raised month, building, unit type, category and vendor (US-10.2);
-- the category and vendor are the versions valid when the request was raised (their SCD2 keys)
-- ---------------------------------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW lue_reporting.mart_maintenance_monthly AS
SELECT m.month_key, m.month_start, u.building_code, u.unit_type, f.maint_category_key, f.vendor_key,
       count(*)::int AS requests,
       count(f.days_to_resolve)::int AS resolved_requests,
       coalesce(sum(f.days_to_resolve), 0)::numeric(12,2) AS days_to_resolve_sum,  -- days with hours (NUMERIC(6,2))
       coalesce(sum(f.sla_breached_flag), 0)::int AS sla_breached,
       coalesce(sum(f.estimated_cost), 0)::numeric(14,2) AS estimated_cost,
       coalesce(sum(f.actual_cost), 0)::numeric(14,2) AS actual_cost
FROM lue_dw.fact_maintenance_request f
JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
JOIN lue_dw.dim_date d ON d.date_key = f.raised_date_key
JOIN lue_reporting.vw_dim_month m ON m.month_start = date_trunc('month', d.full_date)::date
WHERE f.raised_date_key > 0
GROUP BY m.month_key, m.month_start, u.building_code, u.unit_type, f.maint_category_key, f.vendor_key;

CREATE UNIQUE INDEX uq_mart_maintenance_monthly ON lue_reporting.mart_maintenance_monthly
    (month_key, building_code, unit_type, maint_category_key, vendor_key);

-- ---------------------------------------------------------------------------------------------------------
-- mart_owner_portfolio_monthly: one row per month and owner (US-10.2, Q12)
-- ---------------------------------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW lue_reporting.mart_owner_portfolio_monthly AS
WITH fee AS (SELECT value AS rate FROM lue_reporting.vw_reporting_parameter WHERE parameter = 'management_fee_rate'),
rent AS (
    SELECT m.month_key, f.owner_key,
           sum(f.payment_amount) FILTER (WHERE c.charge_code = 'RENT') AS rent_collected,
           sum(f.payment_amount) AS cash_received
    FROM lue_dw.fact_payment f
    JOIN lue_dw.dim_charge_type c ON c.charge_type_key = f.charge_type_key
    JOIN lue_dw.dim_date d ON d.date_key = f.paid_date_key
    JOIN lue_reporting.vw_dim_month m ON m.month_start = date_trunc('month', d.full_date)::date
    WHERE f.paid_date_key > 0
    GROUP BY 1, 2),
cost AS (
    SELECT m.month_key, f.owner_key, count(*) AS requests, sum(f.actual_cost) AS maintenance_cost
    FROM lue_dw.fact_maintenance_request f
    JOIN lue_dw.dim_date d ON d.date_key = f.raised_date_key
    JOIN lue_reporting.vw_dim_month m ON m.month_start = date_trunc('month', d.full_date)::date
    WHERE f.raised_date_key > 0
    GROUP BY 1, 2),
units AS (
    SELECT m.month_key, f.owner_key, count(*) AS unit_days, sum(f.is_occupied) AS occupied_days,
           count(*) FILTER (WHERE d.full_date = m.month_end) AS units_month_end
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    JOIN lue_reporting.vw_dim_month m ON m.month_start = date_trunc('month', d.full_date)::date
    GROUP BY 1, 2),
grid AS (SELECT month_key, owner_key FROM rent UNION SELECT month_key, owner_key FROM cost
         UNION SELECT month_key, owner_key FROM units),
measured AS (
    SELECT g.month_key, g.owner_key,
           coalesce(r.rent_collected, 0)::numeric(14,2) AS rent_collected,
           coalesce(r.cash_received, 0)::numeric(14,2) AS cash_received,
           coalesce(c.requests, 0)::int AS maintenance_requests,
           coalesce(c.maintenance_cost, 0)::numeric(14,2) AS maintenance_cost,
           coalesce(u.unit_days, 0)::int AS unit_days, coalesce(u.occupied_days, 0)::int AS occupied_days,
           coalesce(u.units_month_end, 0)::int AS units_month_end
    FROM grid g
    LEFT JOIN rent r ON r.month_key = g.month_key AND r.owner_key = g.owner_key
    LEFT JOIN cost c ON c.month_key = g.month_key AND c.owner_key = g.owner_key
    LEFT JOIN units u ON u.month_key = g.month_key AND u.owner_key = g.owner_key)
SELECT x.month_key, m.month_start, x.owner_key, x.rent_collected, x.cash_received, x.maintenance_requests,
       x.maintenance_cost, fee.rate AS management_fee_rate,
       round(x.rent_collected * fee.rate, 2)::numeric(14,2) AS management_fee,
       (x.rent_collected - x.maintenance_cost - round(x.rent_collected * fee.rate, 2))::numeric(14,2) AS noi,
       x.unit_days, x.occupied_days, x.units_month_end
FROM measured x
JOIN lue_reporting.vw_dim_month m ON m.month_key = x.month_key
CROSS JOIN fee;

CREATE UNIQUE INDEX uq_mart_owner_portfolio_monthly ON lue_reporting.mart_owner_portfolio_monthly (month_key, owner_key);

-- ---------------------------------------------------------------------------------------------------------
-- refresh_marts(): the pipeline's marts stage (US-10.2). Concurrently once a mart holds data (readers are
-- not blocked; the unique indexes allow it), plainly the first time. Returns each mart's rows and seconds.
-- ---------------------------------------------------------------------------------------------------------
CREATE FUNCTION lue_reporting.refresh_marts()
RETURNS TABLE (mart text, row_count bigint, seconds numeric)
LANGUAGE plpgsql AS $$
DECLARE
    name text;
    started timestamptz;
    populated boolean;
BEGIN
    FOREACH name IN ARRAY ARRAY['mart_collections_monthly', 'mart_occupancy_monthly',
                                'mart_maintenance_monthly', 'mart_owner_portfolio_monthly'] LOOP
        started := clock_timestamp();
        SELECT ispopulated INTO populated FROM pg_matviews
        WHERE schemaname = 'lue_reporting' AND matviewname = name;
        IF populated THEN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY lue_reporting.%I', name);
        ELSE
            EXECUTE format('REFRESH MATERIALIZED VIEW lue_reporting.%I', name);
        END IF;
        mart := name;
        EXECUTE format('SELECT count(*) FROM lue_reporting.%I', name) INTO row_count;
        seconds := round(extract(epoch FROM clock_timestamp() - started)::numeric, 2);
        RETURN NEXT;
    END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION lue_reporting.refresh_marts() FROM PUBLIC;

-- ---------------------------------------------------------------------------------------------------------
-- The brief's three reporting views, LUE names (US-10.1)
-- ---------------------------------------------------------------------------------------------------------
-- vw_monthly_collections: one row per month (the portfolio), from mart_collections_monthly
CREATE VIEW lue_reporting.vw_monthly_collections AS
WITH monthly AS (
    SELECT c.month_key, m.year_month, m.fiscal_year_label, m.fiscal_quarter_no,
           sum(c.invoice_lines) AS invoice_lines, sum(c.billed_due) AS billed_due,
           sum(c.collected_cohort) AS collected_cohort, sum(c.cash_received) AS cash_received,
           sum(c.arrears_month_end) AS arrears_month_end
    FROM lue_reporting.mart_collections_monthly c
    JOIN lue_reporting.vw_dim_month m ON m.month_key = c.month_key
    GROUP BY 1, 2, 3, 4)
SELECT month_key, year_month, fiscal_year_label, fiscal_quarter_no, invoice_lines, billed_due, collected_cohort,
       round(collected_cohort / nullif(billed_due, 0), 4) AS collection_rate_cohort,
       cash_received, arrears_month_end,
       round((billed_due - lag(billed_due) OVER w) / nullif(lag(billed_due) OVER w, 0), 4) AS billed_growth,
       round((cash_received - lag(cash_received) OVER w) / nullif(lag(cash_received) OVER w, 0), 4)
           AS cash_received_growth
FROM monthly
WINDOW w AS (ORDER BY month_key);

-- vw_tenant_analysis: one row per tenant version (the tenant as it was when it paid or was billed)
CREATE VIEW lue_reporting.vw_tenant_analysis AS
WITH w AS (SELECT window_end FROM lue_reporting.vw_reporting_window),
band AS (SELECT max(value) FILTER (WHERE parameter = 'chronically_late_from') AS chronic
         FROM lue_reporting.vw_reporting_parameter),
paid AS (
    SELECT f.tenant_key,
           count(DISTINCT f.payment_reference) FILTER (WHERE NOT f.is_reversal) AS payments,
           count(DISTINCT f.payment_reference) FILTER (WHERE NOT f.is_reversal AND f.days_past_due > 0)
               AS late_payments,
           sum(f.days_past_due * f.payment_amount) FILTER (WHERE NOT f.is_reversal)
               / nullif(sum(f.payment_amount) FILTER (WHERE NOT f.is_reversal), 0) AS avg_days_past_due,
           sum(f.payment_amount) AS total_collected
    FROM lue_dw.fact_payment f
    GROUP BY 1),
-- arrears as of the window end, by the version the line was billed to
open_line AS (
    SELECT l.tenant_key, l.net_amount - coalesce(p.paid, 0) AS balance
    FROM lue_dw.fact_rent_invoice_line l
    JOIN lue_dw.dim_date dd ON dd.date_key = l.due_date_key
    CROSS JOIN w
    LEFT JOIN (SELECT f.invoice_number, f.invoice_line_no, sum(f.payment_amount) AS paid
               FROM lue_dw.fact_payment f
               JOIN lue_dw.dim_date fd ON fd.date_key = f.due_date_key
               JOIN lue_dw.dim_date pd ON pd.date_key = f.paid_date_key
               CROSS JOIN lue_reporting.vw_reporting_window pw
               WHERE f.due_date_key > 0 AND f.paid_date_key > 0
                 AND greatest(fd.full_date + 1, pd.full_date) <= pw.window_end
               GROUP BY 1, 2) p
           ON p.invoice_number = l.invoice_number AND p.invoice_line_no = l.invoice_line_no
    WHERE l.due_date_key > 0 AND dd.full_date + 1 <= w.window_end),
owed AS (SELECT tenant_key, sum(balance) AS current_arrears FROM open_line GROUP BY 1),
tenants AS (SELECT tenant_key FROM paid UNION SELECT tenant_key FROM lue_dw.fact_rent_invoice_line)
SELECT t.tenant_key, t.tenant_code, t.tenant_name, t.tenant_type, t.employer_sector, t.is_current,
       coalesce(p.payments, 0)::int AS payments, coalesce(p.late_payments, 0)::int AS late_payments,
       round(p.late_payments::numeric / nullif(p.payments, 0), 4) AS late_payment_share,
       round(p.avg_days_past_due, 1) AS avg_days_past_due,
       coalesce(p.total_collected, 0)::numeric(14,2) AS total_collected,
       coalesce(o.current_arrears, 0)::numeric(14,2) AS current_arrears,
       CASE WHEN coalesce(p.payments, 0) = 0 THEN 'No payments'
            WHEN p.late_payments = 0 THEN 'On time'
            WHEN p.late_payments::numeric / p.payments >= band.chronic THEN 'Chronically late'
            ELSE 'Occasionally late' END AS payer_segment
FROM tenants k
JOIN lue_dw.dim_tenant t ON t.tenant_key = k.tenant_key
CROSS JOIN band
LEFT JOIN paid p ON p.tenant_key = k.tenant_key
LEFT JOIN owed o ON o.tenant_key = k.tenant_key;

-- vw_unit_performance: one row per building and unit type over the data window, from the marts
CREATE VIEW lue_reporting.vw_unit_performance AS
WITH occ AS (
    SELECT building_code, unit_type, sum(unit_days) AS unit_days, sum(occupied_days) AS occupied_days,
           sum(vacant_days) AS vacant_days, sum(completed_vacancy_spells) AS completed_vacancy_spells,
           sum(units_month_end) AS unit_months, sum(occupied_units_month_end) AS occupied_unit_months,
           sum(rent_roll_month_end) AS rent_roll_sum,
           sum(units_month_end) FILTER (WHERE month_key = (SELECT max(month_key) FROM lue_reporting.vw_dim_month)) AS units,
           sum(rent_roll_month_end) FILTER (WHERE month_key = (SELECT max(month_key) FROM lue_reporting.vw_dim_month)) AS rent_roll_current
    FROM lue_reporting.mart_occupancy_monthly GROUP BY 1, 2),
mnt AS (
    SELECT building_code, unit_type, sum(requests) AS requests, sum(resolved_requests) AS resolved_requests,
           sum(days_to_resolve_sum) AS days_to_resolve_sum, sum(sla_breached) AS sla_breached,
           sum(actual_cost) AS maintenance_cost
    FROM lue_reporting.mart_maintenance_monthly GROUP BY 1, 2)
SELECT o.building_code, b.building_name, b.city, b.building_class, o.unit_type,
       coalesce(o.units, 0)::int AS units, o.unit_days::int, o.occupied_days::int,
       round(o.occupied_days::numeric / nullif(o.unit_days, 0), 4) AS occupancy_rate,
       o.vacant_days::int, o.completed_vacancy_spells::int,
       round(o.vacant_days::numeric / nullif(o.completed_vacancy_spells, 0), 1) AS avg_vacancy_days,
       round(o.rent_roll_sum / nullif(o.occupied_unit_months, 0), 2) AS avg_contract_rent,
       coalesce(o.rent_roll_current, 0)::numeric(14,2) AS rent_roll_current,
       coalesce(m.requests, 0)::int AS maintenance_requests,
       coalesce(m.maintenance_cost, 0)::numeric(14,2) AS maintenance_cost,
       round(coalesce(m.maintenance_cost, 0) / nullif(o.unit_months, 0), 2) AS maintenance_cost_per_unit_month,
       round(m.days_to_resolve_sum::numeric / nullif(m.resolved_requests, 0), 1) AS avg_days_to_resolve,
       round(m.sla_breached::numeric / nullif(m.resolved_requests, 0), 4) AS sla_breach_rate
FROM occ o
LEFT JOIN mnt m ON m.building_code = o.building_code AND m.unit_type = o.unit_type
LEFT JOIN lue_reporting.vw_dim_building b ON b.building_code = o.building_code;

-- vw_tenant_by_building: one row per tenant version and building, over the data window (US-13.3): the
-- tenant analysis split by the building billed or paid; summed over the buildings it gives vw_tenant_analysis's
-- collected and arrears, and summed over a building's tenants Q2's billed and arrears
CREATE VIEW lue_reporting.vw_tenant_by_building AS
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
paid AS (
    SELECT f.tenant_key, u.building_code,
           count(DISTINCT f.payment_reference) FILTER (WHERE NOT f.is_reversal) AS payments,
           count(DISTINCT f.payment_reference) FILTER (WHERE NOT f.is_reversal AND f.days_past_due > 0)
               AS late_payments,
           sum(f.payment_amount) AS total_collected
    FROM lue_dw.fact_payment f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    GROUP BY 1, 2),
alloc AS (
    SELECT f.invoice_number, f.invoice_line_no, sum(f.payment_amount) AS paid
    FROM lue_dw.fact_payment f
    JOIN lue_dw.dim_date fd ON fd.date_key = f.due_date_key
    JOIN lue_dw.dim_date pd ON pd.date_key = f.paid_date_key
    CROSS JOIN w
    WHERE f.due_date_key > 0 AND f.paid_date_key > 0 AND greatest(fd.full_date + 1, pd.full_date) <= w.window_end
    GROUP BY 1, 2),
billed AS (
    SELECT l.tenant_key, u.building_code,
           count(*) FILTER (WHERE dd.full_date BETWEEN date_trunc('month', w.window_start)::date AND w.window_end)
               AS invoice_lines,
           sum(l.net_amount) FILTER (WHERE dd.full_date BETWEEN date_trunc('month', w.window_start)::date
                                                            AND w.window_end) AS billed_due,
           sum(l.net_amount - coalesce(a.paid, 0)) FILTER (WHERE dd.full_date + 1 <= w.window_end) AS current_arrears
    FROM lue_dw.fact_rent_invoice_line l
    JOIN lue_dw.dim_unit u ON u.unit_key = l.unit_key
    JOIN lue_dw.dim_date dd ON dd.date_key = l.due_date_key
    CROSS JOIN w
    LEFT JOIN alloc a ON a.invoice_number = l.invoice_number AND a.invoice_line_no = l.invoice_line_no
    WHERE l.due_date_key > 0
    GROUP BY 1, 2),
pairs AS (SELECT tenant_key, building_code FROM paid UNION SELECT tenant_key, building_code FROM billed)
SELECT k.tenant_key, k.building_code, t.tenant_code, t.tenant_name, t.tenant_type, t.employer_sector,
       t.payer_segment,
       coalesce(b.invoice_lines, 0)::int AS invoice_lines,
       coalesce(b.billed_due, 0)::numeric(14,2) AS billed_due,
       coalesce(p.payments, 0)::int AS payments, coalesce(p.late_payments, 0)::int AS late_payments,
       coalesce(p.total_collected, 0)::numeric(14,2) AS total_collected,
       coalesce(b.current_arrears, 0)::numeric(14,2) AS current_arrears
FROM pairs k
JOIN lue_reporting.vw_tenant_analysis t ON t.tenant_key = k.tenant_key
LEFT JOIN paid p ON p.tenant_key = k.tenant_key AND p.building_code = k.building_code
LEFT JOIN billed b ON b.tenant_key = k.tenant_key AND b.building_code = k.building_code;

-- ---------------------------------------------------------------------------------------------------------
-- The brief's names (D18): thin aliases of the LUE views, identical rows
-- ---------------------------------------------------------------------------------------------------------
CREATE VIEW lue_reporting.vw_monthly_sales AS SELECT * FROM lue_reporting.vw_monthly_collections;
CREATE VIEW lue_reporting.vw_customer_analysis AS SELECT * FROM lue_reporting.vw_tenant_analysis;
CREATE VIEW lue_reporting.vw_product_performance AS SELECT * FROM lue_reporting.vw_unit_performance;
