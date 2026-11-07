"""Build the five Phase 1 PDF documents from model.py."""
import os
import sys
from pdfkit import (P, H1, H2, bullets, numbered, table, callout, code, image, cover_block, build, esc, Spacer,
                    PageBreak, CondPageBreak, KeepTogether, mm, CONTENT_W)
from model import (DIMENSIONS, FACTS, TABLES, AUDIT, SOURCES, SOURCE_TABLES, PROCESSES, QUESTIONS, GRAIN_TESTS, KPIS,
                   STAKEHOLDERS, HIERARCHIES, ADDITIVITY, BUS_DIMS, bus_matrix)
from sql_examples import EXAMPLES, GRAIN_CHECKS

OUT = sys.argv[1]
PNG = os.path.join(OUT, "diagrams", "png")

N_Q = len(QUESTIONS)
N_F = len(FACTS)
N_D = len(DIMENSIONS)

DECISIONS = {
    "Q1": "Which buildings need collection follow-up this month",
    "Q2": "Where to escalate arrears recovery and review owner agreements",
    "Q3": "Which balances to chase first and when to start legal notices",
    "Q4": "Whether to ask for larger deposits or post-dated cheques from higher-risk segments",
    "Q5": "Which payment channels to promote to tenants",
    "Q6": "Where to focus leasing effort and adjust asking rents",
    "Q7": "Which unit types need price or furnishing changes",
    "Q8": "Where to run tenant retention before renewal dates",
    "Q9": "Which vendors to keep, retrain or replace",
    "Q10": "Which buildings need more maintenance capacity or stricter vendor SLAs",
    "Q11": "How much maintenance reserve to budget per building",
    "Q12": "What to report to each owner and which portfolios are at risk of leaving LUE",
    "Q13": "Whether incentives are worth their cost, and which type to offer",
    "Q14": "Whether to schedule pre-monsoon roof and drainage inspections",
}

PROBLEMS = [
    ("Collections are opaque: arrears by building and ageing need manual spreadsheets",
     "Late payers are found only when owners complain", "P1 Rent invoicing and payment"),
    ("No daily view of which units are occupied", "Slow-to-let unit types are found months late", "P2 Unit occupancy"),
    ("Maintenance speed and vendor SLAs are not measured", "SLA breaches are anecdotal; poor vendors keep getting work",
     "P3 Maintenance"),
    ("Renewals and move-outs are not tracked", "Tenant churn by building is invisible", "P4 Lease lifecycle"),
    ("Incentives (e.g. one month rent-free) are offered without measuring their effect",
     "Discounts may cost money without shortening vacancy", "P5 Vacancy marketing"),
    ("Owner reports take staff several days", "Owners lose trust in LUE", "Cross-process (NOI per owner)"),
    ("Changes overwrite old values", "Past reports cannot be reproduced", "SCD Type 2 dimensions"),
]

OBJECTIVES = [
    ("1", "Model LUE's core business processes dimensionally", f"5 processes, {N_F} fact tables, each with one written grain"),
    ("2", "Answer management's questions", f"{N_Q} questions, each traced to its fact, dimensions and OLAP operation"),
    ("3", "Preserve history where it matters", "SCD Type 2 queries reproduce a past month's report exactly"),
    ("4", "Guarantee trustworthy numbers", "Every planted defect is caught; source and warehouse totals reconcile on every run"),
    ("5", "Deliver usable analytics", "Power BI report with 5 pages for finance, operations, owners and pipeline health"),
    ("6", "Make the pipeline reproducible", "python run_pipeline.py rebuilds everything from the seeded generator"),
]

STACK = [
    ("Database", "PostgreSQL 16+ and pgAdmin 4", "Required", "Bronze and Silver (schema lue_staging), warehouse (lue_dw), Gold (lue_reporting) and audit (lue_audit) schemas"),
    ("Generation and ingestion", "Python 3, pandas, numpy, Faker, requests, openpyxl", "Required",
     "Seeded generator; loads all six sources into Bronze; calls the weather API"),
    ("Transformation", "Plain SQL scripts: staging.sql, dimensions.sql, facts.sql", "Required",
     "Quality checks, cleaning, SCD processing, fact loads, all readable SQL"),
    ("Orchestration", "run_pipeline.py", "Required", "Runs every step in order and writes lue_audit.etl_run_log"),
    ("BI", "Power BI Desktop", "Required", "Five-page report on the Gold marts"),
    ("Modelling", "draw.io / dbdiagram.io / Mermaid", "Required", "Conceptual, logical and physical models, source ERD, architecture"),
    ("Version control", "GitHub", "Required", "Repository in the structure given in the project brief"),
    ("Optional", "dbt Core", "Only if time allows", "Same SQL as models; SCD written by hand, not dbt snapshot"),
]

ROADMAP = [
    ("1. Design", "1–3", "30%", "Proposal, BRD, questions, fact/dimension identification, grain document, diagrams, data dictionary",
     "All seven deliverables submitted and consistent word for word"),
    ("2. Implementation", "4–6", "40%", "Generator, Bronze/Silver, quality checks and quarantine, SCD processing, facts, audit and reconciliation",
     "A full run reconciles and catches every planted defect"),
    ("3. Analytics and BI", "7–8", "30%", "Gold marts, OLAP SQL, performance tuning, Power BI report",
     "Every question answered with SQL, output and a one-line interpretation"),
]

DELIVERABLES = [
    ("01 Project Proposal", "PDF", "Business context, objectives, scope, data strategy, architecture, roadmap", "Business understanding (5)"),
    ("02 Business Requirements Document", "PDF", "Stakeholders, business, data, quality, reporting and non-functional requirements, KPIs", "Requirement analysis (5)"),
    ("03 Business Questions", "PDF", f"{N_Q} questions, decisions supported, traceability, grain test, example SQL", "Requirement analysis (5)"),
    ("04 Fact and Dimension Identification", "PDF", "Processes, fact types, bus matrix, dimensions, hierarchies, SCD policy, keys", "Fact/dimension identification (10)"),
    ("05 Grain Definition", "PDF", "Source grains, six fact grains, measures and additivity, example rows, grain checks", "Fact/dimension identification (10)"),
    ("06 Schema Diagrams", "PDF + PNG + Mermaid", "Conceptual, logical and physical models, source ERD, hierarchies, architecture", "Schema design (10)"),
    ("07 Data Dictionary", "Excel", "Every table and column: type, keys, nullability, SCD type, source, example, rule", "Schema design (10)"),
]

RISKS = [
    ("Grain wording drifts between documents", "Inconsistent model, lost marks",
     "All documents, diagrams and the dictionary are generated from one model definition"),
    ("Generator takes too long", "Phase 2 slips", "Build a small version first (2 buildings, 3 months); one member owns it from week 3"),
    ("Payment allocation logic is complex", "Wrong collection rates", "Allocate to the oldest open line first; reconcile allocated vs received totals each run"),
    ("Flat synthetic data", "Dull dashboards", "Seasonality, channel delays, monsoon leaks and planted attribute changes"),
    ("Large snapshot slows Power BI", "Slow report", "Power BI reads the Gold marts, not the 2-million-row fact"),
    ("Scope creep", "Missed deadlines", "Hold to the agreed scope; optional tools only after Phase 3 is complete"),
]

ASSUMPTIONS = [
    "LUE and all data are fictional; the generator is seeded, so every run produces identical data.",
    "A unit has one owner at a time; ownership can change on a dated transfer recorded in the S2 register.",
    "A lease has one primary tenant and one unit; a renewal creates a new lease linked to the previous one.",
    "Rent and service charges are invoiced monthly; payments may be partial and split across invoice lines.",
    "LUE's management fee is assumed to be 8% of rent collected (a parameter, used in Q12).",
    "Fiscal year runs July to June; all amounts are in Pakistani Rupees (PKR).",
    "The warehouse refreshes once a day in batch; intraday latency is not required.",
    "Co-ownership of one unit by several owners is out of scope (it would need a bridge table).",
]


FACT_SHORT = {"fact_rent_invoice_line": "rent_invoice_line", "fact_payment": "payment",
              "fact_unit_occupancy_daily": "unit_occupancy_daily", "fact_maintenance_request": "maintenance_request",
              "fact_lease_event": "lease_event", "fact_vacancy_incentive_coverage": "vacancy_incentive_coverage"}
SHORT = {"dim_unit": "Unit", "dim_tenant": "Tenant", "dim_lease": "Lease", "dim_owner": "Owner",
         "dim_payment_method": "Pay method", "dim_charge_type": "Charge type", "dim_maintenance_category": "Maint. category",
         "dim_vendor": "Vendor", "dim_lease_event_type": "Event type", "dim_request_flags": "Request flags",
         "dim_incentive": "Incentive", "dim_weather": "Weather"}


def scd_rows():
    rows = [("dim_date", "all calendar and fiscal attributes", "0", "A date's attributes never change")]
    for d in DIMENSIONS:
        for c in d["cols"]:
            if c["key"] or c["tech"] or c["name"] in ("effective_from", "effective_to", "is_current", "is_inferred"):
                continue
            if d["name"] == "dim_date" and c["scd"] == "0":
                continue
            if c["scd"] in ("0", "2") or c["scd_reason"]:
                reason = c["scd_reason"] or ("Fixed by definition or contract" if c["scd"] == "0"
                                             else "Correction or current value only")
                rows.append((d["name"], c["name"], c["scd"] or "1", reason))
    return rows


def fmt_grain(f):
    return esc(f["grain"])


# ======================================================================= 01 proposal
def proposal():
    s = cover_block("01 · Project Proposal",
                    "This proposal defines the business problem, objectives, scope, data strategy and architecture of the "
                    "LUE analytics warehouse. It is the entry point to the Phase 1 pack; detailed requirements, questions, "
                    "dimensional design, grain definitions, diagrams and the data dictionary are separate deliverables.")
    s += [H1("1. Executive summary"),
          P(f"Lahore Urban Estates (LUE) will get a PostgreSQL star-schema warehouse that answers {N_Q} management "
            f"questions across five business processes, using {N_F} fact tables, {N_D} conformed dimensions, slowly "
            "changing dimensions and a Power BI report. Data comes from six simulated source systems in five formats and "
            "passes through Bronze, Silver and Gold layers with quality checks, a quarantine table and a full audit trail."),
          table([["Processes", "Fact tables", "Dimensions", "Source systems", "Questions", "KPIs"],
                 ["5", str(N_F), str(N_D), "6", str(N_Q), str(len(KPIS))]], [1 / 6] * 6),
          Spacer(1, 4),
          P("The design covers every fact table type taught in the course (transaction, periodic snapshot, "
            "accumulating snapshot, event and coverage factless), conformed dimensions, role-playing dates, a junk "
            "dimension, degenerate dimensions, SCD Types 0, 1 and 2, inferred members for late-arriving data, and "
            "hierarchies for drill-down and roll-up."),
          H1("2. The client"),
          P("LUE is a fictional property management company that manages commercial plazas and developer-owned apartment "
            "blocks on behalf of private owners. It lets units, bills rent, collects payments, arranges repairs and earns "
            "a management fee on rent collected."),
          table([["Attribute", "Value"],
                 ["Portfolio", "About 40 buildings in 4 cities (Lahore, Karachi, Islamabad, Faisalabad): residential, office and retail"],
                 ["Scale", "About 1,800 units and 1,500 active leases; 3 years of history (July 2023 – June 2026)"],
                 ["Revenue", "Management fee on rent collected, service charges, late fees"],
                 ["Leases", "11-month residential leases; 2–5 year commercial leases"],
                 ["Payment channels", "Cash, cheque, bank transfer, Raast, JazzCash, Easypaisa"],
                 ["Currency and fiscal year", "PKR; fiscal year July–June"]], [0.25, 0.75], bold_first_col=True),
          H1("3. Business problem"),
          P("LUE's data sits in separate systems: a property management system, Excel registers kept by different teams, "
            "bank and wallet settlement files, a tenant maintenance app and per-building leasing spreadsheets. Reporting "
            "is manual and slow, so management finds problems weeks after they start."),
          table([["Problem today", "Business impact", "Process that addresses it"]] + [list(p) for p in PROBLEMS],
                [0.42, 0.33, 0.25]),
          H1("4. Why a data warehouse and not the operational database"),
          P("The operational systems are built to record transactions; the warehouse is built to analyse them over time. "
            "As in Lab 03, the source keeps a normalised model for consistent updates, while the warehouse is a "
            "denormalised dimensional model designed around business processes rather than copied from operational tables."),
          table([["", "Operational systems (sources)", "LUE warehouse"],
                 ["Purpose", "Record a lease, an invoice, a payment, a ticket", "Analyse collections, occupancy, maintenance and owners over time"],
                 ["Typical question", "What is the status of invoice INV-2026-03-00831?", "How did the collection rate by building change over three fiscal years?"],
                 ["History", "Current state only; values overwritten", "History kept through daily snapshots and SCD Type 2"],
                 ["Design", "Normalised tables (Lab 03)", "Star schemas with conformed dimensions (Labs 04–05)"],
                 ["Integration", "One system each", "Six sources integrated, cleaned and reconciled"],
                 ["Workload", "Inserts and updates", "Aggregation, ROLLUP/CUBE, drill-down, dashboards"]],
                [0.18, 0.38, 0.44], bold_first_col=True),
          H1("5. Objectives and success measures"),
          table([["#", "Objective", "Success measure"]] + [list(o) for o in OBJECTIVES], [0.05, 0.40, 0.55]),
          H1("6. Scope"),
          H2("In scope"),
          *bullets(["Conceptual, logical and physical dimensional models, source ERD and architecture diagram",
                    "Six simulated source systems produced by a seeded generator with deliberate data defects",
                    "Bronze / Silver / Gold pipeline with quality checks, quarantine, audit log and reconciliation",
                    "Star schemas with SCD Type 0/1/2, special members and inferred members",
                    "OLAP SQL (ROLLUP, CUBE, GROUPING, window functions), performance tuning, Power BI report"]),
          H2("Out of scope"),
          *bullets(["Real or personal data; live connections to production systems",
                    "Real-time or streaming analytics; predictive models",
                    "Accounting-grade general ledger and tax; co-ownership of one unit by several owners"]),
          H1("7. Stakeholders"),
          table([["Stakeholder", "Needs", "Example question", "Power BI page"]] + [list(x) for x in STAKEHOLDERS],
                [0.17, 0.22, 0.38, 0.23], bold_first_col=True),
          H1("8. Business processes"),
          P("Each process becomes one or more fact tables. Together they cover all fact table types from Lab 05."),
          table([["ID", "Process", "What happens", "Fact table(s)", "Fact type"]] +
                [[p[0], p[1], p[2], ", ".join(p[3]), p[4]] for p in PROCESSES], [0.05, 0.17, 0.33, 0.27, 0.18]),
          H1("9. Data strategy"),
          P("All data is synthetic and generated by a seeded Python script. The generator first creates one consistent "
            "operational world, then exports each part in the format the owning team would really use. This makes "
            "integration, key conflicts and data quality problems genuine rather than staged."),
          table([["ID", "Source system", "Format", "Contents", "Typical defects"]] +
                [[x["id"], x["name"], x["fmt"], x["content"], x["defects"]] for x in SOURCES],
                [0.05, 0.19, 0.18, 0.33, 0.25]),
          Spacer(1, 4),
          *bullets(["<b>Operational data only.</b> The generator never writes warehouse tables; every fact, including the "
                    "daily occupancy snapshot, is derived by the ETL, so the transformation logic is visible and assessable.",
                    "<b>Planted defects with an answer key.</b> The generator records every injected defect in "
                    "defects_answer_key.csv; after each run the pipeline compares its quarantine counts with this file.",
                    "<b>Realism.</b> Rents calibrated by city and building class, seasonal move-ins, channel-specific payment "
                    "delays, maintenance volume scaled by building age, more leak tickets in monsoon months.",
                    "<b>Volumes over 3 years.</b> About 1.97 million occupancy rows (1,800 units × 1,095 days), 130,000 "
                    "invoice lines, 60,000 payment allocations, 8,000 lease events and 6,000 maintenance requests."]),
          CondPageBreak(215 * mm),
          H1("10. Architecture"),
          P("The pipeline follows the 11 sections of the reference architecture diagram. Rows move from the sources "
            "through Bronze, quality checks, Silver and SCD processing into the warehouse, then to Gold marts and Power BI; "
            "failed rows go to quarantine, and audit, performance and lineage run alongside."),
          image(os.path.join(PNG, "06_architecture.png"), max_h=185 * mm),
          P("Figure 1. LUE architecture (Mermaid source: diagrams/mermaid/06_architecture.mmd).", "caption"),
          table([["Section", "LUE implementation", "Schema / script"],
                 ["1 Sources", "S1–S6", "02_Data/raw_data"],
                 ["2 Orchestration", "Fixed step order, one run_id per run", "run_pipeline.py"],
                 ["3 Bronze", "As-is copies + batch_id, source_system, loaded_at", "lue_staging.brz_*, ingest_sources.py"],
                 ["4 Quality and quarantine", "Six ordered checks; failures to lue_audit.quarantine", "staging.sql"],
                 ["5 Silver", "Typed, standardised, deduplicated, incremental by watermark", "lue_staging.stg_*, staging.sql"],
                 ["SCD processing", "Type 1 overwrite, Type 2 expire + insert, inferred members", "dimensions.sql"],
                 ["6 Warehouse", f"{N_D} dimensions, {N_F} facts, special members", "schema lue_dw, warehouse.sql, facts.sql"],
                 ["7 Performance", "Monthly partitions, indexes, EXPLAIN ANALYZE", "warehouse.sql, performance.sql"],
                 ["8 Gold", "Four marts as materialized views", "schema lue_reporting, Views.sql"],
                 ["9 Analytics and BI", "OLAP SQL and the Power BI report", "OLAP.sql, PowerBI.pbix"],
                 ["10 Audit", "Run log and reconciliation results", "schema lue_audit"],
                 ["11 Lineage", "Lineage columns and lue_audit.lineage", "schema lue_audit, data dictionary"]],
                [0.22, 0.48, 0.30], bold_first_col=True),
          H1("11. Technology stack"),
          P("The build uses only the brief's free stack. Every transformation is plain SQL that can be opened and run, "
            "because the labs assess the logic, not the tooling."),
          table([["Layer", "Tool", "Status", "Role"]] + [list(x) for x in STACK], [0.18, 0.30, 0.14, 0.38],
                bold_first_col=True),
          H1("12. Roadmap"),
          table([["Phase", "Weeks", "Weight", "Work", "Done when"]] + [list(x) for x in ROADMAP],
                [0.17, 0.08, 0.08, 0.38, 0.29], bold_first_col=True),
          H1("13. Phase 1 deliverables and marking map"),
          table([["Deliverable", "Format", "Contents", "Rubric area (marks)"]] + [list(x) for x in DELIVERABLES],
                [0.27, 0.14, 0.37, 0.22], bold_first_col=True),
          H1("14. Risks and mitigations"),
          table([["Risk", "Impact", "Mitigation"]] + [list(x) for x in RISKS], [0.28, 0.22, 0.50]),
          H1("15. Assumptions"),
          *bullets(ASSUMPTIONS)]
    build(os.path.join(OUT, "01_Project_Proposal.pdf"), "01 Project Proposal", s)


# ======================================================================= 02 BRD
BRS = [
    ("BR-01", "Report the monthly collection rate by building, city and region, with subtotals", "Finance head", "Must", "Q1"),
    ("BR-02", "Rank buildings by arrears ratio and show overdue balances by ageing bucket", "Finance head, CEO", "Must", "Q2, Q3"),
    ("BR-03", "Identify tenants with recurring late payment and compare segments at the time of payment", "Finance head", "Must", "Q4"),
    ("BR-04", "Compare payment channels on lateness and settlement speed", "Finance head", "Should", "Q5"),
    ("BR-05", "Show daily occupancy and vacancy trends by city and unit type", "Operations head", "Must", "Q6"),
    ("BR-06", "Measure vacancy duration by unit type", "Leasing manager", "Must", "Q7"),
    ("BR-07", "Report renewal rate and tenant loss at renewal by building", "Leasing manager", "Must", "Q8"),
    ("BR-08", "Measure maintenance speed, SLA breaches and cost by category, vendor and building", "Operations head", "Must", "Q9, Q10, Q11"),
    ("BR-09", "Report net operating income per owner portfolio", "CEO, owner relations lead", "Must", "Q12"),
    ("BR-10", "Measure whether vacancy incentives shorten vacancy", "Leasing manager", "Should", "Q13"),
    ("BR-11", "Relate maintenance demand to weather", "Operations head", "Should", "Q14"),
    ("BR-12", "Reproduce any past monthly report exactly, even after master data changes", "All", "Must", "Q4, Q9"),
]

DQ = [
    ("DQ-01", "NULL", "Business keys, amounts and dates must be present", "Quarantine; non-critical text defaults to 'Unknown'"),
    ("DQ-02", "Data type", "Dates parse in every building's format; amounts are numeric", "Quarantine"),
    ("DQ-03", "Duplicate", "No repeated payment_reference or invoice number + line number in a batch", "Keep the first, quarantine the rest"),
    ("DQ-04", "Business rule", "net = billed + tax − discount; lease end after start; resolved after raised; payment > 0 unless a reversal", "Quarantine"),
    ("DQ-05", "Referential", "Every invoice's lease, unit and tenant exist", "Missing tenant → inferred member; missing unit → quarantine"),
    ("DQ-06", "Range", "Dates between 2023-07-01 and the run date; amounts within plausible bounds", "Quarantine"),
    ("DQ-07", "Reconciliation", "Source totals equal warehouse totals (rows, net_amount, payments per channel per day)", "Run marked Warning; reported on the pipeline page"),
]

NFR = [
    ("NFR-01", "Reproducibility", "One command rebuilds sources, warehouse, marts and checks from the seeded generator"),
    ("NFR-02", "Auditability", "Every run logs rows read, inserted, updated and rejected per step; every rejected row is kept with its reason"),
    ("NFR-03", "Lineage", "Every row carries source_system, batch_id and loaded_at; lue_audit.lineage maps each table to its sources"),
    ("NFR-04", "Performance", "Three benchmark queries are measured with EXPLAIN ANALYZE before and after partitioning and indexing"),
    ("NFR-05", "Usability", "Power BI pages load from Gold marts; every subtotal row in SQL output is labelled, never a bare NULL"),
    ("NFR-06", "Privacy", "No real personal data; names, phones and companies are synthetic"),
    ("NFR-07", "Documentation", "Grain sentences, table and column names are identical across all documents and the dictionary"),
    ("NFR-08", "Refresh", "Daily batch; the last 35 days of the occupancy snapshot are re-derived to absorb late-arriving data"),
]


def brd():
    s = cover_block("02 · Business Requirements Document",
                    "This document states what the warehouse must deliver and how each requirement will be accepted. "
                    "It translates stakeholder needs into business, data, quality, reporting and non-functional "
                    "requirements, and traces every business requirement to the questions and facts that satisfy it.")
    s += [H1("1. Purpose and audience"),
          P("The BRD is the agreement between LUE management and the project team. Readers are the six stakeholder "
            "groups below, the course instructor and the team members who will build Phase 2 and Phase 3."),
          H1("2. Business background"),
          P("LUE manages about 1,800 units in 40 buildings across Lahore, Karachi, Islamabad and Faisalabad for private "
            "owners. Its data is spread across a property management system, Excel registers, settlement files, a tenant "
            "maintenance app and leasing spreadsheets, so cross-building questions take days to answer and history is "
            "lost whenever a record is updated."),
          H1("3. Stakeholders and needs"),
          table([["Stakeholder", "Needs", "Example question", "Report page"]] + [list(x) for x in STAKEHOLDERS],
                [0.17, 0.22, 0.38, 0.23], bold_first_col=True),
          H1("4. Business requirements"),
          table([["ID", "Requirement", "Stakeholder", "Priority", "Questions"]] + [list(b) for b in BRS],
                [0.08, 0.52, 0.20, 0.09, 0.11], bold_first_col=True),
          P("Acceptance: each requirement is met when its questions are answered by SQL on the warehouse with output and "
            "a one-line interpretation, and the same figures appear on the Power BI report.", "caption"),
          H1("5. KPI definitions"),
          P("Every KPI is computed from additive parts (sums and counts) and divided at the end. Averaging per-row ratios "
            "gives the wrong answer when rows have different weights (Lab 05 Task 6.3)."),
          table([["KPI", "Formula (from additive parts)", "Facts used", "Q"]] + [list(k) for k in KPIS],
                [0.20, 0.47, 0.26, 0.07], bold_first_col=True),
          H1("6. Data requirements"),
          table([["Requirement", "Detail"],
                 ["Sources", "Six systems: PostgreSQL (S1), Excel (S2), CSV (S3, S6), JSON (S4), REST API (S5)"],
                 ["Granularity", "Lowest available level: invoice line, payment allocation, unit-day, request, lease event, offer-day"],
                 ["History", "Three years; SCD Type 2 on tenant type and sector, unit type and furnishing, vendor rating, SLA policy"],
                 ["Ownership", "Owner on each fact row resolved from the ownership register at the event date"],
                 ["Calendar", "Calendar and fiscal (July–June) hierarchies; public holidays and Ramadan flags"],
                 ["Late-arriving data", "Inferred dimension members with deferred update; late facts loaded at their true date"],
                 ["Refresh", "Daily batch with incremental loads by watermark per source"]], [0.22, 0.78],
                bold_first_col=True),
          H1("7. Data quality requirements"),
          table([["ID", "Check", "Rule", "On failure"]] + [list(d) for d in DQ], [0.08, 0.13, 0.49, 0.30],
                bold_first_col=True),
          P("Every rejected row is stored in lue_audit.quarantine with source system, source table, batch_id, check name, "
            "reason and timestamp. The generator's defect answer key is used to prove each check works.", "body"),
          H1("8. Reporting requirements"),
          table([["Page", "Audience", "Main visuals", "Requirements"],
                 ["Collections", "Finance head, building managers", "Collection rate trend, ageing buckets, overdue tenants", "BR-01 to BR-04"],
                 ["Occupancy and leasing", "Operations head, leasing manager", "Occupancy by city and unit type, vacancy duration, renewal rate, incentive effect", "BR-05 to BR-07, BR-10"],
                 ["Maintenance", "Operations head", "SLA breaches by vendor, days to resolve, rain vs leak requests", "BR-08, BR-11"],
                 ["Owner portfolio", "CEO, owner relations lead", "NOI per owner, maintenance cost per unit", "BR-09"],
                 ["Pipeline health", "Project team, instructor", "Run log, rejects by reason, reconciliation status", "NFR-02"]],
                [0.17, 0.23, 0.42, 0.18], bold_first_col=True),
          H1("9. Non-functional requirements"),
          table([["ID", "Area", "Requirement"]] + [list(n) for n in NFR], [0.09, 0.15, 0.76], bold_first_col=True),
          H1("10. Assumptions and constraints"),
          *bullets(ASSUMPTIONS + ["Only the brief's free stack is used: PostgreSQL, pgAdmin, Python/pandas, Power BI "
                                  "Desktop, draw.io/Mermaid and GitHub."]),
          H1("11. Out of scope"),
          *bullets(["Real or personal data, live integration, streaming and prediction",
                    "Accounting-grade ledger and tax reporting", "Co-ownership of a unit by several owners"]),
          H1("12. Requirements traceability"),
          table([["Requirement", "Questions", "Fact tables", "Report page"],
                 ["BR-01 to BR-04", "Q1–Q5", "fact_rent_invoice_line, fact_payment", "Collections"],
                 ["BR-05, BR-06", "Q6, Q7", "fact_unit_occupancy_daily", "Occupancy and leasing"],
                 ["BR-07", "Q8", "fact_lease_event", "Occupancy and leasing"],
                 ["BR-08", "Q9–Q11", "fact_maintenance_request", "Maintenance"],
                 ["BR-09", "Q12", "fact_payment, fact_maintenance_request", "Owner portfolio"],
                 ["BR-10", "Q13", "fact_vacancy_incentive_coverage, fact_unit_occupancy_daily", "Occupancy and leasing"],
                 ["BR-11", "Q14", "fact_maintenance_request (dim_weather)", "Maintenance"],
                 ["BR-12", "Q4, Q9", "All facts via SCD Type 2 dimensions", "All pages"]],
                [0.18, 0.14, 0.45, 0.23], bold_first_col=True)]
    build(os.path.join(OUT, "02_Business_Requirements_Document.pdf"), "02 Business Requirements Document", s)


# ======================================================================= 03 questions
def questions():
    s = cover_block("03 · Business Questions",
                    f"The {N_Q} analytical questions below were derived from the stakeholders' decisions, not from the "
                    "source tables. Each one is traced to the fact table whose grain can answer it, the dimensions it "
                    "slices by, its measures and the OLAP operation it needs. The minimum required by the brief is 10.")
    s += [H1("1. Questions and the decisions they support"),
          table([["#", "Question", "Process", "Stakeholder", "Decision supported"]] +
                [[q[0], q[1], q[2], q[3], DECISIONS[q[0]]] for q in QUESTIONS],
                [0.06, 0.36, 0.09, 0.17, 0.32], bold_first_col=True),
          KeepTogether([H1("2. Traceability matrix"),
          P("Every question maps to an existing fact and conformed dimensions. Questions that span two processes are "
            "answered by drill-across: each fact is aggregated to the shared dimensions first and then combined."),
          table([["#", "Fact table(s)", "Key dimensions", "Measures", "OLAP operation"]] +
                [[q[0], q[4], q[5], q[6], q[7]] for q in QUESTIONS],
                [0.06, 0.27, 0.24, 0.18, 0.25], bold_first_col=True)]),
          H1("3. Grain test: why only this fact can answer it"),
          P("Following Lab 05 Task 4.2, each group of questions was tested against every fact grain. The table records "
            "why the chosen fact is the only correct source."),
          table([["Questions", "Answered by", "Why the other facts cannot answer them"]] + [list(g) for g in GRAIN_TESTS],
                [0.12, 0.25, 0.63], bold_first_col=True),
          H1("4. Detail versus pre-aggregation"),
          P("The Gold marts store monthly summaries for Power BI (a MOLAP-style pre-aggregation, Lab 04 Section 9). "
            "Some questions need the detail the marts discard:"),
          *bullets(["<b>“Which units were vacant during Eid week?”</b> is answerable from fact_unit_occupancy_daily but "
                    "not from mart_occupancy_monthly, because the day was aggregated away.",
                    "<b>Q7 vacancy spells</b> need consecutive days per unit, which only the daily snapshot keeps.",
                    "<b>Q1</b> is answered both ways in Phase 3 to compare joins, query-time aggregation and detail "
                    "available (ROLAP vs MOLAP vs HOLAP)."]),
          PageBreak(),
          H1("5. Example SQL"),
          P("These sketches show how five questions run on the physical model. Each query was executed against the "
            "PostgreSQL 16 schema in sql/physical_model.sql. Subtotal rows are always labelled with GROUPING() so a "
            "manager never has to interpret a bare NULL (Lab 04 Tasks 6.2 and 7.4).")]
    for q, title, note, sql in EXAMPLES:
        s += [KeepTogether([H2(f"{q} · {title}"), P(esc(note)), code(sql)]), Spacer(1, 6)]
    build(os.path.join(OUT, "03_Business_Questions.pdf"), "03 Business Questions", s)


# ======================================================================= 04 fact & dimension identification
def fact_dim():
    s = cover_block("04 · Fact and Dimension Identification",
                    "This document identifies LUE's business processes, chooses a fact table type for each, identifies "
                    "the conformed dimensions, their hierarchies and SCD policy, and defines the key strategy. It follows "
                    "the four-step dimensional design process taught in Lab 05: business process → grain → dimensions → facts.")
    s += [H1("1. Business processes and fact table types"),
          table([["ID", "Process", "Fact table(s)", "Type", "Why this type"]] +
                [[p[0], p[1], ", ".join(p[3]), p[4], p[5]] for p in PROCESSES],
                [0.05, 0.15, 0.22, 0.15, 0.43], bold_first_col=True),
          P("The five processes are never combined into one fact table, because each has a different grain (Lab 05 "
            "Task 3.3). The grain sentences are defined in deliverable 05.", "caption"),
          H1("2. Fact tables"),
          table([["Fact table", "Type", "Measures", "Degenerate dimensions", "Expected rows"]] +
                [[f["name"], f["type"],
                  ", ".join(c["name"] for c in f["cols"] if not c["key"] and not c["ref"] and not c["tech"]
                            and c["name"] not in ("invoice_number", "invoice_line_no", "payment_reference",
                                                  "request_number", "request_status", "is_reversal")) or "none (factless)",
                  ", ".join(c["name"] for c in f["cols"] if c["name"] in ("invoice_number", "invoice_line_no",
                                                                           "payment_reference", "request_number",
                                                                           "request_status")) or "—",
                  f["rows"]] for f in FACTS],
                [0.24, 0.15, 0.31, 0.18, 0.12], bold_first_col=True),
          KeepTogether([H1("3. Bus matrix"),
          P("Rows are dimensions, columns are fact tables. An X marks a dimension used by a fact; for dim_date the date "
            "roles are listed. A row with several marks is a conformed dimension: the same table, keys and attribute "
            "values serve every process, which is what allows drill-across questions such as Q12."),
          table([["Dimension"] + [FACT_SHORT[f] for f, _ in bus_matrix()]] +
                [[d] + [r[j].replace("X (", "").rstrip(")") if j == 0 else r[j] for f, r in bus_matrix()]
                 for j, d in enumerate(BUS_DIMS)],
                [0.22] + [0.13] * 6, bold_first_col=True)]),
          PageBreak(),
          H1("4. Dimension catalogue"),
          table([["Dimension", "One row per", "Natural key", "Main attributes", "Hierarchy"]] +
                [[d["name"], d["grain"].replace("One row per ", ""), d["nk"],
                  ", ".join(c["name"] for c in d["cols"] if not c["key"] and not c["tech"]
                            and c["name"] not in ("effective_from", "effective_to", "is_current"))[:220],
                  d["hierarchy"]] for d in DIMENSIONS],
                [0.17, 0.17, 0.15, 0.31, 0.20], bold_first_col=True),
          H1("5. Hierarchies"),
          P("Hierarchies are flattened into their dimension (star, not snowflake), as required by Lab 04's design rule. "
            "Drill-down moves left to right; roll-up moves right to left."),
          table([["Dimension", "Hierarchy", "Levels (lowest → highest)"]] + [list(h) for h in HIERARCHIES],
                [0.25, 0.18, 0.57], bold_first_col=True),
          H1("6. SCD policy"),
          P("Every descriptive attribute has a declared type. Type 0 attributes never change; Type 1 attributes are "
            "corrected in place for all history; Type 2 attributes create a new dimension row with effective_from, "
            "effective_to and is_current, so facts keep pointing at the version valid at the time of the event."),
          table([["Dimension", "Attribute", "Type", "Reason"]] +
                [[r[0], r[1], "Type " + r[2], r[3]] for r in scd_rows()],
                [0.22, 0.20, 0.09, 0.49], bold_first_col=True,
                highlight_rows=[i + 1 for i, r in enumerate(scd_rows()) if r[2] == "2"]),
          P("Highlighted rows are SCD Type 2. Attributes not listed here (for example method names and flag labels) are "
            "Type 1. The complete attribute-level list is in the data dictionary, sheet SCD_Policy.", "caption"),
          H1("7. Keys"),
          H2("Natural keys and surrogate keys"),
          table([["Dimension", "Natural / business key (from source)", "Surrogate key (warehouse)"]] +
                [[d["name"], d["nk"], [c["name"] for c in d["cols"] if c["key"] == "PK"][0]] for d in DIMENSIONS],
                [0.30, 0.42, 0.28], bold_first_col=True),
          H2("Why surrogate keys even when natural keys are unique (Lab 05 Task 7.2)"),
          *numbered(["<b>History.</b> An SCD Type 2 tenant has several rows for one tenant_code; only a surrogate key can "
                     "point at one version.",
                     "<b>Independence from source systems.</b> If PropertyHub renumbers tenants or LUE changes systems, "
                     "warehouse keys and history are unaffected.",
                     "<b>Multi-source integration.</b> Unit A-101 exists in several buildings in the S6 spreadsheets; the "
                     "natural key becomes building_code + unit_no and facts join on unit_key (Lab 05 Scenario D).",
                     "<b>Special members and performance.</b> Integer keys allow -1/-2 rows and are smaller and faster to "
                     "join than text codes."]),
          H2("Special members"),
          table([["Key", "Meaning", "Example"],
                 ["-1", "Unknown: a reference was missing or could not be matched", "A maintenance ticket with no matching vendor code"],
                 ["-2", "Not applicable / not yet happened", "A vacant unit-day has no tenant or lease; an open request has no resolved date"]],
                [0.08, 0.44, 0.48], bold_first_col=True),
          KeepTogether([H2("Surrogate-key mapping walkthrough (Lab 05 Task 7.3)"),
          P("Source payment PAY-0098812 from tenant T-0912, on lease L-2025-00831 for unit GLB01-A101, paid by JazzCash on "
            "14 March 2026 against the rent line of invoice INV-2026-03-00831 (due 10 March):"),
          code("""lookup                                               -> surrogate key
dim_tenant  tenant_code = 'T-0912', version valid on 2026-03-14 -> tenant_key = 402
dim_unit    unit_nk = 'GLB01-A101', version valid on 2026-03-14 -> unit_key = 117
dim_lease   lease_number = 'L-2025-00831'                   -> lease_key = 2210
ownership   owner of GLB01-A101 on 2026-03-14 = 'OW-0217'    -> owner_key = 57
dim_payment_method method_code = 'JAZZ'                     -> payment_method_key = 5

fact_payment row:
  paid_date_key 20260314 | due_date_key 20260310 | unit_key 117 | tenant_key 402 | lease_key 2210
  owner_key 57 | payment_method_key 5 | charge_type_key 1
  payment_reference 'PAY-0098812' | invoice_number 'INV-2026-03-00831' | invoice_line_no 1   (degenerate)
  payment_amount 50000.00 | days_past_due 4 | settlement_lag_days 1 | is_reversal FALSE""")]),
          H1("8. Special dimension techniques"),
          table([["Technique", "Where", "Why"],
                 ["Conformed dimensions", "dim_date, dim_unit, dim_owner, dim_tenant, dim_lease", "Same keys and values across facts, enabling drill-across (Q12, Q13)"],
                 ["Role-playing dimension", "dim_date as invoice, due, paid, snapshot, raised, assigned, resolved, verified, event, coverage date", "One calendar table joined under different meanings; time attributes always come from dim_date, never from date_key arithmetic (Lab 04 Task 5.1)"],
                 ["Degenerate dimensions", "invoice_number, invoice_line_no, payment_reference, request_number", "Transaction identifiers with no further attributes stay on the fact (Lab 05 Task 5.2)"],
                 ["Junk dimension", "dim_request_flags (8 rows)", "Three low-cardinality yes/no flags combined instead of three tiny dimensions"],
                 ["Inferred members", "dim_tenant.is_inferred", "A fact that arrives before its tenant record links to a placeholder row that is updated later"],
                 ["Star, not snowflake", "Location hierarchy inside dim_unit", "One join per question; a snowflaked Building/City/Region chain was considered and rejected"]],
                [0.20, 0.35, 0.45], bold_first_col=True),
          H1("9. Attribute placement decisions (Lab 05 Task 8.3)"),
          table([["Attribute", "Decision", "Reason"],
                 ["Payment method", "Small dimension dim_payment_method", "Reused by Q5 with a Method → Channel group hierarchy and typical settlement days"],
                 ["Request status", "Degenerate attribute on the accumulating snapshot", "Changes with every milestone and belongs to the request, not to a reusable dimension"],
                 ["Emergency / recurring / tenant-caused", "Junk dimension", "Low cardinality, used together as filters"],
                 ["Owner", "owner_key on each fact, not an attribute of dim_unit", "Ownership changes over time; the owner at the event date must be kept"],
                 ["Arrears", "Measure on the occupancy snapshot and derived from invoice and payment facts", "A balance is a measurement, not a description of the tenant"],
                 ["Weather", "Dimension dim_weather (city × day)", "Reusable descriptive context; keeps the maintenance fact narrow"]],
                [0.22, 0.34, 0.44], bold_first_col=True),
          H1("10. Reversals and credit notes (Lab 05 Scenario A)"),
          P("Credit notes are invoice lines with charge type 'Credit note' and a negative net_amount; a bounced cheque is a "
            "new payment row with a negative amount and is_reversal = TRUE. Original rows are never edited. Reversals share "
            "the grain and dimensions of the original transactions, so keeping them in the same fact lets SUM return the "
            "correct net figure; a separate returns fact was considered and rejected."),
          H1("11. Late-arriving data"),
          table([["Case", "Example", "Handling"],
                 ["Late-arriving dimension", "An invoice for tenant T-0912 arrives before the tenant record",
                  "Insert an inferred tenant row (is_inferred = TRUE) and link the fact to it; update that row in place when the real record arrives"],
                 ["Late-arriving fact", "A JazzCash payment made on 2 March arrives on 14 March",
                  "Load at its true paid date; look up the tenant version valid on 2 March; re-derive the affected occupancy days"],
                 ["Late milestone", "A request resolved last week is marked resolved today",
                  "Update the accumulating snapshot row with the true resolved date"]],
                [0.20, 0.33, 0.47], bold_first_col=True)]
    build(os.path.join(OUT, "04_Fact_Dimension_Identification.pdf"), "04 Fact and Dimension Identification", s)


# ======================================================================= 05 grain definition
CAN_CANNOT = {
    "fact_rent_invoice_line": ("What was billed, by charge type, lease, unit, owner and due month; credit notes.",
                               "When or how it was paid (needs fact_payment)."),
    "fact_payment": ("When and how money arrived, lateness per line, reversals, settlement lag.",
                     "Amounts billed but never paid (needs fact_rent_invoice_line)."),
    "fact_unit_occupancy_daily": ("The state of every unit on every day: occupancy, rent roll, current arrears, vacancy spells.",
                                  "Why a unit became vacant, or a departed tenant's debt."),
    "fact_maintenance_request": ("Lags between milestones, SLA breaches, cost by vendor and category, open requests.",
                                 "Each individual status change after the four milestones (kept in Silver)."),
    "fact_lease_event": ("Counts of signings, renewals, notices and terminations by building and period.",
                         "How long a unit then stayed vacant (needs the occupancy snapshot)."),
    "fact_vacancy_incentive_coverage": ("Which offers existed on which vacant units and days, even with no result.",
                                        "Whether a lease followed, unless combined with lease events or the snapshot."),
}


def grain():
    s = cover_block("05 · Grain Definition",
                    "The grain is the contract of a fact table: one sentence stating what a single row represents, precise "
                    "enough that two developers would build the same table (Lab 04 Task 3.1, Lab 05 Section 4). Grains "
                    "were fixed before any measures or dimensions were chosen, and each sentence below is used word for "
                    "word in the diagrams and the data dictionary.")
    s += [H1("1. Summary of fact grains"),
          table([["Fact table", "Type", "Grain: one row represents…"]] +
                [[f["name"], f["type"], f["grain"].replace("One row represents ", "")] for f in FACTS],
                [0.26, 0.17, 0.57], bold_first_col=True),
          H1("2. Source grains (Lab 05 Task 3.1)"),
          P("Source grains were profiled first. Invoice headers and invoice lines have different grains, exactly like "
            "order headers and order lines in Lab 05, so they are never loaded into one fact."),
          table([["Source", "Table / file", "One row represents…", "Natural key"]] + [list(x) for x in SOURCE_TABLES],
                [0.09, 0.26, 0.42, 0.23], bold_first_col=True),
          H1("3. Grain rules applied"),
          *bullets(["Facts of different grains are never mixed in one table: invoicing and payment are two facts because "
                    "one invoice line can be paid in several instalments and one payment can cover several lines.",
                    "Every dimension attached to a fact is true at that fact's grain (for example, the tenant version "
                    "valid on the paid date).",
                    "Measures are classified by additivity before any aggregation is written (Lab 05 Section 6).",
                    "A grain check query is defined for every fact and runs after each load."])]
    measures_by_fact = {}
    for fact, m, add, rule in ADDITIVITY:
        measures_by_fact.setdefault(fact, []).append([m, add, rule])
    for i, f in enumerate(FACTS, 1):
        dims = []
        for c in f["cols"]:
            if c["ref"] and c["ref"].startswith("dim_"):
                dims.append(f"{c['name']} → {c['ref']}")
        example = [[c["name"], c["ex"]] for c in f["cols"] if not c["tech"]]
        half = (len(example) + 1) // 2
        ex_rows = [["Column", "Example", "Column", "Example"]]
        for a, b in zip(example[:half], example[half:] + [["", ""]]):
            ex_rows.append(a + b)
        s += [PageBreak() if i in (1, 3, 5) else Spacer(1, 10),
              H1(f"{i + 3}. {f['name']}"),
              callout(fmt_grain(f), f"Grain · {f['type']}"),
              Spacer(1, 6),
              table([["Item", "Definition"],
                     ["Business process", f["process"]],
                     ["Primary key", f["pk"]],
                     ["Load pattern", f["load"]],
                     ["Expected rows (3 years)", f["rows"]],
                     ["Dimensions at this grain", "; ".join(dims)],
                     ["This grain answers", CAN_CANNOT[f["name"]][0]],
                     ["This grain cannot answer", CAN_CANNOT[f["name"]][1]]], [0.24, 0.76], bold_first_col=True),
              Spacer(1, 5),
              KeepTogether([H2("Measures and additivity"),
                            table([["Measure(s)", "Additivity", "Correct aggregation"]] + measures_by_fact[f["name"]],
                                  [0.42, 0.18, 0.40])]),
              Spacer(1, 5),
              KeepTogether([H2("Example row"), table(ex_rows, [0.22, 0.28, 0.22, 0.28])]),
              Spacer(1, 5),
              KeepTogether([H2("Grain check, run after every load"), code(GRAIN_CHECKS[f["name"]])])]
    build(os.path.join(OUT, "05_Grain_Definition.pdf"), "05 Grain Definition", s)


if __name__ == "__main__":
    proposal()
    brd()
    questions()
    fact_dim()
    grain()
    print("done")
