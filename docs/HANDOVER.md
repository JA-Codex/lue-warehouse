# Handover: finishing the LUE warehouse (E13 to E15)

For the teammates who complete the project. It says where things stand, how to get the project running on your
machine, and, for each remaining story, what to do, what to produce and how to know it is done. The plan behind
it is [docs/plan/LUE_Development_Plan_v1.1.md](plan/LUE_Development_Plan_v1.1.md) (E13 to E15, Appendix B).

## 1. Where the project stands

| Epics | State |
|---|---|
| E0 to E9 (Phase 2: design, data, ETL, quality, dimensions, facts, pipeline, reports) | Done, submitted (tag `phase2-submission`) |
| E10 to E12 (reporting layer, analytical SQL, indexing report) | Done, merged |
| E13 (Power BI) | The model, the 51 measures, the theme, the validation and a click-by-click guide are done and tested. **The PBIX itself is not built yet** (section 4) |
| E14 (insights report, presentation) | To do (section 5) |
| E15 (release, QA, submission) | To do (section 6) |

Everything the remaining work needs already exists: the numbers are in the SQL results and the evidence folders, and
the findings are written up in [docs/analytics.md](analytics.md). Nothing below needs new SQL or Python.

## 2. Get it running on your machine (once, about 30 minutes)

You need PostgreSQL 16 or newer (running, with its superuser password), Python 3.11 or newer, Git, and for the
dashboard Power BI Desktop (free, Microsoft Store; Windows only). In PowerShell:

```powershell
git clone https://github.com/JA-Codex/lue-warehouse.git
cd lue-warehouse
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-ci.txt
Copy-Item .env.example .env        # then edit .env: PGPASSWORD (and PGPORT if not 5432)
python scripts/test_connection.py
python scripts/run_ci.py           # ✅ ALL PASSED
```

Then load the data. The dashboard and the reports use the **full profile** (40 buildings, 36 months; several
minutes, heavier on a slow laptop: plug in, close other programs):

```powershell
python scripts/db_reset.py
python etl/run_pipeline.py --profile full      # ✅ 52/52 steps without failure
python scripts/test_powerbi.py                 # ✅ 13/13
```

Each later session: `cd` into the folder and run `.venv\Scripts\Activate.ps1` again. The data stays loaded.
More detail: the README, "Run it from a fresh clone".

## 3. How we work (please keep to it)

- **Never** commit `.env` (it holds passwords), never change anything in `docs/phase1/` (frozen, checked by CI)
  or the DDL in `sql/10_ddl/`.
- One branch per epic or story, for example `e13-pbix` or `e14-14.2-insights-report`, created from an up-to-date
  `main`:

  ```powershell
  git checkout main; git pull
  git checkout -b e14-14.2-insights-report
  # ... work ...
  git add <the files>
  git commit -m "Write the Business Insights Report (US-14.2)"
  git push -u origin e14-14.2-insights-report
  ```
- Open a pull request on GitHub; the `ci` check must pass. Merge with **Create a merge commit**, then delete the
  branch.
- Big binary files (PBIX, PPTX, PDF, MP4) are fine in the repo, but keep the demo video under about 50 MB (or put it
  on Drive and link it).
- Evidence for a story goes in `docs/evidence/us-<story>/`; mark the story done in `docs/stories/README.md`.

## 4. E13: build the Power BI dashboard (owner: Eesha)

**There is no ready-made file to open.** A PBIX can only be made in Power BI Desktop, so it is built by hand, and
[docs/powerbi/README.md](powerbi/README.md) gives every click, step by step, each step ending with a ✅ check. The
slow parts are already done: the 51 measures are pasted in one go (step 4, not typed one by one), the theme is a
file you import, and the expected value of every number is already computed. Expect two to four hours.

| Step of the guide | What you do |
|---|---|
| 0 to 3 | Connect as `lue_reader`, load 15 tables, rename them, paste three filters |
| 4 and 5 | Paste `measures.dax` into DAX query view; set the formats a group at a time |
| 6 and 7 | Create 17 relationships, mark the date table, hide columns; import the theme |
| 8 to 10 | Build the three pages: Executive Overview, Detailed Analysis, Decision Page |
| 11 | Run `validation.dax` and compare with `docs/evidence/us-13.1/expected_measures.csv`; fill in `docs/evidence/us-13.5/README.md` |
| 12 | Save `powerbi/LUE_Dashboard.pbix`, export `powerbi/LUE_Dashboard.pdf`, screenshots in `powerbi/screenshots/` |

If a measure shows an error, a number does not match, or a step does not look like the guide (Power BI's menus move
between versions), take a screenshot and ask; do not change the measures to make a number fit.

Done when (US-13.1 to US-13.5): the three pages are built, every number in the validation table matches, the
PBIX opens on two other teammates' machines (note who in `docs/evidence/us-13.5/README.md`), and the PBIX, the PDF
and the six screenshots are merged. Then update `docs/stories/US-13.1.md` to `US-13.5.md` (Status: Done).

## 5. E14: insights report and final presentation (whole team)

### US-14.1 Shortlist the insights

Most of the work is done: [docs/analytics.md](analytics.md) answers Q1 to Q14 with an interpretation each, and the
six planted patterns (`data/answer_key/planted_patterns.md`) all show in ordinary queries:

| Pattern | Found in | On the full profile |
|---|---|---|
| 1 High-arrears building (GLB03) | Q2; Decision Page D1 | arrears ratio 21.8 percent against 5.8 for the portfolio |
| 2 Slow plumbing vendor (V-001) | Q9; Decision Page D2 | 2.3 times the plumbing average days; SLA breached on 86.5 percent |
| 3 Seasonal move-ins (June to August) | Q6b | peak month 1.43 times the other months |
| 4 Incentives shorten vacancy | Q13; Decision Page D3 | an offer cuts vacancy by more than half |
| 5 Rain-driven leak tickets | Q14 | 6.3 times as many leak tickets on a rainy day or the day after |
| 6 Renewal churn in Karachi | Q8 | lower renewal rate in Karachi |

Pick **three to five** insights, rank them by impact in PKR or days, and write the shortlist in
`docs/evidence/us-14.1/README.md`: for each, the finding, the number, where it comes from (the query label, the
visual, or the file in `docs/evidence/`), the confidence, and for every pattern not used, why. Check each number
against the source before using it.

### US-14.2 Business Insights Report (PDF)

Write `docs/reports/LUE_Business_Insights_Report.pdf` (Word or Google Docs, exported to PDF):

1. An executive summary (half a page): the three to five findings and decisions in one line each.
2. One section per insight: **finding**, **evidence** (a dashboard screenshot or a query result table), **decision
   and expected effect** (the Decision Page texts, `docs/evidence/us-13.1/decisions.txt`, are written this way),
   **caveat**.
3. A clear statement that the data is synthetic, with planted patterns: the conclusions illustrate the method, not
   a real portfolio.

Every figure must match the dashboard and the SQL; take them from the evidence files, not from memory.

### US-14.3 Final presentation and demo

`presentation/LUE_Final_Presentation.pptx`, 12 to 15 slides: the business problem; the design (grain, star
schema: `docs/phase1/`); the architecture and layers; the ETL; the data-quality results
(`docs/reports/LUE_Data_Quality_Report.pdf`); an SCD2 example; the performance results
(`docs/reports/LUE_Indexing_Report.pdf`); the dashboard; the insights and decisions; lessons learned. Most of the
material is in the existing reports and `docs/stories/`.

**Demo script** (on the small profile, so it takes under a minute):

```powershell
python scripts/db_reset.py
python etl/run_pipeline.py --profile small       # the whole pipeline, live
```

Then, in pgAdmin or `psql` on `lue_warehouse`:

```sql
-- a quarantined row and why
SELECT check_name, source_table, rejection_reason, record FROM lue_audit.quarantine LIMIT 5;
-- an SCD2 history: a tenant with more than one version (full profile)
SELECT tenant_code, tenant_type, effective_from, effective_to, is_current FROM lue_dw.dim_tenant
WHERE tenant_code = (SELECT tenant_code FROM lue_dw.dim_tenant WHERE tenant_key > 0
                     GROUP BY 1 HAVING count(*) > 1 LIMIT 1) ORDER BY effective_from;
```

For EXPLAIN ANALYZE before and after an index, show the B5 plans in `docs/evidence/us-12.2/plans/` (17.5 ms to
0.97 ms), then open the dashboard. Rehearse twice with a timer, record a fallback video of the demo, and prepare
answers for: why invoices and payments are separate facts; how late-arriving data is handled; how SCD2 keys are
chosen; why the occupancy fact is partitioned; why the collection rate is cohort-based (D17). The answers are in
`docs/phase1/` and the stories of E6 to E8. Rehearsal notes: `docs/evidence/us-14.3/README.md`.

## 6. E15: release and submission (lead: Ahmad Waqar, with Junaid)

1. **Freeze** (end of day 4 of the final week): after it, only fixes merge.
2. **US-15.1 Clean-machine rebuild** (Ahmad Waqar): on a machine or a new Windows user without the project, follow
   the README from the clone exactly, load the full profile, run `python scripts/run_ci.py` and the database tests,
   and compare the row counts and the key figures (the expected values file of US-13.1) with the recorded ones. Fix
   any missing README step and repeat. Evidence: the log and the comparison in `docs/evidence/us-15.1/`.
3. **US-15.2 Documentation audit** (Junaid): a script that checks the grain sentences, the table and column names,
   the PDFs for placeholder text, the brief-name mapping and the D17 definition agree everywhere (plan, US-15.2).
   Zero mismatches; output in `docs/evidence/us-15.2/`.
4. **US-15.3 Rubric sweep and submission** (whole team): tick every line of the plan's Appendix B, Phase 3, against
   a real file:

   | Deliverable | File |
   |---|---|
   | Analytical SQL, OLAP queries | `sql/60_analytics/analytical.sql`, `olap.sql` |
   | Reporting views | `sql/50_reporting/01_reporting.sql` |
   | Indexing Report | `docs/reports/LUE_Indexing_Report.pdf` |
   | Power BI dashboard | `powerbi/LUE_Dashboard.pbix` |
   | Dashboard screenshots | `powerbi/LUE_Dashboard.pdf` |
   | Business Insights Report | `docs/reports/LUE_Business_Insights_Report.pdf` |
   | Final presentation | `presentation/LUE_Final_Presentation.pptx` |

   Then tag and push:

   ```powershell
   git checkout main; git pull
   git tag phase3-submission
   git push origin phase3-submission
   ```
   and submit, saving the confirmation.

## 7. When something goes wrong

| Problem | What to do |
|---|---|
| `python scripts/run_ci.py` fails | Read the first FAILED line; it names the check and what differs |
| The pipeline stops | `python scripts/db_reset.py`, then run it again (it is safe to repeat). README, "Recovery" |
| The laptop crashed or Git says "not a git repository" | Clone again into a new folder; your pushed branches are safe on GitHub |
| A number does not match | Do not adjust it: compare with `python scripts/powerbi_expected.py` and the evidence files, and ask |
