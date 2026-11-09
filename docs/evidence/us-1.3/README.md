# Evidence for US-1.3: fact DDL, foreign keys and partitions

| File | What it shows |
|---|---|
| `01_contract_check.txt` | The 6 facts (and 13 dimensions) match the frozen Phase 1 DDL |
| `02_deploy.txt` | `01_dimensions.sql` and `02_facts.sql` deployed as `lue_etl` |
| `03_acceptance_tests.txt` | 24 PASS lines: keys, 41 foreign keys, 49 partitions, rejected bad keys, partition pruning, no secondary indexes, safe re-run |