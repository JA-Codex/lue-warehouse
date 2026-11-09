# Evidence for US-1.1: databases, roles and schemas

| File | What it shows |
|---|---|
| `01_setup_first_run.txt` | `python scripts/db_setup.py` on a server without the LUE databases: both databases are created |
| `02_setup_second_run.txt` | The same command again: no statements generated, no errors (safe to re-run) |
| `03_acceptance_tests.txt` | `python scripts/test_db_setup.py`: 22 PASS lines, including the failed write and the failed cross-schema reads by `lue_reader`, and the check that a second run changes nothing |

The tests log in as `lue_etl` and `lue_reader` with their real passwords, so a PASS means the roles really work,
not just that they exist. They stand in for the plan's `\dn` and `\du` screenshots: the same facts, checked
automatically and repeatable on any machine.
