# Evidence for US-13.5: validate, finish and export

Built and checked in Power BI Desktop 2.159.883.0 (October 2026) on 25 November 2026, on the full profile.

| File | What it shows |
|---|---|
| [`01_kpi_reconciliation.md`](01_kpi_reconciliation.md) | Every numeric measure (44) in Power BI against SQL for the whole window, March 2025, FY2024-25 and Lahore: **176 of 176 values agree** |
| [`02_powerbi_validation.tsv`](02_powerbi_validation.tsv) | The `validation.dax` result exactly as Power BI returned it |
| `powerbi/screenshots/06_validation.png` | That result on screen |
| `powerbi/LUE_Dashboard.pdf` | The three pages exported from Power BI (File, Export to PDF) |
| `powerbi/screenshots/01_model.png` to `05_decision_page.png` | The model view, the three pages, and page 2 opened by a drill-through |

## Checks

| Check | Result |
|---|---|
| Every KPI matches SQL | Pass: 176/176 (`01_kpi_reconciliation.md`); the cards with no slicer read PKR 5,347,289,709 (shown as PKR 5bn), 94.2%, 84.5%, PKR 329,363,109 (5.8% of billed to date) |
| Slicers filter the visuals | Pass: the fiscal year, month and city filters of `validation.dax` are the slicers' filters and match SQL; on the pages, FY2023-24 changed every visual and the three decision texts (GLB03 17.0% against 5.4% for the portfolio; Gondal Plumbing Services V-020; Karachi apartments 76.8%) |
| Cross-filtering | Pass: clicking a month or a matrix row filters the other visuals |
| Drill-through | Pass: right-click a building bar on page 1, Drill through, Detailed Analysis opens page 2 filtered to it (`04_drill_through.png`) |
| PBIX and PDF exist | Pass: `powerbi/LUE_Dashboard.pbix` (1.8 MB after Auto date/time was turned off), `powerbi/LUE_Dashboard.pdf` (3 pages) |
| PBIX opens on two other machines | **To do**: two teammates open the PBIX and add their names below |

| Opened by | Machine | Date |
|---|---|---|
| | | |
| | | |
