# LUE Warehouse: Development Plan for Phases 2 and 3

**Epics, user stories and delivery strategy for the Lahore Urban Estates analytics warehouse**

DL3004 Data Warehousing and Business Intelligence · Final Project · Phase 2 (Implementation and ETL, 40 marks) and Phase 3 (OLAP, Optimization and BI, 30 marks) · FAST-NU Lahore

Prepared by: Junaid Minhas (23L-2559), Ahmad Waqar (23L-2634), Hanan Tiwana (23L-2536) and Eesha Khurram (23L-2641)

**Version 1.1 · Revision of the team-approved v1.0 baseline · 4-week delivery · 68 stories in 16 epics**

> **What changed in v1.1.** This revision resolves the contradictions, gaps and scheduling risks found in a full review of v1.0. Every change is listed in Appendix D. Story numbers from v1.0 are unchanged; one story (US-11.6) was added.

---

# Part A. Strategy

## A1. Purpose and scope

This plan converts the Phase 2 and Phase 3 briefs into an executable backlog for the LUE warehouse designed in the Phase 1 pack (version 2.1). Part A sets the strategy. Part B contains 16 epics and 68 user stories, each with a workflow narrative, detailed steps, owner, week, dependencies, acceptance criteria and the evidence that earns marks. Appendices give a story index, a deliverables traceability checklist, the decisions log and the revision log.

| | Description |
|---|---|
| **Fixed inputs (do not redesign)** | 5 business processes, 6 fact tables, 13 conformed dimensions, 14 business questions, 6 source systems (S1 to S6), the declared grain sentences, the physical DDL and the data dictionary from Phase 1 |
| **In scope** | Build the databases and schemas, generate the source data, ingest, validate, clean, load dimensions (SCD) and facts, orchestrate with audit and reconciliation, write the reporting layer, analytical and OLAP SQL, indexing experiments, a 3-page Power BI dashboard, insights report and final presentation |
| **Out of scope** | New dimensional design, real or personal data, streaming, machine learning, dbt and Dagster (a post-semester port), production hosting |
| **Time frame** | Four weeks with a team of four. Weeks 1 to 3 deliver Phase 2 (with a head start on the reporting layer, the Power BI model and the analytical SQL drafts in week 3); week 4 completes Phase 3. The week boundaries assume Phase 2 is due at the end of week 3 and Phase 3 at the end of week 4; replace with the official deadlines when confirmed (open item O1) |

### Where the marks are

| Phase | Mark area | Marks | Epics that earn it |
|---|---|---|---|
| 2 | Database implementation | 10 | E1, E0 |
| 2 | ETL pipeline | 15 | E2, E3, E5, E8 |
| 2 | Surrogate key implementation | 5 | E6, E7 |
| 2 | Data quality validation | 10 | E4, E8, E9 |
| 3 | Analytical SQL | 10 | E10, E11 |
| 3 | OLAP implementation | 5 | E11 |
| 3 | Dashboard | 10 | E13 |
| 3 | Business insights | 5 | E14 |
| 3 | Indexing report and presentation | Confirm in the rubric (open item O3); the four areas above already sum to 30 | E12, E14 |
| All | Consistency, rebuild and submission | protects every mark | E15 |

## A2. Guiding principles

1. **Vertical slice first.** Get one source flowing through staging, one dimension, one fact and one report before widening.
2. **One command rebuilds everything.** `run_pipeline.py` (plus a reset script) rebuilds sources, warehouse, marts and checks from the seeded generator (NFR-01).
3. **Determinism.** The generator uses a fixed seed. Any number in a report can be reproduced, so reports never contradict each other.
4. **Answer key.** The generator records every planted defect and business pattern. Quality checks are proven by matching the key; insights are proven by finding the planted patterns.
5. **Fail loudly, never drop silently.** Bad rows go to quarantine with a reason. Every step logs rows read, inserted, updated and rejected.
6. **Idempotent loads.** Re-running a load leaves every table's data unchanged and inserts no duplicates (precise definition in A3, decision D14).
7. **Evidence as you build.** Capture the screenshot or query output the moment a story is accepted.
8. **Documents are the contract.** Grain sentences, table and column names stay identical across the dictionary, DDL, scripts and reports (NFR-07). Change the generator `tools/model.py` and regenerate; never edit generated files by hand.
9. **Brief names win where the brief is explicit.** Where the briefs name a schema, view or deliverable, use that exact shape, or provide an alias or a documented mapping that the instructor has confirmed (open item O4).
10. **Parallel by contract.** Consumers build against published table contracts, not unfinished code, so week 2 is not a strictly serial chain.

## A3. Key technical decisions

| # | Decision | Choice | Reason |
|---|---|---|---|
| D1 | Databases | Two on one PostgreSQL 16+ instance: `lue_source` (schema `src_pms`, system S1) and `lue_warehouse` | Cross-database separation makes ingestion a real extract |
| D2 | Warehouse schemas | `lue_staging`, `lue_dw`, `lue_reporting`, `lue_audit` | Brief requires `project_staging`, `project_dw`, `project_reporting`; audit is the pack's audit layer |
| D3 | Bronze and Silver | Both in `lue_staging`: raw tables prefixed `brz_`, cleaned tables prefixed `stg_` | Matches the brief's `stg_customer` style and the 11-section diagram |
| D4 | Gold | Marts and views in `lue_reporting`: `mart_*` materialized views, `vw_*` views, and `vw_dim_*` read-only views of the dimensions needed for slicers | Power BI connects as `lue_reader`, which can read only `lue_reporting` |
| D5 | Language split | Python for generation, ingestion, orchestration; SQL for validation, transformation, SCD and loads | Brief grades SQL ETL logic |
| D6 | Surrogate keys | Integer identity per dimension declared `GENERATED BY DEFAULT AS IDENTITY`, so special members -1 (Unknown) and -2 (Not applicable, vacant) can be inserted explicitly; the identity sequence then starts at 1 | Keeps facts loadable under late-arriving data |
| D7 | SCD2 pattern | Expire-and-insert with `effective_from`, `effective_to` (exclusive, 9999-12-31 while current) and `is_current` | Pack's SCD policy |
| D8 | Fact key lookup | Join on business key and `event_date >= effective_from AND event_date < effective_to` | Facts reference the dimension version valid at event time |
| D9 | Incremental strategy | Watermark per source and table in `lue_audit.etl_watermark`; occupancy re-derives the last 35 days each run (NFR-08) | Handles late and corrected data without full reloads |
| D10 | Partitioning | `fact_unit_occupancy_daily` partitioned monthly by `snapshot_date_key` (48 partitions to 2027-06) plus a default partition | About 1.97 million rows; partition pruning is a clear before and after story |
| D11 | Orchestration | `run_pipeline.py` runs ordered steps with one `run_id`, writes `lue_audit.etl_run_log`, stops on a failed critical step | Matches the brief's pipeline order |
| D12 | Weather source | S5 is downloaded once to `data/weather_cache.json`; the pipeline reads the cache | Reproducible without network |
| D13 | Dates | `DATE` only, no time zones; business calendar in PKT, fiscal year July to June | Pack design |
| D14 | Idempotency definition | A rerun on unchanged inputs inserts, updates and rejects zero rows in every step, and table content hashes are identical before and after. The occupancy 35-day refresh is the one declared exception: it rewrites rows, but the resulting values must be identical | Resolves the conflict between "zero rows" and NFR-08 |
| D15 | Duplicate policy | DQ-03 quarantines only exact duplicates (same natural key and same values) within a batch, keeping the first by ingestion order. Conflicting duplicates (same key, different values) are warned, not rejected, and continue to staging where the survivorship rule (latest `updated_at`, then latest `loaded_at`) keeps one version | One rule per stage, no overlap between E4 and E5 |
| D16 | File-source rerun policy | S2, S3, S4 and S6 are full-snapshot files. A file whose checksum already exists in `lue_audit.lineage` as loaded is skipped. A new or changed file lands as a new batch (append, never truncate); staging survivorship resolves repeated keys | Prevents duplicate bronze rows on rerun |
| D17 | Collection rate definition | **Collection rate (cohort)** = amount paid against invoice lines due in month M, divided by amount billed for lines due in month M, measured as of the data window end. **Cash received** = amount paid with paid date in month M. Q1, `vw_monthly_collections`, `mart_collections_monthly` and the Power BI measure Collection Rate all use the cohort definition; Cash Received is a separate, labelled measure | Ensures marts, views and Q1 reconcile |
| D18 | Brief-name aliases | Besides the renamed views, create thin alias views `vw_monthly_sales`, `vw_customer_analysis` and `vw_product_performance` in `lue_reporting` that select from the LUE views | Cheap insurance if the marker searches for the brief's exact names |
| D19 | Cut-line schema policy | A cut feature (for example S5 or the coverage fact) keeps its DDL deployed and its table empty or minimally loaded; the smoke test counts stay 13 / 6 / 41 / 48; the weather key defaults to -1. The cut is recorded in the README | Keeps the smoke test and foreign keys valid |
| D20 | Baseline definition | "No secondary indexes" means no indexes beyond primary keys and unique constraints; PK and unique-constraint indexes are present in the baseline and are stated as such in the indexing report | Honest before and after comparison |

## A4. Architecture mapped to the 11 sections

| Section of reference diagram | Implementation | Epic |
|---|---|---|
| 1. Data sources | S1 PostgreSQL, S2 Excel, S3 CSV, S4 JSON, S5 REST (cached), S6 CSV | E2 |
| 2. Pipeline orchestration | `run_pipeline.py` | E8 |
| 3. Bronze (raw landing) | `lue_staging.brz_*` with `batch_id`, `source_system`, `loaded_at` | E3 |
| 4. Data quality and validation | Seven ordered checks DQ-01 to DQ-07 | E4, E8 |
| 4b. Reject and quarantine | `lue_audit.quarantine` | E4 |
| 5. Silver (cleaned) | `lue_staging.stg_*`, incremental by watermark | E5 |
| SCD processing | SQL dimension loaders (Types 0, 1, 2, inferred members) | E6 |
| 6. Dimensional warehouse | 13 dimensions and 6 facts in `lue_dw` | E6, E7 |
| 7. Warehouse performance | Monthly partitions, indexes, `EXPLAIN ANALYZE` | E1, E12 |
| 8. Gold marts | `mart_*`, `vw_*`, `vw_dim_*` in `lue_reporting` | E10 |
| 9. Analytics and BI | Analytical SQL, ROLLUP and CUBE, window functions, Power BI | E11, E13 |
| 10. Audit, monitoring and reconciliation | `etl_run_log`, `reconciliation`, `lineage`, `quarantine` | E8 |
| 11. Metadata and lineage | `lue_audit.lineage`, data dictionary | E8, E15 |

## A5. Repository layout

```
lue-warehouse/
  README.md                 how to build, run, test, with brief-name mapping
  docs/phase1/              the Phase 1 pack (frozen v2.1 baseline)
  docs/contracts/           generated table and key contracts, refreshed weekly
  docs/reports/             generated PDFs: cleaning, data quality, indexing, insights
  sql/
    00_setup/               databases, roles, schemas, reset
    10_ddl/                 dimension, fact, audit DDL, partitions
    20_staging/             staging.sql: brz_ and stg_ tables, cleaning
    30_dimensions/          dimensions.sql: dimension and SCD loaders
    40_facts/               facts.sql: fact loaders
    50_reporting/           views.sql, marts.sql
    60_analytics/           analytical.sql, olap.sql
    70_performance/         benchmark queries, index scripts, before and after
    90_tests/               grain, integrity, reconciliation checks
  etl/
    generate_data.py        seeded generator and answer key writer
    refresh_weather.py      one-time weather cache download
    ingest/                 one module per source system
    run_pipeline.py         orchestrator
    reports/                report generators for PDFs
  data/                     generated source files, weather cache, answer key
  powerbi/                  PBIX and screenshots
  presentation/             final slides
  Makefile                  make setup, rebuild, test, reports
```

## A6. Team and ways of working

### Team and tracks

| Person | Track | Primary responsibility | Backup for |
|---|---|---|---|
| Junaid | Pipeline and quality | Repository and CI, ingestion framework and S1/S4/S5 ingestors, S2/S3/S6 ingestors, quarantine engine and DQ-04 to DQ-06, orchestrator, idempotency and full-volume runs, maintenance fact, grain and orphan checks, query optimisation and the indexing report | Hanan (occupancy fact), Eesha (reporting layer) |
| Ahmad Waqar | Data and staging | Seeded generator, staging transformations, invoice and payment facts, Phase 2 reports, analytical SQL (maintenance, owner, incentive and weather questions, window analytics), clean-machine rebuild | Junaid (orchestrator), Hanan (finance SQL) |
| Hanan | Warehouse modelling | Alignment of the design pack, databases and DDL, master data, tenant SCD2, occupancy fact, reconciliation, finance and occupancy analytics, ROLLUP and CUBE | Ahmad Waqar (occupancy fact), Eesha (SCD2 engine) |
| Eesha | Analytics and BI | Environment, date and reference dimensions, audit tables and reset script, ticket, incentive and weather generation, DQ-01 to DQ-03, SCD2 extension and remaining dimensions, lease event and coverage facts, reporting views and marts, Power BI dashboard | Junaid (ingestion), Hanan (SCD2) |

The whole team jointly owns the baseline freeze (US-0.2), the Phase 2 submission (US-9.3), the Decision Page (US-13.4), the insights report, the presentation and the final submission sweep. Individual stories can be swapped; record any change on the board so reviewers stay correct.

**Workload note (v1.1).** In v1.0, Junaid carried 18 stories, almost all on the critical path, while Eesha was light in weeks 1 and 2. US-4.2 (DQ-01 to DQ-03) now belongs to Eesha, and every track has a named backup so no module has a single point of failure.

### Ways of working

| Topic | Agreement |
|---|---|
| Cadence | One-week sprints; a 15-minute daily sync (yesterday, today, blockers); an integration build every Friday: run `make rebuild` on the small profile from `main` and fix whatever breaks before the weekend |
| Review rotation | Reviews are optional and not enforced by the ruleset (team decision, 7 November 2026). If a review is wanted: Junaid reviews Hanan, Hanan reviews Ahmad Waqar, Ahmad Waqar reviews Eesha, Eesha reviews Junaid |
| Pairing | SCD2 engine (Hanan with Eesha), occupancy fact (Hanan with Ahmad Waqar), orchestrator (Junaid with Hanan), ingestion framework hand-over (Junaid with Eesha) |
| Interface contracts | Bronze and staging table specifications and dimension keys are generated from `tools/model.py` and published in `docs/contracts/` at the start of each week. Consumers build against the contract |
| Branching | `main` is always runnable. Feature branches named `epic-story` (for example `e6-6.2-tenant-scd2`), merged by pull request once `ci` passes |
| Definition of Ready | Dependencies done or contract published, acceptance criteria clear, test data available |
| Demo | End of each week: run `make rebuild` and show that week's evidence |
| Story format | Owner, week, dependencies, user story sentence, detailed approach, acceptance criteria, evidence to capture |

## A7. Four-week plan

| Week | Focus | Epics | Exit criterion |
|---|---|---|---|
| 1 | Foundation, sources and bronze | E0, E1, E2, E3 | Warehouse deploys empty from scripts; all six sources generated and landed in bronze with counts reconciled; repository and CI running |
| 2 | Quality, staging and dimensions (overlapped by contract) | E4, E5, E6 | Planted defects caught per the answer key; staging loads incrementally; all 13 dimensions load; SCD2 proven |
| 3 | Facts, pipeline, Phase 2 package, Phase 3 head start | E7, E8, E9; E10; US-13.1; US-11.6 | One-command full run; reconciliation clean; Phase 2 package submitted; marts and Power BI connection working; analytical SQL drafts running on the small profile |
| 4 | Analytics, optimisation, dashboard, insights, release | E11, E12, E13, E14, E15 | All 14 questions answered; ROLLUP and CUBE done; indexing evidence captured; three dashboard pages validated; release candidate frozen mid-week; Phase 3 submitted; clean-machine rebuild passes |

**Critical path.** Generator and bronze (week 1) → staging and dimensions (week 2) → facts (week 3) → reconciliation and full-volume run (week 3) → marts (week 3) → analytics and dashboard (week 4). Anything off this path (reports, benchmark preparation, dashboard wireframes, the presentation outline) runs in parallel and must never block it.

**Overlap rules that shorten the week 2 chain (v1.1).**
- Staging (US-5.1) starts as soon as US-4.1 (the engine) and the bronze contract exist; it picks up quarantine results as DQ-04 to DQ-06 land.
- Dimension loaders (US-6.1) start against the staging contract; tenant SCD2 can be developed on the small profile before US-5.1 is fully accepted.
- Eesha drafts the dashboard wireframes and measure list in weeks 1 and 2 and confirms Power BI Desktop connects to the PostgreSQL warehouse.

**Buffers built into the plan (v1.1).**
- Week 3: a full-volume trial load of the occupancy fact (US-7.3) is run by mid-week, before the formal full run (US-8.4). Report generators (US-9.1, US-9.2) are built and tested against small-profile evidence first, and simply re-run after US-8.4.
- Week 4: a **release candidate freeze at the end of day 4 of the final week**. After the freeze only fixes are merged. US-15.1 (clean-machine rebuild) and US-15.2 (consistency audit) then run in parallel, leaving the last day as slack.

## A8. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Phase 2 scope (6 sources, SCD2 on four dimensions, 6 facts) is large for three weeks | Medium | High | Four parallel tracks, vertical slice first, cut-lines in A9, Friday integration builds |
| R2 | Generator produces unrealistic data, so reports look flat | Medium | High | Calibrated distributions; planted patterns; story 2.6 validates them before loading |
| R3 | SCD2 date-aware lookups mis-assign facts | Medium | High | Dedicated tests in E6 and E7; before and after tenant change evidence; pair on the engine |
| R4 | Occupancy fact (1.97M rows) loads slowly, especially the arrears measure | Medium | Medium | Set-based `generate_series` and `COPY`; pre-aggregate billed and paid by lease and day and use cumulative window sums, never correlated subqueries; monthly partitions; trial full-volume load by mid-week 3 |
| R5 | Documents drift from code | Medium | Medium | Single source `tools/model.py`; E15 consistency audit |
| R6 | Power BI model issues discovered late | Low | High | Connection and stub page in week 3 (US-13.1); slicer dimensions exposed as `vw_dim_*` views |
| R7 | A teammate becomes unavailable | Low | High | Named backups (A6); optional review rotation; any person can run the full build |
| R8 | Integration breaks between parallel tracks | Medium | High | Interface contracts; Friday integration build; `main` must always run |
| R9 | Week 4 overload | Medium | High | US-11.6 drafts analytical SQL in week 3; dashboard pages built on marts; release candidate freeze mid-week 4 |
| R10 | Brief's exact schema or view names are expected by the marker | Medium | Medium | Alias views (D18), README mapping, instructor confirmation (O4) |
| R11 | File-source reruns duplicate bronze rows | Medium | Medium | Checksum-based skip and append policy (D16), tested in US-3.3 |

## A9. Cut-lines and stretch policy

1. **Never cut:** one-command ETL, quarantine and reconciliation, SCD2 on tenant, grain and orphan checks, the three required dashboard pages and the Decision page.
2. **Cut first:** S5 weather and question Q14, then S6 incentives, Q13 and the coverage fact. Apply decision D19: DDL, foreign keys and the smoke test stay unchanged; the affected tables stay empty and the weather key resolves to -1.
3. **Downgrade next:** SCD2 on unit, vendor and maintenance category to Type 1 (document the change).
4. **Stretch (only after the above are done):** extra dashboard pages, ROLAP, MOLAP and HOLAP comparison for Q1, additional indexes.

## A10. Global Definition of Done

A story is done only when all of these are true:

- Code is merged to `main` through a pull request with `ci` passing, and `make rebuild` still passes.
- Acceptance criteria are met and the stated evidence is captured and stored under `docs/` or `powerbi/`.
- Tests for the story exist and pass (grain, integrity or reconciliation as applicable).
- Names and grain sentences match the Phase 1 pack.
- The audit log shows the step ran with row counts.
- The README or story note records any deviation from the brief or the pack.

## A11. Epic overview

| Epic | Name | Week | Lead | Stories | Brief section |
|---|---|---|---|---|---|
| E0 | Foundation and Phase 1 closure | 1 | Whole team | 4 | Prerequisite |
| E1 | Database implementation | 1 | Hanan (with Eesha) | 5 | P2 section 2 |
| E2 | Synthetic source data generator | 1 | Ahmad Waqar | 6 | P2 section 1 |
| E3 | Ingestion and bronze landing | 1 | Junaid | 4 | P2 section 3 |
| E4 | Data quality validation and quarantine | 2 | Junaid (with Eesha) | 4 | P2 section 6 |
| E5 | Staging transformations | 2 | Ahmad Waqar | 4 | P2 section 3 |
| E6 | Dimension loading and surrogate keys | 2 | Hanan (with Eesha) | 5 | P2 section 4 |
| E7 | Fact loading | 3 | Hanan | 6 | P2 section 5 |
| E8 | Orchestration, audit and reconciliation | 3 | Junaid | 4 | P2 section 6, pipeline |
| E9 | Phase 2 reports and packaging | 3 | Ahmad Waqar | 3 | P2 deliverables |
| E10 | Reporting layer | 3 | Eesha | 3 | P3 section 2 |
| E11 | Analytical SQL and OLAP | 3 to 4 | Hanan (with Ahmad Waqar) | 6 | P3 section 1 |
| E12 | Query optimization | 4 | Junaid | 3 | P3 section 3 |
| E13 | Power BI dashboard | 3 to 4 | Eesha | 5 | P3 section 4 |
| E14 | Business insights and final presentation | 4 | Whole team | 3 | P3 deliverables |
| E15 | Release, QA and submission | 4 | Ahmad Waqar | 3 | Cross-cutting |

---

# Part B. Epics and user stories

## E0. Foundation and Phase 1 closure

**Week 1 · Lead: Whole team**

**Epic workflow.** Phase 1 produced a design pack that is almost aligned with the Phase 2 and 3 briefs but not exactly: schema names differ, author names are placeholders and no repository exists. This epic first updates the single generator (`tools/model.py`) so the vocabulary matches the briefs, regenerates the DDL, diagrams, PDFs and dictionary in one pass, freezes the result as the v2.1 baseline, creates the repository and automation, and makes every machine able to run the same environment. The outcome is a clean, versioned starting point from which any developer can clone, set up and deploy the empty warehouse in minutes.

### US-0.1 Align the Phase 1 pack with the briefs

**Owner:** Hanan · **Week:** 1 · **Depends on:** none

**Story.** As the project team, we want the design pack to use the schema and naming vocabulary of the Phase 2 and 3 briefs, so that implementation scripts and documents never disagree.

**Detailed approach.**
1. In `tools/model.py` map the schema names: `bronze` and `silver` to `lue_staging` (tables prefixed `brz_` and `stg_`), `dw` to `lue_dw`, `gold` to `lue_reporting`, `audit` to `lue_audit`; keep `src_pms` inside `lue_source`.
2. Update the architecture and layer text so the diagram, proposal, BRD and dictionary use the new names.
3. Add a README mapping table: brief name (`project_staging`, `project_dw`, `project_reporting`, `vw_monthly_sales`, `vw_customer_analysis`, `vw_product_performance`) against the LUE name, noting that alias views with the brief's exact view names exist (D18).
4. Regenerate the DDL, Mermaid diagrams (mermaid-cli 11.4.2), PDFs and the dictionary, then run the DDL parse check.
5. Record the team decision that renamed equivalents are acceptable, and mark it **pending instructor confirmation** (O4).

**Acceptance criteria.**
- A regex search for old schema names that are not preceded by a letter or underscore, for example `(?<![A-Za-z_])(bronze|silver|gold|dw|audit)\.`, returns nothing in generated artifacts (so `lue_dw.` and `lue_audit.` do not count as hits).
- DDL parses; counts remain 13 dimensions, 6 facts and 4 pack audit tables.
- The README mapping table exists.

**Evidence.** Before and after search output; the mapping table.

### US-0.2 Complete and freeze the Phase 1 baseline

**Owner:** Whole team · **Week:** 1 · **Depends on:** US-0.1

**Story.** As the team, we want the Phase 1 pack finalized with real author details and frozen, so that the submitted design is the exact design we build.

**Detailed approach.** Set `AUTHORS` in `tools/model.py` to Junaid, Ahmad Waqar, Hanan and Eesha with their roll numbers (**roll numbers must be collected on day 1; see O2**), regenerate all PDFs once more, tag the commit `phase1-v2.1-final` and copy the pack to `docs/phase1/`. After this point, design changes require a written change note in the README and a regeneration.

**Acceptance criteria.** No placeholder text (including any roll-number prompt on a title page) remains in any PDF or in this plan; the tag exists; `docs/phase1/` matches the submitted files.

**Evidence.** Text search of the PDFs for placeholders returns zero results.

### US-0.3 Create the repository, branching and quality gates

**Owner:** Junaid · **Week:** 1 · **Depends on:** US-0.2

**Story.** As developers, we want a structured repository with branch protection and automatic checks, so that broken code never reaches `main`.

**Detailed approach.**
1. Create the GitHub repository using the layout in A5 and add a `.gitignore` for generated data (except the weather cache), virtual environments and credentials.
2. Protect `main`: pull request required and the `ci` status check must pass. A review is optional (team decision, 7 November 2026).
3. Add a `Makefile` with targets `setup`, `rebuild`, `test`, `reports` and `db-reset`, even if stubs now.
4. Add a GitHub Actions workflow running SQL syntax checks (pglast parse) and Python linting on each push.
5. Add a pull request template with the Definition of Done checklist from A10.

**Acceptance criteria.** A test pull request is blocked until the `ci` check passes; the workflow passes on `main`; the template appears.

**Evidence.** Screenshot of the passing workflow and branch protection settings.

### US-0.4 Provide a reproducible local environment

**Owner:** Eesha · **Week:** 1 · **Depends on:** US-0.3

**Story.** As any team member, I want to set up the same environment from the README in under thirty minutes, so that results do not depend on whose machine runs them.

**Detailed approach.** Document and script: PostgreSQL 16 or newer and pgAdmin 4; a Python 3.11 or newer virtual environment from `requirements.txt` (pandas, numpy, Faker, psycopg2-binary, requests, openpyxl, reportlab); an `.env.example` holding host, port, database names and credentials (never committed); and a connection test script that prints the server version and creates a throwaway table. Record the Power BI Desktop version used.

**Acceptance criteria.** All four team members run the setup from scratch and pass the connection test; the README lists versions.

**Evidence.** Four screenshots of the passing connection test (one per team member).

---

## E1. Database implementation

**Week 1 · Lead: Hanan (with Eesha)**

**Epic workflow.** This epic builds the empty warehouse: the two databases, the roles and the four schemas; then the 13 dimensions with keys and special members; then the 6 facts with foreign keys and monthly partitions. Reference data follows (date dimension and small static dimensions), then the audit tables and a reset script. The epic deliberately creates no secondary performance indexes beyond primary and unique-constraint indexes (D20): that state is the baseline for the Phase 3 comparison. The outcome is a database that deploys from scripts in a couple of minutes and proves its own structure with a smoke test. This epic carries the 10 marks for database implementation.

### US-1.1 Create databases, roles and schemas

**Owner:** Hanan · **Week:** 1 · **Depends on:** US-0.4

**Story.** As a developer, I want the databases, roles and schemas created by an idempotent script, so that any machine gets the same structure.

**Detailed approach.**
1. In `sql/00_setup/` create the databases `lue_source` (holding schema `src_pms`) and `lue_warehouse`.
2. Create roles: `lue_etl` (owns all warehouse schemas, used by the pipeline) and `lue_reader` (read-only on `lue_reporting` only, used by Power BI).
3. In `lue_warehouse` create the schemas `lue_staging`, `lue_dw`, `lue_reporting`, `lue_audit` and grant privileges accordingly. Because `lue_reader` cannot see `lue_dw`, slicer dimensions are exposed through `vw_dim_*` views (built in US-10.1).
4. Make every statement safe to re-run and set a sensible `search_path` for each role.

**Acceptance criteria.**
- Running the script twice produces no errors and no duplicates.
- `lue_reader` can read `lue_reporting` but cannot write anywhere and cannot read `lue_dw`, `lue_staging` or `lue_audit`.
- The four schemas exist with the exact names in D2.

**Evidence.** `\dn` and `\du` screenshots; a failed-write test and a failed cross-schema read by `lue_reader`.

### US-1.2 Deploy dimension DDL with keys and special members

**Owner:** Hanan · **Week:** 1 · **Depends on:** US-1.1

**Story.** As a data modeler, I want all 13 dimensions deployed with surrogate keys, natural keys and constraints, so that facts and SCD logic have a sound foundation.

**Detailed approach.**
1. Run the generated dimension DDL from the Phase 1 pack (renamed to `lue_dw`), with surrogate keys declared `GENERATED BY DEFAULT AS IDENTITY` (D6).
2. Confirm each dimension has an identity surrogate key as primary key, the natural business key, and lineage columns (`source_system`, `batch_id`, `loaded_at`).
3. Add constraints for SCD2 dimensions: unique `(natural key, effective_from)`, a check that `effective_to > effective_from`, and a partial unique index allowing only one `is_current = true` row per natural key.
4. Insert the special members explicitly: key -1 labelled Unknown in every dimension and key -2 labelled Not applicable (vacant) in tenant, then restart each identity sequence at 1 so loaded members never collide with special keys.

**Acceptance criteria.**
- 13 dimensions exist; each has a primary key, a natural key and special members.
- Two current rows for one natural key fail; an inverted effective range fails.
- The first loaded member of any dimension receives key 1 (not an error and not a collision).

**Evidence.** DDL listing, the constraint violation messages, and a query showing the special members.

### US-1.3 Deploy fact DDL, foreign keys and partitions

**Owner:** Hanan · **Week:** 1 · **Depends on:** US-1.2

**Story.** As a data engineer, I want the six fact tables created with their foreign keys and the occupancy fact partitioned by month, so that loads are validated and large scans can be pruned.

**Detailed approach.**
1. Run the fact DDL for `fact_rent_invoice_line`, `fact_payment`, `fact_unit_occupancy_daily`, `fact_maintenance_request`, `fact_lease_event` and `fact_vacancy_incentive_coverage`.
2. Create foreign keys to each participating dimension (41 in total) and primary keys: surrogate fact keys on transactional and accumulating facts, composite `(snapshot_date_key, unit_key)` on the occupancy snapshot and `(coverage_date_key, unit_key, incentive_key)` on the coverage fact.
3. Create the 48 monthly partitions from 2023-07 to 2027-06 plus a default partition.
4. Create no secondary indexes; record in the README that primary and unique-constraint indexes are the intentional Phase 3 baseline (D20).

**Acceptance criteria.**
- 6 fact tables, 41 foreign keys and 48 partitions (plus the default) exist.
- A row with a nonexistent dimension key is rejected; a row dated outside every partition goes to the default partition.

**Evidence.** Catalog queries showing counts; rejected insert message.

### US-1.4 Load the date dimension and static reference dimensions

**Owner:** Eesha · **Week:** 1 · **Depends on:** US-1.2

**Story.** As an analyst, I want a complete calendar and the small static dimensions loaded up front, so that every fact can resolve its date and code keys.

**Detailed approach.**
1. Generate `dim_date` for 2023-07-01 to 2027-06-30 with `generate_series`: integer `date_key` (`YYYYMMDD`), day, week, month, quarter, year, fiscal year and period (July to June), weekday flag and a holiday flag initialised to false (filled in US-6.4).
2. Load `dim_payment_method` (cash, cheque, bank transfer, Raast, JazzCash, Easypaisa) with channel groups (cash, bank, mobile wallet, instant payment).
3. Load `dim_charge_type` (rent, service charge, late fee, utility) with category roll-ups, and `dim_lease_event_type` (signed, renewed, terminated, notice given).
4. Load `dim_request_flags` as every combination of its three flags (8 rows) plus the Unknown member.

**Acceptance criteria.**
- `dim_date` has 1,461 date rows plus special members; no gaps; fiscal periods correct at the July boundary.
- Static dimensions contain exactly the agreed members.

**Evidence.** Row counts; a query showing 30 June 2026 and 1 July 2026 in different fiscal years.

### US-1.5 Create audit tables, the watermark table and the reset script

**Owner:** Eesha · **Week:** 1 · **Depends on:** US-1.1

**Story.** As an operator, I want audit tables and a one-command reset, so that every run is logged and we can rebuild from nothing during development.

**Detailed approach.**
1. Deploy the four audit tables from the pack: `etl_run_log`, `quarantine`, `reconciliation` and `lineage`.
2. Add one control table, `lue_audit.etl_watermark` (source system, table name, last watermark value, updated at). This is a Phase 2 implementation addition, not a design change; record it in the README and the data dictionary (open item O5).
3. Write `sql/00_setup/reset.sql` and `make db-reset`, which drop and recreate the warehouse schemas and re-run the deployment steps in order.
4. Write a smoke test verifying 13 dimensions, 6 facts, 4 pack audit tables plus the watermark table, 41 foreign keys and 48 partitions (counts stay fixed even after a cut-line, per D19).

**Acceptance criteria.**
- `make db-reset` completes in a couple of minutes and leaves the smoke test green; running it twice gives the same result.

**Evidence.** Smoke test output; terminal screenshot of a clean reset.

---

## E2. Synthetic source data generator

**Week 1 · Lead: Ahmad Waqar (with Hanan and Eesha)**

**Epic workflow.** The briefs allow public datasets or Python-generated data. LUE uses a seeded generator so we control volume, realism and, crucially, the defects and patterns needed to prove quality checks and insights. Data is built in dependency order: framework and configuration; master data; leases and invoices; payments and settlements; tickets, incentives and weather; and finally the defect injector and planted patterns, which write an answer key. Each stage writes its native source form: S1 tables in `lue_source.src_pms`, S2 as an Excel workbook, S3 and S6 as CSV, S4 as JSON and S5 as a cached API snapshot. Two profiles exist: small (2 buildings, 3 months) for fast development and full (about 40 buildings, 1,800 units, 36 months). The outcome is deterministic, realistic source data plus an answer key later epics test against.

### US-2.1 Build the generator framework, configuration and seeding

**Owner:** Ahmad Waqar · **Week:** 1 · **Depends on:** US-0.4

**Story.** As a developer, I want a configurable, seeded generator skeleton, so that every run is reproducible and scalable.

**Detailed approach.**
1. Create `etl/generate_data.py` with a config file holding portfolio size, the date window (2023-07-01 to 2026-06-30), volume targets, defect rates and the random seed.
2. Use a single seeded NumPy generator passed to every sub-generator; never use unseeded randomness.
3. Provide flags `--profile small|full`, `--seed` and `--out`; create output folders `data/s1` to `data/s6`.
4. Add a determinism test: two runs with the same seed produce byte-identical files (compare hashes).

**Acceptance criteria.** The small profile completes in under a minute; same seed gives identical hashes; a different seed gives different data.

**Evidence.** Hash comparison output.

### US-2.2 Generate master data

**Owner:** Hanan · **Week:** 1 · **Depends on:** US-2.1

**Story.** As a data engineer, I want realistic master data across all sources, so that facts have meaningful context.

**Detailed approach.**
1. Build 4 cities with localities and about 40 buildings with class and age; about 1,800 units with floor, type (apartment, office, shop), area, bedrooms and furnished flag.
2. Build owners and an ownership register with periods (some units change owner), vendors with trade and rating bands (some change), maintenance categories with default SLA hours, and a holiday register, all in the S2 workbook, one sheet per register.
3. Build tenants for S1 with synthetic names from curated lists, phone formats, employer sector, contact channel and tenant type. No real personal data (NFR-06).
4. Write S1 reference tables into `lue_source.src_pms` with source `updated_at` columns.

**Acceptance criteria.** Counts match the config; every unit belongs to a building and city; every ownership period is contiguous with no overlap; the workbook has the expected sheets.

**Evidence.** Count queries; workbook screenshot.

### US-2.3 Generate leases, lease events and invoices

**Owner:** Ahmad Waqar · **Week:** 1 · **Depends on:** US-2.2

**Story.** As a data engineer, I want a realistic lease lifecycle with monthly invoicing, so that occupancy, invoicing and lease event facts have consistent history.

**Detailed approach.**
1. Simulate leases per unit over 36 months: residential leases of 11 months, longer terms for commercial; renewals with rent escalation; terminations; vacancy gaps; no overlapping leases on a unit.
2. Emit lease events (signed, renewed, terminated, notice given) in S1.
3. Generate monthly invoices per active lease with lines per charge type (rent always; service charge for most; occasional utility), a due date rule (for example the 10th) and mid-lease rent changes.
4. Target about 1,500 active leases at any time and about 130,000 invoice lines.

**Acceptance criteria.** Zero overlapping leases per unit; invoice totals equal lease rent times months active (except planted rent changes); seasonal move-in peaks visible.

**Evidence.** Overlap check query; monthly lease start histogram.

### US-2.4 Generate payments and settlements

**Owner:** Ahmad Waqar · **Week:** 1 · **Depends on:** US-2.3

**Story.** As a data engineer, I want tenant payment behaviour modelled with realistic channels and delays, so that collection and arrears analytics are meaningful.

**Detailed approach.**
1. Assign each tenant a behaviour profile: on time, occasionally late, chronically late, partial payer, defaulter.
2. Generate S1 payments and allocations to invoice lines, including partial payments, one payment split across lines, late payments after period end and bounced cheques that create reversals (negative amounts).
3. Generate S3 bank and wallet settlements: one record per electronic payment with a settlement lag by channel, a fee and a reference matching the S1 payment reference; leave a small share unmatched on purpose.
4. Target about 60,000 payments.

**Acceptance criteria.** Each payment reference is unique; total allocated never exceeds the payment amount; behaviour profiles show the intended late-day distributions; settlement lags differ by channel.

**Evidence.** Days-late distribution by profile; settlement lag by channel.

### US-2.5 Generate tickets, incentives and weather

**Owner:** Eesha · **Week:** 1 · **Depends on:** US-2.2

**Story.** As a data engineer, I want maintenance tickets, leasing incentives and a weather history, so that the remaining processes have data.

**Detailed approach.**
1. Generate about 6,000 S4 tickets as JSON with a nested status history (raised, assigned, resolved, verified), category, vendor, emergency and recurring flags, estimated and actual cost.
2. Generate the S6 incentive log as CSV: incentive type (for example a free first month), unit, start and end dates.
3. Write `etl/refresh_weather.py` to download daily temperature and rainfall for the four cities from the Open-Meteo historical API once, save `data/weather_cache.json` and commit it. The pipeline reads only the cache.

**Acceptance criteria.** Every ticket has a valid unit, category and vendor reference (before defect injection); incentive windows lie within the window and reference real units; the weather cache covers every city and every day.

**Evidence.** Sample JSON ticket; weather cache coverage check.

### US-2.6 Inject defects, plant business patterns and write the answer key

**Owner:** Ahmad Waqar · **Week:** 1 · **Depends on:** US-2.3, US-2.4, US-2.5

**Story.** As a tester, I want controlled defects and known business patterns recorded in an answer key, so that quality checks and later insights can be proven correct.

**Detailed approach.**
1. Inject defects at configurable rates (about 1 to 3 percent): exact duplicates, conflicting duplicates (same key, different values), nulls in required columns, inconsistent text (' lahore ', 'LAHORE'), wrong data types, out-of-range dates, orphan references, late-arriving payments and tenant references, duplicate settlement lines, tenant attribute changes (for SCD2) and mid-lease rent changes.
2. Write `data/answer_key` listing every defect with source, table, record identifier, defect type and the expected handling (reject, warn, repair), plus totals per type.
3. Plant business patterns and document expected effects in `planted_patterns.md`: one building with high arrears, one slow vendor, seasonal move-in peaks, an incentive that shortens vacancy, rain-driven leak tickets, and higher renewal churn in one city.
4. Verify each pattern with a quick pandas check.

**Acceptance criteria.** Answer key totals are reproducible with the same seed; each planted pattern shows its intended effect size.

**Evidence.** Answer key summary table; pattern verification output.

---

## E3. Ingestion and bronze landing

**Week 1 · Lead: Junaid**

**Epic workflow.** Ingestion moves data from each source into bronze without changing it. A shared framework opens a batch, records it in the run log, reads a source, stamps every row with `batch_id`, `source_system` and `loaded_at`, writes it as-is into a `brz_` table, and closes the batch with row counts. Specific ingestors cover the four source types: the S1 PostgreSQL extract with a watermark, the file sources (S2, S3, S6) governed by the checksum policy D16, and the S4 JSON tickets with the S5 weather cache. The epic ends with a completeness check: for every table, rows read equal rows landed. The outcome is a faithful, auditable, rerun-safe copy of all six sources.

### US-3.1 Build the ingestion framework

**Owner:** Junaid · **Week:** 1 · **Depends on:** US-1.5, US-2.1

**Story.** As a developer, I want a shared ingestion framework, so that every source loads consistently with logging and error handling.

**Detailed approach.**
1. Create `etl/ingest/base.py` with helpers to open and close a batch (insert and update `etl_run_log`), obtain connections from environment settings, and bulk-load a DataFrame using `COPY`.
2. Add the three metadata columns to every landed row and generate a `batch_id` per run.
3. Wrap each source in its own transaction; on failure roll back that source, log the error and mark the step failed.
4. Provide structured logging with step name, source, rows read and rows written.
5. Hand the framework over to Eesha in a 30-minute walkthrough so she can maintain it (backup coverage).

**Acceptance criteria.** A failed load leaves no partial rows in bronze and records the failure; every landed row carries the three metadata columns.

**Evidence.** Run log rows for a success and a forced failure.

### US-3.2 Ingest S1 from the source database

**Owner:** Junaid · **Week:** 1 · **Depends on:** US-3.1

**Story.** As a data engineer, I want S1 extracted incrementally, so that reruns only move new or changed rows.

**Detailed approach.**
1. For each `src_pms` table open a server-side cursor on `lue_source` and stream chunks into `COPY` on `lue_warehouse` (separate connections).
2. Read the last watermark from `lue_audit.etl_watermark` and select rows with `updated_at` greater than it; the first run uses a minimum date.
3. After a successful load update the watermark to the maximum `updated_at` seen; never update it on failure.
4. Land into `brz_unit`, `brz_tenant`, `brz_lease`, `brz_lease_event`, `brz_invoice`, `brz_invoice_line`, `brz_payment` and `brz_payment_allocation`.

**Acceptance criteria.** The first run loads everything; an immediate second run loads zero rows; updating one source row causes exactly one row to land on the next run.

**Evidence.** Row counts for run one, run two and the single-row update test.

### US-3.3 Ingest the Excel and CSV sources (S2, S3, S6)

**Owner:** Junaid · **Week:** 1 · **Depends on:** US-3.1

**Story.** As a data engineer, I want the file-based sources landed with their file identity recorded and reruns made safe, so that every row is traceable and nothing is duplicated.

**Detailed approach.**
1. Read the S2 workbook sheet by sheet with openpyxl (owners, ownership register, vendors, categories and SLA hours, holidays) into one bronze table each.
2. Read S3 settlements and S6 incentives with pandas using string types so raw values are preserved.
3. Validate expected column names before loading; if the structure has drifted, fail the file with a clear message.
4. Compute each file's checksum. If `lue_audit.lineage` already records that checksum as loaded, skip the file and log "skipped, unchanged" (D16). A changed or new file lands as a new batch, appended and never truncated.
5. Record file name, checksum, row count and batch in `lue_audit.lineage`.

**Acceptance criteria.**
- A file with a renamed column is rejected before load.
- Re-running with unchanged files lands zero rows; replacing a file with an edited version lands exactly its rows as a new batch.
- Lineage contains one entry per file load with a checksum.

**Evidence.** Lineage rows; schema drift rejection message; second-run counts.

### US-3.4 Ingest JSON and weather, and reconcile bronze

**Owner:** Junaid · **Week:** 1 · **Depends on:** US-3.1

**Story.** As a data engineer, I want the JSON tickets and the weather cache landed and every bronze table reconciled to its source, so that nothing is lost before validation.

**Detailed approach.**
1. Flatten the S4 tickets into `brz_ticket` and the status history array into `brz_ticket_status`, keeping the ticket identifier as the link; apply the same checksum policy as US-3.3.
2. Load `data/weather_cache.json` into `brz_weather` (city, date, temperature, rainfall) with the same checksum policy.
3. For every bronze table write a row to `lue_audit.reconciliation`: source rows read, bronze rows written, difference and pass or fail.

**Acceptance criteria.** All bronze tables show zero difference between source and landed row counts; status history rows equal the sum of array lengths in the JSON.

**Evidence.** Reconciliation table output for all bronze tables.

---

## E4. Data quality validation and quarantine

**Week 2 · Lead: Junaid (with Eesha)**

**Epic workflow.** Validation sits between bronze and staging. A rule catalogue defines each check with an identifier, target table and column, check type and severity. An engine runs checks in a fixed order on every bronze table: DQ-01 NULL, DQ-02 data type, DQ-03 duplicate, DQ-04 business rule, DQ-05 referential and DQ-06 range (DQ-07 reconciliation runs in E8). A row failing a reject-level rule is written once to `lue_audit.quarantine` with the rule identifier, a readable reason, source system, batch identifier, a JSON copy of the row and a timestamp; passing rows flow to staging. The final story proves the engine against the answer key. The outcome is measurable data quality and the evidence for the Data Quality Report.

### US-4.1 Define the rule catalogue and engine

**Owner:** Junaid · **Week:** 2 · **Depends on:** US-3.4

**Story.** As a data engineer, I want validation rules defined as data and run by one engine, so that adding or changing a rule never means rewriting pipeline code.

**Detailed approach.**
1. Create a rule catalogue (table or YAML): rule id, bronze table, column, check type, severity (reject or warn) and message.
2. Write an engine that, for each rule in order, runs an `INSERT INTO lue_audit.quarantine ... SELECT ...` for violating rows and marks them rejected so later rules skip them.
3. Record only the first failing rule per row for rejection; count warnings separately.
4. Make reruns idempotent: before validating a batch, delete that batch's quarantine rows.
5. Publish the engine's interface so US-4.2 (Eesha) and US-4.3 (Junaid) can add rules in parallel.

**Acceptance criteria.** Adding a rule changes behaviour with no code edit; validating twice yields identical quarantine counts.

**Evidence.** The catalogue file and two identical run summaries.

### US-4.2 Implement completeness, type and duplicate checks (DQ-01 to DQ-03)

**Owner:** Eesha · **Week:** 2 · **Depends on:** US-4.1

**Story.** As a data steward, I want missing values, wrong types and duplicates detected, so that only structurally sound rows continue.

**Detailed approach.**
1. DQ-01: reject rows where required fields (natural keys, dates, amounts) are NULL or empty; warn on optional fields.
2. DQ-02: test numeric and date text with safe casts or regular expressions and reject failures.
3. DQ-03 (policy D15): detect **exact** duplicates on the natural key within a batch; keep the first by ingestion order and quarantine the rest with a reason identifying the survivor. **Conflicting** duplicates (same key, different values) are *not* rejected: raise a warn-level finding and pass them to staging, where US-5.1 survivorship keeps the latest `updated_at`.

**Acceptance criteria.**
- Each rule has a test with a known bad row and a known good row.
- Quarantine reasons show column and value.
- A conflicting duplicate produces a warning and reaches staging; an exact duplicate is quarantined.

**Evidence.** Test results and a sample of quarantine rows.

### US-4.3 Implement business, referential and range checks (DQ-04 to DQ-06)

**Owner:** Junaid · **Week:** 2 · **Depends on:** US-4.1

**Story.** As a data steward, I want business rules, references and plausible ranges enforced, so that analytics are never built on impossible data.

**Detailed approach.**
1. DQ-04: due date on or after issue date; payment amount positive unless flagged as a reversal; lease end after start; ticket resolved on or after raised; no overlapping leases on a unit.
2. DQ-05: payment to invoice line, invoice to lease, lease to unit and tenant, ticket to unit. Orphans are rejected, except tenant and vendor references that may arrive late: those are flagged for the inferred-member path (US-6.5) instead of rejected.
3. DQ-06: dates inside 2023-07-01 to 2026-06-30, rent within a plausible band per unit type, amounts under a configured cap.
4. Write each failure to quarantine with the offending value in the reason.

**Acceptance criteria.** Each planted business-rule, orphan and range defect type is caught by exactly one rule; a late-arriving tenant reference is flagged, not rejected.

**Evidence.** Per-rule counts and sample quarantine rows.

### US-4.4 Validate the checks against the answer key

**Owner:** Junaid · **Week:** 2 · **Depends on:** US-4.2, US-4.3, US-2.6

**Story.** As a tester, I want proof that the checks catch what we planted and reject nothing else, so that the quality claims are defensible.

**Detailed approach.** Write a script comparing the answer key with the quarantine table by source, table, defect type and rule, using the key's expected handling column. Report detected, missed and false positives. For false positives, run the engine on a clean control batch (defect rates zero) and require zero rejections. Investigate every gap and either fix the rule or document why it is acceptable. Save the comparison as `dq_validation.csv`.

**Acceptance criteria.** Detection is 100 percent for rejectable defect types; warn-only types are reported as warnings; false positives are zero on the control batch; every deviation is explained in the README.

**Evidence.** `dq_validation.csv` and the control batch result.

---

## E5. Staging transformations

**Week 2 · Lead: Ahmad Waqar**

**Epic workflow.** Valid bronze rows are cleaned and standardised into the `stg_` tables, the clean contract the dimension and fact loaders read. Four steps: apply cleaning and standardisation (trim, case, vocabulary maps, date parsing, casts); deduplicate with the survivorship rule; apply business transformations such as payment allocation and days past due; and load incrementally using the per-table watermark. Before and after samples are captured throughout for the Data Cleaning Report. Staging starts as soon as the engine (US-4.1) and bronze contract exist and picks up quarantine results as later rules land. The outcome is a trustworthy staging layer with proven incremental behaviour.

### US-5.1 Clean, standardise and deduplicate

**Owner:** Ahmad Waqar · **Week:** 2 · **Depends on:** US-3.4, US-4.1

**Story.** As a data engineer, I want consistent, deduplicated staging tables, so that downstream loads need no further cleanup.

**Detailed approach.**
1. Create reusable SQL functions: `clean_text` (trim, collapse spaces, standardise case so ' lahore ' and 'LAHORE' both become 'Lahore'), a date parser for formats seen in the sources, and safe numeric casts.
2. Map vocabularies with lookup tables: city names and codes, unit types, payment method names, ticket categories.
3. Handle NULLs deliberately: default, mark unknown or reject, per column as documented.
4. Deduplicate with `ROW_NUMBER()` over the natural key ordered by source `updated_at` descending then `loaded_at` descending, keeping the latest row (D15). Only rows not rejected by DQ checks participate.
5. Create the `stg_` tables: units, tenants, leases, lease events, invoice lines, payments, allocations, settlements, tickets, ticket status, incentives, weather, owners, vendors and categories.
6. Publish the staging contract in `docs/contracts/` on day 1 of the week so E6 can start in parallel.

**Acceptance criteria.** No city, unit type or payment method appears in more than one spelling; row counts per staging table equal bronze rows minus quarantined minus deduplicated, with the difference explained.

**Evidence.** Distinct value lists before and after; count bridge per table.

### US-5.2 Apply business transformations

**Owner:** Ahmad Waqar · **Week:** 2 · **Depends on:** US-5.1

**Story.** As an analyst, I want derived business fields computed once in staging, so that every downstream query agrees on their meaning.

**Detailed approach.**
1. Allocate payments to invoice lines where the source did not (oldest due line first), never allocating more than a payment's amount or a line's balance.
2. Compute `days_past_due` as paid date minus due date (zero or negative for on time), including for reversals.
3. Match S3 settlements to S1 payments on the payment reference; flag unmatched settlements and unsettled electronic payments.
4. Compute lease term in months, ticket lifecycle durations and the emergency flag.

**Acceptance criteria.** Sum of allocations equals the payment amount for every fully allocated payment; unmatched settlement count matches the answer key.

**Evidence.** Allocation reconciliation query; unmatched count versus answer key.

### US-5.3 Implement incremental loading with watermarks

**Owner:** Ahmad Waqar · **Week:** 2 · **Depends on:** US-5.1

**Story.** As an operator, I want staging to process only new or changed rows, so that daily runs are fast and repeatable.

**Detailed approach.**
1. For each staging table read its watermark and select bronze rows with a newer `updated_at` or `loaded_at`.
2. Merge with `INSERT ... ON CONFLICT (natural key) DO UPDATE`, updating only when values differ.
3. Advance the watermark only after the whole step succeeds.
4. Write counts of rows inserted, updated and unchanged to the run log.

**Acceptance criteria.** A second run with no source changes inserts and updates zero rows; changing one source row results in exactly one update.

**Evidence.** Run log counts for the unchanged rerun and the single change.

### US-5.4 Capture cleaning evidence

**Owner:** Ahmad Waqar · **Week:** 2 · **Depends on:** US-5.1

**Story.** As a report author, I want cleaning evidence saved as the pipeline runs, so that the Data Cleaning Report can be generated rather than reconstructed.

**Detailed approach.** For each source and issue type, store counts and before and after samples in an evidence table or CSV: whitespace and case fixes, duplicates removed, conflicting duplicates resolved by survivorship, nulls handled, type conversions, and rows rejected versus repaired. Include the ' lahore ' to 'Lahore' sample by name.

**Acceptance criteria.** An evidence file exists for every source with counts reconciling to the count bridge in US-5.1.

**Evidence.** The evidence CSVs.

---

## E6. Dimension loading and surrogate keys

**Week 2 · Lead: Hanan (with Eesha)**

**Epic workflow.** Dimensions are loaded from staging before any fact. A reusable loader handles new members and Type 1 changes. A parameterised SCD2 engine expires the current version and inserts a new one when a tracked attribute changes, first for tenant and then for unit, vendor and maintenance category. The remaining dimensions are loaded next, and inferred and late-arriving members are handled so facts never fail to load. The epic ends with a dimension test suite and the business key to surrogate key evidence the brief asks for. Development begins against the staging contract and the small profile, so it overlaps with E5 rather than waiting for it. This epic carries the 5 surrogate key marks and underpins every fact.

### US-6.1 Build the dimension loader pattern and surrogate keys

**Owner:** Hanan · **Week:** 2 · **Depends on:** US-1.2, staging contract (US-5.1 day 1)

**Story.** As a data engineer, I want one reusable loader pattern with surrogate key generation, so that every dimension loads the same way.

**Detailed approach.**
1. Write a SQL template or function that inserts staging members whose natural key is not yet in the dimension, letting the identity column assign surrogate keys.
2. Add the Type 1 step: update overwrite attributes in place when they change.
3. Define the load order: independent dimensions first (owner, vendor, category, incentive, weather, flags, static), then unit, tenant and lease.
4. Log inserted and updated counts per dimension.
5. Capture the brief's evidence: a query showing a tenant business key and its surrogate key side by side.

**Acceptance criteria.** Re-running inserts zero new members; surrogate keys are unique and never reused.

**Evidence.** Business key versus surrogate key query output.

### US-6.2 Implement tenant SCD Type 2

**Owner:** Hanan · **Week:** 2 · **Depends on:** US-6.1

**Story.** As an analyst, I want tenant history preserved, so that a report for a past month reproduces exactly as it was.

**Detailed approach.**
1. Define tracked attributes (employer sector, contact channel, tenant type) and compute a hash for comparison with the current row.
2. In one transaction, expire the current row (`effective_to` set to the change date, `is_current` false) and insert the new version with `effective_from` equal to the change date and `effective_to` 9999-12-31.
3. Process multiple changes for one tenant in the same batch chronologically.
4. Make it idempotent: a rerun creates no extra versions.
5. Verify continuity: each version's `effective_to` equals the next version's `effective_from`, with no gaps or overlaps.

**Acceptance criteria.** Each planted tenant change produces exactly one new version; rerunning creates no rows; a past-month query returns the old attribute value.

**Evidence.** A tenant's version history before and after a change; the past-month query.

### US-6.3 Extend SCD2 to unit, vendor and maintenance category

**Owner:** Eesha · **Week:** 2 · **Depends on:** US-6.2

**Story.** As an analyst, I want unit, vendor and category history preserved where the design requires it, so that performance is attributed to the right version.

**Detailed approach.** Parameterise the SCD2 engine by table, natural key and tracked columns. Apply it to `dim_unit` (unit type, furnished flag), `dim_vendor` (rating band, status) and `dim_maintenance_category` (default SLA hours); keep contact-style attributes as Type 1. Follow the SCD policy sheet in the Phase 1 dictionary; if time forces a downgrade to Type 1 under the cut-line, document it in the README.

**Acceptance criteria.** Each dimension passes the same continuity checks as tenant; a changed SLA value creates a new category version without altering history.

**Evidence.** Version history samples for one unit, vendor and category.

### US-6.4 Load the remaining dimensions and hierarchies

**Owner:** Eesha · **Week:** 2 · **Depends on:** US-6.1

**Story.** As an analyst, I want every dimension fully populated with its hierarchy, so that all questions can slice and roll up.

**Detailed approach.**
1. `dim_unit`: populate hierarchy columns (unit, floor, building, locality, city, region).
2. `dim_owner` from the ownership register, `dim_lease` from leases, `dim_incentive` from S6 and `dim_weather` from weather staging (city and date).
3. Update `dim_date.is_public_holiday` from the S2 holiday register.
4. Check completeness: no hierarchy level is NULL for a real member.

**Acceptance criteria.** Row counts are plausible against the config and above the brief's 100-record minimum for the large dimensions; every hierarchy level is populated.

**Evidence.** Dimension row counts; hierarchy completeness query.

### US-6.5 Handle inferred members, late arrivals and test the dimensions

**Owner:** Hanan · **Week:** 2 · **Depends on:** US-6.2, US-6.3

**Story.** As a data engineer, I want late-arriving members handled gracefully and the dimensions proven correct, so that facts always load and keys can be trusted.

**Detailed approach.**
1. When staging references a tenant or vendor not yet in the dimension, create an inferred member (`is_inferred` true, minimal attributes). When the real record arrives, update it in place and clear the flag without creating an SCD version.
2. Use key -1 only when no business key can be determined at all.
3. Write a dimension test suite in `sql/90_tests`: unique surrogate keys, exactly one current row per natural key, no overlapping versions, no NULL keys, and inferred member counts versus the answer key.

**Acceptance criteria.** All dimension tests return zero violations; a late-arriving tenant is created as inferred and later completed with no extra version.

**Evidence.** Test output and an inferred member lifecycle example.

---

## E7. Fact loading

**Week 3 · Lead: Hanan (with Ahmad Waqar, Junaid and Eesha)**

**Epic workflow.** With staging clean and dimensions loaded, facts load in dependency order: invoice lines, payments, lease events, maintenance requests, the daily occupancy snapshot and the incentive coverage fact. A shared framework maps business keys to surrogate keys using the dimension version valid on the event date, falling back to Unknown only when no business key exists. Each loader is idempotent and logs counts. The epic ends with automated grain and orphan checks that must return zero violations. The occupancy fact gets a trial full-volume load by mid-week so load-time problems surface early. The outcome is six populated facts matching their declared grain sentences.

### US-7.1 Build the fact loading framework and date-aware key mapping

**Owner:** Hanan · **Week:** 3 · **Depends on:** US-6.5

**Story.** As a data engineer, I want one tested pattern for turning business keys into surrogate keys, so that every fact references the correct dimension version.

**Detailed approach.**
1. Map each business key with `JOIN dim ON natural_key = business_key AND event_date >= effective_from AND event_date < effective_to` for SCD2 dimensions, and a plain join for others.
2. Resolve every role-playing date (invoice, due, paid, raised, assigned, resolved, verified) through `dim_date`.
3. Where no business key can be resolved, load with key -1 and log the count; never drop a row silently.
4. Load with `INSERT ... ON CONFLICT` on the fact's natural key so reruns do not duplicate.
5. Capture the brief's mapping evidence: a source payment row with `tenant_id`, its resolved `tenant_key` and the final fact row.

**Acceptance criteria.** A payment before a tenant's attribute change maps to the old version; one after maps to the new; rerunning inserts zero rows.

**Evidence.** The key-mapping chain for one payment and the before and after SCD query.

### US-7.2 Load fact_rent_invoice_line and fact_payment

**Owner:** Ahmad Waqar · **Week:** 3 · **Depends on:** US-7.1

**Story.** As a finance analyst, I want invoices and payments in separate facts at their own grains, so that collection analysis is correct for partial and split payments.

**Detailed approach.**
1. `fact_rent_invoice_line` (one charge line on one invoice for one lease): billed amount, tax, discount and net amount; invoice number and line number as degenerate dimensions.
2. `fact_payment` (one payment amount allocated against one invoice line): amount paid and days past due; reversals as negative amounts; payment reference as a degenerate dimension and the payment method key.
3. Resolve late-arriving payments to their invoice lines; payments whose line is genuinely missing were already quarantined.
4. Reconcile totals by month: invoiced net and paid amounts against staging.

**Acceptance criteria.** Zero grain duplicates; monthly totals match staging exactly; reversals reduce collected totals.

**Evidence.** Grain check output and the monthly reconciliation.

### US-7.3 Load fact_unit_occupancy_daily

**Owner:** Hanan · **Week:** 3 · **Depends on:** US-7.1

**Story.** As an operations analyst, I want one row per unit per day, so that occupancy, vacancy duration and arrears can be tracked over time.

**Detailed approach.**
1. Generate every unit and day with `generate_series` and left join to the lease active that day so vacant days remain.
2. Set `tenant_key` to the tenant version valid that day, or -2 when vacant; set `is_occupied` and contract rent.
3. Compute the arrears balance of the active lease as of that day **by pre-aggregating billed and paid amounts per lease per day and taking cumulative window sums**, never correlated subqueries. Arrears is semi-additive across time.
4. Load partition by partition with set-based SQL (and `COPY` where useful), no secondary indexes.
5. Implement the daily refresh rule (NFR-08): each run deletes and re-derives the last 35 days so late payments correct recent arrears (the declared idempotency exception, D14).
6. Run a trial full-volume load by mid-week 3 and record the duration.

**Acceptance criteria.**
- Row count equals units times days in the fixed window ending 2026-06-30 (never today's date).
- Full load duration is recorded and acceptable on a laptop.
- A late payment backdated within 35 days corrects the arrears figure after a refresh; a refresh with no changes yields identical values.

**Evidence.** Grain check; load duration; before and after refresh arrears for one unit.

### US-7.4 Load fact_maintenance_request

**Owner:** Junaid · **Week:** 3 · **Depends on:** US-7.1

**Story.** As an operations manager, I want one row per request tracking its whole lifecycle, so that I can measure assignment and resolution speed.

**Detailed approach.**
1. Insert a row when a ticket is first seen, with the raised date key and the Unknown date key for milestones not yet reached.
2. On later runs update the same row as assigned, resolved and verified dates arrive, recomputing `days_to_assign`, `days_to_resolve` and `days_to_verify`.
3. Set `sla_breached_flag` by comparing resolve time to the category SLA hours valid when the request was raised.
4. Populate costs, request flags, vendor, category, unit, owner and the weather key for the city and raised date (key -1 if weather is cut, D19).

**Acceptance criteria.** One row per request; rerunning does not duplicate or change completed rows; a ticket progressing between two runs is updated, not duplicated.

**Evidence.** The same ticket shown at two lifecycle stages.

### US-7.5 Load fact_lease_event and fact_vacancy_incentive_coverage

**Owner:** Eesha · **Week:** 3 · **Depends on:** US-7.1

**Story.** As a leasing manager, I want lease events and incentive coverage recorded as factless facts, so that renewal rates and incentive effects can be counted.

**Detailed approach.**
1. `fact_lease_event` (one lifecycle event for one lease): load from staging lease events with event type key and date key; optional event count of 1.
2. `fact_vacancy_incentive_coverage` (one row per unit, incentive and day active): expand each S6 window into daily rows with `generate_series`.
3. Verify the composite primary key prevents duplicates.

**Acceptance criteria.** Counts of events by type match staging; coverage rows equal the sum of incentive window lengths in days.

**Evidence.** Counts by event type; coverage row check.

### US-7.6 Automate grain and orphan checks

**Owner:** Junaid · **Week:** 3 · **Depends on:** US-7.2, US-7.3, US-7.4, US-7.5

**Story.** As a quality owner, I want grain, orphan and range checks automated, so that every run proves the facts are structurally correct.

**Detailed approach.** In `sql/90_tests` write one query per fact returning violation rows: duplicate grain, rows with no matching dimension (excluding the declared -1 and -2 members, which are counted and reported separately), and impossible values. Wire them into the pipeline's test step and have each write a pass or fail to the audit tables.

**Acceptance criteria.** All checks return zero violations on a clean run; a deliberately corrupted row makes the matching check fail.

**Evidence.** Passing output and a deliberate failure demonstration.

---

## E8. Orchestration, audit and reconciliation

**Week 3 · Lead: Junaid (with Hanan)**

**Epic workflow.** This epic joins everything into one repeatable pipeline. `run_pipeline.py` executes the steps in the brief's order: ingest, validate, transform, load dimensions, load facts, build marts, test and reconcile, and log. Every run has a run identifier; every step records rows read, inserted, updated and rejected; lineage records which source fed which table. Reconciliation (DQ-07) proves source totals equal warehouse totals after accounting for quarantined rows. Idempotency (as defined in D14) and failure recovery are tested explicitly, and a full-volume run records timing for the Phase 3 baseline. The outcome is a one-command, auditable pipeline.

### US-8.1 Build run_pipeline.py with logging and lineage

**Owner:** Junaid · **Week:** 3 · **Depends on:** US-7.6

**Story.** As an operator, I want one command that runs the entire pipeline with full logging, so that runs are repeatable and auditable.

**Detailed approach.**
1. Implement ordered steps as functions with a common signature; generate a `run_id` and write a start and end row per step to `etl_run_log` with status and the four counts.
2. Add options `--profile`, `--from-step`, `--only` and `--skip-generate`.
3. Mark steps critical or non-critical; a failed critical step stops the run with a non-zero exit code.
4. Write lineage rows linking each source (file or table) to bronze, staging and warehouse targets.
5. Wire `make rebuild` to reset the database, generate data and run the pipeline.
6. Start the orchestrator skeleton in week 2 (pairing Junaid with Hanan) using the already-built steps, so week 3 only wires in facts.

**Acceptance criteria.** One command takes an empty database to a loaded warehouse; the run log shows every step with counts and a final status.

**Evidence.** Terminal output of a full small-profile run and the run log rows.

### US-8.2 Implement source-to-warehouse reconciliation (DQ-07)

**Owner:** Hanan · **Week:** 3 · **Depends on:** US-8.1

**Story.** As a finance controller, I want proof that warehouse totals equal source totals, so that the numbers can be trusted.

**Detailed approach.**
1. Reconcile by month: total billed in source versus `fact_rent_invoice_line` net amount; total paid versus `fact_payment`; ticket counts versus `fact_maintenance_request`; lease event counts versus `fact_lease_event`.
2. Express the rule as source = warehouse + quarantined (reconciling item), so rejected rows explain variance rather than hiding it.
3. Write results to `lue_audit.reconciliation` with measure, period, source value, warehouse value, quarantined value, variance and status.
4. Fail the pipeline test step if any variance is unexplained.

**Acceptance criteria.** Unexplained variance is zero for every measure and month; removing a fact row on purpose makes reconciliation fail.

**Evidence.** The reconciliation table and the deliberate-failure demonstration.

### US-8.3 Test idempotency and failure recovery

**Owner:** Junaid · **Week:** 3 · **Depends on:** US-8.1

**Story.** As an operator, I want to know the pipeline is safe to rerun and safe to resume, so that failures are never catastrophic.

**Detailed approach.** Run the full pipeline twice on unchanged inputs and assert, per D14, that every step reports zero inserted, updated and rejected rows and that table content hashes are identical before and after; the occupancy 35-day refresh is excluded from the zero-row count but its resulting values must hash identically. Simulate a failure in the fact load step, confirm rollback with no partial rows, and resume with `--from-step`. Document the recovery procedure in the README.

**Acceptance criteria.** Second run changes no data (hash-identical) and reports zero rows for every step except the declared occupancy refresh; a resumed run completes and passes all tests.

**Evidence.** Counts and hashes of the second run; the recovery run log.

### US-8.4 Run at full volume and record baseline timings

**Owner:** Junaid · **Week:** 3 · **Depends on:** US-8.2

**Story.** As a performance owner, I want a full-volume run with per-step timings, so that we know where time goes and have a baseline for Phase 3.

**Detailed approach.** Generate the full profile and run end to end. Record duration and row counts per step, identify the two slowest steps and fix obvious problems (batching, `COPY`). Record the total rebuild time as a stated target rather than a guarantee. Start this run no later than the midpoint of week 3 so fixes still fit before the Phase 2 package.

**Acceptance criteria.** Full-volume run completes, reconciliation passes and fact row counts exceed the brief minimum of 10,000 by a wide margin.

**Evidence.** Timing table per step.

---

## E9. Phase 2 reports and packaging

**Week 3 · Lead: Ahmad Waqar (with the whole team)**

**Epic workflow.** Phase 2 is assessed through its scripts and two reports. A report generator reads the evidence tables captured in E4, E5, E7 and E8 and produces the Data Cleaning Report and the Data Quality Report as PDFs. Generators are built and tested against small-profile evidence early in week 3 and simply re-run once US-8.4 completes. SQL scripts are organised under the brief's names, the repository gets a README, and a rehearsal confirms a fresh clone works. The outcome is a complete Phase 2 package and a GitHub link.

### US-9.1 Produce the Data Cleaning Report (PDF)

**Owner:** Ahmad Waqar · **Week:** 3 · **Depends on:** US-5.4, US-8.4 (draft on small-profile evidence earlier)

**Story.** As a marker, I want a report showing what was wrong with the data and how it was fixed, so that the cleaning logic is clearly evidenced.

**Detailed approach.** Generate with reportlab from the evidence tables. Sections: purpose and method; per source the issues found with counts by type; the rule applied to each; before and after samples (including ' lahore ' to 'Lahore'); rows repaired versus rejected; conflicting duplicates and the survivorship rule; the count bridge from source to staging; and answer key coverage. `make reports` regenerates it.

**Acceptance criteria.** Every number is produced by the generator, not typed; counts agree with the run log.

**Evidence.** The generated PDF.

### US-9.2 Produce the Data Quality Report (PDF)

**Owner:** Ahmad Waqar · **Week:** 3 · **Depends on:** US-8.2, US-7.6

**Story.** As a marker, I want a report covering completeness, accuracy and integrity, so that quality validation is demonstrated end to end.

**Detailed approach.** Structure it on the brief's three dimensions. Completeness: null percentages and missing value handling. Accuracy: the revenue reconciliation by month. Integrity: foreign key validation with fact rows without matching dimension equal to zero, plus grain checks. Add rule-by-rule results, the quarantine summary, answer key detection rates, SCD continuity checks, and a short conclusion on residual risks.

**Acceptance criteria.** All tables are generated from audit tables; the integrity section states the zero-orphan result with the query behind it.

**Evidence.** The generated PDF.

### US-9.3 Package scripts, README and the GitHub submission

**Owner:** Whole team · **Week:** 3 · **Depends on:** US-9.1, US-9.2

**Story.** As a marker, I want the repository to match the brief's deliverable list and run from the README, so that I can verify everything quickly.

**Detailed approach.**
1. Map the repository to the brief's list: database SQL scripts (`00_setup`, `10_ddl`), staging schema SQL, DW schema SQL, ETL scripts (SQL and Python), dimension load scripts, fact load scripts, plus both PDFs.
2. Complete the README: prerequisites, setup, `make rebuild`, tests, report generation, brief-name mapping and alias views.
3. Tag the commit `phase2-submission`, clone it into a fresh folder and run the README steps on the small profile.
4. Submit the GitHub repository link.

**Acceptance criteria.** The fresh-clone run passes; every Phase 2 deliverable maps to a file or folder.

**Evidence.** Appendix B checklist with file paths; fresh-clone run log.

---

## E10. Reporting layer

**Week 3 · Lead: Eesha**

**Epic workflow.** Phase 3 turns the warehouse into a decision-support system, and the reporting layer is its interface. The brief names three reporting views; for LUE these become monthly collections, tenant analysis and unit performance, with thin alias views carrying the brief's exact names (D18). Slicer dimensions are exposed as `vw_dim_*` views so Power BI can connect as the read-only role. Behind them sit four materialized marts at monthly grain. The workflow designs the contracts from the dashboard's needs, builds them, validates them against the facts and secures them. The outcome is a stable, fast, documented layer.

### US-10.1 Create the reporting views required by the brief

**Owner:** Eesha · **Week:** 3 · **Depends on:** US-8.2

**Story.** As an analyst, I want ready-made views over the star schemas, so that common reporting needs are one query away.

**Detailed approach.**
1. `vw_monthly_collections`: month, billed, **cohort collection rate (D17)**, cash received (paid-month basis, labelled separately) and growth versus the previous month using `LAG`.
2. `vw_tenant_analysis`: tenant segment, late payment count, average days past due, total collected and current arrears, built on the tenant version valid at payment time.
3. `vw_unit_performance`: occupancy percentage, average vacancy days, maintenance cost per unit and contract rent, by unit type and building.
4. Create the alias views `vw_monthly_sales`, `vw_customer_analysis` and `vw_product_performance` selecting from the three views above (D18).
5. Create `vw_dim_*` read-only views for each dimension used as a slicer (date, building and unit hierarchy, tenant segment, vendor, payment method), excluding technical columns.
6. Document every column's definition and the brief-name mapping in the README.

**Acceptance criteria.** Each view returns rows and its totals match direct fact queries; alias views return identical results to their targets; `lue_reader` can select from every `vw_dim_*` view.

**Evidence.** Sample rows and a reconciliation query per view.

### US-10.2 Build the four gold marts

**Owner:** Eesha · **Week:** 3 · **Depends on:** US-10.1

**Story.** As a dashboard builder, I want pre-aggregated monthly marts, so that reports load quickly and consistently.

**Detailed approach.**
1. Create materialized views `mart_collections_monthly` (cohort basis plus cash received), `mart_occupancy_monthly`, `mart_maintenance_monthly` and `mart_owner_portfolio_monthly` with clear grains (for example building by month).
2. Respect additivity: occupancy is the average of daily occupied units over units, not a sum across days.
3. Add unique indexes so refreshes can run concurrently, and a `refresh_marts()` function that the pipeline calls in its mart-building step.

**Acceptance criteria.** Marts refresh from the pipeline with no manual step; each mart's grain is documented and unique.

**Evidence.** Mart definitions and a refresh log entry.

### US-10.3 Validate the reporting layer and secure access

**Owner:** Eesha · **Week:** 3 · **Depends on:** US-10.2

**Story.** As a data owner, I want proof that reports agree with the warehouse and that Power BI can only read, so that decisions rest on trustworthy numbers.

**Detailed approach.** Write tests comparing mart totals to fact aggregates for several months and measures. Confirm row counts. Grant `lue_reader` select on `lue_reporting` objects only and test that it cannot read `lue_staging`, `lue_dw` or `lue_audit`, and cannot write.

**Acceptance criteria.** Zero variance between marts and facts; `lue_reader` is read-only on `lue_reporting` and nothing else.

**Evidence.** Test output and denied-access messages.

---

## E11. Analytical SQL and OLAP

**Weeks 3 to 4 · Lead: Hanan (with Ahmad Waqar)**

**Epic workflow.** This epic answers the 14 business questions with SQL and delivers the OLAP requirements. Questions are grouped by process: finance (Q1 to Q5), occupancy and leasing (Q6 to Q8), then maintenance, owner, incentive and weather (Q9 to Q14). **Queries are first drafted on the small profile in week 3 (US-11.6) so week 4 is spent finalising on full volume, not starting from scratch.** Each query is run and recorded with its output and a one-line business interpretation. ROLLUP and CUBE follow with `GROUPING()`, then window analytics. Finally, queries are consolidated into runnable script files and three are cross-checked independently. The outcome is `analytical.sql` and `olap.sql` with outputs.

### US-11.6 Draft the analytical SQL on the small profile (new in v1.1)

**Owner:** Hanan (with Ahmad Waqar) · **Week:** 3 · **Depends on:** US-7.2, US-7.3, US-7.4, US-7.5 (small profile loaded)

**Story.** As a team, we want first drafts of all 14 queries running as soon as facts exist, so that week 4 is not overloaded.

**Detailed approach.** As each fact becomes available on the small profile, write the matching question queries (Q1 to Q14) as drafts in `sql/60_analytics/draft/`, using the D17 definitions. Do not capture final evidence yet; the purpose is to find missing columns, ambiguous definitions and performance problems while there is still time to fix the warehouse. Log any change request on the board.

**Acceptance criteria.** Every question has a draft that executes on the small profile; open definition issues are listed.

**Evidence.** The draft folder and an issue list.

### US-11.1 Answer the finance questions (Q1 to Q5)

**Owner:** Hanan · **Week:** 4 · **Depends on:** US-10.3, US-11.6

**Story.** As a finance head, I want collection, arrears and payment behaviour answered in SQL, so that I can act on them.

**Detailed approach.**
1. Q1 collection rate by building and month on the **cohort basis (D17)**: amount paid against lines due in the month divided by billed for the month.
2. Q2 arrears ratio by building; Q3 ageing buckets (0 to 30, 31 to 60, 61 and over) using the arrears balance on a month-end snapshot.
3. Q4 tenants with recurring late payments: count payments more than a set number of days late in the last 12 months, using the tenant version valid at payment time.
4. Q5 settlement speed by payment method: days between paid date and settlement date.
5. Use `LAG` for month-over-month growth where relevant; record output with a one-line interpretation each.

**Acceptance criteria.** Five queries run in `analytical.sql`, each with a result sample and interpretation; Q1 totals agree with `mart_collections_monthly` and `vw_monthly_collections`.

**Evidence.** Outputs captured as text or screenshots.

### US-11.2 Answer the occupancy and leasing questions (Q6 to Q8)

**Owner:** Hanan · **Week:** 4 · **Depends on:** US-10.3, US-11.6

**Story.** As an operations head, I want occupancy, vacancy duration and renewal rates answered, so that I can target leasing effort.

**Detailed approach.**
1. Q6 occupancy and vacancy trends by city and unit type: monthly average of daily occupancy from the snapshot.
2. Q7 vacancy duration by unit type: gaps-and-islands over consecutive vacant days, counting completed spells only and excluding spells that begin on the first day or are still open on the last day of the window.
3. Q8 renewal rate by building: renewed events divided by leases that reached expiry, from the lease event fact.

**Acceptance criteria.** Q7 states its censoring rule beside the query; Q6 monthly averages reconcile to `mart_occupancy_monthly`.

**Evidence.** Outputs and the Q7 rule.

### US-11.3 Answer maintenance, owner, incentive and weather questions (Q9 to Q14)

**Owner:** Ahmad Waqar · **Week:** 4 · **Depends on:** US-10.3, US-11.6

**Story.** As an operations and owner-relations team, I want maintenance performance, owner yield and external effects answered, so that vendors and owners can be managed with evidence.

**Detailed approach.**
1. Q9 average time to resolve by category and vendor; Q10 SLA breach rate by building; Q11 maintenance cost per unit per month by building.
2. Q12 net rental yield per owner: rent collected (charge type rent only, excluding late fees and utilities), minus actual maintenance cost, minus the management fee; state the fee assumption beside the query.
3. Q13 effect of incentives on vacancy duration: compare vacancy spells covered by an incentive with those not covered, using the coverage fact.
4. Q14 leak requests on heavy-rain days: join tickets to the weather dimension on city and raised date with a documented rain threshold.
5. If time is short, Q13 and Q14 are the first cut (A9, D19).

**Acceptance criteria.** Q12 filters on charge type and states the fee assumption; Q13 and Q14 show the planted effects with a stated threshold or comparison group.

**Evidence.** Outputs with interpretations.

### US-11.4 Implement ROLLUP and CUBE

**Owner:** Hanan · **Week:** 4 · **Depends on:** US-10.3, US-11.6

**Story.** As an executive, I want subtotals and grand totals in one result, so that I can see detail and summary together.

**Detailed approach.**
1. ROLLUP across Region, City, Building (the analogue of the brief's Region, Category, Product), on collected amount, producing building, city, region and grand totals.
2. CUBE on City by Payment channel group (the analogue of Region by Channel) for every combination of subtotals.
3. Use `GROUPING()` to label subtotal rows so NULL is not confused with missing data.
4. Verify by assertion that the grand total equals the base total and each city subtotal equals the sum of its buildings.

**Acceptance criteria.** Both queries run, labelled subtotals appear, and the verification query returns zero differences.

**Evidence.** ROLLUP and CUBE outputs and the verification result.

### US-11.5 Add window analytics and consolidate the SQL pack

**Owner:** Ahmad Waqar · **Week:** 4 · **Depends on:** US-11.1, US-11.2, US-11.3, US-11.4

**Story.** As a marker, I want the analytical work in clean, runnable files, so that every query can be verified quickly.

**Detailed approach.** Add window-function analytics where useful: `RANK` of buildings by arrears, `LAG` growth in collections, running totals and a three-month moving average. Consolidate everything in `sql/60_analytics/analytical.sql` and `olap.sql`, each query headed by a comment giving the question number, grain, tables used and definition (for example D17). Confirm the files run end to end in `psql`. Independently recompute three results with pandas as a cross-check.

**Acceptance criteria.** Both files execute without errors; the three cross-checks match to the cent.

**Evidence.** Execution log and the cross-check comparison.

---

## E12. Query optimization

**Week 4 · Lead: Junaid**

**Epic workflow.** The brief asks for before and after measurements with `EXPLAIN ANALYZE`, comparing execution time and cost after creating indexes. The warehouse was built with only primary and unique-constraint indexes (D20), so the baseline is already in place. The workflow selects three heavy queries, builds a repeatable benchmark harness, records the baseline, applies indexes (and exercises partition pruning on the occupancy fact), re-measures and writes the Indexing Report. The harness and baseline can be prepared early in week 4 against queries finalised in week 3. The outcome is honest, reproducible evidence including at least one experiment where an index did not help.

### US-12.1 Build the benchmark harness and record the baseline

**Owner:** Junaid · **Week:** 4 · **Depends on:** US-11.6 (final queries by US-11.5)

**Story.** As a performance tester, I want a repeatable way to measure queries, so that before and after numbers are comparable.

**Detailed approach.**
1. Choose three queries: Q1 collection rate by building, Q7 vacancy spells, and a large occupancy aggregate.
2. Create an unpartitioned copy of the occupancy fact (same constraints, no extra indexes) to represent the baseline for partitioning comparisons.
3. Script the benchmark: `VACUUM ANALYZE`, then run `EXPLAIN (ANALYZE, BUFFERS)` three times per query after a warm-up, recording execution time, total plan cost, plan type and buffers into a results CSV.

**Acceptance criteria.** The harness runs from one command and produces a CSV; baseline numbers are stable within a stated tolerance.

**Evidence.** Baseline CSV and a sample plan.

### US-12.2 Run the indexing and partitioning experiments

**Owner:** Junaid · **Week:** 4 · **Depends on:** US-12.1

**Story.** As a performance tester, I want to test candidate indexes and partitioning, so that each optimisation is justified by measurement.

**Detailed approach.**
1. Create composite indexes aligned to the queries (for example `(unit_key, snapshot_date_key)` on the occupancy fact and `(due_date_key, unit_key)` on payments) and a partial index on current SCD rows; put the statements in `sql/70_performance`.
2. Re-run `VACUUM ANALYZE` and the benchmark; compare sequential scans to index or bitmap scans and observe partition pruning for date-bounded queries.
3. Include at least one experiment where an index is not chosen or gives no gain, and explain why.
4. Record the storage size and load-time cost of each index.

**Acceptance criteria.** At least two queries show a measurable improvement in execution time and cost; every index has a stated purpose and a measured effect.

**Evidence.** After CSV and plan screenshots.

### US-12.3 Write the Indexing Report (PDF)

**Owner:** Junaid · **Week:** 4 · **Depends on:** US-12.2

**Story.** As a marker, I want a clear before and after report, so that the optimisation work is easy to verify.

**Detailed approach.** Generate a PDF with a comparison table (query, index or partition change, execution time before and after, cost before and after, plan type), plan excerpts or screenshots, analysis of why each change worked, index storage and refresh cost, a statement that the baseline already contained primary and unique-constraint indexes (D20), and recommendations. Stretch only if time remains: compare Q1 answered through relational tables, a pre-aggregated mart and a hybrid approach.

**Acceptance criteria.** The report contains the three measured queries with both execution time and cost and states the experiment where indexing did not help.

**Evidence.** The generated PDF.

---

## E13. Power BI dashboard

**Weeks 3 to 4 · Lead: Eesha**

**Epic workflow.** The brief requires exactly three pages: Executive Overview, Detailed Analysis and a Decision Page. The workflow starts with the connection and data model (US-13.1 begins in week 3 against the small profile so any connection issue surfaces early), then builds the three pages in order, each reading from the reporting layer through DAX measures. Every KPI is validated against its SQL result, and the report is exported as a PBIX file and a screenshot PDF. The outcome is a dashboard whose figures provably match the warehouse and whose last page converts evidence into a management decision.

### US-13.1 Connect Power BI and build the data model

**Owner:** Eesha · **Week:** 3 · **Depends on:** US-10.3

**Story.** As a dashboard builder, I want a clean model with consistent measures, so that every visual calculates the same way.

**Detailed approach.**
1. Connect Power BI Desktop to `lue_warehouse` as `lue_reader`, in Import mode, loading the four marts, the views and the `vw_dim_*` slicer views (all in `lue_reporting`).
2. Define relationships (single direction from dimensions to marts), hide technical keys and mark the date table.
3. Write DAX measures: Billed, Collected (cohort basis), Collection Rate (D17), Cash Received, Arrears Ratio, Occupancy Percentage, Active Leases, Average Days to Resolve and SLA Breach Percentage, formatted in PKR and percentages.
4. Apply a consistent theme and document connection parameters in the README so the PBIX opens on another machine.

**Acceptance criteria.** Each measure returns the same value as its SQL equivalent for a test month; the model has no ambiguous relationships; the model loads with no access errors for `lue_reader`.

**Evidence.** Model view screenshot and a measure versus SQL comparison.

### US-13.2 Build Page 1: Executive Overview

**Owner:** Eesha · **Week:** 4 · **Depends on:** US-13.1

**Story.** As an executive, I want the key numbers and trend at a glance, so that I know how the portfolio is performing.

**Detailed approach.** Place KPI cards for collections (the analogue of the brief's revenue KPI), collection rate, occupancy percentage and arrears. Add a monthly collections trend with a prior-year comparison and slicers for fiscal year, city and building class. Keep the layout simple, titles explicit and colours consistent.

**Acceptance criteria.** The page shows the four KPIs and the trend; slicers filter every visual; the page loads in a few seconds.

**Evidence.** Page screenshot.

### US-13.3 Build Page 2: Detailed Analysis

**Owner:** Eesha · **Week:** 4 · **Depends on:** US-13.2

**Story.** As a manager, I want to drill into buildings, cities, tenants and vendors, so that I can find where problems sit.

**Detailed approach.** Include building and unit-type analysis (the analogue of product analysis) as a ranked bar chart and a matrix; city analysis (regional analysis) as bars or a map; tenant segmentation (on time, occasionally late, chronically late) from the tenant analysis view; and vendor performance (days to resolve, SLA breach rate). Enable cross-filtering and a drill-through from building to its tenants.

**Acceptance criteria.** The three required sections (product-style, regional-style, segmentation) are present; drill-through works.

**Evidence.** Page screenshot and a drill-through screenshot.

### US-13.4 Build Page 3: Decision Page

**Owner:** Whole team · **Week:** 4 · **Depends on:** US-13.3, US-11.5

**Story.** As management, I want an explicit recommendation backed by the dashboard, so that analysis ends in a decision.

**Detailed approach.** Answer the brief's question, "Based on the dashboard, what decision should management take?", with one to three recommendations, for example: concentrate arrears follow-up on the building with the highest arrears ratio because it trails the portfolio collection rate by a stated margin. Build the text with dynamic DAX so numbers stay in sync, add the supporting visual beside each recommendation, and add a short assumptions and risks box (including that the data is synthetic).

**Acceptance criteria.** Each recommendation cites a figure from the dashboard and names an action, an owner and an expected effect.

**Evidence.** Page screenshot.

### US-13.5 Validate, finish and export

**Owner:** Eesha (reviewed by Junaid) · **Week:** 4 · **Depends on:** US-13.4

**Story.** As a marker, I want to know the dashboard is accurate and usable, so that I can trust it.

**Detailed approach.** Reconcile every KPI on all pages with its SQL result and screenshot both side by side. Test slicer combinations, tooltips and page load. Save the PBIX, export all three pages to a screenshot PDF, and confirm that the PBIX opens on at least two other team members' machines.

**Acceptance criteria.** Every KPI matches SQL; the PBIX and screenshot PDF exist; the PBIX opens on two other machines.

**Evidence.** Side-by-side validation table; the exported files.

---

## E14. Business insights and final presentation

**Week 4 · Lead: Whole team**

**Epic workflow.** The last graded deliverables are the Business Insights Report and the Final Presentation. The workflow mines the SQL results and dashboard for findings, checks that each planted pattern was actually discovered, and ranks insights by business impact. It then writes the report, with each insight stated as finding, evidence, decision and caveat, and builds the presentation and a rehearsed demo. The presentation outline and slides for finished Phase 2 material (design, architecture, ETL, quality, SCD) are drafted in week 3 so only Phase 3 slides remain in week 4. The outcome is a narrative linking design, engineering, quality, performance and analytics to decisions.

### US-14.1 Mine insights and verify against the planted patterns

**Owner:** Whole team · **Week:** 4 · **Depends on:** US-13.3

**Story.** As an analyst, I want a ranked list of well-evidenced insights, so that the report contains findings that matter.

**Detailed approach.** List candidate findings from the analytical SQL and dashboard. Check each planted pattern (high-arrears building, slow vendor, seasonal move-ins, incentive effect, rain-driven leak tickets, renewal churn in one city) was surfaced by an ordinary analysis, not by looking for it. Size each in PKR or days where possible, rank by impact and note confidence.

**Acceptance criteria.** Three to five insights are selected, each traceable to a query or visual, and each planted pattern is accounted for as found or deliberately not used.

**Evidence.** An insights shortlist with source references.

### US-14.2 Write the Business Insights Report (PDF)

**Owner:** Whole team · **Week:** 4 · **Depends on:** US-14.1

**Story.** As management, I want clear findings with evidence and recommended actions, so that I can decide.

**Detailed approach.** Write an executive summary, then for each insight give the finding, evidence (chart or query result), the decision and expected effect, and the caveats. State plainly that findings come from synthetic data with planted patterns, so conclusions illustrate method rather than describe a real portfolio. Tie recommendations to the Decision Page.

**Acceptance criteria.** Each insight has evidence, a decision and a caveat; figures match the dashboard and SQL outputs.

**Evidence.** The PDF.

### US-14.3 Build the final presentation and rehearse the demo

**Owner:** Whole team · **Week:** 4 (outline and Phase 2 slides in week 3) · **Depends on:** US-14.2, US-12.3, US-9.2

**Story.** As presenters, we want a concise story and a reliable live demo, so that the work is communicated clearly under time pressure.

**Detailed approach.**
1. Build about 12 to 15 slides: business problem, design (grain, star schema), architecture, ETL and layers, data quality results, SCD example, performance results, dashboard, insights and decisions, lessons learned.
2. Prepare a demo script: run `make rebuild` on the small profile, show a quarantined row, show an SCD2 history, show an `EXPLAIN ANALYZE` before and after, then open the dashboard.
3. Rehearse twice with a timer; prepare answers for likely questions: why invoices and payments are separate facts, how late-arriving data is handled, how SCD2 keys are chosen, why the occupancy fact is partitioned, why the collection rate is cohort-based.
4. Record a fallback video of the demo in case of technical failure.

**Acceptance criteria.** The presentation fits the allotted time; the demo runs end to end twice; the fallback exists.

**Evidence.** The PPT and rehearsal notes.

---

## E15. Release, QA and submission

**Week 4 · Lead: Ahmad Waqar (with Junaid and the whole team)**

**Epic workflow.** The final epic protects every earlier mark. A **release candidate freeze at the end of day 4 of the final week** stops feature work; after it, only fixes merge. The clean-machine rebuild and the documentation consistency audit then run in parallel on the release candidate, leaving the last day as slack. The rubric sweep follows. The outcome is a submission with no avoidable losses.

### US-15.1 Run a clean-machine rebuild

**Owner:** Ahmad Waqar · **Week:** 4 · **Depends on:** release candidate freeze, US-13.5, US-14.3

**Story.** As a marker, I want the repository to rebuild from scratch using only the README, so that the work is verifiable.

**Detailed approach.** On a machine or clean user account without the project, clone the repository and follow the README exactly: `make setup`, then `make rebuild` at full profile. Compare row counts, the reconciliation result and key report figures with the previous accepted run. Fix any missing step in the README or Makefile and repeat until clean.

**Acceptance criteria.** The rebuild succeeds with identical counts and figures; no undocumented manual step remains.

**Evidence.** Rebuild log and a count comparison.

### US-15.2 Audit documentation consistency

**Owner:** Junaid · **Week:** 4 · **Depends on:** release candidate freeze (runs in parallel with US-15.1)

**Story.** As a quality owner, I want proof the documents match the code, so that no contradiction costs marks.

**Detailed approach.** Write a script that checks: each fact's grain sentence is identical in the dictionary, DDL comments and reports; table and column names in the dictionary equal the deployed catalog; generated PDFs contain no placeholder text and no old schema names (using the word-boundary regex from US-0.1); the README mapping table lists every brief name; and the D17 collection rate definition is stated identically in the README, SQL headers, views and the dashboard. Prepare the script in week 3 so it only needs running at the freeze.

**Acceptance criteria.** The script reports zero mismatches.

**Evidence.** Script output.

### US-15.3 Sweep the rubric and package the submission

**Owner:** Whole team · **Week:** 4 · **Depends on:** US-15.1, US-15.2

**Story.** As a team, we want a last check of every deliverable against the briefs, so that nothing is missing at submission.

**Detailed approach.** Walk both deliverable lists in Appendix B and tick each against a real file with the correct name and format; check the PBIX opens; tag the repository `phase3-submission`; assemble the Phase 3 package (SQL files, indexing report, PBIX, screenshots PDF, insights report, presentation) and submit.

**Acceptance criteria.** Every line of Appendix B is ticked with a file path; the tag exists; submission confirmation is saved.

**Evidence.** The completed Appendix B checklist.

---

# Appendix A. Story index

| Story | Title | Epic | Week | Owner |
|---|---|---|---|---|
| US-0.1 | Align the Phase 1 pack with the briefs | E0 | 1 | Hanan |
| US-0.2 | Complete and freeze the Phase 1 baseline | E0 | 1 | Whole team |
| US-0.3 | Create the repository, branching and quality gates | E0 | 1 | Junaid |
| US-0.4 | Provide a reproducible local environment | E0 | 1 | Eesha |
| US-1.1 | Create databases, roles and schemas | E1 | 1 | Hanan |
| US-1.2 | Deploy dimension DDL with keys and special members | E1 | 1 | Hanan |
| US-1.3 | Deploy fact DDL, foreign keys and partitions | E1 | 1 | Hanan |
| US-1.4 | Load date and static reference dimensions | E1 | 1 | Eesha |
| US-1.5 | Create audit tables, watermark table and reset script | E1 | 1 | Eesha |
| US-2.1 | Build generator framework, configuration and seeding | E2 | 1 | Ahmad Waqar |
| US-2.2 | Generate master data | E2 | 1 | Hanan |
| US-2.3 | Generate leases, lease events and invoices | E2 | 1 | Ahmad Waqar |
| US-2.4 | Generate payments and settlements | E2 | 1 | Ahmad Waqar |
| US-2.5 | Generate tickets, incentives and weather | E2 | 1 | Eesha |
| US-2.6 | Inject defects, plant patterns, write answer key | E2 | 1 | Ahmad Waqar |
| US-3.1 | Build the ingestion framework | E3 | 1 | Junaid |
| US-3.2 | Ingest S1 from the source database | E3 | 1 | Junaid |
| US-3.3 | Ingest the Excel and CSV sources (S2, S3, S6) | E3 | 1 | Junaid |
| US-3.4 | Ingest JSON and weather, reconcile bronze | E3 | 1 | Junaid |
| US-4.1 | Define the rule catalogue and engine | E4 | 2 | Junaid |
| US-4.2 | Implement DQ-01 to DQ-03 | E4 | 2 | **Eesha** (was Junaid) |
| US-4.3 | Implement DQ-04 to DQ-06 | E4 | 2 | Junaid |
| US-4.4 | Validate the checks against the answer key | E4 | 2 | Junaid |
| US-5.1 | Clean, standardise and deduplicate | E5 | 2 | Ahmad Waqar |
| US-5.2 | Apply business transformations | E5 | 2 | Ahmad Waqar |
| US-5.3 | Implement incremental loading with watermarks | E5 | 2 | Ahmad Waqar |
| US-5.4 | Capture cleaning evidence | E5 | 2 | Ahmad Waqar |
| US-6.1 | Build the dimension loader pattern and surrogate keys | E6 | 2 | Hanan |
| US-6.2 | Implement tenant SCD Type 2 | E6 | 2 | Hanan |
| US-6.3 | Extend SCD2 to unit, vendor and category | E6 | 2 | Eesha |
| US-6.4 | Load remaining dimensions and hierarchies | E6 | 2 | Eesha |
| US-6.5 | Inferred members, late arrivals, dimension tests | E6 | 2 | Hanan |
| US-7.1 | Fact loading framework and date-aware key mapping | E7 | 3 | Hanan |
| US-7.2 | Load invoice line and payment facts | E7 | 3 | Ahmad Waqar |
| US-7.3 | Load the daily occupancy snapshot | E7 | 3 | Hanan |
| US-7.4 | Load the maintenance request fact | E7 | 3 | Junaid |
| US-7.5 | Load lease event and incentive coverage facts | E7 | 3 | Eesha |
| US-7.6 | Automate grain and orphan checks | E7 | 3 | Junaid |
| US-8.1 | Build run_pipeline.py with logging and lineage | E8 | 3 | Junaid |
| US-8.2 | Source-to-warehouse reconciliation (DQ-07) | E8 | 3 | Hanan |
| US-8.3 | Test idempotency and failure recovery | E8 | 3 | Junaid |
| US-8.4 | Full-volume run and baseline timings | E8 | 3 | Junaid |
| US-9.1 | Data Cleaning Report (PDF) | E9 | 3 | Ahmad Waqar |
| US-9.2 | Data Quality Report (PDF) | E9 | 3 | Ahmad Waqar |
| US-9.3 | Package scripts, README and GitHub submission | E9 | 3 | Whole team |
| US-10.1 | Reporting views, alias views and slicer views | E10 | 3 | Eesha |
| US-10.2 | Build the four gold marts | E10 | 3 | Eesha |
| US-10.3 | Validate the reporting layer and secure access | E10 | 3 | Eesha |
| US-11.1 | Finance questions Q1 to Q5 | E11 | 4 | Hanan |
| US-11.2 | Occupancy and leasing questions Q6 to Q8 | E11 | 4 | Hanan |
| US-11.3 | Maintenance, owner, incentive, weather Q9 to Q14 | E11 | 4 | Ahmad Waqar |
| US-11.4 | ROLLUP and CUBE | E11 | 4 | Hanan |
| US-11.5 | Window analytics and SQL pack | E11 | 4 | Ahmad Waqar |
| US-11.6 | Draft the analytical SQL on the small profile (new) | E11 | 3 | Hanan (with Ahmad Waqar) |
| US-12.1 | Benchmark harness and baseline | E12 | 4 | Junaid |
| US-12.2 | Indexing and partitioning experiments | E12 | 4 | Junaid |
| US-12.3 | Indexing Report (PDF) | E12 | 4 | Junaid |
| US-13.1 | Connect Power BI and build the model | E13 | 3 | Eesha |
| US-13.2 | Page 1: Executive Overview | E13 | 4 | Eesha |
| US-13.3 | Page 2: Detailed Analysis | E13 | 4 | Eesha |
| US-13.4 | Page 3: Decision Page | E13 | 4 | Whole team |
| US-13.5 | Validate, finish and export | E13 | 4 | Eesha |
| US-14.1 | Mine insights, verify planted patterns | E14 | 4 | Whole team |
| US-14.2 | Business Insights Report (PDF) | E14 | 4 | Whole team |
| US-14.3 | Final presentation and demo rehearsal | E14 | 4 | Whole team |
| US-15.1 | Clean-machine rebuild | E15 | 4 | Ahmad Waqar |
| US-15.2 | Documentation consistency audit | E15 | 4 | Junaid |
| US-15.3 | Rubric sweep and submission packaging | E15 | 4 | Whole team |

**Owner load by sole-owner stories (v1.1):** Junaid 17, Hanan 14, Ahmad Waqar 14, Eesha 15, plus 7 whole-team stories and US-11.6 shared.

# Appendix B. Deliverables traceability checklist

## Phase 2 (40 marks)

| Brief deliverable | Format | Produced by | Done |
|---|---|---|---|
| PostgreSQL database SQL scripts | SQL | US-1.1 to US-1.5 | [ ] |
| Staging Schema SQL | SQL | US-3.x, US-5.x | [ ] |
| DW Schema SQL | SQL | US-1.2, US-1.3 | [ ] |
| ETL scripts | SQL and Python | US-3.x to US-8.x | [ ] |
| Data Cleaning Report | PDF | US-9.1 | [ ] |
| Dimension Load Scripts | SQL | US-6.x | [ ] |
| Fact Load Scripts | SQL | US-7.x | [ ] |
| Data Quality Report | PDF | US-9.2 | [ ] |
| GitHub repository link | URL | US-0.3, US-9.3 | [ ] |

## Phase 3 (30 marks)

| Brief deliverable | Format | Produced by | Done |
|---|---|---|---|
| Analytical SQL queries | SQL | US-11.1 to US-11.3, US-11.5, US-11.6 | [ ] |
| OLAP queries (ROLLUP, CUBE) | SQL | US-11.4 | [ ] |
| Reporting views (including brief-named aliases) | SQL | US-10.1 | [ ] |
| Indexing Report | PDF | US-12.3 | [ ] |
| Power BI dashboard | PBIX | US-13.1 to US-13.4 | [ ] |
| Dashboard screenshots | PDF | US-13.5 | [ ] |
| Business Insights Report | PDF | US-14.2 | [ ] |
| Final presentation | PPT | US-14.3 | [ ] |

# Appendix C. Decisions and open items

## Confirmed by the team

- Delivery takes four weeks with four people (Junaid, Ahmad Waqar, Hanan, Eesha).
- No story points; planning uses weeks, owners and dependencies only.
- Renamed reporting views (monthly collections, tenant analysis, unit performance) are the team's choice, now backed by brief-named alias views (D18).
- The track split in A6 was approved by the team; v1.1 moves US-4.2 to Eesha and adds backups (to be re-confirmed by the team).
- Power BI Desktop is installed.

## Still open

| # | Item | Action and owner |
|---|---|---|
| O1 | **Official deadlines.** The plan assumes Phase 2 is due at the end of week 3 and Phase 3 at the end of week 4. If Phase 2 is due earlier, move E9 earlier and push the Phase 3 head start (E10, US-13.1, US-11.6) later | Whole team: check the course portal this week |
| O2 | **Roll numbers.** Needed for the Phase 1 pack and every report (US-0.2) | **Closed 2026-11-07:** all four received and set in `AUTHORS` in `tools/model.py`; reuse that line for every later report |
| O3 | **Rubric weight of the Indexing Report and presentation.** The Phase 3 marks table sums to 30 without them | Confirm with the instructor or rubric |
| O4 | **Instructor confirmation of the renamed schemas and views** (`lue_*` instead of `project_*`, alias views for view names) | Ask once, in writing |
| O5 | **Watermark table.** `lue_audit.etl_watermark` extends the four audit tables designed in Phase 1; needs team agreement and a line in the data dictionary | Hanan and Eesha, week 1 |
| O6 | **Unmeasured targets.** Runtimes (full rebuild, 1.97M-row occupancy load) are targets until measured; record actuals in the README | Junaid, weeks 1 and 3 |

# Appendix D. Revision log (v1.0 to v1.1)

| # | Issue found in v1.0 | Resolution in v1.1 |
|---|---|---|
| 1 | Power BI (`lue_reader`) was to load dimensions from `lue_dw`, which it cannot read | Decision D4: `vw_dim_*` slicer views in `lue_reporting`; US-1.1, US-10.1, US-10.3, US-13.1 updated |
| 2 | US-0.1 old-name search would match `lue_dw.` and `lue_audit.` and never pass | Word-boundary regex in US-0.1 and US-15.2 |
| 3 | DQ-03 (keep first, quarantine) conflicted with US-5.1 (keep latest) | Decision D15; US-4.2 and US-5.1 aligned; answer key records expected handling |
| 4 | "Second run inserts and updates zero rows" contradicted the 35-day occupancy refresh | Decision D14; US-7.3 and US-8.3 reworded with content hashes |
| 5 | File sources S2, S3, S4, S6 had no rerun policy, so bronze would duplicate | Decision D16; US-3.3 and US-3.4 updated; risk R11 added |
| 6 | Collection rate ambiguous (due-month vs paid-month) | Decision D17 applied to Q1, views, marts and DAX; separate Cash Received measure |
| 7 | Leftover two-developer wording | US-0.4, US-13.5 updated for four people |
| 8 | Brief names "win" but views and schemas were renamed | Alias views (D18); instructor confirmation O4 |
| 9 | Indexing and presentation marks unclear | Open item O3 |
| 10 | Special members -1 and -2 vs identity columns | Decision D6 and US-1.2: `GENERATED BY DEFAULT`, sequence restart |
| 11 | Occupancy arrears could be written as slow correlated subqueries | Cumulative window sums mandated in US-7.3 and R4 |
| 12 | Cut-lines conflicted with the fixed smoke test and weather key | Decision D19 |
| 13 | "No secondary indexes" ignored PK and unique indexes | Decision D20; US-1.3, US-12.3 |
| 14 | Roll-number placeholder on the title page | Resolved in US-0.2: real names and roll numbers set; O2 closed |
| 15 | Uneven workload (Junaid 18 stories, Eesha light early) | US-4.2 moved to Eesha; backups added in A6; ingestion hand-over in US-3.1 |
| 16 | Week 2 was a strictly serial chain | Overlap rules in A7; dependencies of US-5.1 and US-6.1 relaxed to contracts |
| 17 | Week 3 had no buffer for the full-volume run | Mid-week trial load in US-7.3; US-8.4 starts by midweek; report generators built on small-profile evidence |
| 18 | Week 4 ended serially with no slack | Release candidate freeze at end of day 4; US-15.1 and US-15.2 in parallel |
| 19 | E11 queries were only a risk mitigation, not scheduled work | New US-11.6 in week 3 |
| 20 | Presentation work entirely in week 4 | Outline and Phase 2 slides drafted in week 3 (E14) |