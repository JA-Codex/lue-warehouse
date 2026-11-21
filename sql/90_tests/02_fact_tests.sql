-- US-7.6: fact tests. Each query returns one row: the test and its violations (must be 0).
-- Run by etl/facts/run.py as its last step (fact_tests: one row per test in lue_audit.reconciliation, the step
-- fails on any violation) and by scripts/test_fact_load.py; also runnable alone:
--   psql -d lue_warehouse -f sql/90_tests/02_fact_tests.sql
-- Per fact: the grain (no duplicates); no orphan for each of the 41 foreign keys (a key with no dimension row; the
-- special members -1 and -2 are dimension rows, counted and reported separately by the run); impossible values.
-- A test name is at most 60 characters (lue_audit.reconciliation.check_name).

-- fact_rent_invoice_line
SELECT 'fact_rent_invoice_line: one row per invoice line (grain)' AS test, count(*) - count(DISTINCT (invoice_number, invoice_line_no)) AS violations FROM lue_dw.fact_rent_invoice_line
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan invoice_date_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.invoice_date_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan due_date_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.due_date_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan unit_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_unit d WHERE d.unit_key = f.unit_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan tenant_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_tenant d WHERE d.tenant_key = f.tenant_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan lease_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_lease d WHERE d.lease_key = f.lease_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan owner_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_owner d WHERE d.owner_key = f.owner_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no orphan charge_type_key', count(*) FROM lue_dw.fact_rent_invoice_line f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_charge_type d WHERE d.charge_type_key = f.charge_type_key)
UNION ALL
SELECT 'fact_rent_invoice_line: no negative amount', count(*) FROM lue_dw.fact_rent_invoice_line WHERE billed_amount < 0 OR tax_amount < 0 OR discount_amount < 0 OR net_amount < 0
UNION ALL
SELECT 'fact_rent_invoice_line: net = billed + tax - discount', count(*) FROM lue_dw.fact_rent_invoice_line WHERE net_amount <> billed_amount + tax_amount - discount_amount
UNION ALL
SELECT 'fact_rent_invoice_line: due on or after the invoice date', count(*) FROM lue_dw.fact_rent_invoice_line WHERE invoice_date_key > 0 AND due_date_key > 0 AND due_date_key < invoice_date_key
UNION ALL
SELECT 'fact_rent_invoice_line: line numbers from 1', count(*) FROM lue_dw.fact_rent_invoice_line WHERE invoice_line_no < 1
-- fact_payment
UNION ALL
SELECT 'fact_payment: one row per payment allocation (grain)', count(*) - count(DISTINCT (payment_reference, invoice_number, invoice_line_no)) FROM lue_dw.fact_payment
UNION ALL
SELECT 'fact_payment: no orphan paid_date_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.paid_date_key)
UNION ALL
SELECT 'fact_payment: no orphan due_date_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.due_date_key)
UNION ALL
SELECT 'fact_payment: no orphan unit_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_unit d WHERE d.unit_key = f.unit_key)
UNION ALL
SELECT 'fact_payment: no orphan tenant_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_tenant d WHERE d.tenant_key = f.tenant_key)
UNION ALL
SELECT 'fact_payment: no orphan lease_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_lease d WHERE d.lease_key = f.lease_key)
UNION ALL
SELECT 'fact_payment: no orphan owner_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_owner d WHERE d.owner_key = f.owner_key)
UNION ALL
SELECT 'fact_payment: no orphan payment_method_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_payment_method d WHERE d.payment_method_key = f.payment_method_key)
UNION ALL
SELECT 'fact_payment: no orphan charge_type_key', count(*) FROM lue_dw.fact_payment f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_charge_type d WHERE d.charge_type_key = f.charge_type_key)
UNION ALL
SELECT 'fact_payment: a receipt is positive, a reversal negative', count(*) FROM lue_dw.fact_payment WHERE payment_amount = 0 OR is_reversal <> (payment_amount < 0)
UNION ALL
SELECT 'fact_payment: days past due = paid date - due date', count(*) FROM lue_dw.fact_payment f JOIN lue_dw.dim_date p ON p.date_key = f.paid_date_key JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key WHERE f.paid_date_key > 0 AND f.due_date_key > 0 AND f.days_past_due <> p.full_date - d.full_date
UNION ALL
SELECT 'fact_payment: settlement lag not negative', count(*) FROM lue_dw.fact_payment WHERE settlement_lag_days < 0
UNION ALL
SELECT 'fact_payment: every allocation is to a loaded invoice line', count(*) FROM lue_dw.fact_payment p WHERE NOT EXISTS (SELECT 1 FROM lue_dw.fact_rent_invoice_line i WHERE i.invoice_number = p.invoice_number AND i.invoice_line_no = p.invoice_line_no)
UNION ALL
SELECT 'fact_payment: no invoice line paid more than its net', count(*) FROM (SELECT p.invoice_number, p.invoice_line_no, sum(p.payment_amount) AS paid, max(i.net_amount) AS net FROM lue_dw.fact_payment p JOIN lue_dw.fact_rent_invoice_line i ON i.invoice_number = p.invoice_number AND i.invoice_line_no = p.invoice_line_no GROUP BY 1, 2) x WHERE paid > net
-- fact_unit_occupancy_daily
UNION ALL
SELECT 'fact_unit_occupancy_daily: one row per unit and day (grain)', count(*) - count(DISTINCT (f.snapshot_date_key, u.unit_nk)) FROM lue_dw.fact_unit_occupancy_daily f JOIN lue_dw.dim_unit u USING (unit_key)
UNION ALL
SELECT 'fact_unit_occupancy_daily: no orphan snapshot_date_key', count(*) FROM lue_dw.fact_unit_occupancy_daily f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.snapshot_date_key)
UNION ALL
SELECT 'fact_unit_occupancy_daily: no orphan unit_key', count(*) FROM lue_dw.fact_unit_occupancy_daily f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_unit d WHERE d.unit_key = f.unit_key)
UNION ALL
SELECT 'fact_unit_occupancy_daily: no orphan tenant_key', count(*) FROM lue_dw.fact_unit_occupancy_daily f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_tenant d WHERE d.tenant_key = f.tenant_key)
UNION ALL
SELECT 'fact_unit_occupancy_daily: no orphan lease_key', count(*) FROM lue_dw.fact_unit_occupancy_daily f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_lease d WHERE d.lease_key = f.lease_key)
UNION ALL
SELECT 'fact_unit_occupancy_daily: no orphan owner_key', count(*) FROM lue_dw.fact_unit_occupancy_daily f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_owner d WHERE d.owner_key = f.owner_key)
UNION ALL
SELECT 'fact_unit_occupancy_daily: every day inside the data window', count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE snapshot_date_key NOT BETWEEN 20230701 AND 20260630
UNION ALL
SELECT 'fact_unit_occupancy_daily: every day holds every unit once', count(*) FROM (SELECT snapshot_date_key FROM lue_dw.fact_unit_occupancy_daily GROUP BY 1 HAVING count(*) <> (SELECT count(*) FROM lue_staging.stg_unit)) x
UNION ALL
SELECT 'fact_unit_occupancy_daily: is_occupied is 0 or 1', count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE is_occupied NOT IN (0, 1)
UNION ALL
SELECT 'fact_unit_occupancy_daily: no negative rent or arrears', count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE contract_rent < 0 OR current_lease_arrears < 0
UNION ALL
SELECT 'fact_unit_occupancy_daily: vacant: keys -2, rent, arrears 0', count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE is_occupied = 0 AND (tenant_key <> -2 OR lease_key <> -2 OR contract_rent <> 0 OR current_lease_arrears <> 0)
UNION ALL
SELECT 'fact_unit_occupancy_daily: occupied = a tenant and a lease', count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE is_occupied = 1 AND (tenant_key = -2 OR lease_key = -2)
-- fact_maintenance_request
UNION ALL
SELECT 'fact_maintenance_request: one row per request (grain)', count(*) - count(DISTINCT request_number) FROM lue_dw.fact_maintenance_request
UNION ALL
SELECT 'fact_maintenance_request: no orphan raised_date_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.raised_date_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan assigned_date_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.assigned_date_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan resolved_date_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.resolved_date_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan verified_date_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.verified_date_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan unit_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_unit d WHERE d.unit_key = f.unit_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan tenant_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_tenant d WHERE d.tenant_key = f.tenant_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan owner_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_owner d WHERE d.owner_key = f.owner_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan maint_category_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_maintenance_category d WHERE d.maint_category_key = f.maint_category_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan vendor_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_vendor d WHERE d.vendor_key = f.vendor_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan request_flags_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_request_flags d WHERE d.request_flags_key = f.request_flags_key)
UNION ALL
SELECT 'fact_maintenance_request: no orphan weather_key', count(*) FROM lue_dw.fact_maintenance_request f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_weather d WHERE d.weather_key = f.weather_key)
UNION ALL
SELECT 'fact_maintenance_request: no negative duration or cost', count(*) FROM lue_dw.fact_maintenance_request WHERE days_to_assign < 0 OR days_to_resolve < 0 OR days_to_verify < 0 OR estimated_cost < 0 OR actual_cost < 0
UNION ALL
SELECT 'fact_maintenance_request: milestone dates in order', count(*) FROM lue_dw.fact_maintenance_request WHERE (assigned_date_key > 0 AND assigned_date_key < raised_date_key) OR (resolved_date_key > 0 AND resolved_date_key < assigned_date_key) OR (verified_date_key > 0 AND verified_date_key < resolved_date_key)
UNION ALL
SELECT 'fact_maintenance_request: status matches its milestones', count(*) FROM lue_dw.fact_maintenance_request WHERE request_status <> CASE WHEN verified_date_key > 0 THEN 'Verified' WHEN resolved_date_key > 0 THEN 'Resolved' WHEN assigned_date_key > 0 THEN 'Assigned' ELSE 'Raised' END
UNION ALL
SELECT 'fact_maintenance_request: no milestone skipped', count(*) FROM lue_dw.fact_maintenance_request WHERE (resolved_date_key <> -2 AND assigned_date_key = -2) OR (verified_date_key <> -2 AND resolved_date_key = -2)
UNION ALL
SELECT 'fact_maintenance_request: vendor -2 exactly until assigned', count(*) FROM lue_dw.fact_maintenance_request WHERE (vendor_key = -2) <> (assigned_date_key = -2)
UNION ALL
SELECT 'fact_maintenance_request: SLA flag 0/1 if resolved, or NULL', count(*) FROM lue_dw.fact_maintenance_request WHERE (resolved_date_key = -2 AND sla_breached_flag IS NOT NULL) OR (resolved_date_key <> -2 AND sla_breached_flag NOT IN (0, 1))
-- fact_lease_event
UNION ALL
SELECT 'fact_lease_event: one row per lease, type and date (grain)', count(*) - count(DISTINCT (lease_key, lease_event_type_key, event_date_key)) FROM lue_dw.fact_lease_event
UNION ALL
SELECT 'fact_lease_event: no orphan event_date_key', count(*) FROM lue_dw.fact_lease_event f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.event_date_key)
UNION ALL
SELECT 'fact_lease_event: no orphan unit_key', count(*) FROM lue_dw.fact_lease_event f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_unit d WHERE d.unit_key = f.unit_key)
UNION ALL
SELECT 'fact_lease_event: no orphan tenant_key', count(*) FROM lue_dw.fact_lease_event f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_tenant d WHERE d.tenant_key = f.tenant_key)
UNION ALL
SELECT 'fact_lease_event: no orphan lease_key', count(*) FROM lue_dw.fact_lease_event f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_lease d WHERE d.lease_key = f.lease_key)
UNION ALL
SELECT 'fact_lease_event: no orphan owner_key', count(*) FROM lue_dw.fact_lease_event f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_owner d WHERE d.owner_key = f.owner_key)
UNION ALL
SELECT 'fact_lease_event: no orphan lease_event_type_key', count(*) FROM lue_dw.fact_lease_event f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_lease_event_type d WHERE d.lease_event_type_key = f.lease_event_type_key)
UNION ALL
SELECT 'fact_lease_event: event_count is 1', count(*) FROM lue_dw.fact_lease_event WHERE event_count <> 1
-- fact_vacancy_incentive_coverage
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: one row per key (grain)', count(*) - count(DISTINCT (coverage_date_key, unit_key, incentive_key)) FROM lue_dw.fact_vacancy_incentive_coverage
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: no orphan coverage_date_key', count(*) FROM lue_dw.fact_vacancy_incentive_coverage f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_date d WHERE d.date_key = f.coverage_date_key)
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: no orphan unit_key', count(*) FROM lue_dw.fact_vacancy_incentive_coverage f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_unit d WHERE d.unit_key = f.unit_key)
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: no orphan incentive_key', count(*) FROM lue_dw.fact_vacancy_incentive_coverage f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_incentive d WHERE d.incentive_key = f.incentive_key)
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: no orphan owner_key', count(*) FROM lue_dw.fact_vacancy_incentive_coverage f WHERE NOT EXISTS (SELECT 1 FROM lue_dw.dim_owner d WHERE d.owner_key = f.owner_key)
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: only on vacant unit-days', count(*) FROM lue_dw.fact_vacancy_incentive_coverage c JOIN lue_dw.fact_unit_occupancy_daily o ON o.snapshot_date_key = c.coverage_date_key AND o.unit_key = c.unit_key WHERE o.is_occupied = 1
UNION ALL
SELECT 'fact_vacancy_incentive_coverage: days inside the data window', count(*) FROM lue_dw.fact_vacancy_incentive_coverage WHERE coverage_date_key NOT BETWEEN 20230701 AND 20260630
ORDER BY 1;
