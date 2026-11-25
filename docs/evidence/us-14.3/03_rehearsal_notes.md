# Rehearsal notes

## Timing

| Part | Slides | Minutes |
|---|---|---|
| The business and who needs answers | 1 to 3 | 2 |
| Design, architecture, data quality | 4 to 8 | 5 |
| Questions answered: SQL, revenue, OLAP, findings | 9 to 16 | 6 |
| Speed, dashboard, decisions | 17 to 21 | 4 |
| Demo | | 4 |

## Fallback

If the database or Power BI fails on the day: the dashboard pages are in `powerbi/LUE_Dashboard.pdf` and
`powerbi/screenshots/`, the pipeline run is in `docs/evidence/us-8.4/01_full_volume_run.txt`, and the plans in
`docs/evidence/us-12.2/plans/`. Show those instead of the live steps.

## Answers to the likely questions

| Question | Answer |
|---|---|
| Why are invoices and payments separate facts? | They have different grains and dates: one row per invoice line due on a date, one row per payment allocated to a line on the date it was paid. A payment can cover several lines and arrive late, so one table would either repeat amounts or lose the payment date |
| How is late-arriving data handled? | A fact whose tenant or unit has not arrived yet points to an inferred member (or -1, Unknown); when the record lands the inferred row is completed in place. The counts are logged on every run |
| How are SCD2 keys chosen? | Each version gets its own surrogate key; the natural key (tenant code) plus `effective_from` is unique. Facts take the version valid on their own date |
| Why is the occupancy fact partitioned? | It holds one row per unit per day (1,972,800 rows over the window); monthly range partitions let a date-bounded query read only its months (B4: cost 27,597 to 7,321) |
| Why is the collection rate cohort based? | D17: paid against the lines due in the period, so a payment for an old invoice does not inflate this month's rate. Recent months read lower until their invoices have had time to be paid |
