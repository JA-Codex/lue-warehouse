# LUE Warehouse

Lahore Urban Estates analytics warehouse. DL3004 Data Warehousing and Business Intelligence, final project
(FAST-NU Lahore). PostgreSQL star schema, Python ETL and a Power BI dashboard.

Team: Junaid Minhas, Ahmad Waqar, Hanan Tiwana, Eesha Khurram.

## Status

| Item | State |
|---|---|
| Phase 1 design pack | Frozen as v2.1 in `docs/phase1/` (git tag `phase1-v2.1-final`) |
| Repository, branch rules, CI | US-0.3 (this change) |
| Local environment and `.env.example` | US-0.4, pending |
| Database, ETL, marts, reports | Phase 2 and 3, pending |

## Layout

```
docs/phase1/      frozen Phase 1 pack (do not edit; see Change control)
docs/plan/        the development plan for Phases 2 and 3
docs/stories/     story log: what was done in each user story (start at docs/stories/README.md)
docs/contracts/   generated table and key contracts, refreshed weekly
docs/reports/     generated PDFs: cleaning, data quality, indexing, insights
docs/evidence/    screenshots and outputs that prove each story (one folder per story)
sql/              00_setup, 10_ddl, 20_staging, 30_dimensions, 40_facts, 50_reporting,
                  60_analytics, 70_performance, 90_tests
etl/              generate_data.py, refresh_weather.py, ingest/, run_pipeline.py, reports/
data/             generated source files (not committed) and data/weather_cache.json (committed)
powerbi/          PBIX and screenshots
presentation/     final slides
scripts/          ci_checks.py (SQL parse check and frozen-pack check)
```

Two small additions to the plan's layout, recorded here as deviations: `scripts/` holds the CI checks, and
`docs/evidence/` holds story evidence (plan A10 says evidence lives under `docs/`).

## Commands

```
make help        list the targets
make test        lint + SQL parse check + frozen-pack check (what CI runs)
make setup       stub until US-0.4
make rebuild     stub until the pipeline exists; must always pass on main
make reports     stub
make db-reset    stub until US-1.1
```

On Windows, `make` is not installed by default. Either run the checks directly
(`pip install -r requirements-ci.txt`, then `ruff check etl scripts` and `python scripts/ci_checks.py`)
or use Git Bash with `make` installed.

## How we work

- `main` is always runnable. Nobody pushes to it: every change is a pull request, and the `ci` check must pass
  before it can merge. A teammate review is optional and not enforced by the ruleset.
- Branch names are `epic-story`, for example `e6-6.2-tenant-scd2`.
- Reviews are optional. If one is wanted, the rotation is: Junaid reviews Hanan, Hanan reviews Ahmad Waqar,
  Ahmad Waqar reviews Eesha, Eesha reviews Junaid.
- The pull request template carries the Definition of Done. Evidence goes under `docs/evidence/<story>/`.
- Never commit credentials. `.env` is ignored; only `.env.example` is committed.

## Names: brief names against LUE names

The briefs use `project_*` names. We use LUE names; this mapping is **pending instructor confirmation (O4)**.

| Brief name | LUE name | Notes |
|---|---|---|
| `project_staging` | `lue_staging` | Bronze tables `brz_*`, Silver tables `stg_*` |
| `project_dw` | `lue_dw` | 13 dimensions and 6 facts |
| `project_reporting` | `lue_reporting` | Gold marts and views, including `vw_dim_*` |
| (none) | `lue_audit` | `etl_run_log`, `quarantine`, `reconciliation`, `lineage` |
| (none) | `lue_source.src_pms` | Source system S1; separate database `lue_source` |
| `vw_monthly_sales`, `vw_customer_analysis`, `vw_product_performance` | alias views in `lue_reporting` | Planned (US-10.1) |

The warehouse database is `lue_warehouse`.

## Change control for the frozen Phase 1 pack

`docs/phase1/` matches `MANIFEST.sha256`, and CI fails if any file there changes. A design change needs a dated row in
the change log in `docs/phase1/README.md`, a regeneration with `docs/phase1/tools/`, and a new manifest and tag.
