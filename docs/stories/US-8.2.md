# US-8.2 DQ-07 source-to-warehouse reconciliation

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `user-story-8.2` (one pull request for US-8.1 to US-8.3, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-8.2/`](../evidence/us-8.2/) |

## Story

As a quality owner, I want a reconciliation that proves every source row is either in the warehouse
or in quarantine, so that no row is lost between staging and the facts.

## What was done

1. **`etl/pipeline/reconcile.py`**: a `reconcile(conn, run_id)` function that queries staging and
   fact tables and writes one `lue_audit.reconciliation` row per check:
   - Monthly counts for `stg_rent_invoice_line` vs `fact_rent_invoice_line`
   - Monthly counts for `stg_payment` vs `fact_payment`
   - Total counts for `stg_ticket` vs `fact_maintenance_request`
   - Total counts for `stg_lease_event` vs `fact_lease_event`
2. **Reconciliation rule**: `source_rows = warehouse_rows + quarantined_rows`; variance = the
   difference; `passed = (variance == 0)`.
3. **`ReconcileError`**: raised when any variance is unexplained, listing the failing check names.
4. **`check_name` pattern**: `dq07_{staging_table}_{YYYY-MM}` for monthly checks,
   `dq07_{staging_table}_total` for ticket and lease-event totals.

## Files added or changed

- `etl/pipeline/reconcile.py` (new)
- `etl/pipeline/__init__.py` (new, empty)
- `docs/stories/US-8.2.md`, `docs/evidence/us-8.2/README.md`

## Decisions and deviations

- **Monthly check for invoices and payments**: the fact loaders already write per-month
  reconciliation rows; `reconcile()` reads those to derive the warehouse side rather than
  re-counting the fact table, so the two layers agree on what was loaded in this run.
- **Ticket and lease-event totals**: these facts have no calendar-month column in staging, so a
  single total row is used (`_total` suffix).
- **ON CONFLICT DO UPDATE**: the INSERT uses upsert semantics so reconcile() is safe to re-run.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| `etl/pipeline/reconcile.py` exists | Pass | `scripts/test_pipeline_contract.py` check 3 |
| `reconcile()` defined | Pass | check 3 |
| `ReconcileError` defined | Pass | check 3 |

## How to re-check it

    python scripts/test_pipeline_contract.py      # expect 6/6
