-- US-6.5: dimension tests. Each query returns one row: the test and its violations (must be 0).
-- Run by scripts/test_dim_load.py; also runnable alone: psql -d lue_warehouse -f sql/90_tests/01_dimension_tests.sql
-- SCD2 dimensions: versions are half-open [effective_from, effective_to); 9999-12-31 while current.

SELECT 'dim_unit: surrogate key unique' AS test, count(*) - count(DISTINCT unit_key) AS violations FROM lue_dw.dim_unit
UNION ALL
SELECT 'dim_unit: no NULL key or natural key', count(*) FROM lue_dw.dim_unit WHERE unit_key IS NULL OR (unit_nk) IS NULL
UNION ALL
SELECT 'dim_unit: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_unit WHERE unit_key IN (-1, -2)
UNION ALL
SELECT 'dim_unit: exactly one current version per natural key', count(*) FROM (SELECT unit_nk FROM lue_dw.dim_unit GROUP BY unit_nk HAVING count(*) FILTER (WHERE is_current) <> 1) x
UNION ALL
SELECT 'dim_unit: first version starts 1900-01-01', count(*) FROM (SELECT unit_nk FROM lue_dw.dim_unit GROUP BY unit_nk HAVING min(effective_from) <> DATE '1900-01-01') x
UNION ALL
SELECT 'dim_unit: current version open to 9999-12-31, others closed', count(*) FROM lue_dw.dim_unit WHERE is_current <> (effective_to = DATE '9999-12-31')
UNION ALL
SELECT 'dim_unit: no gap or overlap between versions', count(*) FROM (SELECT effective_to, lead(effective_from) OVER (PARTITION BY unit_nk ORDER BY effective_from) AS next_from FROM lue_dw.dim_unit) x WHERE next_from IS NOT NULL AND next_from <> effective_to
UNION ALL
SELECT 'dim_tenant: surrogate key unique' AS test, count(*) - count(DISTINCT tenant_key) AS violations FROM lue_dw.dim_tenant
UNION ALL
SELECT 'dim_tenant: no NULL key or natural key', count(*) FROM lue_dw.dim_tenant WHERE tenant_key IS NULL OR (tenant_code) IS NULL
UNION ALL
SELECT 'dim_tenant: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_tenant WHERE tenant_key IN (-1, -2)
UNION ALL
SELECT 'dim_tenant: exactly one current version per natural key', count(*) FROM (SELECT tenant_code FROM lue_dw.dim_tenant GROUP BY tenant_code HAVING count(*) FILTER (WHERE is_current) <> 1) x
UNION ALL
SELECT 'dim_tenant: first version starts 1900-01-01', count(*) FROM (SELECT tenant_code FROM lue_dw.dim_tenant GROUP BY tenant_code HAVING min(effective_from) <> DATE '1900-01-01') x
UNION ALL
SELECT 'dim_tenant: current version open to 9999-12-31, others closed', count(*) FROM lue_dw.dim_tenant WHERE is_current <> (effective_to = DATE '9999-12-31')
UNION ALL
SELECT 'dim_tenant: no gap or overlap between versions', count(*) FROM (SELECT effective_to, lead(effective_from) OVER (PARTITION BY tenant_code ORDER BY effective_from) AS next_from FROM lue_dw.dim_tenant) x WHERE next_from IS NOT NULL AND next_from <> effective_to
UNION ALL
SELECT 'dim_vendor: surrogate key unique' AS test, count(*) - count(DISTINCT vendor_key) AS violations FROM lue_dw.dim_vendor
UNION ALL
SELECT 'dim_vendor: no NULL key or natural key', count(*) FROM lue_dw.dim_vendor WHERE vendor_key IS NULL OR (vendor_code) IS NULL
UNION ALL
SELECT 'dim_vendor: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_vendor WHERE vendor_key IN (-1, -2)
UNION ALL
SELECT 'dim_vendor: exactly one current version per natural key', count(*) FROM (SELECT vendor_code FROM lue_dw.dim_vendor GROUP BY vendor_code HAVING count(*) FILTER (WHERE is_current) <> 1) x
UNION ALL
SELECT 'dim_vendor: first version starts 1900-01-01', count(*) FROM (SELECT vendor_code FROM lue_dw.dim_vendor GROUP BY vendor_code HAVING min(effective_from) <> DATE '1900-01-01') x
UNION ALL
SELECT 'dim_vendor: current version open to 9999-12-31, others closed', count(*) FROM lue_dw.dim_vendor WHERE is_current <> (effective_to = DATE '9999-12-31')
UNION ALL
SELECT 'dim_vendor: no gap or overlap between versions', count(*) FROM (SELECT effective_to, lead(effective_from) OVER (PARTITION BY vendor_code ORDER BY effective_from) AS next_from FROM lue_dw.dim_vendor) x WHERE next_from IS NOT NULL AND next_from <> effective_to
UNION ALL
SELECT 'dim_maintenance_category: surrogate key unique' AS test, count(*) - count(DISTINCT maint_category_key) AS violations FROM lue_dw.dim_maintenance_category
UNION ALL
SELECT 'dim_maintenance_category: no NULL key or natural key', count(*) FROM lue_dw.dim_maintenance_category WHERE maint_category_key IS NULL OR (subcategory_code) IS NULL
UNION ALL
SELECT 'dim_maintenance_category: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_maintenance_category WHERE maint_category_key IN (-1, -2)
UNION ALL
SELECT 'dim_maintenance_category: exactly one current version per natural key', count(*) FROM (SELECT subcategory_code FROM lue_dw.dim_maintenance_category GROUP BY subcategory_code HAVING count(*) FILTER (WHERE is_current) <> 1) x
UNION ALL
SELECT 'dim_maintenance_category: first version starts 1900-01-01', count(*) FROM (SELECT subcategory_code FROM lue_dw.dim_maintenance_category GROUP BY subcategory_code HAVING min(effective_from) <> DATE '1900-01-01') x
UNION ALL
SELECT 'dim_maintenance_category: current version open to 9999-12-31, others closed', count(*) FROM lue_dw.dim_maintenance_category WHERE is_current <> (effective_to = DATE '9999-12-31')
UNION ALL
SELECT 'dim_maintenance_category: no gap or overlap between versions', count(*) FROM (SELECT effective_to, lead(effective_from) OVER (PARTITION BY subcategory_code ORDER BY effective_from) AS next_from FROM lue_dw.dim_maintenance_category) x WHERE next_from IS NOT NULL AND next_from <> effective_to
UNION ALL
SELECT 'dim_owner: surrogate key unique' AS test, count(*) - count(DISTINCT owner_key) AS violations FROM lue_dw.dim_owner
UNION ALL
SELECT 'dim_owner: no NULL key or natural key', count(*) FROM lue_dw.dim_owner WHERE owner_key IS NULL OR (owner_code) IS NULL
UNION ALL
SELECT 'dim_owner: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_owner WHERE owner_key IN (-1, -2)
UNION ALL
SELECT 'dim_owner: one row per natural key', count(*) - count(DISTINCT (owner_code)) FROM lue_dw.dim_owner
UNION ALL
SELECT 'dim_lease: surrogate key unique' AS test, count(*) - count(DISTINCT lease_key) AS violations FROM lue_dw.dim_lease
UNION ALL
SELECT 'dim_lease: no NULL key or natural key', count(*) FROM lue_dw.dim_lease WHERE lease_key IS NULL OR (lease_number) IS NULL
UNION ALL
SELECT 'dim_lease: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_lease WHERE lease_key IN (-1, -2)
UNION ALL
SELECT 'dim_lease: one row per natural key', count(*) - count(DISTINCT (lease_number)) FROM lue_dw.dim_lease
UNION ALL
SELECT 'dim_incentive: surrogate key unique' AS test, count(*) - count(DISTINCT incentive_key) AS violations FROM lue_dw.dim_incentive
UNION ALL
SELECT 'dim_incentive: no NULL key or natural key', count(*) FROM lue_dw.dim_incentive WHERE incentive_key IS NULL OR (incentive_code) IS NULL
UNION ALL
SELECT 'dim_incentive: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_incentive WHERE incentive_key IN (-1, -2)
UNION ALL
SELECT 'dim_incentive: one row per natural key', count(*) - count(DISTINCT (incentive_code)) FROM lue_dw.dim_incentive
UNION ALL
SELECT 'dim_weather: surrogate key unique' AS test, count(*) - count(DISTINCT weather_key) AS violations FROM lue_dw.dim_weather
UNION ALL
SELECT 'dim_weather: no NULL key or natural key', count(*) FROM lue_dw.dim_weather WHERE weather_key IS NULL OR (city || '|' || weather_date) IS NULL
UNION ALL
SELECT 'dim_weather: special members -1 and -2 present', 2 - count(*) FROM lue_dw.dim_weather WHERE weather_key IN (-1, -2)
UNION ALL
SELECT 'dim_weather: one row per natural key', count(*) - count(DISTINCT (city || '|' || weather_date)) FROM lue_dw.dim_weather
UNION ALL
SELECT 'dim_tenant: an inferred member has one version only', count(*) FROM (SELECT tenant_code FROM lue_dw.dim_tenant WHERE tenant_key > 0 GROUP BY tenant_code HAVING bool_or(is_inferred) AND count(*) > 1) x
UNION ALL
SELECT 'dim_unit: every hierarchy level populated', count(*) FROM lue_dw.dim_unit WHERE unit_key > 0 AND 'Unknown' IN (building_name, locality, city, region, building_age_band, unit_type)
UNION ALL
SELECT 'dim_date: holiday flags equal the S2 register', count(*) FROM lue_dw.dim_date d LEFT JOIN lue_staging.stg_holiday h ON h.holiday_date = d.full_date WHERE d.date_key > 0 AND (d.is_public_holiday, d.holiday_name, d.is_ramadan) IS DISTINCT FROM (coalesce(h.is_public_holiday, FALSE), h.holiday_name, coalesce(h.is_ramadan, FALSE))
ORDER BY 1;
