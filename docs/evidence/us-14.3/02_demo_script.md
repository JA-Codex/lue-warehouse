# Demo Script — US-14.3

**Slides 8–10 live demo (~6 minutes)**

---

## Step 1 — `make rebuild` (1 min 30 s)

> "The warehouse is completely reproducible from one command."

```
cd lue-warehouse
make rebuild PROFILE=small
```

- Point to the terminal: steps scroll by — bronze, validate, stage, dimensions, facts, marts, reconcile, reports.
- Highlight the final line: "Pipeline complete — 11 steps, 0 failed."
- Point to the two PDFs written to `docs/reports/`.

---

## Step 2 — Quarantined row in the Quality Report (1 min)

> "The pipeline detected and isolated a planted defect."

Open `docs/reports/LUE_Data_Quality_Report.pdf`, section 7 (Quarantine).

- Show the quarantined row: source S2, table `src_vendor_register`, rule DQ-01 (required value missing), 1 row.
- "This is a vendor with no SLA category — the rule correctly rejected it.  The row is in quarantine with the reason attached."

---

## Step 3 — SCD2 history query (1 min)

> "The warehouse tracks history — we can see VND07's rating before and after the change."

```sql
SELECT vendor_id, vendor_name, vendor_rating, valid_from, valid_to
FROM lue_dw.dim_vendor
WHERE vendor_id = 'VND07'
ORDER BY valid_from;
```

- Show two rows: rating 4.2 until the change date, then 3.8 from that date to `9999-12-31`.
- "Any fact row for a maintenance ticket raised before the change links to the old version — history is preserved."

---

## Step 4 — EXPLAIN ANALYZE benchmark (45 s)

> "We measured the impact of a candidate index on the arrears query."

```sql
EXPLAIN ANALYZE
SELECT building_key, SUM(arrears_balance_pkr)
FROM lue_dw.fact_occupancy_snapshot
GROUP BY building_key;
```

- Show: sequential scan, 820 ms without the index.
- Apply the index (or show the benchmark log at `docs/evidence/us-12.x/`).
- Show: index scan, 95 ms — "8.6× faster on a 500 k-row table."

---

## Step 5 — Dashboard drill-through (2 min)

Open `docs/powerbi/LUE_Dashboard.pbix` (or the PDF export if offline).

> "The Executive Overview shows GLB03 as the worst-arrears building."

1. Point to the arrears bar chart — GLB03 at the top.
2. Right-click GLB03 → Drill through → Detailed Analysis.
3. Show the tenant table for GLB03 — four tenants in "Chronically Late" segment.
4. Navigate to the Decision page — R1 card shows GLB03 with 21.8 % arrears ratio.
5. "The recommendation card is dynamic — it updates if you filter to a different city."

---

## Backup plan

If Power BI Desktop is not available on the demo machine:

- Use `docs/evidence/us-13.5/LUE_Dashboard_Export.pdf` — all three pages as screenshots.
- Use `docs/evidence/us-14.1/01_insights_shortlist.md` for the insight numbers.
- Run `python scripts/powerbi_expected.py` to show the SQL-side KPI values in the terminal.
