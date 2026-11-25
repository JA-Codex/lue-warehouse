# Evidence for US-14.2: the Business Insights Report

| File | What it is |
|---|---|
| `LUE_Business_Insights_Report.pdf` (in the Phase 3 submission zip; rebuild with `python etl/reports/insights.py`) | The report: a summary with the four findings and decisions, one section per insight (finding, evidence, decision and expected effect, caveat), the dashboard pages and notes on the data |
| [`../../../etl/reports/insights.py`](../../../etl/reports/insights.py) | Builds the PDF; before drawing, looks up each of its figures in `docs/analytics.md`, `docs/evidence/us-13.1/01_expected_values.txt` or `decisions.txt` and stops if one is missing |
| [`../../reports/figures/`](../../reports/figures/) | The charts (`make_figures.py`, matplotlib) and the architecture diagram used by the report and the presentation |

| Check | Result |
|---|---|
| Each insight has evidence, a decision and a caveat | Pass: sections 1 to 4 |
| The figures match the dashboard and SQL | Pass: every figure is in the SQL answers or the Decision Page texts, which match Power BI 176 of 176 (`../us-13.5/`) |
| The data is stated to be synthetic | Pass: in the summary and in section 6 |
| Recommendations tie to the Decision Page | Pass: insights 1 to 3 are D1 to D3 |
