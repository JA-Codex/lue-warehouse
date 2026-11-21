# US-7.5 Load fact_lease_event and fact_vacancy_incentive_coverage

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e7-facts` (one pull request for US-7.1 to US-7.6, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-7.5/`](../evidence/us-7.5/) |

## Story

As a leasing manager, I want lease events and incentive coverage recorded as factless facts, so that renewal rates
and incentive effects can be counted.

## What was done

1. **`fact_lease_event`** (plan step 1): one row per lifecycle event (signed, renewed, notice given, terminated) of one
   lease, from `stg_lease_event`: the event date key and the event type key; the lease, and the lease's unit and
   tenant in the version valid on the event date; the unit's owner that day; `event_count` always 1 (the DDL's
   `ck_event_count`), so `SUM(event_count)` counts events. The grain is the event's natural key (lease, type, date);
   none of the three may be -1, since two unresolved events would look alike.
2. **`fact_vacancy_incentive_coverage`** (step 2): each S6 window (an offer posted on a unit from a start to an end
   date, `stg_incentive_log`) is expanded into its days with `generate_series` and kept on the days the unit is
   vacant (the dictionary: "restricted to vacant unit-days"); the unit version and the owner of that day (who approved
   the offer), and the offer's incentive key.
3. **The composite primary key** (step 3): the coverage grain is the table's primary key (day, unit, incentive); the
   loader refuses a source with a grain twice, and the key itself refuses a duplicate insert (unique violation).
4. Both facts go through the US-7.1 loader (a rerun changes nothing) and reconcile by month each run: events by event
   month, offer-days by month.

E7 now loads all six facts of the DDL; CI checks the spec covers every one.

## Files added or changed

- `etl/facts/spec.py` (the two facts)
- `scripts/test_fact_load_contract.py` (23 checks), `scripts/test_fact_load.py` (49 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **Coverage keeps vacant unit-days only**, as the dictionary defines the grain. Every posted window in this data
  falls on vacant days (0 occupied), so the rows equal the sum of the window lengths, as the acceptance criterion
  asks; the test reports both numbers, so a window overlapping a lease would show as the difference.
- **The lease event grain is (lease, event type, date)**: the frozen DDL keys the table by a surrogate only, so the
  natural key is enforced by the loader (a duplicate is refused) and tested.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Counts of events by type match staging | Pass: SIGN 2,292, RENEW 1,889, NOTICE 2,308, TERM 2,292; difference 0 | `01_` (query 3) |
| Coverage rows equal the sum of incentive window lengths in days | Pass: 624 windows, 20,177 days, 20,177 rows | `01_` (query 5) |
| The composite primary key prevents duplicates | Pass: unique violation on `pk_fact_vacancy_incentive_coverage` | `01_` (query 7), `02_` |
| Evidence: counts by event type, coverage row check | Pass | `01_` |

## How to re-check it

    python scripts/test_fact_load_contract.py                                                    # expect 23/23
    python etl/facts/run.py --fact fact_lease_event --fact fact_vacancy_incentive_coverage       # twice: nothing changes
    python scripts/test_fact_load.py                                                             # expect 49/49
