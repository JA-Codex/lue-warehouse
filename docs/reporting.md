# The reporting layer (`lue_reporting`, E10)

Everything Power BI and the analysts read, in one schema, built by `sql/50_reporting/01_reporting.sql`
(deployed by `scripts/db_deploy.py`; the marts refreshed by the pipeline's last stage, `marts`, or
`python etl/reporting.py`). `lue_reader` reads every object here and nothing else (US-10.3).
`scripts/test_reporting_contract.py` (CI) fails if a column of an object below is missing from this page.

## Definitions

| Measure | Definition | Where |
|---|---|---|
| Collection rate (cohort, D17) | Payments against the invoice lines **due** in month M, as of the window end, divided by the net amount of the lines due in M | `collection_rate_cohort`; DAX Collection Rate = SUM(collected_cohort) / SUM(billed_due) |
| Cash received | Payments with a **paid** date in month M; a separate, labelled measure | `cash_received` |
| Arrears on day D | Net amount of the lines past due on D (due before D) minus the payments against them made by D; a payment made before the due date counts from the day after it. The rule of `fact_unit_occupancy_daily.current_lease_arrears` | `arrears_month_end`, `current_arrears` |
| Occupancy rate | Occupied unit-days / unit-days: the average of daily occupied units over units, never a sum of daily counts | `occupancy_rate`; DAX = SUM(occupied_days) / SUM(unit_days) |
| Average vacancy days (pack KPI) | Vacant unit-days / completed vacancy spells; a spell is completed when the unit is let again inside the window | `avg_vacancy_days` |
| Maintenance cost per unit-month (pack KPI) | Actual cost / unit-months (the units at each month end, summed over the months) | `maintenance_cost_per_unit_month` |
| Average days to resolve | Days to resolve of the resolved requests / resolved requests | `avg_days_to_resolve` |
| SLA breach rate | SLA breaches / resolved requests | `sla_breach_rate` |
| NOI per owner (Q12) | Rent collected (charge type RENT, by paid month) - actual maintenance cost (by raised month) - management fee (rent collected x `management_fee_rate`, an assumption: 8 percent) | `noi` |
| Payer segment | No payments; On time (no late payment); Chronically late (late in half or more of its payments, `chronically_late_from`); Occasionally late (the rest) | `payer_segment` |

**Reading the cohort rate.** It is measured as of the window end, so the latest months read lower: their lines
have had the least time to be paid (full profile: June 2026 88 percent, against about 94 percent a few months
earlier). Compare months of the same age, or read cash received for the most recent month.

**Additivity.** The marts store additive parts only, so a rate is always a ratio of sums, right at any level
(building, city, month, year). Month-end values (`*_month_end`, `active_leases`) are semi-additive: sum them across
buildings, owners or unit types, never across months.

**The window.** The data window is the occupancy snapshot's first to last day (`vw_reporting_window`): 2023-07-01
to 2026-06-30 on the full profile. Months are its calendar months; a line due after the window end is not billed
in it.

**Special members.** A fact row whose dimension is unknown (-1) or not applicable (-2) is kept and shows the
member's text (`Unknown`, `N/A`), so every total equals the facts.

## Parameters

### `vw_reporting_window`: the data window (one row)

| Column | Definition |
|---|---|
| `window_start` | First day of the occupancy snapshot |
| `window_end` | Last day of the occupancy snapshot; "as of" for the cohort collection rate and current arrears |

### `vw_reporting_parameter`: the stated assumptions

| Column | Definition |
|---|---|
| `parameter` | `management_fee_rate` (0.08), `occasionally_late_from` (0), `chronically_late_from` (0.50) |
| `value` | The value used by the marts and views |
| `note` | What it is and where it is used |

## Slicer views (`vw_dim_*`)

The dimensions without their technical columns (`source_system`, `batch_id`, `loaded_at`). Keys are kept for the
relationships (hide them in Power BI). The SCD Type 2 slicers (unit, tenant, vendor, maintenance category) have one
row per version: a mart or view row points at the version that was valid at the time.

### `vw_dim_date`: one row per day (the date table)

| Column | Definition |
|---|---|
| `date_key` | YYYYMMDD; -1 Unknown, -2 Not applicable |
| `full_date` | The date (mark as the date table on this column) |
| `day_of_month` | 1 to 31 |
| `day_name` | Monday to Sunday |
| `is_weekend` | Saturday or Sunday |
| `week_of_year` | ISO week |
| `month_no` | 1 to 12 |
| `month_name` | January to December |
| `quarter_no` | Calendar quarter 1 to 4 |
| `year_no` | Calendar year |
| `year_month` | `YYYY-MM` |
| `fiscal_month_no` | 1 (July) to 12 (June) |
| `fiscal_quarter_no` | Fiscal quarter 1 to 4 |
| `fiscal_year_label` | `FY2025-26` (July to June) |
| `is_public_holiday` | A public holiday in Pakistan (S2 register) |
| `holiday_name` | Its name, when it is one |
| `is_ramadan` | A day of Ramadan |

### `vw_dim_month`: one row per month of the window

| Column | Definition |
|---|---|
| `month_key` | The date key of the month's first day (the marts' month key) |
| `month_start` | First day of the month |
| `month_end` | Last day of the month, or the window end in the last month |
| `year_month` | `YYYY-MM` |
| `month_no` | 1 to 12 |
| `month_name` | January to December |
| `quarter_no` | Calendar quarter |
| `year_no` | Calendar year |
| `fiscal_month_no` | 1 (July) to 12 (June) |
| `fiscal_quarter_no` | Fiscal quarter |
| `fiscal_year_label` | `FY2025-26` |

### `vw_dim_building`: one row per building (the location hierarchy above the unit)

| Column | Definition |
|---|---|
| `building_code` | Building natural key (`GLB01`) |
| `building_name` | Name |
| `building_class` | A, B or C |
| `building_age_band` | Age band of the building |
| `locality` | Area of the city |
| `city` | Lahore, Karachi, Islamabad, Faisalabad |
| `region` | Province (Punjab, Sindh) or Islamabad Capital Territory |

### `vw_dim_unit`: one row per unit version (Unit, Floor, Building, Locality, City, Region)

| Column | Definition |
|---|---|
| `unit_key` | Surrogate key of the version |
| `unit_nk` | `building_code-unit_no` |
| `building_code` | Building |
| `unit_no` | Unit number in the building |
| `unit_type` | Apartment, Office, Shop |
| `bedrooms` | 1 to 4 for apartments, 0 otherwise |
| `area_sqft` | Floor area |
| `furnished_flag` | Let furnished |
| `floor_no` | Floor |
| `building_name` | Building name |
| `building_class` | A, B or C |
| `building_age_band` | Age band |
| `locality` | Area of the city |
| `city` | City |
| `region` | Region |
| `effective_from` | First day of the version |
| `effective_to` | Day after its last day (9999-12-31 while current) |
| `is_current` | The current version |

### `vw_dim_unit_type`: one row per unit type

One slicer for the occupancy and maintenance marts and `vw_unit_performance` together (all three carry
`unit_type`); the dashboard's model relates it to each (docs/powerbi).

| Column | Definition |
|---|---|
| `unit_type` | Apartment, Office, Shop (and the special members `Unknown`, `Not applicable`) |
| `current_units` | Units of the type today (current versions) |

### `vw_dim_tenant`: one row per tenant version (Tenant, Tenant type)

| Column | Definition |
|---|---|
| `tenant_key` | Surrogate key of the version |
| `tenant_code` | `T-0001` |
| `tenant_name` | Name |
| `tenant_type` | Individual or Corporate (Type 2) |
| `employer_sector` | Sector at the time (Unknown when missing) |
| `contact_channel` | Preferred channel |
| `is_inferred` | Created from a reference before its record arrived (US-6.5) |
| `effective_from` | First day of the version |
| `effective_to` | Day after its last day |
| `is_current` | The current version |

### `vw_dim_owner`: one row per owner (Owner, Owner type)

| Column | Definition |
|---|---|
| `owner_key` | Surrogate key |
| `owner_code` | Owner natural key |
| `owner_name` | Name |
| `owner_type` | Individual or Company |
| `portfolio_size_band` | Band of the number of units owned |

### `vw_dim_vendor`: one row per vendor version (Vendor, Trade)

| Column | Definition |
|---|---|
| `vendor_key` | Surrogate key of the version |
| `vendor_code` | Vendor natural key |
| `vendor_name` | Name |
| `trade` | Plumbing, Electrical, HVAC, Civil, Pest control, General maintenance |
| `rating_band` | A, B or C at the time (Type 2) |
| `phone` | Contact number |
| `effective_from` | First day of the version |
| `effective_to` | Day after its last day |
| `is_current` | The current version |

### `vw_dim_maintenance_category`: one row per subcategory version (Subcategory, Category)

| Column | Definition |
|---|---|
| `maint_category_key` | Surrogate key of the version |
| `subcategory_code` | Subcategory natural key |
| `subcategory_name` | Name |
| `category_name` | Category above it |
| `default_sla_hours` | SLA at the time (Type 2) |
| `effective_from` | First day of the version |
| `effective_to` | Day after its last day |
| `is_current` | The current version |

### `vw_dim_payment_method`: one row per method (Method, Channel group)

| Column | Definition |
|---|---|
| `payment_method_key` | Surrogate key |
| `method_code` | `CASH`, `CHEQUE`, `BANK`, `RAAST`, `JAZZ`, `EASY` |
| `method_name` | Name |
| `channel_group` | Channel group |
| `typical_settlement_days` | Days a payment usually takes to settle |

## The marts (US-10.2)

### `mart_collections_monthly`: one row per month and building

| Column | Definition |
|---|---|
| `month_key` | Month (`vw_dim_month`, `vw_dim_date`) |
| `month_start` | First day of the month |
| `building_code` | Building (`vw_dim_building`) |
| `invoice_lines` | Invoice lines due in the month |
| `billed_due` | Net amount of the lines due in the month |
| `collected_cohort` | Payments against those lines, as of the window end (D17) |
| `cash_received` | Payments with a paid date in the month |
| `arrears_month_end` | Arrears on the month's last day (semi-additive) |

### `mart_occupancy_monthly`: one row per month, building and unit type

| Column | Definition |
|---|---|
| `month_key` | Month |
| `month_start` | First day of the month |
| `building_code` | Building |
| `unit_type` | Unit type of the unit version on the day |
| `unit_days` | Units x days in the month |
| `occupied_days` | Occupied unit-days |
| `vacant_days` | Vacant unit-days |
| `completed_vacancy_spells` | Vacancy spells that ended in the month (the unit let again) |
| `active_leases` | Leases with an occupied day in the month (semi-additive) |
| `units_month_end` | Units on the month's last day (semi-additive) |
| `occupied_units_month_end` | Occupied units on the month's last day (semi-additive) |
| `rent_roll_month_end` | Sum of contract rent on the month's last day (semi-additive) |
| `arrears_month_end` | Sum of the occupied leases' arrears on the month's last day (semi-additive) |

### `mart_maintenance_monthly`: one row per raised month, building, unit type, category and vendor

| Column | Definition |
|---|---|
| `month_key` | Month the request was raised |
| `month_start` | First day of the month |
| `building_code` | Building |
| `unit_type` | Unit type |
| `maint_category_key` | Subcategory version when raised (`vw_dim_maintenance_category`) |
| `vendor_key` | Vendor version when raised (`vw_dim_vendor`); -1 when no vendor was assigned |
| `requests` | Requests raised |
| `resolved_requests` | Of those, resolved |
| `days_to_resolve_sum` | Sum of days to resolve of the resolved requests (with hours) |
| `sla_breached` | Resolved requests that breached the SLA |
| `estimated_cost` | Estimated cost |
| `actual_cost` | Actual cost |

### `mart_owner_portfolio_monthly`: one row per month and owner

| Column | Definition |
|---|---|
| `month_key` | Month |
| `month_start` | First day of the month |
| `owner_key` | Owner (`vw_dim_owner`) |
| `rent_collected` | Payments of rent charges (`RENT`) paid in the month |
| `cash_received` | All payments paid in the month |
| `maintenance_requests` | Requests raised in the month on the owner's units |
| `maintenance_cost` | Their actual cost |
| `management_fee_rate` | The fee rate (`vw_reporting_parameter`) |
| `management_fee` | Rent collected x fee rate |
| `noi` | Rent collected - maintenance cost - management fee |
| `unit_days` | Unit-days owned |
| `occupied_days` | Occupied unit-days owned |
| `units_month_end` | Units owned on the month's last day (semi-additive) |

## The brief's three reporting views (US-10.1)

### `vw_monthly_collections` (alias `vw_monthly_sales`): one row per month

| Column | Definition |
|---|---|
| `month_key` | Month |
| `year_month` | `YYYY-MM` |
| `fiscal_year_label` | Fiscal year |
| `fiscal_quarter_no` | Fiscal quarter |
| `invoice_lines` | Lines due in the month |
| `billed_due` | Net amount due in the month |
| `collected_cohort` | Payments against the lines due in the month (D17) |
| `collection_rate_cohort` | `collected_cohort / billed_due` (D17) |
| `cash_received` | Payments paid in the month |
| `arrears_month_end` | Arrears on the month's last day |
| `billed_growth` | Change in `billed_due` against the previous month (LAG), as a fraction |
| `cash_received_growth` | Change in `cash_received` against the previous month (LAG), as a fraction |

### `vw_tenant_analysis` (alias `vw_customer_analysis`): one row per tenant version

The tenant as it was when it paid (payments) or was billed (arrears): group by `tenant_code` for a tenant, by
`employer_sector` for the sector at the time of payment (Q4).

| Column | Definition |
|---|---|
| `tenant_key` | Tenant version (`vw_dim_tenant`) |
| `tenant_code` | Tenant |
| `tenant_name` | Name |
| `tenant_type` | Type of the version |
| `employer_sector` | Sector of the version |
| `is_current` | The current version |
| `payments` | Payments made (reversals not counted) |
| `late_payments` | Of those, made after the due date |
| `late_payment_share` | `late_payments / payments` |
| `avg_days_past_due` | Days past due, weighted by amount (reversals left out) |
| `total_collected` | Payments, reversals netted |
| `current_arrears` | Arrears at the window end on the lines billed to this version |
| `payer_segment` | No payments, On time, Occasionally late, Chronically late |

### `vw_unit_performance` (alias `vw_product_performance`): one row per building and unit type, over the window

| Column | Definition |
|---|---|
| `building_code` | Building |
| `building_name` | Name |
| `city` | City |
| `building_class` | A, B or C |
| `unit_type` | Unit type |
| `units` | Units at the window end |
| `unit_days` | Unit-days |
| `occupied_days` | Occupied unit-days |
| `occupancy_rate` | `occupied_days / unit_days` |
| `vacant_days` | Vacant unit-days |
| `completed_vacancy_spells` | Vacancy spells that ended with a new letting |
| `avg_vacancy_days` | `vacant_days / completed_vacancy_spells` (pack KPI) |
| `avg_contract_rent` | Average monthly rent of the occupied units at month ends |
| `rent_roll_current` | Rent roll on the window's last day |
| `maintenance_requests` | Requests raised |
| `maintenance_cost` | Their actual cost |
| `maintenance_cost_per_unit_month` | `maintenance_cost` / unit-months (pack KPI, Q11) |
| `avg_days_to_resolve` | Average days to resolve |
| `sla_breach_rate` | SLA breaches / resolved requests |

### The brief's names (D18)

| Brief name | Selects from | Columns |
|---|---|---|
| `vw_monthly_sales` | `vw_monthly_collections` | the same (`SELECT *`) |
| `vw_customer_analysis` | `vw_tenant_analysis` | the same |
| `vw_product_performance` | `vw_unit_performance` | the same |

## For the dashboard (E13)

### `vw_tenant_by_building`: one row per tenant version and building, over the window

The tenant analysis split by the building that billed or was paid (a tenant can rent in more than one), so the
dashboard can drill from a building to its tenants (US-13.3). Summed over a tenant's buildings it gives
`vw_tenant_analysis`'s `total_collected` and `current_arrears`; summed over a building's tenants it gives Q2's
billed and arrears. `scripts/test_powerbi.py` checks both.

| Column | Definition |
|---|---|
| `tenant_key` | Tenant version (`vw_tenant_analysis`, `vw_dim_tenant`) |
| `building_code` | Building (`vw_dim_building`) |
| `tenant_code` | Tenant |
| `tenant_name` | Name |
| `tenant_type` | Type of the version |
| `employer_sector` | Sector of the version |
| `payer_segment` | The version's payer segment over all its buildings (`vw_tenant_analysis`) |
| `invoice_lines` | Invoice lines due in the window at this building |
| `billed_due` | Their net amount |
| `payments` | Payments made at this building (reversals not counted) |
| `late_payments` | Of those, made after the due date |
| `total_collected` | Payments at this building, reversals netted |
| `current_arrears` | Arrears at the window end on the lines of this building |

## Refreshing

`lue_reporting.refresh_marts()` refreshes the four marts (concurrently once they hold data: readers keep the
previous rows until the new ones are complete) and returns each mart's rows and seconds. It is owned by `lue_etl`;
`lue_reader` cannot run it. The pipeline runs it as its last step (`refresh_marts` in `lue_audit.etl_run_log`).
