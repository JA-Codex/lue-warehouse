# US-6.3 Extend SCD2 to unit, vendor and maintenance category

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e6-dimensions` (one pull request for US-6.1 to US-6.5, one commit per story) |
| Evidence | [`../evidence/us-6.3/`](../evidence/us-6.3/) |

## Story

As an analyst, I want unit, vendor and category history preserved where the design requires it, so that performance
is attributed to the right version.

## What was done

The SCD2 step of US-6.2 is parameterised by the spec: each SCD2 dimension gives its natural key, Type 2 columns and a
history query. Type 2 columns follow the data dictionary:

| Dimension | Type 2 | History from |
|---|---|---|
| `dim_unit` | unit type, furnished flag | bronze `brz_unit` with staging's cleaning, by `updated_at` |
| `dim_vendor` | rating band | the register: `previous_rating` until `rating_changed_on`, then `rating` |
| `dim_maintenance_category` | default SLA hours | the SLA policy's versions (`valid_from`) |

Contact-style attributes (vendor phone, names, unit area and bedrooms, building attributes) are Type 1.
`unit_nk` = `building_code || '-' || unit_no` ('GLB01-A-101'), the dictionary's building plus unit.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Each dimension passes the same continuity checks as tenant | Pass: one current version per key, first from 1900-01-01, no gap or overlap (sql/90_tests, US-6.5) | `01_version_history.txt`, `../us-6.5/` |
| A changed SLA value creates a new category version without altering history | Pass: 4 SLA changes, 4 new versions, every earlier value kept | `01_` |
| Vendor rating changes | Pass: 17 changes, 17 versions | `01_` |
