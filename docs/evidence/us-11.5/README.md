# Evidence for US-11.5: the SQL pack runs, and three results cross-checked

Full profile, seed 3004.

| File | What it shows |
|---|---|
| `01_psql_run.txt` | Both files run end to end in `psql -v ON_ERROR_STOP=1 -f`: exit 0, the result sets, no error |
| `02_analytics_tests.txt` | `python scripts/test_analytics.py` (22 checks): every query runs; Q1 = the collections mart and view; Q6 = the occupancy mart; the six planted patterns; the OLAP labels and 0 differences; the three pandas cross-checks to the cent |
