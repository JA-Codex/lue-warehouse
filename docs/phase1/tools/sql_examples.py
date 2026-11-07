"""Example analytical SQL shown in the Business Questions document; each one is checked against the physical model."""

EXAMPLES = [
    ("Q1", "Collection rate by Region → City → Building with labelled subtotals (ROLLUP, drill-across)",
     "Invoice lines and payments are combined at the same conformed grain (unit, due date) before one ROLLUP, so "
     "billed and collected amounts are never double-counted.",
     """WITH lines AS (                       -- drill-across: two facts, one conformed grain
    SELECT i.unit_key, i.due_date_key, i.net_amount AS billed, 0::numeric AS collected
    FROM lue_dw.fact_rent_invoice_line i
    UNION ALL
    SELECT p.unit_key, p.due_date_key, 0, p.payment_amount
    FROM lue_dw.fact_payment p
)
SELECT CASE WHEN GROUPING(u.region) = 1        THEN 'Grand total'
            WHEN GROUPING(u.city) = 1          THEN 'Region subtotal'
            WHEN GROUPING(u.building_name) = 1 THEN 'City subtotal'
            ELSE 'Building' END                  AS row_type,
       u.region, u.city, u.building_name,
       SUM(l.billed)                             AS billed_pkr,
       SUM(l.collected)                          AS collected_pkr,
       ROUND(100 * SUM(l.collected) / NULLIF(SUM(l.billed), 0), 1) AS collection_rate_pct
FROM lines l
JOIN lue_dw.dim_unit u ON u.unit_key = l.unit_key
JOIN lue_dw.dim_date d ON d.date_key = l.due_date_key
WHERE d.year_no = 2026 AND d.month_no = 3
GROUP BY ROLLUP (u.region, u.city, u.building_name)
ORDER BY u.region NULLS LAST, u.city NULLS LAST, u.building_name NULLS LAST;"""),
    ("Q4", "Late payment by employer sector at the time of payment (SCD Type 2 point-in-time)",
     "fact_payment.tenant_key already points at the tenant version valid on the paid date, so a tenant who changed "
     "sector is counted under the sector they had when they paid. days_past_due is non-additive, so it is "
     "amount-weighted.",
     """SELECT t.employer_sector,
       COUNT(DISTINCT p.payment_reference)  AS payments,
       ROUND(SUM(p.days_past_due * p.payment_amount)
             / NULLIF(SUM(p.payment_amount), 0), 1) AS weighted_days_past_due,
       ROUND(100 * SUM(CASE WHEN p.days_past_due > 0 THEN p.payment_amount ELSE 0 END)
             / NULLIF(SUM(p.payment_amount), 0), 1) AS pct_amount_paid_late
FROM lue_dw.fact_payment p
JOIN lue_dw.dim_tenant t ON t.tenant_key = p.tenant_key   -- version valid on the paid date
JOIN lue_dw.dim_date   d ON d.date_key   = p.paid_date_key
WHERE d.fiscal_year_label = 'FY2025-26'
  AND NOT p.is_reversal
GROUP BY t.employer_sector
ORDER BY weighted_days_past_due DESC;"""),
    ("Q6", "Occupancy rate City × Unit type with every subtotal labelled (CUBE)",
     "is_occupied is semi-additive: summed across units and divided by unit-days, never summed across days on its own.",
     """SELECT CASE WHEN GROUPING(u.city) = 1 AND GROUPING(u.unit_type) = 1 THEN 'Grand total'
            WHEN GROUPING(u.city) = 1      THEN 'Unit type total (all cities)'
            WHEN GROUPING(u.unit_type) = 1 THEN 'City total (all unit types)'
            ELSE 'City x unit type' END     AS row_type,
       u.city, u.unit_type,
       ROUND(100.0 * SUM(o.is_occupied) / COUNT(*), 1) AS occupancy_rate_pct
FROM lue_dw.fact_unit_occupancy_daily o
JOIN lue_dw.dim_unit u ON u.unit_key = o.unit_key
JOIN lue_dw.dim_date d ON d.date_key = o.snapshot_date_key
WHERE d.fiscal_year_label = 'FY2025-26'
GROUP BY CUBE (u.city, u.unit_type)
ORDER BY GROUPING(u.city), GROUPING(u.unit_type), u.city, u.unit_type;"""),
    ("Q7", "Average vacancy spell by unit type (window functions on the daily snapshot)",
     "Consecutive vacant days are grouped into spells with the gaps-and-islands technique; this question cannot be "
     "answered from a monthly aggregate because the day-level sequence is lost.",
     """WITH days AS (
    SELECT u.unit_nk, u.unit_type, d.full_date, o.is_occupied,
           d.full_date - ROW_NUMBER() OVER (PARTITION BY u.unit_nk, o.is_occupied
                                            ORDER BY d.full_date)::int AS spell_id
    FROM lue_dw.fact_unit_occupancy_daily o
    JOIN lue_dw.dim_unit u ON u.unit_key = o.unit_key
    JOIN lue_dw.dim_date d ON d.date_key = o.snapshot_date_key
), spells AS (
    SELECT unit_nk, unit_type, spell_id, COUNT(*) AS vacant_days
    FROM days
    WHERE is_occupied = 0
    GROUP BY unit_nk, unit_type, spell_id
)
SELECT unit_type,
       COUNT(*)                                   AS vacancy_spells,
       ROUND(AVG(vacant_days), 1)                 AS avg_vacant_days,
       RANK() OVER (ORDER BY AVG(vacant_days) DESC) AS rank_longest
FROM spells
GROUP BY unit_type;"""),
    ("Q12", "Net operating income per owner (drill-across on conformed Owner and Date)",
     "Rent and maintenance cost come from different processes; each is aggregated to the owner first and only then "
     "combined. The management fee rate is a stated assumption (8% of rent collected).",
     """WITH rent AS (
    SELECT p.owner_key, SUM(p.payment_amount) AS rent_collected
    FROM lue_dw.fact_payment p
    JOIN lue_dw.dim_date d        ON d.date_key        = p.paid_date_key
    JOIN lue_dw.dim_charge_type c ON c.charge_type_key = p.charge_type_key
    WHERE d.fiscal_year_label = 'FY2025-26' AND c.charge_category = 'Rent'
    GROUP BY p.owner_key
), cost AS (
    SELECT m.owner_key, SUM(m.actual_cost) AS maintenance_cost
    FROM lue_dw.fact_maintenance_request m
    JOIN lue_dw.dim_date d ON d.date_key = m.resolved_date_key
    WHERE d.fiscal_year_label = 'FY2025-26'
    GROUP BY m.owner_key
)
SELECT o.owner_name,
       COALESCE(r.rent_collected, 0)                   AS rent_collected,
       COALESCE(c.maintenance_cost, 0)                 AS maintenance_cost,
       ROUND(0.08 * COALESCE(r.rent_collected, 0), 2)  AS lue_fee,
       ROUND(0.92 * COALESCE(r.rent_collected, 0) - COALESCE(c.maintenance_cost, 0), 2)
                                                       AS net_operating_income
FROM lue_dw.dim_owner o
LEFT JOIN rent r ON r.owner_key = o.owner_key
LEFT JOIN cost c ON c.owner_key = o.owner_key
WHERE o.owner_key > 0
ORDER BY net_operating_income DESC;"""),
]

GRAIN_CHECKS = {
    "fact_rent_invoice_line": """SELECT invoice_number, invoice_line_no, COUNT(*)
FROM lue_dw.fact_rent_invoice_line
GROUP BY invoice_number, invoice_line_no
HAVING COUNT(*) > 1;          -- must return no rows""",
    "fact_payment": """SELECT payment_reference, invoice_number, invoice_line_no, is_reversal, COUNT(*)
FROM lue_dw.fact_payment
GROUP BY payment_reference, invoice_number, invoice_line_no, is_reversal
HAVING COUNT(*) > 1;          -- must return no rows""",
    "fact_unit_occupancy_daily": """SELECT COUNT(*) AS actual_rows,
       (SELECT COUNT(DISTINCT unit_nk) FROM lue_dw.dim_unit WHERE unit_key > 0)
     * (SELECT COUNT(*) FROM lue_dw.dim_date
        WHERE date_key > 0 AND full_date <= CURRENT_DATE) AS expected_rows
FROM lue_dw.fact_unit_occupancy_daily;   -- every unit, every day: the two must match""",
    "fact_maintenance_request": """SELECT request_number, COUNT(*)
FROM lue_dw.fact_maintenance_request
GROUP BY request_number
HAVING COUNT(*) > 1;          -- one row per request for its whole life""",
    "fact_lease_event": """SELECT lease_key, lease_event_type_key, event_date_key, COUNT(*)
FROM lue_dw.fact_lease_event
GROUP BY lease_key, lease_event_type_key, event_date_key
HAVING COUNT(*) > 1;          -- must return no rows""",
    "fact_vacancy_incentive_coverage": """SELECT c.coverage_date_key, c.unit_key
FROM lue_dw.fact_vacancy_incentive_coverage c
JOIN lue_dw.fact_unit_occupancy_daily o
  ON o.snapshot_date_key = c.coverage_date_key AND o.unit_key = c.unit_key
WHERE o.is_occupied = 1;      -- offers exist only on vacant unit-days""",
}
