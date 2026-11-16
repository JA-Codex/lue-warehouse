# US-4.3 Implement business, referential and range checks (DQ-04 to DQ-06)

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e4-quality` |
| Evidence | [`../evidence/us-4.3/`](../evidence/us-4.3/) |

## Story

As a data steward, I want business rules, references and plausible ranges enforced, so that analytics are never built
on impossible data.

## What was done

Rules in `etl/quality/rules.toml`:

- **DQ-04 Business rule** (10): net = billed + tax - discount; due date on or after the invoice date; lease ends after
  it starts; no two leases overlap on a unit; a payment is above 0 unless it reverses one; a settlement's net = gross
  - fee and it is not settled before the payment; resolved not before raised; an offer and an ownership do not end
  before they start. A warning: rent billed above the lease's rent (a mid-lease change).
- **DQ-05 Referential** (21): payment to invoice line, invoice to lease, lease to unit, unit to building, ticket to
  unit and subcategory, the incentive log to unit and offer, ownership to owner and unit, codes in their lists. A
  **tenant** (or vendor) that is not there yet is a **warning** for the inferred-member path (US-6.5), not a rejection.
- **DQ-06 Range** (17): dates inside 2023-07-01 to 2026-06-30 (leases: 2015 to 2035, as legacy leases began before
  the window; settlements: up to a month after it), rent within a band per unit type, amounts under a cap of
  5,000,000, plausible weather and SLA hours.
- Every reason quotes the offending value (`lease_number = 'L-1999-01874' not in brz_lease`).

## Decisions and deviations

- **The 1970 raise time is caught on the status row** (`brz_ticket_status`, status Raised): that is where the time
  is. "Resolved before raised" compares the two status rows of the same ticket copy.
- **Settlement lines without a payment are not a DQ-05 rule:** the answer key gives them to US-5.2 (unmatched
  settlements), so E4 lets them through.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Each planted business-rule, orphan and range defect type is caught by exactly one rule | Pass: every planted row by its expected check, each rejected once | `01_rule_counts.txt`, `../us-4.4/01_dq_validation.csv` |
| A late-arriving tenant reference is flagged, not rejected | Pass: 62 leases and 570 payments, all warnings | `01_`, `../us-4.4/01_` |
