# US-0.1 Align the Phase 1 pack with the briefs

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-06 |
| Result | Phase 1 pack version 2.0 became version 2.1 (the `lue_*` naming) |
| Evidence | [`../evidence/us-0.1/`](../evidence/us-0.1/) |

## Story

As the project team, we want the design pack to use the schema and naming vocabulary of the Phase 2 and 3 briefs, so
that implementation scripts and documents never disagree.

## What was done

1. Read the submitted Phase 1 pack and searched every generator and output for the old schema names. Findings that
   shaped the work: the DDL only creates two schemas (`dw` with 13 dimensions and 6 facts, `audit` with 4 tables), so
   the Bronze, Silver and Gold names appeared only in prose, diagram labels and lineage examples, never as tables.
   `build_plain.py` imports `build_pdfs.py`, so both feed the PDFs.
2. Changed the generators, never the generated files. Added one block of `SCHEMA_*` constants to `tools/model.py`
   (`SCHEMA_STAGING`, `SCHEMA_DW`, `SCHEMA_REPORTING`, `SCHEMA_AUDIT`, `SCHEMA_SOURCE`, plus `SCHEMA_MAP`). If the
   instructor insists on the `project_*` names (O4), each is a one-line change followed by a regeneration.
3. Updated the text: audit table names, lineage examples, ingestion targets (`lue_staging.brz_*`), the architecture table,
   the architecture diagram and the dictionary. Bronze, Silver and Gold remain as layer concepts (decision D3); the
   physical name is added where each is first introduced.
4. Added the brief-name mapping table to the Phase 1 README, with the three alias views marked as planned (D18) and the
   decision marked pending instructor confirmation (O4).
5. Regenerated everything in one pass: DDL, 17 Mermaid diagrams (PNG and vector PDF), the five PDFs, the schema
   diagrams PDF and the data dictionary. The dictionary was recalculated with LibreOffice so its formula values are stored.
6. Loaded the new DDL into PostgreSQL 16.15 and counted the objects.

## Files changed

- `tools/model.py`, `tools/ddl.py`, `tools/sql_examples.py` (28 `dw.` to `lue_dw.`), `tools/build_pdfs.py`,
  `tools/build_plain.py`, `tools/diagrams.py`, `tools/build_xlsx.py` (Schema column and its width).
- `README.md` (mapping table, decision record, `psql -d lue_warehouse`, corrected regeneration commands, version 2.1).
- Regenerated: `sql/physical_model.sql`, `diagrams/mermaid/*.mmd`, `diagrams/png/*.png`, PDFs 01 to 06,
  `07_Data_Dictionary.xlsx`.

## Decisions and deviations

- The DDL creates only `lue_dw` and `lue_audit`. `lue_staging` and `lue_reporting` are created by the setup scripts
  in US-1.1, not here.
- `src_pms` and `lue_source` were not changed.
- The pack version was raised from 2.0 to 2.1 to match the tag planned in US-0.2.
- The README's `psql -d lue_dw` was corrected to the database `lue_warehouse` (decision D1), because the old name would
  now collide with the schema `lue_dw`.
- Diagrams were rendered with mermaid-cli 11.16.0, not the 11.4.2 the plan pins; 11.4.2 could not be installed in the
  environment used. The rendered architecture diagram was checked by eye.
- Pending: instructor confirmation of the renamed schemas and views (O4).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Old schema names (`bronze.`, `silver.`, `gold.`, `dw.`, `audit.`) do not appear in generated artifacts | Pass: 268 matching lines before, 0 after. A second search for unqualified forms (`CREATE SCHEMA dw`, `schema bronze` and similar) went from 17 to 0 | `1_search_BEFORE.txt`, `2_search_AFTER.txt` |
| DDL parses; 13 dimensions, 6 facts, 4 audit tables | Pass: loaded into PostgreSQL 16.15 with no errors. Also 48 partitions and 41 foreign keys | `3_ddl_check.txt` |
| README mapping table exists | Pass | `docs/phase1/README.md`, section "Naming" |

## How to re-check it

From `docs/phase1/`: load `sql/physical_model.sql` into an empty database with `psql -v ON_ERROR_STOP=1 -f`, and confirm
only `lue_dw` and `lue_audit` exist. CI also parses the file and verifies the whole pack against `MANIFEST.sha256`.

## Open items and follow-ups

- O4: send the instructor the written question about the renamed schemas and views.
- The dictionary's Schema column now reads `lue_dw` and `lue_audit`; the regex does not catch that column (no dot), so
  it is verified with a positive check instead.
