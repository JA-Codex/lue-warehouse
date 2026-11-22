# The analytical SQL pack: answers (E11)

The 14 business questions of the Phase 1 pack, the window analytics and the OLAP queries, answered from the warehouse.
The SQL is in [`sql/60_analytics/analytical.sql`](../sql/60_analytics/analytical.sql) (Q1 to Q14, W1 to W4) and
[`sql/60_analytics/olap.sql`](../sql/60_analytics/olap.sql) (O1 to O3); each query is headed by its question, grain,
tables and definition. The results below are from the **full profile** (seed 3004, data window 2023-07-01 to
2026-06-30); the full outputs are in [`docs/evidence/us-11.1/`](evidence/us-11.1/).

Run them: `psql -d lue_warehouse -v ON_ERROR_STOP=1 -f sql/60_analytics/analytical.sql` (and `olap.sql`), or
`python scripts/run_analytics.py` (each query with its rows and time). `python scripts/test_analytics.py` checks the
answers against the marts, the planted patterns and an independent pandas recomputation.

The six patterns planted in the data (`data/answer_key/planted_patterns.md`) all show where they should: in Q2
(pattern 1), Q9 (2), Q6b (3), Q13 (4), Q14 (5) and Q8 (6). The data is synthetic: the numbers illustrate the method,
not a real portfolio.

## Finance (US-11.1)

### Q1 What is the monthly collection rate by building?

1,440 building-months. Over the window the portfolio collected **94.2 percent** of what fell due (cohort basis, D17:
5,347,289,709 of 5,676,652,818). By building it ranges from **78.2 percent (GLB03)** to 99.0 percent (E1101).
Q1 agrees with `mart_collections_monthly` in every building-month and with `vw_monthly_collections` in total.

**Interpretation:** collection is healthy almost everywhere; GLB03 is the outlier, 16 points below the portfolio,
and is where follow-up pays first.

### Q2 Which buildings have the highest arrears ratio?

| Rank | Building | City | Arrears | Arrears ratio |
|---|---|---|---|---|
| 1 | GLB03 | Lahore | 64,267,854 | 21.8% |
| 2 | DGR01 | Faisalabad | 9,060,746 | 9.9% |
| 3 | FS701 | Islamabad | 19,245,546 | 9.5% |

**Interpretation:** GLB03 carries more than twice the arrears ratio of any other building (planted pattern 1), and
holds one fifth of all arrears (W1).

### Q3 How are overdue balances distributed across ageing buckets?

| Bucket (days past due) | Lines | Balance | Share |
|---|---|---|---|
| 0-30 | 583 | 20,773,534 | 6.3% |
| 31-60 | 370 | 13,463,523 | 4.1% |
| 61-90 | 300 | 10,858,609 | 3.3% |
| 90+ | 8,913 | 284,267,443 | 86.3% |

**Interpretation:** the overdue book is old debt: 86 percent is more than 90 days past due, so the problem is
collection of long-standing balances, not slow payment of new bills.

### Q4a Which tenants pay late repeatedly?

328 tenants made 3 or more payments more than 15 days late in the last 12 months; the worst, T-0362 (Qureshi
Traders, Energy), 32 of 79, on average 47 days late.

**Interpretation:** a small, named group of mostly corporate tenants accounts for the repeat lateness; they are the
list for the collections team.

### Q4b Does late payment differ by employer sector at the time of payment?

The late share (payments over 15 days late) ranges from **14.4 percent (Manufacturing)** down to **8.4 percent
(Government)**, with Logistics (8.5) and Legal and Consulting (9.0) also reliable; every sector has repeat late payers.

**Interpretation:** the sector at the time of payment matters: Manufacturing tenants are late almost twice as often
as Government ones, so payment terms and reminders can be set by sector.

### Q5 Which payment methods settle fastest after the due date?

| Method | Average settlement lag (days) | Average days past due |
|---|---|---|
| Raast | 0.31 | 6.92 |
| Bank transfer | 1.59 | 4.88 |
| JazzCash | 1.78 | 4.87 |
| Easypaisa | 1.86 | 4.78 |
| Cash, cheque | no settlement file | 5.33, 4.34 |

**Interpretation:** Raast settles the same day but is paid latest; bank transfer is the best balance of on-time
payment and quick settlement. Cash and cheques cannot be measured for settlement (no S3 file).

## Occupancy and leasing (US-11.2)

### Q6a How do occupancy and vacancy trend by city and unit type?

396 month, city and unit-type rows. Over the window occupancy averages from **78.2 percent (Karachi apartments)**
to 93.2 percent (Faisalabad shops); Karachi apartments fell from 83.8 percent in the first month to 72.1 percent in
the last. The monthly averages reconcile with `mart_occupancy_monthly` in every row.

**Interpretation:** offices and shops stay fuller than apartments everywhere; Karachi apartments are the one segment
trending down, in line with Karachi's weak renewals (Q8).

### Q6b When do new tenants move in?

June (1.41 times an average month) and August (1.58) are the peaks; June to August average 259 new-tenant move-ins a
month, 1.43 times the other months (planted pattern 3). July reads lower because the go-live leases started before
the window opened.

**Interpretation:** leasing effort and vacancy marketing should be ready before the summer peak.

### Q7 Which unit types stay vacant longest?

| Unit type | Completed spells | Average days | Median days |
|---|---|---|---|
| Office | 94 | 141.4 | 120 |
| Shop | 114 | 131.7 | 122 |
| Apartment | 1,897 | 113.4 | 92 |

Censoring rule (beside the query): only completed spells count; spells that began on the window's first day or are
still open on its last are left out.

**Interpretation:** offices take longest to let once vacant, although they are vacant less often (Q6a).

### Q8 What is the lease renewal rate, and which buildings lose tenants at renewal?

The ten lowest renewal rates are nine Karachi buildings and one in Lahore (MDT02); the lowest, PCH02, renewed 16 of
118 expiring leases (13.6 percent). Karachi renews **17.9 percent** of expiring leases against 36.1 percent elsewhere
(planted pattern 6). The lease-link rate is up to six points higher (DHK01) where RENEW events were quarantined as
planted defects.

**Interpretation:** Karachi loses most tenants at renewal; a retention offer at renewal time in Karachi is the
clearest leasing action.

## Maintenance, owners, incentives and weather (US-11.3)

### Q9a What is the average time to resolve a request by category and vendor?

140 category and vendor rows. In plumbing, **V-001 (Sheikh Plumbing Works)** is the slowest: 3.14 days on average and
a median of 1.36 times the SLA, against 0.68 for the median other plumber (planted pattern 2).

**Interpretation:** one vendor drives plumbing delays; reassigning its work is the quickest SLA gain.

### Q9b Were low-rated vendors slower?

Yes, in every trade the C-rated vendors were the slowest: plumbing vendors rated C at the time took 1.78 days and breached the SLA on 41 percent of
requests, against 1.22 days and 24 percent for A-rated ones; civil works 3.93 against 2.62 days.

**Interpretation:** the vendor rating (taken when the request was raised) is a useful signal for assigning urgent
work.

### Q10 Which buildings breach the maintenance SLA most often?

Highest: SSR01 (Faisalabad) 34.7 percent of resolved requests, CLF02 (Karachi) 33.7, CNT02 (Lahore) 33.3; lowest
DHI01 (Islamabad) 15.5.

**Interpretation:** SLA performance varies twofold between buildings; the top three deserve a vendor review.

### Q11 What is the maintenance cost per unit per month by building?

Highest MDT02 (Lahore) PKR 1,058 per unit-month, then E1102 740 and WPT01 733; lowest BLA01 (Islamabad) 278.

**Interpretation:** MDT02 costs nearly four times the cheapest building per unit; its request mix is worth a look.

### Q12 What is the net operating income per owner portfolio?

900 owners. Rent collected (charge type RENT only) minus actual maintenance cost minus the management fee
(**assumption: 8 percent of rent collected**, `vw_reporting_parameter`). The largest, OW-0834 (8 units),
25,997,265; NOI margins run from 84 to 92 percent (median 91).

**Interpretation:** owner NOI follows rent almost one for one because maintenance costs are small next to rent in this
data; the fee assumption, not maintenance, is the main lever on owner returns here.

### Q13 Do vacancy incentives shorten vacancy, and which offer type works best?

| Group | Completed spells | Average vacancy days | Against no offer |
|---|---|---|---|
| No offer | 1,594 | 134.3 | 1.000 |
| Any offer | 511 | 57.5 | 0.428 |
| Discount | 246 | 56.6 | 0.421 |
| Rent-free days | 165 | 57.8 | 0.431 |
| Free maintenance | 100 | 59.0 | 0.439 |

**Interpretation:** an offer cuts vacancy by more than half (planted pattern 4); the type matters little, so the
cheapest offer for the unit is the right one.

### Q14 Do leak and plumbing requests rise on heavy-rain days?

Leak requests (PLB-LEAK, CIV-SEEP, CIV-ROOF) run at 2.05 per 1,000 unit-days on heavy-rain days (10 mm or more) or
the day after, against 0.32 on other days: **6.3 times** as many (planted pattern 5).

**Interpretation:** after heavy rain, plumbing and civil vendors should be on standby; roof and seepage work before the
monsoon would cut the peak.

## Window analytics (US-11.5)

### W1 RANK of buildings by arrears

GLB03 ranks first overall (19.5 percent of all arrears) and first in Lahore; BLA02, FS701 and BLA01 lead Islamabad.

**Interpretation:** arrears are concentrated: one building holds a fifth of the total.

### W2 LAG growth in collections

Cash received grew 3.1 percent in June 2026 after a 2.1 percent dip in April and a flat May; the cohort rate's fall in the latest months is
the cohort effect (their lines have had the least time to be paid), not a collection problem.

**Interpretation:** read month-on-month growth on cash received; compare cohort rates only between months of the same
age.

### W3 Running total of cash received within each fiscal year

FY2025-26 collected 1,931,428,672; 83 percent of it was in by the end of April.

**Interpretation:** the running total shows how far through its collections the fiscal year is at any month.

### W4 Three-month moving average of collections

The three-month average of cash received rose to 163.2 million by June 2026; the three-month cohort rate (a ratio of
sums, not an average of rates) is 91.4 percent.

**Interpretation:** the moving average smooths one-off months and is the trend line for the dashboard.

## OLAP (US-11.4)

### O1 ROLLUP: building, city, region and grand totals

48 rows: 40 buildings, 4 city subtotals, 3 region subtotals and the grand total (5,347,289,709), each labelled by
`GROUPING()`. Punjab collects 49.3 percent (Lahore 40.9), Islamabad Capital Territory 32.2, Sindh 18.5.

**Interpretation:** Lahore is the largest market by cash; Islamabad collects a third of the cash from a fifth of the
buildings.

### O2 CUBE: city by payment channel group

30 rows: every city and channel, each city's total over channels, each channel's total over cities and the grand
total. Bank transfer is the largest channel everywhere (29 percent overall); Raast ("Instant payment") the smallest
(14 percent).

**Interpretation:** a third of Islamabad's cash comes by bank transfer; cash is still about a fifth of collections in
every city (20 to 23 percent).

### O3 Verification of O1 and O2

8 checks over 23 subtotals: the ROLLUP and CUBE grand totals equal the base total of the payments, every city and
region subtotal equals the sum of its parts, and the CUBE's city totals equal the ROLLUP's. **0 differences.**

**Interpretation:** the subtotals can be trusted as they are.
