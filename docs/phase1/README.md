# Lahore Urban Estates Analytics Warehouse — Phase 1 pack

DL3004 Data Warehousing and Business Intelligence · Final Project · Phase 1 (Business Analysis and Dimensional Design) · Version 2.1

## Deliverables

| # | File | Phase 1 deliverable | Rubric area |
|---|------|---------------------|-------------|
| 01 | `01_Project_Proposal.pdf` | Project Proposal | Business understanding (5) |
| 02 | `02_Business_Requirements_Document.pdf` | Business Requirements Document | Requirement analysis (5) |
| 03 | `03_Business_Questions.pdf` | 10 Business Questions (14 provided) | Requirement analysis (5) |
| 04 | `04_Fact_Dimension_Identification.pdf` | Fact & Dimension Identification | Fact/dimension identification (10) |
| 05 | `05_Grain_Definition.pdf` | Grain Definition Document | Fact/dimension identification (10) |
| 06 | `06_Schema_Diagrams.pdf` + `diagrams/` | Star/Snowflake Schema Diagram (PNG/PDF) | Schema design (10) |
| 07 | `07_Data_Dictionary.xlsx` | Data Dictionary (Excel) | Schema design (10) |

Extra: `sql/physical_model.sql` is the physical model as PostgreSQL DDL. It has been run successfully on PostgreSQL 16
(13 dimensions, 6 facts, 4 audit tables, 48 monthly partitions, 41 foreign keys). It creates the schemas `lue_dw` and
`lue_audit`; `lue_staging` and `lue_reporting` are created by the setup scripts (US-1.1).

## Naming: brief names against LUE names (US-0.1)

The Phase 2 and 3 briefs use `project_*` schema names. This pack uses LUE names. The medallion layer names (Bronze, Silver,
Gold) remain as concepts in the documents and the 11-section architecture diagram; only the physical names changed
(they were `bronze`, `silver`, `dw`, `gold` and `audit` in version 2.0).

| Brief name | LUE name | Notes |
|---|---|---|
| `project_staging` | `lue_staging` | Bronze tables are prefixed `brz_`, Silver tables `stg_` (decision D3) |
| `project_dw` | `lue_dw` | The 13 dimensions and 6 facts |
| `project_reporting` | `lue_reporting` | Gold marts and views, including the `vw_dim_*` slicer views |
| (no brief name) | `lue_audit` | `etl_run_log`, `quarantine`, `reconciliation`, `lineage` |
| (no brief name) | `lue_source.src_pms` | Source system S1; separate database `lue_source` |
| `vw_monthly_sales` | `vw_monthly_sales`, an alias view in `lue_reporting` | Planned for US-10.1 (D18); selects from the LUE view |
| `vw_customer_analysis` | `vw_customer_analysis`, an alias view in `lue_reporting` | Planned for US-10.1 (D18) |
| `vw_product_performance` | `vw_product_performance`, an alias view in `lue_reporting` | Planned for US-10.1 (D18) |

Database names: the warehouse database is `lue_warehouse`; the source database is `lue_source`.

**Decision record.** The team decided that the renamed equivalents above are acceptable in place of the brief's exact
names. Status: **pending instructor confirmation (open item O4).** Because every name comes from `SCHEMA_*` constants in
`tools/model.py`, changing to the `project_*` names would be a one-line change per schema followed by a regeneration.

## Diagrams (Mermaid)

`diagrams/mermaid/*.mmd` are the editable sources; `diagrams/png/*.png` are high-resolution renders.

| File | Diagram |
|------|---------|
| `01_conceptual_model.mmd` | Conceptual model: business entities and relationships |
| `02_conceptual_dimensional_model.mmd` | Conceptual dimensional model: processes → facts → conformed dimensions |
| `03_logical_star_1…6_*.mmd` | Logical star schema per fact (grain in the title; measures, hierarchies, SCD2, degenerate dimensions annotated) |
| `04_physical_star_1…6_*.mmd` | Physical star schema per fact (PostgreSQL types, PK/FK, NULL/NOT NULL) |
| `05_source_erd.mmd` | Normalised source ERD of the PropertyHub system (Lab 03 style) |
| `06_architecture.mmd` | End-to-end architecture mapped to the 11 sections of the reference diagram |
| `07_hierarchies.mmd` | Drill-down hierarchies |

To view or edit: paste a `.mmd` file into https://mermaid.live, or render locally with
`npx @mermaid-js/mermaid-cli -i diagrams/mermaid/06_architecture.mmd -o architecture.png -s 2 -b white -c tools/mermaid_config.json`.
GitHub also renders Mermaid inside a Markdown code block marked `mermaid`.

## Physical model

```
psql -d lue_warehouse -f sql/physical_model.sql
```

## Regenerating everything

All documents, diagrams, the DDL and the data dictionary come from one definition, `tools/model.py`, so table names,
column names and grain sentences are identical everywhere. After changing the model:

```
cd tools
python3 ddl.py ../sql/physical_model.sql
python3 diagrams.py ../diagrams/mermaid          # then render each .mmd with mmdc (PNG and vector PDF, see above)
python3 build_xlsx.py ../07_Data_Dictionary.xlsx
python3 build_plain.py ..                       # the five PDFs (plain style)
python3 build_schema_pdf.py .. <folder of mmdc vector PDFs>
```

## Before submitting

- Authors and roll numbers are set (`AUTHORS` in `tools/model.py`, done in US-0.2). Nothing to replace.
- Copy the files into the repository structure from the brief: PDFs, diagrams and the data dictionary go in
  `01_Project_Documentation/`; `sql/physical_model.sql` can seed `04_Data_Warehouse/warehouse.sql`.

## Frozen baseline (US-0.2)

This pack is the frozen Phase 1 baseline, **version 2.1**. The submitted design is the design we build.

- Git tag: `phase1-v2.1-final`.
- Repository copy: `docs/phase1/`. It must match this pack file for file.
- `MANIFEST.sha256` lists the SHA-256 of every file. To check the copy: `cd docs/phase1 && sha256sum -c MANIFEST.sha256`
  (every line must say OK).

## Change control

After the freeze, a design change is made only like this:

1. Change the generator (`tools/model.py` or the relevant script), never a generated file.
2. Add a row to the change log below, with the date, what changed, why and who agreed.
3. Regenerate the DDL, diagrams, PDFs and dictionary, then re-run the checks (no old names, no placeholders, DDL loads).
4. Bump the version, rebuild `MANIFEST.sha256` and tag the commit.

| Date | Version | Change | Reason | Agreed by |
|---|---|---|---|---|
| 2026-11-06 | 2.0 to 2.1 | Schemas renamed to `lue_*` (see "Naming" above); mapping table added | Align with the Phase 2 and 3 briefs (US-0.1) | Team |
| 2026-11-07 | 2.1 | Authors and roll numbers set; baseline frozen; change control added | US-0.2 | Team |
