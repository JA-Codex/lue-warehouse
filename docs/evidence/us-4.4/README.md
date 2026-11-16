# Evidence for US-4.4: against the answer key (and E4 as a whole)

| File | What it shows |
|---|---|
| `01_dq_validation.csv` | The comparison: per planted group expected, detected, missed and the rules that found them; false positives (none) |
| `02_quality_tests.txt` | 100% detection, 0 false positives, warnings as warnings, the comparison catching a wrong rule, the clean control batch with 0 findings |
| `03_tests_catch_broken_code.txt` | 12 deliberate breakages of the E4 code and catalogue: all caught after two test additions |
| `04_all_suites.txt` | `make test` (CI) and every database suite |
