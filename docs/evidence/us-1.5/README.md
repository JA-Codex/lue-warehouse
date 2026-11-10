# Evidence for US-1.5: audit tables, watermark table and reset

| File | What it shows |
|---|---|
| `01_reset.txt` | `python scripts/db_reset.py`: schemas dropped, then setup, deploy, reference load and smoke test all run |
| `02_smoke_test.txt` | `python scripts/test_smoke.py`: 12 PASS lines (13 dims, 6 facts, 5 audit tables, 41 FKs, 48 partitions) |
| `03_contract_check.txt` | `python scripts/check_contract.py`: 24 tables checked, 0 problems |
