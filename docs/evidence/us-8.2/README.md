# Evidence for US-8.2: source-to-warehouse reconciliation (DQ-07)

Full profile, seed 3004, loaded by `python etl/run_pipeline.py` on an empty warehouse.

| File | What it shows |
|---|---|
| `01_reconciliation.txt` | The pipeline run ending with the reconcile step; per measure, source = warehouse + quarantined (billed and paid exact, tickets 6,000 = 5,670 + 330, lease events 9,195 = 8,781 + 414); the reconciliation table of that run, every measure and month (`lue_audit.reconciliation`); where the quarantined rows come from; and the deliberate failure: a lease event removed and an invoice amount changed fail exactly their months, the step Fails (exit 1), a reload of the facts restores the pass |
| `02_pipeline_tests.txt` | `scripts/test_pipeline_contract.py` (17 checks, no database) and `scripts/test_pipeline.py` (14 checks; the US-8.2 part: every month reconciles, source = warehouse + quarantined, the deliberate failures, the restore) |
