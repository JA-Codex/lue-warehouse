# Evidence for US-7.2: fact_rent_invoice_line, fact_payment and the monthly reconciliation

Full profile, seed 3004. Staging and the dimensions as left by US-6.5 (both S1 extracts applied).

| File | What it shows |
|---|---|
| `01_reconciliation.txt` | The first load of both facts (129,885 invoice lines, 127,210 payment allocations) and a rerun (0 inserted, 0 updated, 0 deleted), the run log, the grain check (0 duplicates in both facts; the DDL's `uq_invoice_line` and `ck_net_amount`), totals against staging, reversals reducing collected, and the monthly reconciliation as written to `lue_audit.reconciliation` (36 months, 72 rows, all passed, difference 0.00) |
| `02_fact_tests.txt` | `scripts/test_fact_load_contract.py` (12 checks, no database), `scripts/test_fact_load.py` (20 checks: US-7.1's 10, then invoice totals and keys at the invoice date, grain duplicates, an independent monthly reconciliation, the run's reconciliation rows, reversals, a PKR 1 change failing exactly its month, rerun) and the US-1.3 identity checks with both facts loaded |
