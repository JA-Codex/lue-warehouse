# Evidence for US-14.1: the insights shortlist

Full profile, seed 3004, data window 2023-07-01 to 2026-06-30. Every number is quoted from a recorded result and
checked against it by `etl/reports/insights.py` before the report is drawn (the `SOURCES` list in that file).

## The shortlist, ranked by effect

| Rank | Insight | The number | Source | Size of the effect | Confidence |
|---|---|---|---|---|---|
| 1 | Arrears concentrate in Gulberg Residency 2 (GLB03) | Arrears ratio 21.8% against 5.8%; collection rate 78.2%, 16.0 points under 94.2%; PKR 64,267,854, 19.5% of all arrears; 86.3% of the overdue book is over 90 days | Q1, Q2, Q3, W1 (`docs/analytics.md`); Decision Page D1 (`../us-13.1/decisions.txt`) | Half recovered cuts portfolio arrears by 10% (about PKR 32 million) | High: the same building leads in every fiscal year (17.0% in FY2023-24, 20.5% in FY2024-25) |
| 2 | Karachi apartments lose occupancy because Karachi tenants do not renew | Occupancy 78.2% against 84.5%, falling from 83.8% to 72.1%; Karachi renews 17.9% of expiring leases against 36.1% elsewhere; an incentive cuts vacancy from 134.3 to 57.5 days; move-ins peak June to August at 1.43 times other months | Q6a, Q6b, Q8, Q13; Decision Page D3 | About 23 more units let, about PKR 1,775,190 of rent a month (PKR 21.3 million a year) | Medium: the incentive effect is a comparison, not a trial |
| 3 | One plumbing vendor slows maintenance | Sheikh Plumbing Works (V-001): 3.1 days against 1.4 for all plumbing vendors (2.3 times); SLA breached on 86.5% of jobs against 24.9% | Q9a, Q9b; Decision Page D2 | About 76 fewer days of waiting on its 37 requests | High: ranked only among vendors with 20 or more resolved requests |
| 4 | Heavy rain drives leak requests | 2.05 leak requests per 1,000 unit-days on a heavy-rain day or the day after, against 0.32: 6.3 times | Q14 | Fewer and faster leak repairs in the rainy months | High: weather is per city per day |

## The six planted patterns

`data/answer_key/planted_patterns.md` lists six patterns. Each was found by an ordinary query, written before the
answer key was opened, and each is used:

| Pattern | Found by | Used in |
|---|---|---|
| 1 High-arrears building (GLB03) | Q2, W1 | Insight 1 |
| 2 Slow plumbing vendor (V-001) | Q9a | Insight 3 |
| 3 Seasonal move-ins (June to August) | Q6b | Insight 2 (timing of the incentive) |
| 4 Incentives shorten vacancy | Q13 | Insight 2 (the action) |
| 5 Rain-driven leak tickets | Q14 | Insight 4 |
| 6 Renewal churn in one city (Karachi) | Q8 | Insight 2 (the cause) |

Patterns 3, 4 and 6 are one leasing story (why Karachi apartments empty, when and how to fill them), so they make one
insight. Candidates left out: late payment by sector (Manufacturing 14.4% against Government 8.4%, Q4b), used as a
supporting point under insight 1; maintenance cost per unit (MDT02 PKR 1,058 per unit-month, Q11), too small next to
rent to change a decision.
