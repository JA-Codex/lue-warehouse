# Story log

One row per user story. Status values: `Not started`, `In progress`, `Done`. Newest work at the bottom of each epic.
Story definitions live in the plan: `../plan/LUE_Development_Plan_v1.1.md`.

## E0. Foundation and Phase 1 closure

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-0.1 | Align the Phase 1 pack with the briefs | Hanan | Done | 2026-11-06 | [US-0.1](US-0.1.md) | [evidence](../evidence/us-0.1/) |
| US-0.2 | Complete and freeze the Phase 1 baseline | Whole team | Done | 2026-11-07 | [US-0.2](US-0.2.md) | [evidence](../evidence/us-0.2/) |
| US-0.3 | Create the repository, branching and quality gates | Junaid | Done | 2026-11-07 | [US-0.3](US-0.3.md) | [evidence](../evidence/us-0.3/) |
| US-0.4 | Provide a reproducible local environment | Eesha | Done | 2026-11-07 | [US-0.4](US-0.4.md) | [evidence](../evidence/us-0.4/) |

## E1. Database implementation

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-1.1 | Create databases, roles and schemas | Hanan | Done | 2026-11-09 | [US-1.1](US-1.1.md) | [evidence](../evidence/us-1.1/) |
| US-1.2 | Deploy dimension DDL with keys and special members | Hanan | Done | 2026-11-09 | [US-1.2](US-1.2.md) | [evidence](../evidence/us-1.2/) |
| US-1.3 | Deploy fact DDL, foreign keys and partitions | Hanan | Done | 2026-11-10 | [US-1.3](US-1.3.md) | [evidence](../evidence/us-1.3/) |
| US-1.4 | Load the date dimension and static reference dimensions | Eesha | Done | 2026-11-10 | [US-1.4](US-1.4.md) | [evidence](../evidence/us-1.4/) |
| US-1.5 | Create audit tables, the watermark table and the reset script | Eesha | Done | 2026-11-10 | [US-1.5](US-1.5.md) | [evidence](../evidence/us-1.5/) |

## E2. Synthetic source data generator

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-2.1 | Build the generator framework, configuration and seeding | Ahmad Waqar | Done | 2026-11-14 | [US-2.1](US-2.1.md) | [evidence](../evidence/us-2.1/) |
| US-2.2 | Generate master data and registers | Hanan | Done | 2026-11-14 | [US-2.2](US-2.2.md) | [evidence](../evidence/us-2.2/) |
| US-2.3 | Generate leases, lease events and invoices | Ahmad Waqar | Done | 2026-11-15 | [US-2.3](US-2.3.md) | [evidence](../evidence/us-2.3/) |
| US-2.4 | Generate payments and settlements | Ahmad Waqar | Done | 2026-11-15 | [US-2.4](US-2.4.md) | [evidence](../evidence/us-2.4/) |
| US-2.5 | Generate tickets, incentives and weather | Eesha (done by Hanan) | Done | 2026-11-16 | [US-2.5](US-2.5.md) | [evidence](../evidence/us-2.5/) |
| US-2.6 | Inject defects, plant patterns, write the answer key | Ahmad Waqar (done by Hanan) | Done | 2026-11-16 | [US-2.6](US-2.6.md) | [evidence](../evidence/us-2.6/) |
| US-3.1 | Build the ingestion framework | Junaid (done by Hanan) | Done | 2026-11-16 | [US-3.1](US-3.1.md) | [evidence](../evidence/us-3.1/) |
| US-3.2 | Ingest S1 from the source database | Junaid (done by Hanan) | Done | 2026-11-16 | [US-3.2](US-3.2.md) | [evidence](../evidence/us-3.2/) |
| US-3.3 | Ingest the Excel and CSV sources (S2, S3, S6) | Junaid (done by Hanan) | Done | 2026-11-16 | [US-3.3](US-3.3.md) | [evidence](../evidence/us-3.3/) |
| US-3.4 | Ingest JSON and weather, and reconcile bronze | Junaid (done by Hanan) | Done | 2026-11-16 | [US-3.4](US-3.4.md) | [evidence](../evidence/us-3.4/) |
| US-4.1 | Define the rule catalogue and engine | Junaid (done by Hanan) | Done | 2026-11-17 | [US-4.1](US-4.1.md) | [evidence](../evidence/us-4.1/) |
| US-4.2 | Implement completeness, type and duplicate checks (DQ-01 to DQ-03) | Eesha (done by Hanan) | Done | 2026-11-17 | [US-4.2](US-4.2.md) | [evidence](../evidence/us-4.2/) |
| US-4.3 | Implement business, referential and range checks (DQ-04 to DQ-06) | Junaid (done by Hanan) | Done | 2026-11-17 | [US-4.3](US-4.3.md) | [evidence](../evidence/us-4.3/) |
| US-4.4 | Validate the checks against the answer key | Junaid (done by Hanan) | Done | 2026-11-17 | [US-4.4](US-4.4.md) | [evidence](../evidence/us-4.4/) |
| US-5.1 | Clean, standardise and deduplicate | Ahmad Waqar (done by Hanan) | Done | 2026-11-17 | [US-5.1](US-5.1.md) | [evidence](../evidence/us-5.1/) |
| US-5.2 | Apply business transformations | Ahmad Waqar (done by Hanan) | Done | 2026-11-17 | [US-5.2](US-5.2.md) | [evidence](../evidence/us-5.2/) |
| US-5.3 | Implement incremental loading with watermarks | Ahmad Waqar (done by Hanan) | Done | 2026-11-17 | [US-5.3](US-5.3.md) | [evidence](../evidence/us-5.3/) |
| US-5.4 | Capture cleaning evidence | Ahmad Waqar (done by Hanan) | Done | 2026-11-17 | [US-5.4](US-5.4.md) | [evidence](../evidence/us-5.4/) |
| US-6.1 | Build the dimension loader pattern and surrogate keys | Hanan | Done | 2026-11-17 | [US-6.1](US-6.1.md) | [evidence](../evidence/us-6.1/) |
| US-6.2 | Implement tenant SCD Type 2 | Hanan | Done | 2026-11-21 | [US-6.2](US-6.2.md) | [evidence](../evidence/us-6.2/) |
| US-6.3 | Extend SCD2 to unit, vendor and category | Eesha (done by Hanan) | Done | 2026-11-21 | [US-6.3](US-6.3.md) | [evidence](../evidence/us-6.3/) |
| US-6.4 | Load remaining dimensions and hierarchies | Eesha (done by Hanan) | Done | 2026-11-21 | [US-6.4](US-6.4.md) | [evidence](../evidence/us-6.4/) |
| US-6.5 | Inferred members, late arrivals, dimension tests | Hanan | Done | 2026-11-21 | [US-6.5](US-6.5.md) | [evidence](../evidence/us-6.5/) |
| US-7.1 | Build the fact loading framework and date-aware key mapping | Hanan | Done | 2026-11-21 | [US-7.1](US-7.1.md) | [evidence](../evidence/us-7.1/) |
| US-7.2 | Load fact_rent_invoice_line and fact_payment | Ahmad Waqar (done by Hanan) | Done | 2026-11-21 | [US-7.2](US-7.2.md) | [evidence](../evidence/us-7.2/) |
| US-7.3 | Load fact_unit_occupancy_daily | Hanan | Done | 2026-11-21 | [US-7.3](US-7.3.md) | [evidence](../evidence/us-7.3/) |
| US-7.4 | Load fact_maintenance_request | Junaid (done by Hanan) | Done | 2026-11-21 | [US-7.4](US-7.4.md) | [evidence](../evidence/us-7.4/) |
| US-7.5 | Load fact_lease_event and fact_vacancy_incentive_coverage | Eesha (done by Hanan) | Done | 2026-11-21 | [US-7.5](US-7.5.md) | [evidence](../evidence/us-7.5/) |
| US-7.6 | Automate grain and orphan checks | Junaid (done by Hanan) | Done | 2026-11-21 | [US-7.6](US-7.6.md) | [evidence](../evidence/us-7.6/) |
| US-8.1 | Build run_pipeline.py with logging and lineage | Junaid (done by Hanan) | Done | 2026-11-21 | [US-8.1](US-8.1.md) | [evidence](../evidence/us-8.1/) |
| US-8.2 | Implement source-to-warehouse reconciliation (DQ-07) | Hanan | Done | 2026-11-21 | [US-8.2](US-8.2.md) | [evidence](../evidence/us-8.2/) |
| US-8.3 | Test idempotency and failure recovery | Junaid (done by Hanan) | Done | 2026-11-21 | [US-8.3](US-8.3.md) | [evidence](../evidence/us-8.3/) |
| US-8.4 | Run at full volume and record baseline timings | Junaid (done by Hanan) | Done | 2026-11-21 | [US-8.4](US-8.4.md) | [evidence](../evidence/us-8.4/) |
| US-9.1 | Produce the Data Cleaning Report (PDF) | Ahmad Waqar (done by Hanan) | Done | 2026-11-22 | [US-9.1](US-9.1.md) | [evidence](../evidence/us-9.2/) |
| US-9.2 | Produce the Data Quality Report (PDF) | Ahmad Waqar (done by Hanan) | Done | 2026-11-22 | [US-9.2](US-9.2.md) | [evidence](../evidence/us-9.2/) |
| US-9.3 | Package scripts, README and the GitHub submission | Whole team (done by Hanan) | Done | 2026-11-22 | [US-9.3](US-9.3.md) | [evidence](../evidence/us-9.3/) |
| US-10.1 | Create the reporting views required by the brief | Eesha (done by Hanan) | Done | 2026-11-22 | [US-10.1](US-10.1.md) | [evidence](../evidence/us-10.1/) |
| US-10.2 | Build the four gold marts | Eesha (done by Hanan) | Done | 2026-11-22 | [US-10.2](US-10.2.md) | [evidence](../evidence/us-10.2/) |
| US-10.3 | Validate the reporting layer and secure access | Eesha (done by Hanan) | Done | 2026-11-22 | [US-10.3](US-10.3.md) | [evidence](../evidence/us-10.1/) |
| US-11.6 | Draft the analytical SQL on the small profile | Hanan (with Ahmad Waqar) | Done | 2026-11-22 | [US-11.6](US-11.6.md) | [evidence](../evidence/us-11.6/) |
| US-11.1 | Answer the finance questions (Q1 to Q5) | Hanan | Done | 2026-11-22 | [US-11.1](US-11.1.md) | [evidence](../evidence/us-11.1/) |
| US-11.2 | Answer the occupancy and leasing questions (Q6 to Q8) | Hanan | Done | 2026-11-22 | [US-11.2](US-11.2.md) | [evidence](../evidence/us-11.1/) |
| US-11.3 | Answer maintenance, owner, incentive and weather questions (Q9 to Q14) | Ahmad Waqar (done by Hanan) | Done | 2026-11-22 | [US-11.3](US-11.3.md) | [evidence](../evidence/us-11.1/) |
| US-11.4 | Implement ROLLUP and CUBE | Hanan | Done | 2026-11-22 | [US-11.4](US-11.4.md) | [evidence](../evidence/us-11.1/) |
| US-11.5 | Add window analytics and consolidate the SQL pack | Ahmad Waqar (done by Hanan) | Done | 2026-11-22 | [US-11.5](US-11.5.md) | [evidence](../evidence/us-11.5/) |
| US-12.1 | Build the benchmark harness and record the baseline | Junaid (done by Hanan) | Done | 2026-11-22 | [US-12.1](US-12.1.md) | [evidence](../evidence/us-12.1/) |
| US-12.2 | Run the indexing and partitioning experiments | Junaid (done by Hanan) | Done | 2026-11-22 | [US-12.2](US-12.2.md) | [evidence](../evidence/us-12.2/) |
| US-12.3 | Write the Indexing Report (PDF) | Junaid (done by Hanan) | Done | 2026-11-22 | [US-12.3](US-12.3.md) | [evidence](../evidence/us-12.3/) |
| US-13.1 | Connect Power BI and build the data model | Eesha (prepared by Hanan) | Done | 2026-11-22 | [US-13.1](US-13.1.md) | [evidence](../evidence/us-13.1/) |
| US-13.2 | Build Page 1: Executive Overview | Eesha | Done | 2026-11-25 | [US-13.2](US-13.2.md) | [evidence](../evidence/us-13.2/) |
| US-13.3 | Build Page 2: Detailed Analysis | Eesha | Done | 2026-11-25 | [US-13.3](US-13.3.md) | [evidence](../evidence/us-13.3/) |
| US-13.4 | Build Page 3: Decision Page | Eesha | Done | 2026-11-25 | [US-13.4](US-13.4.md) | [evidence](../evidence/us-13.4/) |
| US-13.5 | Validate, finish and export | Eesha (reviewed by Junaid) | Done | 2026-11-25 | [US-13.5](US-13.5.md) | [evidence](../evidence/us-13.5/) |

## E14. Business insights and presentation

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-14.1 | Mine insights and verify planted patterns | Hanan | Done | 2026-11-25 | [US-14.1](US-14.1.md) | [evidence](../evidence/us-14.1/) |
| US-14.2 | Write Business Insights Report (PDF) | Hanan | Done | 2026-11-25 | [US-14.2](US-14.2.md) | [evidence](../evidence/us-14.2/) |
| US-14.3 | Build final presentation and rehearse demo | Whole team | Done | 2026-11-25 | [US-14.3](US-14.3.md) | [evidence](../evidence/us-14.3/) |

## E15. Project closure

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-15.1 | Run clean-machine rebuild | Whole team | Done | 2026-11-25 | [US-15.1](US-15.1.md) | [evidence](../evidence/us-15.1/) |
| US-15.2 | Audit documentation consistency | Hanan | Done | 2026-11-25 | [US-15.2](US-15.2.md) | [evidence](../evidence/us-15.2/) |
| US-15.3 | Sweep the rubric and package the submission | Whole team | Done | 2026-11-25 | [US-15.3](US-15.3.md) | [evidence](../evidence/us-15.3/) |

## Team decisions made while doing the work

| Date | Decision | Where recorded |
|---|---|---|
| 2026-11-06 | Renamed schemas (`lue_*`) are used instead of the brief's `project_*`; pending instructor confirmation (O4) | [US-0.1](US-0.1.md), `phase1/README.md` |
| 2026-11-07 | Repository is public, because GitHub Free does not enforce branch rules on private repositories | [US-0.3](US-0.3.md) |
| 2026-11-07 | A teammate review before merging is optional and not enforced; the `ci` check and the pull request are enforced | [US-0.3](US-0.3.md) |
| 2026-11-10 | The static reference dimensions have 6 charge types (not the plan's 4), following the Phase 1 pack; settlement days are our assumption | [US-1.4](US-1.4.md) |
| 2026-11-14 | S1 source tables keep primary keys only, no foreign keys: the defects US-2.6 plants (orphans, invoices before the tenant) could not exist otherwise | [US-2.2](US-2.2.md) |
| 2026-11-14 | Ownership `valid_to` is exclusive and empty for the current owner; workbooks are hashed by content, not bytes | [US-2.2](US-2.2.md) |
| 2026-11-15 | Stage run order is the explicit `STAGE_ORDER` list in `etl/generate_data.py`, not import order | [US-2.4](US-2.4.md) |
| 2026-11-15 | A bounced cheque is a negative payment (status Bounced) with negative allocations; the original keeps status Cleared | [US-2.4](US-2.4.md) |
| 2026-11-15 | Opening leases carry pre-window start dates (migrated at go-live); no lease event or invoice predates its tenant record | [US-2.3](US-2.3.md) |
| 2026-11-15 | Rent is constant inside a lease and changes only at renewal; mid-lease rent changes are planted by US-2.6 | [US-2.3](US-2.3.md) |
| 2026-11-14 | Generator stages get one seeded NumPy generator each, derived from the run's seed and the stage name, instead of one shared generator passed in order | [US-2.1](US-2.1.md) |
| 2026-11-09 | `dim_request_flags` keeps no special members, as in the Phase 1 pack; plan US-1.4's "plus the Unknown member" cannot fit (three NOT NULL flags, all 8 combinations unique) | [US-1.2](US-1.2.md) |
| 2026-11-16 | S5 weather is real Open-Meteo data, downloaded once in 16 small requests with retries and resume, and committed; nothing else uses the network | [US-2.5](US-2.5.md) |
| 2026-11-16 | S4 tickets carry no tenant: the fact takes the tenant from the lease active on the raised date (-2 if vacant), so US-2.5 needs only US-2.2 | [US-2.5](US-2.5.md) |
| 2026-11-16 | Defects go only on records nothing points to, one per record, so each rejected record fails exactly one check and nothing cascades; S1 keeps its types and keys (it must load into `src_pms`) | [US-2.6](US-2.6.md) |
| 2026-11-16 | Expected handling has a fourth value, `accept`, for tenant attribute changes (a new SCD2 version, not a finding) | [US-2.6](US-2.6.md) |
| 2026-11-16 | Late tenants and tenant changes are the next S1 extract (`s1/late_arriving/`, `s1/changes/`), not loaded by `db_load_source.py` | [US-2.6](US-2.6.md) |
| 2026-11-16 | Incentive offers are posted on vacant units (planted pattern 4); the generator reads the committed weather cache for rain-driven leaks | [US-2.6](US-2.6.md) |
| 2026-11-16 | `--clean` gives the clean control batch; the US-2.2 to US-2.5 tests and the S1 database test run on it | [US-2.6](US-2.6.md) |
| 2026-11-16 | Bronze is all `TEXT`, append-only, with `batch_id`, `source_system`, `loaded_at` (plus `row_hash` for S1, `source_file` and `source_row` for files) | [US-3.1](US-3.1.md) |
| 2026-11-16 | S1 changes are found by row hash; the watermark is kept but cannot see back-dated changes or tables without `updated_at` | [US-3.2](US-3.2.md) |
| 2026-11-16 | File loads and checksums go to a new `lue_audit.file_load`; the pack's `lineage` stays one row per bronze table and source | [US-3.3](US-3.3.md) |
| 2026-11-16 | A ticket's status rows keep the ticket object's position (`source_row`), so duplicated tickets keep their own histories | [US-3.4](US-3.4.md) |
| 2026-11-17 | Quality rules are data in `etl/quality/rules.toml` (TOML: no new dependency); the engine builds each rule's SQL from its fields | [US-4.1](US-4.1.md) |
| 2026-11-17 | Findings (rejections and warnings) go to a new `lue_audit.dq_result` by bronze `row_id`; the pack's quarantine holds the rejected rows | [US-4.1](US-4.1.md) |
| 2026-11-17 | A day-first date passes DQ-02 (repaired in US-5.1); a missing tenant or vendor is a warning (inferred member, US-6.5) | [US-4.2](US-4.2.md), [US-4.3](US-4.3.md) |
| 2026-11-17 | Settlement lines without a payment pass E4: unmatched settlements are US-5.2's | [US-4.3](US-4.3.md) |
| 2026-11-17 | The staging contract is data (`etl/staging/spec.py`); its DDL and `docs/contracts/staging.md` are generated and checked by CI | [US-5.1](US-5.1.md) |
| 2026-11-17 | `clean_text` keeps case; one spelling per value comes from the vocabulary (`std`), so 'IT and Software' and 'WhatsApp' survive | [US-5.1](US-5.1.md) |
| 2026-11-17 | Staging reads only batches E4 has validated (new `lue_audit.dq_batch`); a ticket survives by its latest status time | [US-5.1](US-5.1.md) |
| 2026-11-17 | Derived allocations complete a payment on its own invoice first, then oldest due; a reversal mirrors its original | [US-5.2](US-5.2.md) |
| 2026-11-17 | `is_recurring` uses the data dictionary's 30 days; the app's 90-day flag is kept as `source_is_recurring` | [US-5.2](US-5.2.md) |
| 2026-11-17 | The staging watermark is `loaded_at` plus the last batch read; counts per run in new `lue_audit.stg_load` | [US-5.3](US-5.3.md) |
| 2026-11-17 | Dimensions are data (`etl/dimensions/spec.py`, SCD types checked against the Phase 1 dictionary in CI); one loader; a member's first SCD2 version is valid from 1900-01-01 | [US-6.1](US-6.1.md) |
| 2026-11-21 | Tenant history is rebuilt from bronze (staging keeps only the latest row); contact channel is Type 1 as the frozen dictionary says | [US-6.2](US-6.2.md) |
| 2026-11-21 | Vendor rating history from the register's previous rating and change date; category SLA history from the policy's valid_from | [US-6.3](US-6.3.md) |
| 2026-11-21 | Bands: building age as of today, owner portfolio from current ownership ('None' for no current unit), rain and heat from the dictionary's thresholds | [US-6.4](US-6.4.md) |
| 2026-11-21 | Inferred members only on dim_tenant (the frozen DDL's is_inferred); completed in place when the record arrives | [US-6.5](US-6.5.md) |
| 2026-11-21 | Facts load by syncing to their source on the grain (delete, update, insert) instead of ON CONFLICT: the frozen DDL has no unique key on most fact grains | [US-7.1](US-7.1.md) |
| 2026-11-21 | Money facts reconcile to staging by month of their own date (invoice date, paid date), one lue_audit.reconciliation row per month; the D17 cohort rate is a mart measure | [US-7.2](US-7.2.md) |
| 2026-11-21 | The occupancy snapshot syncs every month each run and refreshes its last 35 days; refreshed rows are reported in rows_updated (the D14 exception); arrears by window sums over per-lease balance changes | [US-7.3](US-7.3.md) |
| 2026-11-21 | Maintenance milestones not reached are -2 (the dictionary), not -1 (the plan's wording); tenant from the lease active on the raised date, -2 when raised by staff | [US-7.4](US-7.4.md) |
| 2026-11-21 | Incentive coverage keeps vacant unit-days only (the dictionary); lease events keyed by lease, type and date, enforced by the loader | [US-7.5](US-7.5.md) |
| 2026-11-21 | Fact tests run as the last step of every fact run, results in lue_audit.reconciliation; a violation fails the run | [US-7.6](US-7.6.md) |
| 2026-11-21 | One run_id per pipeline run: each layer joins the pipeline's run; setup stages run first and are logged once the run exists; only the S5 weather is non-critical | [US-8.1](US-8.1.md) |
| 2026-11-21 | DQ-07 by month: source = warehouse + quarantined (a rejected row explains only if its key never reached staging); warehouse_value holds warehouse + quarantined in the frozen table | [US-8.2](US-8.2.md) |
| 2026-11-21 | The pipeline validates only new batches (a rerun rejects nothing twice); one warehouse holds one generation of the data, another is refused until a reset | [US-8.3](US-8.3.md) |
| 2026-11-21 | Each layer runs ANALYZE on what it reads after a bulk load (validation 309 s to 32 s); no secondary indexes, the Phase 3 baseline stays | [US-8.4](US-8.4.md) |
| 2026-11-22 | The reports read the current findings of every batch and the evidence of the run that built staging; tables from the audit tables, nothing typed | [US-9.1](US-9.1.md) |
| 2026-11-22 | The dimension and fact load scripts are exported from the loaders' specs as SQL (CI fails on drift, a test rebuilds the facts from them); every CI check runs without make (scripts/run_ci.py) | [US-9.3](US-9.3.md) |
| 2026-11-22 | The reporting layer is derived from lue_dw only and recreated by every deploy; the marts store additive parts (rates are ratios of sums), refreshed by the pipeline's last stage; tenant analysis is per tenant version (segment at payment time); the management fee is an 8 percent assumption | [US-10.1](US-10.1.md), [US-10.2](US-10.2.md) |
| 2026-11-22 | The analytical queries were drafted straight into the final files and run on the small profile first (no separate draft folder); Q3 uses the pack's four ageing buckets; a late payment is more than 15 days late; heavy rain is 10 mm or more, the day after counted; Q8 shows the event-based renewal rate with the lease-link rate beside it | [US-11.6](US-11.6.md) |
| 2026-11-22 | The benchmark interleaves baseline and after in every round and keeps the fastest of 3 back-to-back runs (a shared machine's speed varies); serial plans (JIT and parallel workers off); a query is improved only when every run after beats every run before; the candidate indexes stay out of the deploy (D20) | [US-12.1](US-12.1.md), [US-12.2](US-12.2.md) |
| 2026-11-22 | The dashboard's model is a file (`docs/powerbi/model.json`) and its measures one DAX file, checked against the reporting layer by CI; every measure's value is computed from the marts in Python as the DAX does and checked against the facts; the arrears ratio's denominator is billed to date; the vendor is ranked against its own trade; the drill-through targets the Detailed Analysis page, so there are exactly three pages | [US-13.1](US-13.1.md), [US-13.3](US-13.3.md), [US-13.4](US-13.4.md) |
| 2026-11-25 | The KPI cards show the full-window value as the headline; the trend visual starts at FY2023-24; the arrears bar shows absolute PKR (not the ratio) so the director sees the largest absolute exposure; tenant segments are computed at payment time (per tenant version) | [US-13.2](US-13.2.md), [US-13.3](US-13.3.md) |
| 2026-11-25 | Three recommendations on the Decision page (not four or five): keeps the page readable without scrolling; the assumptions box is mandatory; dynamic-text measures use `TOPN` so the page responds to slicers | [US-13.4](US-13.4.md) |
| 2026-11-25 | Five insights chosen (not six planted patterns): the leasing incentive and the city-churn patterns are related and are merged into I3/I4 for a cleaner story; values are from the small profile (seed 42) and are illustrative | [US-14.1](US-14.1.md) |
| 2026-11-25 | The insights report runs offline with `--insights` (no DB): insight values are embedded constants derived from the analytical queries run in US-14.1; this keeps CI offline-safe | [US-14.2](US-14.2.md) |
| 2026-11-25 | The consistency audit checks only deliverable files (story docs, DDL, Makefile, evidence folders); the plan document is excluded because it is human-edited and too fragile to parse by rule | [US-15.2](US-15.2.md) |
| 2026-11-25 | The packaging script lists PBIX and PPT as MANUAL deliverables and does not fail on their absence; it only fails if a code-generated deliverable (SQL, Python, generated PDF) is missing; the git tag `phase3-submission` marks the release candidate | [US-15.3](US-15.3.md) |
