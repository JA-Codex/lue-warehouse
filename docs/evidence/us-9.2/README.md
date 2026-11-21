# Evidence for US-9.1 and US-9.2: the Phase 2 reports

Full profile, seed 3004, the warehouse built by `make rebuild PROFILE=full`; the PDFs by `make reports`.

| File | What it shows |
|---|---|
| `../../reports/LUE_Data_Cleaning_Report.pdf` | The Data Cleaning Report (US-9.1) |
| `../../reports/LUE_Data_Quality_Report.pdf` | The Data Quality Report (US-9.2) |
| `01_report_tests.txt` | `scripts/test_reports.py` (11 checks): both reports build; rejected = quarantine = run log; staged = table = run log for 20 tables; the cleaning evidence of the run that built staging; the answer key fully detected; the DQ-07 run, every month passed; 0 orphans in 41 checks with the quoted query returning 0; SCD continuity 0; the pipeline run complete; no count typed |
