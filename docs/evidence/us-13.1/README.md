# Evidence for US-13.1: the model and the measures

Recorded on the full profile (data window 2023-07-01 to 2026-06-30, seed 3004).

| File | What it shows |
|---|---|
| [`01_expected_values.txt`](01_expected_values.txt) | `python scripts/powerbi_expected.py`: every numeric measure of `docs/powerbi/measures.dax` as the dashboard must show it, for the whole window, the month 2025-03, the fiscal year FY2024-25 and the city Lahore, and the decision texts; computed as `lue_reader` from the same objects Power BI loads |
| [`expected_measures.csv`](expected_measures.csv) | The same values unrounded (six decimals): the SQL side of the side-by-side validation (US-13.5) |
| [`decisions.txt`](decisions.txt) | The three decision texts for each selection, word for word |
| [`02_powerbi_tests.txt`](02_powerbi_tests.txt) | `python scripts/test_powerbi.py`, 13/13: `lue_reader` loads all 15 tables; all 17 relationships are many-to-one with no orphan key; 24 measures equal queries on the facts for each selection; the tenants-by-building view adds up to the tenant analysis and to Q2; each decision text picks what the facts pick |

To be added from Power BI Desktop: the model view screenshot (`powerbi/screenshots/01_model.png`) and the measure
against SQL comparison (`docs/evidence/us-13.5/README.md`, with `06_validation.png`).
