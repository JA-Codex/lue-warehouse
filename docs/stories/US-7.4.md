# US-7.4 Load fact_maintenance_request

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e7-facts` (one pull request for US-7.1 to US-7.6, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-7.4/`](../evidence/us-7.4/) |

## Story

As an operations manager, I want one row per request tracking its whole lifecycle, so that I can measure assignment
and resolution speed.

## What was done

1. **One row per request, inserted when first seen** (plan step 1): the grain is the ticket number
   (`request_number`, a degenerate dimension). The raised date key is set; the assigned, resolved and verified date
   keys are -2 until the milestone happens.
2. **Updated in place as the ticket progresses** (step 2): the accumulating snapshot goes through the US-7.1 loader,
   whose update on the grain rewrites the row when a later extract brings a new milestone: the date keys, the status,
   `days_to_assign` and `days_to_resolve` (from raised), `days_to_verify` (from resolved), the actual cost and the SLA
   flag. The surrogate `request_sk` stays the same; a rerun with nothing new changes no row.
3. **SLA in force when raised** (step 3): `sla_breached_flag` is 1 when the hours to resolve exceed the
   `default_sla_hours` of the category version valid on the raised date (SCD2, US-6.3), 0 otherwise, NULL while the
   ticket is open.
4. **Keys and measures** (step 4): estimated and actual cost; the request flags junk key from emergency, recurring
   and tenant-caused; the category version on the raised date; the vendor version on the assigned date (-2 until
   assigned); the unit version and the unit's owner (who pays) on the raised date; the tenant of the lease active on
   the unit that day (-2 when none: raised by staff on a vacant unit); the weather of the unit's city on the raised
   date (-1 if a day had no weather, D19). Tickets by raised month are reconciled to staging each run.

## Files added or changed

- `etl/facts/spec.py` (the fact), `etl/facts/keys.py` (`weather`, `flags`: the composite natural keys)
- `scripts/test_fact_load_contract.py` (20 checks), `scripts/test_fact_load.py` (41 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **A milestone not reached yet is -2, not -1**: the plan says "Unknown", the frozen data dictionary says "-2 until it
  happens" (Not applicable). The dictionary is the contract; -1 stays for a date that cannot be resolved.
- **The tenant is the lease's tenant on the raised date**: the tickets carry the unit, not the tenant; with no lease
  active the request was raised by staff (945 requests).
- **The durations come from staging** (US-5.2) and the test recomputes them from the timestamps; the SLA flag is
  computed in the fact from the category version, and agrees with staging's flag on every ticket.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| One row per request | Pass: 5,670 rows, 5,670 request numbers, 5,670 staged tickets | `01_` (query 3), `02_` |
| Rerunning does not duplicate or change completed rows | Pass: 0 inserted, updated, deleted; content hash identical | `01_` (run 2), `02_` |
| A ticket progressing between two runs is updated, not duplicated | Pass: MR-2026-00944 assigned in run A, verified in run B, one row, request_sk 5659 both times | `01_` (query 6), `02_` |
| Evidence: the same ticket at two lifecycle stages | Pass | `01_` (query 6) |

## How to re-check it

    python scripts/test_fact_load_contract.py                   # no database: expect 20/20
    python etl/facts/run.py --fact fact_maintenance_request     # twice: the second run changes nothing
    python scripts/test_fact_load.py                            # expect 41/41 (about 6 minutes)
