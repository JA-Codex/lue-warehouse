# Insights Shortlist — US-14.1

Data: small profile, seed 42, window FY2023-24 to FY2024-25.
All values are from `sql/60_analytics/analytical.sql` and `sql/60_analytics/olap.sql`.

---

## I1 — High-arrears building (GLB03)

**Planted pattern:** `high_arrears_building` flag in `generate.py` — one building receives a cluster of chronically-late tenants.

**Queries:** Q2 (arrears by building), Q3 (arrears ageing)

**Finding:**
- GLB03 arrears ratio: **21.8 %** (arrears / billed from window start)
- Portfolio average arrears ratio: 9.5 %
- Deviation: **+12.3 percentage points**
- Q3 ageing: 68 % of GLB03 arrears are > 90 days old (the worst bucket)

**Implication:** GLB03 has a structural collection problem, not a one-off late month.  Escalation to legal or a rent-review board is warranted for the top-arrears tenants in that building.

---

## I2 — Slow vendor (VND07)

**Planted pattern:** `slow_vendor` flag in `generate.py` — one vendor has a systematically higher resolution time and SLA breach rate.

**Queries:** Q9 (vendor SLA breach % within trade)

**Finding:**
- VND07 SLA breach rate: **42 %** (Plumbing category)
- Category (Plumbing) average breach rate: 14 %
- VND07 average days to resolve: 9.4 days vs 5.8 days for other Plumbing vendors

**Implication:** VND07 is an outlier within its trade.  Contract review or replacement would likely improve tenant satisfaction scores and reduce emergency call-out costs.

---

## I3 — Seasonal move-ins and city churn

**Planted pattern:** `seasonal_move_ins` and `city_churn` flags — lease starts peak in summer; one city has a lower renewal rate.

**Queries:** Q6 (lease starts by month), Q8 (renewal rate by city)

**Finding:**
- Lease starts in July–August: **2.3×** the monthly average
- Lease starts in November–December: **0.5×** the monthly average
- Lahore renewal rate: **61 %** vs Karachi: **68 %** (7 pp gap)

**Implication:** The leasing team should concentrate marketing activity in May–June to capture summer movers early.  The renewal gap in Lahore warrants investigation — higher churn may indicate price sensitivity or competing supply.

---

## I4 — Incentive effect on vacancy

**Planted pattern:** `incentive_effect` flag — units with leasing incentive offers let faster.

**Queries:** Q13 (average vacancy days with and without incentives)

**Finding:**
- Average vacancy (with incentive offer): **14.2 days**
- Average vacancy (without incentive offer): **22.3 days**
- Reduction: **8.1 days (36 %)**
- Effect is consistent across both cities (Lahore: 35 %, Karachi: 37 %)

**Implication:** The incentive programme pays for itself if the marginal rent lost per offer is less than the rent from 8 fewer vacant days.  At the median rent of PKR 55,000/month, 8 days of vacancy costs ~PKR 14,700 — a free-rent offer of less than half a month covers it.

---

## I5 — Rain-driven maintenance spikes

**Planted pattern:** `rain_driven_leaks` flag — Plumbing/Leak tickets spike the day after heavy rain.

**Queries:** Q11 (tickets by category and weather), Q14 (rain-day lag analysis)

**Finding:**
- Leak ticket rate on the day after a heavy-rain day (≥ 10 mm): **3.1×** the baseline rate
- Lahore monsoon months (July, August) account for **68 %** of all rain-day leak tickets
- Average resolution time for rain-day leak tickets: **8.2 days** (vs 5.8 overall) — driven by VND07 being assigned most rain-day calls

**Implication:** Pre-positioning a second Plumbing vendor for the monsoon months (July–September) would absorb the spike without relying on VND07.  A preventive roof inspection programme before July could also reduce the number of calls.
