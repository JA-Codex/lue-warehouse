# US-6.4 Load the remaining dimensions and hierarchies

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e6-dimensions` (one pull request for US-6.1 to US-6.5, one commit per story) |
| Evidence | [`../evidence/us-6.4/`](../evidence/us-6.4/) |

## Story

As an analyst, I want every dimension fully populated with its hierarchy, so that all questions can slice and roll up.

## What was done

1. **`dim_unit`** with its hierarchy: unit, floor, building, locality, city, region (from staging's building and
   city lookup), building class and an age band as of today (0–5, 6–15, 16+ years).
2. **`dim_owner`** with a portfolio band from the units owned today in the ownership register (1 unit, 2–5, 6+;
   'None' for an owner with no current unit), **`dim_lease`** (all Type 0: the contract as signed),
   **`dim_incentive`** from the S6 offers, **`dim_weather`** per city and day with rain and heat bands (rain: None
   under 1 mm, Light to 10, Heavy above; heat: Mild under 35 °C, Hot to 40, Extreme above).
3. **`dim_date`** holiday and Ramadan flags and names from the S2 holiday register (a full snapshot: a date it no
   longer lists goes back to FALSE).
4. Load order: holidays, then owner, vendor, category, incentive, weather, then unit, tenant and lease.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Row counts plausible and above 100 for the large dimensions | Pass: units 1,800, tenants 3,800, leases 5,883, owners 900, vendors 140, weather 4,384 city-days | `01_counts_and_hierarchy.txt` |
| Every hierarchy level populated | Pass: 0 units with a missing level | `01_` |
| Holidays from the register | Pass: 59 public holidays, 116 Ramadan days | `01_` |
