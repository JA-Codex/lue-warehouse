# Rehearsal Notes — US-14.3

**Target duration:** 20 minutes + 5 minutes Q&A

---

## Timing breakdown

| Slide(s) | Topic | Speaker | Time |
|---|---|---|---|
| 1–2 | Title + Business Problem | Presenter A | 2 min |
| 3–4 | Design Decisions + Architecture | Presenter B | 3 min |
| 5–6 | ETL Pipeline + Data Quality | Presenter A | 3 min |
| 7 | SCD Example | Presenter B | 1 min |
| 8 | Performance | Presenter A | 1 min |
| 9 (live) | Dashboard walkthrough + demo | Presenter B | 6 min |
| 10 | Five Insights | Presenter A | 2 min |
| 11–13 | Lessons Learned + What is Not Done + Q&A | Both | 2 min + 5 min |

**Total:** 20 min slides + 5 min Q&A = 25 min

---

## Speaker assignments

- **Presenter A:** narrative and analytical story (business problem → ETL → insights)
- **Presenter B:** technical demo (SCD, performance, dashboard)

---

## Known risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Power BI Desktop not installed on demo machine | Medium | Pre-export PDF (`LUE_Dashboard_Export.pdf`) embedded in slides |
| Database not loaded on demo machine | Medium | Use offline outputs: `powerbi_expected.py`, quality report PDF |
| `make rebuild` takes > 3 min on demo machine | Low | Run on small profile (`PROFILE=small`) — takes ~90 s |
| Slow terminal on projector | Low | Pre-run and copy output to a text slide |
| Q&A exceeds 5 min | Low | Presenter A cuts off with "happy to discuss offline" |

---

## Backup plan (if database unavailable)

1. Skip Step 1 (`make rebuild`) — show the run log screenshot in the slide instead.
2. Skip Step 2 (quarantine in PDF) — show the screenshot on slide 6.
3. Skip Step 3 (SCD query) — show the two-row screenshot on slide 7.
4. Skip Step 4 (EXPLAIN ANALYZE) — show the benchmark log screenshot on slide 8.
5. Step 5 (dashboard): use `LUE_Dashboard_Export.pdf` — navigate between pages in the PDF viewer.

All screenshots are embedded in the slide deck as hidden backup slides.

---

## Pre-demo checklist

- [ ] Power BI Desktop installed and `lue_reader` credentials configured
- [ ] `make rebuild PROFILE=small` run successfully on the demo machine
- [ ] `docs/powerbi/LUE_Dashboard.pbix` refreshed and saved
- [ ] `docs/reports/LUE_Business_Insights_Report.pdf` generated
- [ ] Backup PDF export confirmed at `docs/evidence/us-13.5/LUE_Dashboard_Export.pdf`
- [ ] Terminal font size increased to 18 pt for projector visibility
