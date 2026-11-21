# Evidence: US-8.2 — DQ-07 source-to-warehouse reconciliation

US-8.2 implements `etl/pipeline/reconcile.py`, which provides the `reconcile(conn, run_id)`
function that checks the fundamental reconciliation rule: every source row must be accounted for
as either in the warehouse or in quarantine (variance = source − warehouse − quarantined = 0).
The function queries `lue_staging` and `lue_dw` for row counts — by calendar month for
`stg_rent_invoice_line` vs `fact_rent_invoice_line` and `stg_payment` vs `fact_payment`, and as
totals for `stg_ticket` vs `fact_maintenance_request` and `stg_lease_event` vs
`fact_lease_event` — and writes one row per check to `lue_audit.reconciliation` with the pattern
`dq07_{table}_{YYYY-MM}` (or `_total` for the non-monthly tables). If any variance is unexplained,
`ReconcileError` is raised listing the failing check names and variance values.

## Key files

- `etl/pipeline/reconcile.py` — the reconciliation module
- `etl/pipeline/__init__.py` — empty package marker
- `docs/stories/US-8.2.md`
- `docs/evidence/us-8.2/README.md` (this file)

## Verification

Run `python scripts/test_pipeline_contract.py` to verify offline.
