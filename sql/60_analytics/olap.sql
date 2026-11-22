-- sql/60_analytics/olap.sql: ROLLUP and CUBE with GROUPING() labels, and their verification (E11, US-11.4)
-- Runs in: lue_warehouse, as lue_etl; read-only.
--   psql -d lue_warehouse -v ON_ERROR_STOP=1 -f sql/60_analytics/olap.sql
-- The measure is the collected amount: payments with a paid date in the data window (cash received; reversals
-- net out), placed by the unit's location at the time of payment (its dim_unit version) and the method's
-- channel group. GROUPING() labels every subtotal row, so a subtotal is never mistaken for missing data.

-- ==========================================================================================================
-- O1  Collected amount with building, city, region and grand totals (ROLLUP)
-- Grain:      region > city > building (the brief's Region > Category > Product), plus every subtotal
-- Tables:     fact_payment, dim_unit, dim_date, lue_reporting.vw_reporting_window
-- Definition: GROUP BY ROLLUP (region, city, building_code); row_level and the "All ..." labels come from
--             GROUPING(); grouping_id = GROUPING(region, city, building_code) (0 a building, 1 a city
--             subtotal, 3 a region subtotal, 7 the grand total). Details first, then each subtotal.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
pay AS (
    SELECT u.region, u.city, u.building_code, p.payment_amount
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_unit u ON u.unit_key = p.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE p.paid_date_key > 0 AND d.full_date BETWEEN w.window_start AND w.window_end),
rolled AS (
    SELECT GROUPING(region) AS g_region, GROUPING(city) AS g_city, GROUPING(building_code) AS g_building,
           GROUPING(region, city, building_code) AS grouping_id, region, city, building_code,
           count(*) AS payment_rows, sum(payment_amount) AS collected
    FROM pay
    GROUP BY ROLLUP (region, city, building_code))
SELECT CASE WHEN g_region = 1 THEN 'Grand total'
            WHEN g_city = 1 THEN 'Region subtotal'
            WHEN g_building = 1 THEN 'City subtotal'
            ELSE 'Building' END AS row_level,
       CASE WHEN g_region = 1 THEN 'All regions' ELSE region END AS region,
       CASE WHEN g_city = 1 THEN 'All cities' ELSE city END AS city,
       CASE WHEN g_building = 1 THEN 'All buildings' ELSE building_code END AS building,
       grouping_id, payment_rows, collected,
       round(collected / sum(collected) FILTER (WHERE g_region = 1) OVER (), 4) AS share_of_total
FROM rolled
ORDER BY g_region, region, g_city, city, g_building, building_code;

-- ==========================================================================================================
-- O2  Collected amount by city and payment channel group, with every subtotal (CUBE)
-- Grain:      city x channel group (the brief's Region x Channel), every combination of subtotals
-- Tables:     fact_payment, dim_unit, dim_payment_method, dim_date, lue_reporting.vw_reporting_window
-- Definition: GROUP BY CUBE (city, channel_group); GROUPING() labels the rows: a city's total over every
--             channel, a channel's total over every city, and the grand total. Share = of the city's total.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
pay AS (
    SELECT u.city, m.channel_group, p.payment_amount
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_unit u ON u.unit_key = p.unit_key
    JOIN lue_dw.dim_payment_method m ON m.payment_method_key = p.payment_method_key
    JOIN lue_dw.dim_date d ON d.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE p.paid_date_key > 0 AND d.full_date BETWEEN w.window_start AND w.window_end),
cubed AS (
    SELECT GROUPING(city) AS g_city, GROUPING(channel_group) AS g_channel, city, channel_group,
           count(*) AS payment_rows, sum(payment_amount) AS collected
    FROM pay
    GROUP BY CUBE (city, channel_group))
SELECT CASE WHEN g_city = 1 AND g_channel = 1 THEN 'Grand total'
            WHEN g_city = 1 THEN 'Channel total (all cities)'
            WHEN g_channel = 1 THEN 'City total (all channels)'
            ELSE 'City x channel' END AS row_level,
       CASE WHEN g_city = 1 THEN 'All cities' ELSE city END AS city,
       CASE WHEN g_channel = 1 THEN 'All channels' ELSE channel_group END AS channel_group,
       g_city * 2 + g_channel AS grouping_id, payment_rows, collected,
       round(collected / sum(collected) FILTER (WHERE g_channel = 1) OVER (PARTITION BY g_city, city), 4)
           AS share_of_city
FROM cubed
ORDER BY g_city, city, g_channel, channel_group;

-- ==========================================================================================================
-- O3  Verification of O1 and O2: every subtotal equals the sum of its parts
-- Grain:      one row per check
-- Tables:     fact_payment, dim_unit, dim_payment_method, dim_date, lue_reporting.vw_reporting_window
-- Definition: the ROLLUP and the CUBE computed again; each check compares a subtotal with the plain sum of the
--             rows below it (or the base total of the payments). differing = rows whose difference is not
--             0; max_difference = the largest absolute difference. Every row must read 0 and 0.
-- ==========================================================================================================
WITH w AS (SELECT window_start, window_end FROM lue_reporting.vw_reporting_window),
pay AS (
    SELECT u.region, u.city, u.building_code, m.channel_group, p.payment_amount
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_unit u ON u.unit_key = p.unit_key
    JOIN lue_dw.dim_payment_method m ON m.payment_method_key = p.payment_method_key
    JOIN lue_dw.dim_date d ON d.date_key = p.paid_date_key
    CROSS JOIN w
    WHERE p.paid_date_key > 0 AND d.full_date BETWEEN w.window_start AND w.window_end),
base AS (SELECT sum(payment_amount) AS total FROM pay),
rolled AS (
    SELECT GROUPING(region, city, building_code) AS gid, region, city, building_code, sum(payment_amount) AS collected
    FROM pay GROUP BY ROLLUP (region, city, building_code)),
cubed AS (
    SELECT GROUPING(city, channel_group) AS gid, city, channel_group, sum(payment_amount) AS collected
    FROM pay GROUP BY CUBE (city, channel_group)),
diff AS (
    SELECT 'ROLLUP grand total = the base total of the payments' AS check_name, r.collected - b.total AS d
    FROM rolled r CROSS JOIN base b WHERE r.gid = 7
    UNION ALL
    SELECT 'ROLLUP region subtotal = the sum of its cities', r.collected - (SELECT sum(c.collected) FROM rolled c WHERE c.gid = 1 AND c.region = r.region)
    FROM rolled r WHERE r.gid = 3
    UNION ALL
    SELECT 'ROLLUP city subtotal = the sum of its buildings', r.collected - (SELECT sum(c.collected) FROM rolled c WHERE c.gid = 0 AND c.region = r.region AND c.city = r.city)
    FROM rolled r WHERE r.gid = 1
    UNION ALL
    SELECT 'ROLLUP grand total = the sum of the regions', r.collected - (SELECT sum(c.collected) FROM rolled c WHERE c.gid = 3)
    FROM rolled r WHERE r.gid = 7
    UNION ALL
    SELECT 'CUBE grand total = the base total of the payments', c.collected - b.total FROM cubed c CROSS JOIN base b WHERE c.gid = 3
    UNION ALL
    SELECT 'CUBE city total = the sum of its channels', c.collected - (SELECT sum(x.collected) FROM cubed x WHERE x.gid = 0 AND x.city = c.city)
    FROM cubed c WHERE c.gid = 1
    UNION ALL
    SELECT 'CUBE channel total = the sum of its cities', c.collected - (SELECT sum(x.collected) FROM cubed x WHERE x.gid = 0 AND x.channel_group = c.channel_group)
    FROM cubed c WHERE c.gid = 2
    UNION ALL
    SELECT 'CUBE city total = the ROLLUP city subtotal', c.collected - (SELECT sum(r.collected) FROM rolled r WHERE r.gid = 1 AND r.city = c.city)
    FROM cubed c WHERE c.gid = 1)
SELECT check_name, count(*) AS items_checked, count(*) FILTER (WHERE d <> 0) AS differing,
       coalesce(max(abs(d)), 0) AS max_difference
FROM diff
GROUP BY check_name
ORDER BY min(CASE WHEN check_name LIKE 'ROLLUP%' THEN 0 ELSE 1 END), check_name;
