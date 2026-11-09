# Evidence for US-1.2: dimension DDL with keys and special members

| File | What it shows |
|---|---|
| `01_contract_check.txt` | `python scripts/check_contract.py`: all 13 dimensions match the frozen Phase 1 DDL; the only differences are the listed Phase 2 additions |
| `02_deploy.txt` | `python scripts/db_deploy.py`: the dimensions deployed as `lue_etl` |
| `03_acceptance_tests.txt` | `python scripts/test_dimensions.py`: 27 PASS lines, including the constraint violation messages the plan asks for (two current rows, inverted range), the special members, key 1 for the first loaded member, and a re-run that changes nothing |

The tests stand in for the plan's DDL listing and screenshots: the same facts, checked automatically and repeatable.
To see the tables yourself in pgAdmin: lue_warehouse → Schemas → lue_dw → Tables (refresh first).
