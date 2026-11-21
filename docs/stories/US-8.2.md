# US-8.2 Implement source-to-warehouse reconciliation (DQ-07)

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-21 |
| Branch and pull request | `e8-pipeline` (one pull request for US-8.1 to US-8.4, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.2/`](../evidence/us-8.2/) |

## Story

As a finance controller, I want proof that warehouse totals equal source totals, so that the numbers can be trusted.

## What was done

1. **Four measures by month** (plan step 1), in `etl/reconcile.py`, each against the source itself:
   - **billed**: net amount of the invoice lines by invoice month, `src_pms` against `fact_rent_invoice_line`;
   - **paid**: cash received by paid month, `src_pms.payments` against `fact_payment`;
   - **tickets**: requests by raised month, the S4 file (as landed in bronze, proven equal to the file by US-3.4)
     against `fact_maintenance_request`; a ticket is one request number however many copies the file holds, and its
     raised date is its "Raised" status entry;
   - **lease events**: events by event month, `src_pms` against `fact_lease_event`.
   The month is the source's own date: a planted out-of-range date keeps its month, a missing date is 'none'.
2. **source = warehouse + quarantined** (step 2): the quarantined rows of `lue_audit.quarantine` are the reconciling
   item, counted in the month of their own source date. A rejected row explains a difference only when its key never
   reached staging, so a row that was rejected and loaded anyway cannot hide a gap. The unexplained variance,
   source - warehouse - quarantined, must be 0.
3. **Results in `lue_audit.reconciliation`** (step 3): one row per measure and month (`DQ-07 <measure> <month>`):
   `source_value` the source, `warehouse_value` the warehouse plus the quarantined (what is accounted for),
   `difference` the unexplained variance, `passed` when it is 0. The terminal shows the four columns per measure.
4. **A failing step** (step 4): the pipeline's `reconcile` stage runs after the facts; any unexplained variance fails
   it and the run exits 1. `python etl/reconcile.py` runs it alone.

## Files added or changed

- `etl/reconcile.py`, `etl/run_pipeline.py` (the reconcile stage)
- `scripts/test_pipeline_contract.py` (17 checks), `scripts/test_pipeline.py` (14 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **The frozen pack's reconciliation table has no quarantined column**: `warehouse_value` holds warehouse +
  quarantined and `difference` the unexplained variance, so a row still reads "expected, found, passed"; the split is
  in the terminal output and the evidence.
- **Paid is the cash received**: staging allocates every payment (US-5.2), re-deriving the allocations that E4
  rejected, so the cash reconciles exactly; the rejected allocation rows stay in quarantine, with no cash missing.
- **Tickets are counted by request number**: the file's duplicate copies (60 exact, 60 conflicting) are not
  requests; 270 tickets lost every copy to a quality rule and 60 their only raised date (an out-of-range status
  entry), together the 330 quarantined.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Unexplained variance is zero for every measure and month | Pass: 194 measure-months, all passed, total unexplained 0.00 | `01_` |
| Removing a fact row on purpose makes reconciliation fail | Pass: a lease event removed (and an invoice amount changed) fail exactly their months; the step Fails, exit 1 | `01_`, `02_` |
| Evidence: the reconciliation table and the deliberate-failure demonstration | Pass | `01_` |

## How to re-check it

    python scripts/test_pipeline_contract.py    # no database: expect 17/17
    python etl/reconcile.py                     # every measure-month reconciles
    python scripts/test_pipeline.py             # expect 14/14 (resets the warehouse; leaves the small profile loaded)
