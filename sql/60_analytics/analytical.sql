-- sql/60_analytics/analytical.sql: the 14 business questions and the window analytics (E11)
-- Runs in: lue_warehouse, as lue_etl (or any role that reads lue_dw and lue_reporting); read-only.
--   psql -d lue_warehouse -v ON_ERROR_STOP=1 -f sql/60_analytics/analytical.sql
-- Each query is headed by its question, grain, the tables it reads and its definition. "The window" is the
-- data window (lue_reporting.vw_reporting_window: the occupancy snapshot's first and last day); "as of" means
-- its last day. Results, interpretations and the planted patterns they show: docs/analytics.md.
-- Q1 to Q14 are the pack's business questions (docs/phase1, 03_Business_Questions.pdf); W1 to W4 are the
-- window analytics of US-11.5. The OLAP queries (ROLLUP, CUBE) are in olap.sql.

-- ==========================================================================================================
-- Q1  What is the monthly collection rate by building?
-- Grain:      building x due month (months of the window with billing)
-- Tables:     fact_rent_invoice_line, fact_payment, dim_unit, dim_date
-- Definition: D17, cohort basis: payments against the lines due in month M, as of the window end, divided
--             by the net amount of the lines due in M. LAG gives the change against the building's
--             previous month. Agrees with mart_collections_monthly and vw_monthly_collections.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
billed AS (
    SELECT u.building_code, date_trunc('month', d.full_date)::date AS month, sum(f.net_amount) AS billed
    FROM lue_dw.fact_rent_invoice_line f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key
    CROSS JOIN w
    WHERE f.due_date_key > 0 AND d.full_date BETWEEN date_trunc('month', w.window_start)::date AND w.window_end
    GROUP BY 1, 2),
collected AS (
    SELECT u.building_code, date_trunc('month', dd.full_date)::date AS month, sum(p.payment_amount) AS collected
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_unit u ON u.unit_key = p.unit_key
    JOIN lue_dw.dim_date dd ON dd.date_key = p.due_date_key
    JOIN lue_dw.dim_date pd ON pd.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE p.due_date_key > 0 AND p.paid_date_key > 0
      AND dd.full_date BETWEEN date_trunc('month', w.window_start)::date AND w.window_end
      AND pd.full_date <= w.window_end
    GROUP BY 1, 2),
rate AS (
    SELECT b.building_code, b.month, b.billed, coalesce(c.collected, 0) AS collected,
           coalesce(c.collected, 0) / nullif(b.billed, 0) AS rate
    FROM billed b
    LEFT JOIN collected c ON c.building_code = b.building_code AND c.month = b.month)
SELECT building_code, to_char(month, 'YYYY-MM') AS month, billed, collected,
       round(rate, 4) AS collection_rate,
       round(rate - lag(rate) OVER (PARTITION BY building_code ORDER BY month), 4) AS change_vs_previous_month
FROM rate
ORDER BY building_code, month;

-- ==========================================================================================================
-- Q2  Which buildings have the highest arrears ratio?
-- Grain:      building, as of the window end
-- Tables:     fact_rent_invoice_line, fact_payment, dim_unit, dim_date
-- Definition: arrears ratio = arrears / net amount billed (lines due in the window). Arrears = the open balance
--             of the lines past due on the last day: net amount of the lines due before it, minus the payments
--             against them made by then (a payment before the due date counts from the day after it; the rule
--             of fact_unit_occupancy_daily.current_lease_arrears). RANK orders the buildings.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
line AS (
    SELECT u.building_code, u.city, f.invoice_number, f.invoice_line_no, f.net_amount, d.full_date AS due_date
    FROM lue_dw.fact_rent_invoice_line f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key
    WHERE f.due_date_key > 0),
paid AS (
    SELECT p.invoice_number, p.invoice_line_no, sum(p.payment_amount) AS paid
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_date dd ON dd.date_key = p.due_date_key
    JOIN lue_dw.dim_date pd ON pd.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE p.due_date_key > 0 AND p.paid_date_key > 0 AND greatest(dd.full_date + 1, pd.full_date) <= w.window_end
    GROUP BY 1, 2),
building AS (
    SELECT l.building_code, l.city,
           sum(l.net_amount) FILTER (WHERE l.due_date BETWEEN date_trunc('month', w.window_start)::date AND w.window_end) AS billed,
           sum(l.net_amount - coalesce(p.paid, 0)) FILTER (WHERE l.due_date + 1 <= w.window_end) AS arrears
    FROM line l
    CROSS JOIN w
    LEFT JOIN paid p ON p.invoice_number = l.invoice_number AND p.invoice_line_no = l.invoice_line_no
    GROUP BY 1, 2)
SELECT building_code, city, billed, arrears, round(arrears / nullif(billed, 0), 4) AS arrears_ratio,
       rank() OVER (ORDER BY arrears / nullif(billed, 0) DESC) AS arrears_rank
FROM building
ORDER BY arrears_rank, building_code;

-- ==========================================================================================================
-- Q3  How are overdue balances distributed across ageing buckets?
-- Grain:      ageing bucket, as of the window end (the last month-end snapshot)
-- Tables:     fact_rent_invoice_line, fact_payment, dim_date
-- Definition: per line, open balance = net amount - payments made by the snapshot day; a line is overdue when
--             it is past due (due before the day) with an open balance above 0. Days past due = snapshot day -
--             due date. Buckets 0-30, 31-60, 61-90, 90+ (the pack's KPI; the plan's "61 and over" is the last
--             two together). Credit lines and overpayments (balance 0 or below) are not overdue.
-- ==========================================================================================================
WITH w AS (SELECT window_end FROM lue_reporting.vw_reporting_window),
paid AS (
    SELECT p.invoice_number, p.invoice_line_no, sum(p.payment_amount) AS paid
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_date pd ON pd.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE p.paid_date_key > 0 AND pd.full_date <= w.window_end
    GROUP BY 1, 2),
open_line AS (
    SELECT w.window_end - d.full_date AS days_past_due, l.net_amount - coalesce(p.paid, 0) AS balance
    FROM lue_dw.fact_rent_invoice_line l
    JOIN lue_dw.dim_date d ON d.date_key = l.due_date_key
    CROSS JOIN w
    LEFT JOIN paid p ON p.invoice_number = l.invoice_number AND p.invoice_line_no = l.invoice_line_no
    WHERE l.due_date_key > 0 AND d.full_date < w.window_end),
bucketed AS (
    SELECT CASE WHEN days_past_due <= 30 THEN '0-30' WHEN days_past_due <= 60 THEN '31-60'
                WHEN days_past_due <= 90 THEN '61-90' ELSE '90+' END AS bucket,
           CASE WHEN days_past_due <= 30 THEN 1 WHEN days_past_due <= 60 THEN 2
                WHEN days_past_due <= 90 THEN 3 ELSE 4 END AS bucket_order,
           balance
    FROM open_line
    WHERE balance > 0)
SELECT bucket, count(*) AS overdue_lines, sum(balance) AS overdue_balance,
       round(sum(balance) / sum(sum(balance)) OVER (), 4) AS share_of_overdue
FROM bucketed
GROUP BY bucket, bucket_order
ORDER BY bucket_order;

-- ==========================================================================================================
-- Q4a Which tenants pay late repeatedly?
-- Grain:      tenant (tenant code), over the last 12 months of the window
-- Tables:     fact_payment, dim_tenant, dim_date
-- Definition: a payment is late when it was made more than 15 days after its due date (days_past_due > 15);
--             reversals are not payments. A repeat late payer has 3 or more late payments in the 12 months to
--             the window end. The sector is the tenant version's when it paid (fact_payment.tenant_key).
-- ==========================================================================================================
WITH w AS (SELECT window_end FROM lue_reporting.vw_reporting_window),
pay AS (
    SELECT t.tenant_code, t.tenant_name, t.tenant_type, t.employer_sector, p.payment_reference,
           max(p.days_past_due) AS days_past_due
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_tenant t ON t.tenant_key = p.tenant_key
    JOIN lue_dw.dim_date d ON d.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE NOT p.is_reversal AND p.paid_date_key > 0 AND d.full_date > w.window_end - interval '12 months'
    GROUP BY 1, 2, 3, 4, 5)
SELECT tenant_code, tenant_name, tenant_type, string_agg(DISTINCT employer_sector, ', ') AS employer_sector_when_paid,
       count(*) AS payments, count(*) FILTER (WHERE days_past_due > 15) AS late_payments,
       round(avg(days_past_due) FILTER (WHERE days_past_due > 15), 1) AS avg_days_late_when_late
FROM pay
GROUP BY tenant_code, tenant_name, tenant_type
HAVING count(*) FILTER (WHERE days_past_due > 15) >= 3
ORDER BY late_payments DESC, avg_days_late_when_late DESC, tenant_code;

-- ==========================================================================================================
-- Q4b Does late payment differ by employer sector at the time of payment?
-- Grain:      employer sector of the tenant version that paid, over the last 12 months of the window
-- Tables:     fact_payment, dim_tenant, dim_date
-- Definition: as Q4a; late share = late payments / payments; repeat late payers as in Q4a.
-- ==========================================================================================================
WITH w AS (SELECT window_end FROM lue_reporting.vw_reporting_window),
pay AS (
    SELECT t.tenant_code, t.employer_sector, p.payment_reference, max(p.days_past_due) AS days_past_due
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_tenant t ON t.tenant_key = p.tenant_key
    JOIN lue_dw.dim_date d ON d.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE NOT p.is_reversal AND p.paid_date_key > 0 AND d.full_date > w.window_end - interval '12 months'
    GROUP BY 1, 2, 3),
tenant AS (
    SELECT employer_sector, tenant_code, count(*) FILTER (WHERE days_past_due > 15) AS late
    FROM pay GROUP BY 1, 2)
SELECT p.employer_sector, count(*) AS payments, count(*) FILTER (WHERE p.days_past_due > 15) AS late_payments,
       round(count(*) FILTER (WHERE p.days_past_due > 15)::numeric / count(*), 4) AS late_share,
       (SELECT count(*) FROM tenant t WHERE t.employer_sector = p.employer_sector AND t.late >= 3) AS repeat_late_payers
FROM pay p
GROUP BY p.employer_sector
ORDER BY late_share DESC, p.employer_sector;

-- ==========================================================================================================
-- Q5  Which payment methods settle fastest after the due date?
-- Grain:      payment method (and its channel group), over the window
-- Tables:     fact_payment, dim_payment_method
-- Definition: settlement lag = days from the paid date to the settlement date (fact_payment.
--             settlement_lag_days, from the S3 settlement files: electronic methods only; cash and cheques
--             have no settlement file, so their lag is NULL); days past due = paid date - due date. One row per
--             payment allocation; reversals left out. Ranked by settlement lag, fastest first.
-- ==========================================================================================================
SELECT m.method_code, m.method_name, m.channel_group, count(*) AS allocations,
       count(p.settlement_lag_days) AS settled_allocations,
       round(avg(p.settlement_lag_days), 2) AS avg_settlement_lag_days,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY p.settlement_lag_days) AS median_settlement_lag_days,
       round(avg(p.days_past_due), 2) AS avg_days_past_due,
       round(avg(p.days_past_due + coalesce(p.settlement_lag_days, 0)) FILTER (WHERE p.settlement_lag_days IS NOT NULL), 2)
           AS avg_days_due_to_settled,
       rank() OVER (ORDER BY avg(p.settlement_lag_days) NULLS LAST) AS settlement_rank
FROM lue_dw.fact_payment p
JOIN lue_dw.dim_payment_method m ON m.payment_method_key = p.payment_method_key
WHERE NOT p.is_reversal
GROUP BY m.method_code, m.method_name, m.channel_group
ORDER BY settlement_rank, m.method_code;

-- ==========================================================================================================
-- Q6a How do occupancy and vacancy trend by city and unit type?
-- Grain:      month x city x unit type
-- Tables:     fact_unit_occupancy_daily, dim_unit, dim_date
-- Definition: occupancy = the monthly average of daily occupancy = occupied unit-days / unit-days (never a sum
--             of daily counts); vacancy = 1 - occupancy; average units = unit-days / days in the month.
--             Reconciles with mart_occupancy_monthly. LAG gives the change against the previous month.
-- ==========================================================================================================
WITH m AS (
    SELECT date_trunc('month', d.full_date)::date AS month, u.city, u.unit_type,
           count(*) AS unit_days, sum(f.is_occupied) AS occupied_days, count(DISTINCT d.full_date) AS days
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    GROUP BY 1, 2, 3)
SELECT to_char(month, 'YYYY-MM') AS month, city, unit_type, round(unit_days::numeric / days, 1) AS avg_units,
       round(occupied_days::numeric / days, 1) AS avg_occupied_units,
       round(occupied_days::numeric / unit_days, 4) AS occupancy_rate,
       round(1 - occupied_days::numeric / unit_days, 4) AS vacancy_rate,
       round(occupied_days::numeric / unit_days
             - lag(occupied_days::numeric / unit_days) OVER (PARTITION BY city, unit_type ORDER BY month), 4) AS change_vs_previous_month
FROM m
ORDER BY city, unit_type, month;

-- ==========================================================================================================
-- Q6b When do new tenants move in? (the seasonal side of the occupancy trend)
-- Grain:      calendar month (1 to 12), over the window
-- Tables:     dim_lease, lue_reporting.vw_reporting_window
-- Definition: a move-in is a new tenant's lease starting: a lease with no previous lease (a renewal keeps the
--             tenant in place, so it is not a move-in), counted by its start month inside the window. The index
--             is the month's move-ins over the average month's (1.00 = an average month).
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
move_in AS (
    SELECT extract(month FROM l.start_date)::int AS month_no, count(*) AS move_ins
    FROM lue_dw.dim_lease l
    CROSS JOIN w
    WHERE l.lease_key > 0 AND l.previous_lease_number IS NULL AND l.start_date BETWEEN w.window_start AND w.window_end
    GROUP BY 1)
SELECT m.month_no, trim(to_char(make_date(2000, m.month_no, 1), 'Month')) AS month_name, m.move_ins,
       round(m.move_ins / avg(m.move_ins) OVER (), 2) AS index_vs_average_month
FROM move_in m
ORDER BY m.month_no;

-- ==========================================================================================================
-- Q7  Which unit types stay vacant longest?
-- Grain:      unit type, over the window
-- Tables:     fact_unit_occupancy_daily, dim_unit, dim_date
-- Definition: gaps and islands: a vacancy spell is a run of consecutive vacant days of one unit.
--             CENSORING RULE: only completed spells count; a spell that begins on the window's first day
--             (it began earlier, its length is unknown) or is still open on its last day (it ends later) is
--             left out. Length = days in the spell.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
vacant AS (
    SELECT u.unit_nk, u.unit_type, d.full_date,
           d.full_date - (row_number() OVER (PARTITION BY u.unit_nk ORDER BY d.full_date))::int AS island
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    WHERE f.is_occupied = 0),
spell AS (
    SELECT unit_nk, min(unit_type) AS unit_type, min(full_date) AS first_day, max(full_date) AS last_day,
           count(*) AS days
    FROM vacant GROUP BY unit_nk, island)
SELECT s.unit_type, count(*) AS completed_spells, round(avg(s.days), 1) AS avg_vacancy_days,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY s.days) AS median_vacancy_days, max(s.days) AS longest_spell_days,
       rank() OVER (ORDER BY avg(s.days) DESC) AS longest_vacancy_rank
FROM spell s
CROSS JOIN w
WHERE s.first_day > w.window_start AND s.last_day < w.window_end
GROUP BY s.unit_type
ORDER BY longest_vacancy_rank;

-- ==========================================================================================================
-- Q8  What is the lease renewal rate, and which buildings lose tenants at renewal?
-- Grain:      building, over the window
-- Tables:     fact_lease_event, dim_lease_event_type, dim_lease, dim_unit, dim_date
-- Definition: renewal rate = renewed leases / leases that reached expiry. A lease reached expiry when its end
--             date falls in the window. It was renewed when a RENEW event (fact_lease_event) sits on its
--             successor lease (dim_lease.previous_lease_number). Lost at renewal = expired, not renewed. The
--             lease-link column counts successors whether or not their RENEW event survived quality checks
--             (some were quarantined as planted defects): the gap between the two is that rejection.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
renew AS (
    SELECT DISTINCT n.previous_lease_number AS lease_number
    FROM lue_dw.fact_lease_event f
    JOIN lue_dw.dim_lease_event_type t ON t.lease_event_type_key = f.lease_event_type_key
    JOIN lue_dw.dim_lease n ON n.lease_key = f.lease_key
    WHERE t.event_code = 'RENEW' AND n.previous_lease_number IS NOT NULL),
successor AS (SELECT DISTINCT previous_lease_number AS lease_number FROM lue_dw.dim_lease
              WHERE previous_lease_number IS NOT NULL),
lease_unit AS (  -- a lease's unit: the unit of its first event (each lease is on one unit)
    SELECT DISTINCT ON (f.lease_key) f.lease_key, f.unit_key
    FROM lue_dw.fact_lease_event f ORDER BY f.lease_key, f.event_date_key),
expired AS (
    SELECT l.lease_number, u.building_code, u.city, r.lease_number IS NOT NULL AS renewed,
           s.lease_number IS NOT NULL AS has_successor
    FROM lue_dw.dim_lease l
    CROSS JOIN w
    JOIN lease_unit lu ON lu.lease_key = l.lease_key
    JOIN lue_dw.dim_unit u ON u.unit_key = lu.unit_key
    LEFT JOIN renew r ON r.lease_number = l.lease_number
    LEFT JOIN successor s ON s.lease_number = l.lease_number
    WHERE l.lease_key > 0 AND l.end_date BETWEEN w.window_start AND w.window_end)
SELECT building_code, city, count(*) AS leases_expired, count(*) FILTER (WHERE renewed) AS renewed,
       round(count(*) FILTER (WHERE renewed)::numeric / count(*), 4) AS renewal_rate,
       count(*) FILTER (WHERE NOT renewed) AS lost_at_renewal,
       round(count(*) FILTER (WHERE has_successor)::numeric / count(*), 4) AS renewal_rate_lease_link,
       rank() OVER (ORDER BY count(*) FILTER (WHERE renewed)::numeric / count(*)) AS lowest_renewal_rank
FROM expired
GROUP BY building_code, city
ORDER BY lowest_renewal_rank, building_code;

-- ==========================================================================================================
-- Q9a What is the average time to resolve a request by category and vendor?
-- Grain:      maintenance category x vendor (code), resolved requests over the window
-- Tables:     fact_maintenance_request, dim_maintenance_category, dim_vendor
-- Definition: average days to resolve of the resolved requests; over SLA = days to resolve x 24 / the
--             subcategory's SLA hours (above 1 is late); the vendor's rating is the one valid when the request
--             was raised (SCD2). RANK within the category, slowest first.
-- ==========================================================================================================
SELECT c.category_name, v.vendor_code, v.vendor_name, string_agg(DISTINCT v.rating_band, '/') AS rating_when_raised,
       count(*) AS resolved_requests, round(avg(f.days_to_resolve), 2) AS avg_days_to_resolve,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY f.days_to_resolve * 24 / c.default_sla_hours)::numeric, 2)
           AS median_resolve_over_sla,
       rank() OVER (PARTITION BY c.category_name ORDER BY avg(f.days_to_resolve) DESC) AS slowest_in_category
FROM lue_dw.fact_maintenance_request f
JOIN lue_dw.dim_maintenance_category c ON c.maint_category_key = f.maint_category_key
JOIN lue_dw.dim_vendor v ON v.vendor_key = f.vendor_key
WHERE f.days_to_resolve IS NOT NULL AND f.vendor_key > 0
GROUP BY c.category_name, v.vendor_code, v.vendor_name
ORDER BY c.category_name, slowest_in_category, v.vendor_code;

-- ==========================================================================================================
-- Q9b Were low-rated vendors slower?
-- Grain:      vendor rating band at the time of the request (SCD2) x trade
-- Tables:     fact_maintenance_request, dim_vendor
-- Definition: as Q9a, by the rating band of the vendor version valid when the request was raised.
-- ==========================================================================================================
SELECT v.trade, v.rating_band AS rating_when_raised, count(*) AS resolved_requests,
       round(avg(f.days_to_resolve), 2) AS avg_days_to_resolve,
       round(avg(f.sla_breached_flag), 4) AS sla_breach_rate
FROM lue_dw.fact_maintenance_request f
JOIN lue_dw.dim_vendor v ON v.vendor_key = f.vendor_key
WHERE f.days_to_resolve IS NOT NULL AND f.vendor_key > 0
GROUP BY v.trade, v.rating_band
ORDER BY v.trade, v.rating_band;

-- ==========================================================================================================
-- Q10 Which buildings breach the maintenance SLA most often?
-- Grain:      building, resolved requests over the window
-- Tables:     fact_maintenance_request, dim_unit
-- Definition: SLA breach rate = SLA breaches / resolved requests (the pack's KPI).
-- ==========================================================================================================
SELECT u.building_code, u.city, count(*) AS resolved_requests, sum(f.sla_breached_flag) AS sla_breaches,
       round(sum(f.sla_breached_flag)::numeric / count(*), 4) AS sla_breach_rate,
       rank() OVER (ORDER BY sum(f.sla_breached_flag)::numeric / count(*) DESC) AS breach_rank
FROM lue_dw.fact_maintenance_request f
JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
WHERE f.days_to_resolve IS NOT NULL
GROUP BY u.building_code, u.city
ORDER BY breach_rank, u.building_code;

-- ==========================================================================================================
-- Q11 What is the maintenance cost per unit per month by building?
-- Grain:      building, over the window
-- Tables:     fact_maintenance_request, fact_unit_occupancy_daily, dim_unit, dim_date
-- Definition: actual cost / unit-months; unit-months = the building's units on each month's last day, summed
--             over the months (the pack's KPI).
-- ==========================================================================================================
WITH cost AS (
    SELECT u.building_code, count(*) AS requests, sum(f.actual_cost) AS actual_cost
    FROM lue_dw.fact_maintenance_request f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    GROUP BY 1),
unit_months AS (
    SELECT u.building_code, u.city, count(*) AS unit_months
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    WHERE f.snapshot_date_key IN (SELECT max(snapshot_date_key) FROM lue_dw.fact_unit_occupancy_daily
                                  GROUP BY snapshot_date_key / 100)
    GROUP BY 1, 2)
SELECT m.building_code, m.city, m.unit_months, coalesce(c.requests, 0) AS requests,
       coalesce(c.actual_cost, 0) AS actual_cost,
       round(coalesce(c.actual_cost, 0) / m.unit_months, 2) AS cost_per_unit_month,
       rank() OVER (ORDER BY coalesce(c.actual_cost, 0) / m.unit_months DESC) AS cost_rank
FROM unit_months m
LEFT JOIN cost c ON c.building_code = m.building_code
ORDER BY cost_rank, m.building_code;

-- ==========================================================================================================
-- Q12 What is the net operating income per owner portfolio?
-- Grain:      owner, over the window
-- Tables:     fact_payment, dim_charge_type, fact_maintenance_request, fact_unit_occupancy_daily, dim_owner,
--             dim_date, lue_reporting.vw_reporting_parameter
-- Definition: NOI = rent collected - actual maintenance cost - LUE management fee. Rent collected = payments
--             against charge type RENT only (late fees, utilities, service charges and credits left out).
--             FEE ASSUMPTION: the management fee is 8 percent of the rent collected (management_fee_rate in
--             lue_reporting.vw_reporting_parameter; the brief gives no rate). NOI margin = NOI / rent
--             collected. Units = units owned on the window's last day.
-- ==========================================================================================================
WITH w AS (SELECT window_end FROM lue_reporting.vw_reporting_window),
fee AS (SELECT value AS rate FROM lue_reporting.vw_reporting_parameter WHERE parameter = 'management_fee_rate'),
rent AS (
    SELECT p.owner_key, sum(p.payment_amount) AS rent_collected
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_charge_type c ON c.charge_type_key = p.charge_type_key
    WHERE c.charge_code = 'RENT' AND p.paid_date_key > 0
    GROUP BY 1),
cost AS (SELECT owner_key, sum(actual_cost) AS maintenance_cost FROM lue_dw.fact_maintenance_request GROUP BY 1),
units AS (
    SELECT f.owner_key, count(*) AS units
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    CROSS JOIN w
    WHERE d.full_date = w.window_end
    GROUP BY 1),
noi AS (
    SELECT o.owner_code, o.owner_name, o.owner_type, coalesce(u.units, 0) AS units_owned_at_end,
           coalesce(r.rent_collected, 0) AS rent_collected, coalesce(c.maintenance_cost, 0) AS maintenance_cost,
           round(coalesce(r.rent_collected, 0) * fee.rate, 2) AS management_fee
    FROM lue_dw.dim_owner o
    CROSS JOIN fee
    LEFT JOIN rent r ON r.owner_key = o.owner_key
    LEFT JOIN cost c ON c.owner_key = o.owner_key
    LEFT JOIN units u ON u.owner_key = o.owner_key
    WHERE r.owner_key IS NOT NULL OR c.owner_key IS NOT NULL OR u.owner_key IS NOT NULL)
SELECT owner_code, owner_name, owner_type, units_owned_at_end, rent_collected, maintenance_cost, management_fee,
       rent_collected - maintenance_cost - management_fee AS noi,
       round((rent_collected - maintenance_cost - management_fee) / nullif(rent_collected, 0), 4) AS noi_margin,
       rank() OVER (ORDER BY rent_collected - maintenance_cost - management_fee DESC) AS noi_rank
FROM noi
ORDER BY noi_rank, owner_code;

-- ==========================================================================================================
-- Q13 Do vacancy incentives shorten vacancy, and which offer type works best?
-- Grain:      offer type (and no offer), completed vacancy spells over the window
-- Tables:     fact_unit_occupancy_daily, fact_vacancy_incentive_coverage, dim_incentive, dim_unit, dim_date
-- Definition: completed vacancy spells as in Q7 (same censoring rule). A spell is covered when its unit had an
--             offer on at least one of its days (the coverage fact holds one row per vacant unit, day and
--             offer); its offer type is the one with the most days in the spell. COMPARISON GROUP: the spells
--             with no offer. Ratio = the group's average length / the no-offer average (below 1 = shorter).
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
vacant AS (
    SELECT u.unit_nk, d.full_date,
           d.full_date - (row_number() OVER (PARTITION BY u.unit_nk ORDER BY d.full_date))::int AS island
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    WHERE f.is_occupied = 0),
spell AS (
    SELECT s.unit_nk, s.first_day, s.last_day, s.days
    FROM (SELECT unit_nk, min(full_date) AS first_day, max(full_date) AS last_day, count(*) AS days
          FROM vacant GROUP BY unit_nk, island) s
    CROSS JOIN w
    WHERE s.first_day > w.window_start AND s.last_day < w.window_end),
offer AS (
    SELECT u.unit_nk, d.full_date, i.incentive_type
    FROM lue_dw.fact_vacancy_incentive_coverage c
    JOIN lue_dw.dim_unit u ON u.unit_key = c.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = c.coverage_date_key
    JOIN lue_dw.dim_incentive i ON i.incentive_key = c.incentive_key),
offer_days AS (  -- per spell and offer type, the days the unit had that offer
    SELECT s.unit_nk, s.first_day, o.incentive_type, count(*) AS days
    FROM spell s
    JOIN offer o ON o.unit_nk = s.unit_nk AND o.full_date BETWEEN s.first_day AND s.last_day
    GROUP BY 1, 2, 3),
main_offer AS (
    SELECT DISTINCT ON (unit_nk, first_day) unit_nk, first_day, incentive_type
    FROM offer_days ORDER BY unit_nk, first_day, days DESC, incentive_type),
typed AS (
    SELECT s.unit_nk, s.first_day, s.days, m.incentive_type AS offer_type
    FROM spell s
    LEFT JOIN main_offer m ON m.unit_nk = s.unit_nk AND m.first_day = s.first_day),
grouped AS (
    SELECT coalesce(offer_type, 'No offer') AS offer_group, count(*) AS completed_spells, avg(days) AS avg_days
    FROM typed GROUP BY 1
    UNION ALL
    SELECT 'Any offer', count(*), avg(days) FROM typed WHERE offer_type IS NOT NULL)
SELECT offer_group, completed_spells, round(avg_days, 1) AS avg_vacancy_days,
       round(avg_days / (SELECT avg_days FROM grouped WHERE offer_group = 'No offer'), 3) AS ratio_to_no_offer
FROM grouped
ORDER BY offer_group = 'No offer' DESC, offer_group = 'Any offer' DESC, avg_days;

-- ==========================================================================================================
-- Q14 Do leak and plumbing requests rise on heavy-rain days?
-- Grain:      day class (heavy rain or the day after, other days), over the window, all cities
-- Tables:     fact_maintenance_request, dim_maintenance_category, dim_weather, fact_unit_occupancy_daily,
--             dim_unit, dim_date
-- Definition: leak requests = subcategories PLB-LEAK (leak), CIV-SEEP (seepage), CIV-ROOF (roof leak).
--             RAIN THRESHOLD: a heavy-rain day has 10.0 mm of rain or more in the city (dim_weather, the
--             unit's city and the raised date); the day after one counts with it (water shows up late). Rate
--             = requests per 1,000 unit-days of that class. Ratio = heavy-rain rate / other days' rate.
-- ==========================================================================================================
WITH city_day AS (
    SELECT w.city, w.weather_date,
           (w.rainfall_mm >= 10.0 OR coalesce(y.rainfall_mm, 0) >= 10.0) AS heavy_rain
    FROM lue_dw.dim_weather w
    LEFT JOIN lue_dw.dim_weather y ON y.city = w.city AND y.weather_date = w.weather_date - 1
    WHERE w.weather_key > 0),
exposure AS (
    SELECT cd.heavy_rain, count(*) AS unit_days, count(DISTINCT (cd.city, cd.weather_date)) AS city_days
    FROM lue_dw.fact_unit_occupancy_daily f
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
    JOIN city_day cd ON cd.city = u.city AND cd.weather_date = d.full_date
    GROUP BY 1),
leaks AS (
    SELECT cd.heavy_rain, count(*) AS leak_requests
    FROM lue_dw.fact_maintenance_request f
    JOIN lue_dw.dim_maintenance_category c ON c.maint_category_key = f.maint_category_key
    JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = f.raised_date_key
    JOIN city_day cd ON cd.city = u.city AND cd.weather_date = d.full_date
    WHERE c.subcategory_code IN ('PLB-LEAK', 'CIV-SEEP', 'CIV-ROOF')
    GROUP BY 1),
rated AS (
    SELECT e.heavy_rain, e.city_days, e.unit_days, coalesce(l.leak_requests, 0) AS leak_requests,
           coalesce(l.leak_requests, 0) * 1000.0 / e.unit_days AS per_1000
    FROM exposure e LEFT JOIN leaks l ON l.heavy_rain = e.heavy_rain)
SELECT CASE WHEN heavy_rain THEN 'Heavy rain (10 mm or more) or the day after' ELSE 'Other days' END AS day_class,
       city_days, unit_days, leak_requests, round(per_1000, 4) AS leak_requests_per_1000_unit_days,
       round(per_1000 / nullif((SELECT per_1000 FROM rated WHERE NOT heavy_rain), 0), 2) AS ratio_to_other_days
FROM rated
ORDER BY heavy_rain DESC;

-- ==========================================================================================================
-- W1  RANK of buildings by arrears, within their city and overall (US-11.5)
-- Grain:      building, as of the window end
-- Tables:     lue_reporting.mart_collections_monthly, lue_reporting.vw_dim_building, lue_reporting.vw_dim_month
-- Definition: arrears at the last month end (the rule of Q2); DENSE_RANK in the city, RANK overall.
-- ==========================================================================================================
SELECT b.city, c.building_code, c.arrears_month_end AS arrears,
       dense_rank() OVER (PARTITION BY b.city ORDER BY c.arrears_month_end DESC) AS rank_in_city,
       rank() OVER (ORDER BY c.arrears_month_end DESC) AS rank_overall,
       round(c.arrears_month_end / sum(c.arrears_month_end) OVER (), 4) AS share_of_arrears
FROM lue_reporting.mart_collections_monthly c
JOIN lue_reporting.vw_dim_building b ON b.building_code = c.building_code
WHERE c.month_key = (SELECT max(month_key) FROM lue_reporting.vw_dim_month)
ORDER BY rank_overall, c.building_code;

-- ==========================================================================================================
-- W2  LAG growth in collections, month on month (US-11.5)
-- Grain:      month (the portfolio)
-- Tables:     lue_reporting.vw_monthly_collections
-- Definition: cash received and the cohort collection rate (D17), each against the previous month (LAG).
-- ==========================================================================================================
SELECT year_month, cash_received, lag(cash_received) OVER w AS previous_month,
       round((cash_received - lag(cash_received) OVER w) / nullif(lag(cash_received) OVER w, 0), 4) AS growth,
       collection_rate_cohort, round(collection_rate_cohort - lag(collection_rate_cohort) OVER w, 4) AS rate_change
FROM lue_reporting.vw_monthly_collections
WINDOW w AS (ORDER BY month_key)
ORDER BY month_key;

-- ==========================================================================================================
-- W3  Running total of cash received within each fiscal year (US-11.5)
-- Grain:      month (the portfolio), fiscal year July to June
-- Tables:     lue_reporting.vw_monthly_collections
-- Definition: SUM over the fiscal year's months so far; the year's share reached so far (none for a fiscal year
--             without cash, as in the small profile's early years).
-- ==========================================================================================================
SELECT fiscal_year_label, year_month, cash_received,
       sum(cash_received) OVER (PARTITION BY fiscal_year_label ORDER BY month_key) AS fiscal_year_to_date,
       round(sum(cash_received) OVER (PARTITION BY fiscal_year_label ORDER BY month_key)
             / nullif(sum(cash_received) OVER (PARTITION BY fiscal_year_label), 0), 4) AS share_of_fiscal_year
FROM lue_reporting.vw_monthly_collections
ORDER BY month_key;

-- ==========================================================================================================
-- W4  Three-month moving average of collections (US-11.5)
-- Grain:      month (the portfolio)
-- Tables:     lue_reporting.vw_monthly_collections
-- Definition: the average cash received of the month and the two before it; the cohort collection rate over
--             the same three months as a ratio of sums (collected / billed), not an average of rates.
-- ==========================================================================================================
SELECT year_month, cash_received,
       round(avg(cash_received) OVER m3, 2) AS cash_received_3m_avg,
       collection_rate_cohort,
       round(sum(collected_cohort) OVER m3 / nullif(sum(billed_due) OVER m3, 0), 4) AS collection_rate_3m,
       count(*) OVER m3 AS months_in_average
FROM lue_reporting.vw_monthly_collections
WINDOW m3 AS (ORDER BY month_key ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
ORDER BY month_key;
