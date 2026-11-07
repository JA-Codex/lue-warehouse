"""Phase 1 PDFs in plain document style (text, headings by size/weight, lists instead of coloured tables)."""
import os
import sys
from plainkit import (P, H1, H2, H3, note, bullets, numbered, field, entry, grain, code, grid, image, cover, build,
                      esc, Spacer, PageBreak, CondPageBreak, KeepTogether, mm)
import build_pdfs as B
from model import (DIMENSIONS, FACTS, SOURCES, SOURCE_TABLES, PROCESSES, QUESTIONS, GRAIN_TESTS, KPIS, STAKEHOLDERS,
                   HIERARCHIES, ADDITIVITY, BUS_DIMS, bus_matrix)
from sql_examples import EXAMPLES, GRAIN_CHECKS

OUT = sys.argv[1]
PNG = os.path.join(OUT, "diagrams", "png")
NQ, NF, ND = len(QUESTIONS), len(FACTS), len(DIMENSIONS)


def proposal():
    s = cover("Project Proposal",
              "This proposal defines the business problem, objectives, scope, data strategy and architecture of the LUE "
              "analytics warehouse. It is the entry point to the Phase 1 pack; the requirements, questions, dimensional "
              "design, grain definitions, diagrams and data dictionary are separate deliverables.")
    s += [H1("1. Executive Summary"),
          P(f"Lahore Urban Estates (LUE) will get a PostgreSQL star-schema data warehouse that answers {NQ} management "
            f"questions across five business processes, using {NF} fact tables, {ND} conformed dimensions, slowly changing "
            "dimensions and a Power BI report. Data comes from six simulated source systems in five formats and passes "
            "through Bronze, Silver and Gold layers with quality checks, a quarantine table and a full audit trail."),
          P("The design covers every fact table type taught in the course: transaction, periodic snapshot, accumulating "
            "snapshot, and factless (both event and coverage). It also uses conformed dimensions, role-playing dates, a "
            "junk dimension, degenerate dimensions, SCD Types 0, 1 and 2, inferred members for late-arriving data, and "
            "hierarchies for drill-down and roll-up."),
          P(f"<i>At a glance:</i> 5 business processes, {NF} fact tables, {ND} dimensions, 6 source systems, {NQ} business "
            f"questions, {len(KPIS)} KPIs."),
          H1("2. The Client"),
          P("LUE is a fictional property management company that manages commercial plazas and developer-owned apartment "
            "blocks on behalf of private owners. It lets units, bills rent, collects payments, arranges repairs and earns "
            "a management fee on rent collected."),
          field("Portfolio", "about 40 buildings in Lahore, Karachi, Islamabad and Faisalabad: residential, office and retail"),
          field("Scale", "about 1,800 units and 1,500 active leases; three years of history (July 2023 – June 2026)"),
          field("Revenue", "management fee on rent collected, service charges and late fees"),
          field("Leases", "11-month residential leases; 2–5 year commercial leases"),
          field("Payment channels", "cash, cheque, bank transfer, Raast, JazzCash, Easypaisa"),
          field("Currency and fiscal year", "Pakistani Rupee (PKR); fiscal year July–June"),
          H1("3. Business Problem"),
          P("LUE's data sits in separate systems: a property management system, Excel registers kept by different teams, "
            "bank and wallet settlement files, a tenant maintenance app and per-building leasing spreadsheets. Reporting is "
            "manual and slow, so management finds problems weeks after they start."),
          *numbered([f"<b>{esc(a)}.</b> {esc(b)}. <i>Addressed by: {esc(c)}.</i>" for a, b, c in B.PROBLEMS]),
          H1("4. Why a Data Warehouse, Not the Operational Database"),
          P("The operational systems are built to record transactions; the warehouse is built to analyse them over time. "
            "As in Lab 03, the source keeps a normalised model so updates stay consistent, while the warehouse is a "
            "dimensional model designed around business processes and analytical questions rather than copied from "
            "operational tables."),
          *bullets(["<b>Purpose.</b> Sources record a lease, an invoice, a payment or a ticket. The warehouse analyses "
                    "collections, occupancy, maintenance and owner income over time.",
                    "<b>Typical question.</b> Source: “What is the status of invoice INV-2026-03-00831?” Warehouse: “How did "
                    "the collection rate by building change over three fiscal years?”",
                    "<b>History.</b> Sources keep only the current state. The warehouse keeps history through daily "
                    "snapshots and SCD Type 2.",
                    "<b>Design.</b> Sources are normalised (Lab 03). The warehouse uses star schemas with conformed "
                    "dimensions (Labs 04–05).",
                    "<b>Integration.</b> Each source is one system. The warehouse integrates, cleans and reconciles six.",
                    "<b>Workload.</b> Sources handle inserts and updates. The warehouse handles aggregation, ROLLUP/CUBE, "
                    "drill-down and dashboards."]),
          H1("5. Objectives and Success Measures"),
          *numbered([f"<b>{esc(o)}.</b> <i>Success measure:</i> {esc(m)}." for _, o, m in B.OBJECTIVES]),
          H1("6. Scope"),
          H2("In scope"),
          *bullets(["Conceptual, logical and physical dimensional models, a source ERD and an architecture diagram",
                    "Six simulated source systems produced by a seeded generator with deliberate data defects",
                    "A Bronze, Silver and Gold pipeline with quality checks, quarantine, audit log and reconciliation",
                    "Star schemas with SCD Types 0, 1 and 2, special members and inferred members",
                    "OLAP SQL (ROLLUP, CUBE, GROUPING, window functions), performance tuning and a Power BI report"]),
          H2("Out of scope"),
          *bullets(["Real or personal data; live connections to production systems",
                    "Real-time or streaming analytics; predictive models",
                    "Accounting-grade general ledger and tax; co-ownership of one unit by several owners"]),
          H1("7. Stakeholders"),
          *[entry(esc(n), [("Needs", esc(need)), ("Example question", esc(q)), ("Power BI page", esc(pg))])
            for n, need, q, pg in STAKEHOLDERS],
          H1("8. Business Processes"),
          P("Each business process becomes one or more fact tables. Together they cover every fact table type from Lab 05."),
          *[entry(f"{p[0]}. {esc(p[1])}", [("What happens", esc(p[2])), ("Fact table(s)", esc(", ".join(p[3]))),
                                         ("Fact type", esc(p[4]))]) for p in PROCESSES],
          H1("9. Data Strategy"),
          P("All data is synthetic and generated by a seeded Python script. The generator first creates one consistent "
            "operational world, then exports each part in the format the owning team would really use. Integration, key "
            "conflicts and data quality problems are therefore genuine rather than staged."),
          H2("Source systems"),
          *[entry(f"{x['id']}. {esc(x['name'])}", [("Format", esc(x["fmt"])), ("Contents", esc(x["content"])),
                                                ("Typical defects", esc(x["defects"]))]) for x in SOURCES],
          H2("Data principles"),
          *bullets(["<b>Operational data only.</b> The generator never writes warehouse tables. Every fact, including the "
                    "daily occupancy snapshot, is derived by the ETL, so the transformation logic is visible and assessable.",
                    "<b>Planted defects with an answer key.</b> Every injected defect is recorded in defects_answer_key.csv; "
                    "after each run the pipeline compares its quarantine counts with this file.",
                    "<b>Realism.</b> Rents calibrated by city and building class, seasonal move-ins, channel-specific payment "
                    "delays, maintenance volume scaled by building age, and more leak tickets in monsoon months.",
                    "<b>Volumes over three years.</b> About 1.97 million occupancy rows (1,800 units × 1,095 days), 130,000 "
                    "invoice lines, 60,000 payment allocations, 8,000 lease events and 6,000 maintenance requests."]),
          CondPageBreak(200 * mm),
          H1("10. Architecture"),
          P("The pipeline follows the 11 sections of the reference architecture diagram. Rows move from the sources through "
            "Bronze, quality checks, Silver and SCD processing into the warehouse, then to Gold marts and Power BI. Failed "
            "rows go to quarantine, and audit, performance and lineage run alongside."),
          image(os.path.join(PNG, "06_architecture.png"), max_h=165 * mm),
          note("Figure 1. LUE architecture. Full-size version: 06 Schema Diagrams, Figure 17."),
          H2("How each section is implemented"),
          *numbered(["<b>Sources:</b> S1–S6, landed as files and a source schema.",
                     "<b>Orchestration:</b> run_pipeline.py runs every step in a fixed order with one run_id per run.",
                     "<b>Bronze (lue_staging.brz_*):</b> as-is copies plus batch_id, source_system and loaded_at.",
                     "<b>Quality and quarantine:</b> six ordered checks; failures go to lue_audit.quarantine (staging.sql).",
                     "<b>Silver (lue_staging.stg_*):</b> typed, standardised, deduplicated, loaded incrementally by watermark.",
                     f"<b>Warehouse:</b> SCD processing (dimensions.sql), then {ND} dimensions and {NF} facts (facts.sql).",
                     "<b>Performance:</b> monthly partitions, indexes, EXPLAIN ANALYZE before and after.",
                     "<b>Gold (schema lue_reporting):</b> four marts as materialized views (Views.sql).",
                     "<b>Analytics and BI:</b> OLAP SQL (OLAP.sql) and the Power BI report.",
                     "<b>Audit:</b> run log and reconciliation results in the audit schema.",
                     "<b>Lineage:</b> lineage columns on every row and the lue_audit.lineage mapping."]),
          H1("11. Technology Stack"),
          P("The build uses only the brief's free stack. Every transformation is plain SQL that can be opened and run, "
            "because the labs assess the logic, not the tooling."),
          *bullets([f"<b>{esc(a)}:</b> {esc(t)} — <i>{esc(st)}</i>. {esc(r)}." for a, t, st, r in B.STACK]),
          H1("12. Roadmap"),
          *[entry(f"Phase {esc(p)} (weeks {esc(w)}, {esc(wt)} of the project mark)",
                  [("Work", esc(work)), ("Done when", esc(done))]) for p, w, wt, work, done in
            [(r[0].split(". ", 1)[0] + " — " + r[0].split(". ", 1)[1], r[1], r[2], r[3], r[4]) for r in B.ROADMAP]],
          H1("13. Phase 1 Deliverables"),
          *numbered([f"<b>{esc(d)}</b> ({esc(f)}): {esc(c)}. <i>Rubric area: {esc(r)}.</i>"
                     for d, f, c, r in B.DELIVERABLES]),
          H1("14. Risks and Mitigations"),
          *numbered([f"<b>{esc(r)}.</b> Impact: {esc(i)}. Mitigation: {esc(m)}." for r, i, m in B.RISKS]),
          H1("15. Assumptions"),
          *bullets([esc(a) for a in B.ASSUMPTIONS])]
    build(os.path.join(OUT, "01_Project_Proposal.pdf"), "Project Proposal", s)


def brd():
    s = cover("Business Requirements Document",
              "This document states what the warehouse must deliver and how each requirement will be accepted. It "
              "translates stakeholder needs into business, data, quality, reporting and non-functional requirements, and "
              "traces every business requirement to the questions and facts that satisfy it.")
    s += [H1("1. Purpose and Audience"),
          P("The BRD is the agreement between LUE management and the project team. Its readers are the six stakeholder "
            "groups, the course instructor and the team members who will build Phase 2 and Phase 3."),
          H1("2. Business Background"),
          P("LUE manages about 1,800 units in 40 buildings across Lahore, Karachi, Islamabad and Faisalabad for private "
            "owners. Its data is spread across a property management system, Excel registers, settlement files, a tenant "
            "maintenance app and leasing spreadsheets. Cross-building questions take days to answer, and history is lost "
            "whenever a record is updated."),
          H1("3. Stakeholders and Their Needs"),
          *[entry(esc(n), [("Needs", esc(need)), ("Example question", esc(q)), ("Report page", esc(pg))])
            for n, need, q, pg in STAKEHOLDERS],
          H1("4. Business Requirements"),
          P("Priority uses MoSCoW: <i>Must</i> requirements are needed for acceptance; <i>Should</i> requirements are "
            "planned but can be reduced if time runs short."),
          *[entry(f"{esc(i)}. {esc(r)}", [("Stakeholder", esc(st)), ("Priority", esc(pr)), ("Answered by", esc(q))])
            for i, r, st, pr, q in B.BRS],
          P("<b>Acceptance.</b> A requirement is met when its questions are answered by SQL on the warehouse, with output "
            "and a one-line interpretation, and the same figures appear in the Power BI report."),
          H1("5. KPI Definitions"),
          P("Every KPI is computed from additive parts (sums and counts) and divided at the end. Averaging per-row ratios "
            "gives the wrong answer when rows have different weights (Lab 05 Task 6.3)."),
          *[entry(esc(k), [("Formula", esc(f)), ("Facts used", esc(fa)), ("Question", esc(q))]) for k, f, fa, q in KPIS],
          H1("6. Data Requirements"),
          field("Sources", "six systems: PostgreSQL (S1), Excel (S2), CSV (S3 and S6), JSON (S4) and a REST API (S5)"),
          field("Granularity", "the lowest available level: invoice line, payment allocation, unit-day, maintenance "
                               "request, lease event and offer-day"),
          field("History", "three years; SCD Type 2 on tenant type and sector, unit type and furnishing, vendor rating "
                           "and SLA policy"),
          field("Ownership", "the owner on each fact row is resolved from the ownership register at the event date"),
          field("Calendar", "calendar and fiscal (July–June) hierarchies, with public holiday and Ramadan flags"),
          field("Late-arriving data", "inferred dimension members with deferred update; late facts loaded at their true date"),
          field("Refresh", "daily batch, with incremental loads by watermark per source"),
          H1("7. Data Quality Requirements"),
          *[entry(f"{esc(i)}. {esc(c)} check", [("Rule", esc(r)), ("On failure", esc(f))]) for i, c, r, f in B.DQ],
          P("Every rejected row is stored in lue_audit.quarantine with its source system, source table, batch_id, check name, "
            "reason and timestamp. The generator's defect answer key is used to prove that each check works."),
          H1("8. Reporting Requirements"),
          *[entry(esc(p), [("Audience", esc(a)), ("Main visuals", esc(v)), ("Requirements", esc(r))]) for p, a, v, r in [
              ("Collections", "Finance head, building managers", "collection rate trend, ageing buckets, overdue tenants", "BR-01 to BR-04"),
              ("Occupancy and leasing", "Operations head, leasing manager", "occupancy by city and unit type, vacancy duration, renewal rate, incentive effect", "BR-05 to BR-07, BR-10"),
              ("Maintenance", "Operations head", "SLA breaches by vendor, days to resolve, rain vs leak requests", "BR-08, BR-11"),
              ("Owner portfolio", "CEO, owner relations lead", "NOI per owner, maintenance cost per unit", "BR-09"),
              ("Pipeline health", "Project team, instructor", "run log, rejects by reason, reconciliation status", "NFR-02")]],
          H1("9. Non-Functional Requirements"),
          *bullets([f"<b>{esc(i)} {esc(a)}.</b> {esc(r)}." for i, a, r in B.NFR]),
          H1("10. Assumptions and Constraints"),
          *bullets([esc(a) for a in B.ASSUMPTIONS] + ["Only the brief's free stack is used: PostgreSQL, pgAdmin, "
                                                      "Python/pandas, Power BI Desktop, draw.io/Mermaid and GitHub."]),
          H1("11. Out of Scope"),
          *bullets(["Real or personal data, live integration, streaming and prediction",
                    "Accounting-grade ledger and tax reporting", "Co-ownership of a unit by several owners"]),
          H1("12. Requirements Traceability"),
          *bullets([f"<b>{esc(a)}</b> → {esc(b)} → {esc(c)} → <i>{esc(d)}</i>" for a, b, c, d in [
              ("BR-01 to BR-04", "Q1–Q5", "fact_rent_invoice_line, fact_payment", "Collections"),
              ("BR-05, BR-06", "Q6, Q7", "fact_unit_occupancy_daily", "Occupancy and leasing"),
              ("BR-07", "Q8", "fact_lease_event", "Occupancy and leasing"),
              ("BR-08", "Q9–Q11", "fact_maintenance_request", "Maintenance"),
              ("BR-09", "Q12", "fact_payment, fact_maintenance_request", "Owner portfolio"),
              ("BR-10", "Q13", "fact_vacancy_incentive_coverage, fact_unit_occupancy_daily", "Occupancy and leasing"),
              ("BR-11", "Q14", "fact_maintenance_request with dim_weather", "Maintenance"),
              ("BR-12", "Q4, Q9", "all facts through SCD Type 2 dimensions", "All pages")]]),
          note("Read each line as: requirement → questions → fact tables → report page.")]
    build(os.path.join(OUT, "02_Business_Requirements_Document.pdf"), "Business Requirements Document", s)


def questions():
    s = cover("Business Questions",
              f"The {NQ} analytical questions below were derived from the stakeholders' decisions, not from the source "
              "tables. Each one is traced to the fact table whose grain can answer it, the dimensions it slices by, its "
              "measures and the OLAP operation it needs. The brief requires at least 10.")
    groups = [("Collections (rent invoicing and payment)", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
              ("Occupancy and leasing", ["Q6", "Q7", "Q8", "Q13"]),
              ("Maintenance", ["Q9", "Q10", "Q11", "Q14"]),
              ("Owner reporting (cross-process)", ["Q12"])]
    qd = {q[0]: q for q in QUESTIONS}
    s.append(H1("1. The Questions"))
    for gname, ids in groups:
        s.append(H2(gname))
        for i in ids:
            q = qd[i]
            s.append(entry(f"{q[0]}. {esc(q[1])}", [
                ("Stakeholder", esc(q[3])), ("Decision supported", esc(B.DECISIONS[q[0]])),
                ("Answered by", esc(q[4])), ("Dimensions", esc(q[5])), ("Measures", esc(q[6])),
                ("OLAP operation", esc(q[7]))]))
    s += [H1("2. Grain Test: Why Only This Fact Can Answer It"),
          P("Following Lab 05 Task 4.2, each group of questions was tested against every fact grain. The list records why "
            "the chosen fact is the only correct source."),
          *bullets([f"<b>{esc(q)}</b> — answered by {esc(f)}. {esc(w)}" for q, f, w in GRAIN_TESTS]),
          H1("3. Detail Versus Pre-Aggregation"),
          P("The Gold marts store monthly summaries for Power BI, a MOLAP-style pre-aggregation (Lab 04 Section 9). Some "
            "questions need the detail that the marts discard:"),
          *bullets(["<b>“Which units were vacant during Eid week?”</b> can be answered from fact_unit_occupancy_daily but "
                    "not from mart_occupancy_monthly, because the day was aggregated away.",
                    "<b>Q7 vacancy spells</b> need consecutive days per unit, which only the daily snapshot keeps.",
                    "<b>Q1</b> will be answered both ways in Phase 3 to compare joins, query-time aggregation and the "
                    "detail available (ROLAP vs MOLAP vs HOLAP)."]),
          PageBreak(),
          H1("4. Example SQL"),
          P("These sketches show how five questions run on the physical model. Each query was executed against the "
            "PostgreSQL 16 schema in sql/physical_model.sql. Subtotal rows are always labelled with GROUPING(), so a "
            "manager never has to interpret a bare NULL (Lab 04 Tasks 6.2 and 7.4).")]
    for q, title, n, sql in EXAMPLES:
        s += [KeepTogether([H2(f"{q}: {title}"), P(esc(n)), code(sql)]), Spacer(1, 8)]
    build(os.path.join(OUT, "03_Business_Questions.pdf"), "Business Questions", s)


def fact_dim():
    s = cover("Fact and Dimension Identification",
              "This document identifies LUE's business processes, chooses a fact table type for each, identifies the "
              "conformed dimensions with their hierarchies and SCD policy, and defines the key strategy. It follows the "
              "four-step dimensional design process from Lab 05: business process, then grain, then dimensions, then facts.")
    s += [H1("1. Business Processes and Fact Table Types"),
          *[entry(f"{p[0]}. {esc(p[1])}", [("Fact table(s)", esc(", ".join(p[3]))), ("Fact type", esc(p[4])),
                                         ("Why this type", esc(p[5]))]) for p in PROCESSES],
          note("The five processes are never combined into one fact table, because each has a different grain "
               "(Lab 05 Task 3.3). The grain sentences are defined in the Grain Definition document."),
          H1("2. Fact Tables")]
    dd = ("invoice_number", "invoice_line_no", "payment_reference", "request_number", "request_status")
    for f in FACTS:
        meas = ", ".join(c["name"] for c in f["cols"] if not c["key"] and not c["ref"] and not c["tech"]
                         and c["name"] not in dd + ("is_reversal",)) or "none (factless)"
        s.append(entry(esc(f["name"]), [("Type", esc(f["type"])), ("Measures", esc(meas)),
                                         ("Degenerate dimensions", esc(", ".join(c["name"] for c in f["cols"]
                                                                                 if c["name"] in dd) or "none")),
                                         ("Expected rows", esc(f["rows"]))]))
    s += [KeepTogether([H1("3. Bus Matrix"),
          P("Rows are dimensions and columns are fact tables. An X marks a dimension used by a fact; for dim_date the "
            "date roles are listed instead. A dimension with several marks is conformed: the same table, keys and "
            "attribute values serve every process, which is what allows drill-across questions such as Q12."),
          grid([["Dimension"] + [B.FACT_SHORT[f] for f, _ in bus_matrix()]] +
               [[d] + [r[j].replace("X (", "").rstrip(")") if j == 0 else r[j] for f, r in bus_matrix()]
                for j, d in enumerate(BUS_DIMS)], [0.22] + [0.13] * 6)]),
          H1("4. Dimensions")]
    for d in DIMENSIONS:
        attrs = ", ".join(c["name"] for c in d["cols"] if not c["key"] and not c["tech"]
                          and c["name"] not in ("effective_from", "effective_to", "is_current"))
        sk = [c["name"] for c in d["cols"] if c["key"] == "PK"][0]
        fl = [("One row per", esc(d["grain"].replace("One row per ", ""))), ("Natural key", esc(d["nk"])),
              ("Surrogate key", esc(sk)), ("Attributes", esc(attrs)), ("Hierarchy", esc(d["hierarchy"]))]
        if d.get("roles"):
            fl.append(("Roles", esc(d["roles"])))
        s.append(entry(esc(d["name"]), fl))
    s += [H1("5. Hierarchies"),
          P("Hierarchies are flattened into their dimension (a star, not a snowflake), as required by Lab 04's design rule. "
            "Drill-down moves from the lowest level to the highest; roll-up moves the other way."),
          *bullets([f"<b>{esc(d)}</b> ({esc(n)}): {esc(c)}" for d, n, c in HIERARCHIES]),
          H1("6. SCD Policy"),
          P("Every descriptive attribute has a declared type. <i>Type 0</i> attributes never change. <i>Type 1</i> "
            "attributes are corrected in place for all history. <i>Type 2</i> attributes create a new dimension row with "
            "effective_from, effective_to and is_current, so facts keep pointing at the version valid at the time of the "
            "event.")]
    by_dim = {}
    for dname, attr, t, reason in B.scd_rows():
        by_dim.setdefault(dname, {}).setdefault(t, []).append((attr, reason))
    for dname, types in by_dim.items():
        lines = []
        for t in ("2", "1", "0"):
            if t in types:
                lines.append((f"Type {t}", "; ".join(f"{esc(a)} ({esc(r.lower() if r[0].isupper() and not r.startswith('Q') else r)})"
                                                     for a, r in types[t])))
        s.append(entry(esc(dname), lines))
    s += [note("Attributes not listed (for example method names and flag labels) are Type 1. The complete list is in "
               "the data dictionary, sheet SCD_Policy."),
          H1("7. Keys"),
          H2("Natural and surrogate keys"),
          *bullets([f"<b>{esc(d['name'])}</b>: natural key {esc(d['nk'])} → surrogate key "
                    f"{esc([c['name'] for c in d['cols'] if c['key'] == 'PK'][0])}" for d in DIMENSIONS]),
          H2("Why surrogate keys even when natural keys are unique (Lab 05 Task 7.2)"),
          *numbered(["<b>History.</b> An SCD Type 2 tenant has several rows for one tenant_code; only a surrogate key can "
                     "point at one version.",
                     "<b>Independence from source systems.</b> If PropertyHub renumbers tenants or LUE changes systems, "
                     "warehouse keys and history are unaffected.",
                     "<b>Multi-source integration.</b> Unit A-101 exists in several buildings in the S6 spreadsheets, so the "
                     "natural key becomes building_code + unit_no and facts join on unit_key (Lab 05 Scenario D).",
                     "<b>Special members and performance.</b> Integer keys allow the -1 and -2 rows, and they are smaller and "
                     "faster to join than text codes."]),
          H2("Special members"),
          *bullets(["<b>-1 Unknown:</b> a reference was missing or could not be matched (for example, a maintenance "
                    "ticket with no matching vendor code).",
                    "<b>-2 Not applicable / not yet happened:</b> a vacant unit-day has no tenant or lease; an open request "
                    "has no resolved date."]),
          KeepTogether([H2("Surrogate-key mapping walkthrough (Lab 05 Task 7.3)"),
                        P("Source payment PAY-0098812 from tenant T-0912, on lease L-2025-00831 for unit GLB01-A101, paid "
                          "by JazzCash on 14 March 2026 against the rent line of invoice INV-2026-03-00831 (due 10 March):"),
                        code("""dim_tenant   tenant_code 'T-0912', version valid on 2026-03-14   -> tenant_key 402
dim_unit     unit_nk 'GLB01-A101', version valid on 2026-03-14   -> unit_key 117
dim_lease    lease_number 'L-2025-00831'                         -> lease_key 2210
ownership    owner of GLB01-A101 on 2026-03-14 is 'OW-0217'      -> owner_key 57
dim_payment_method  method_code 'JAZZ'                           -> payment_method_key 5

Resulting fact_payment row:
  paid_date_key 20260314, due_date_key 20260310, unit_key 117, tenant_key 402,
  lease_key 2210, owner_key 57, payment_method_key 5, charge_type_key 1,
  payment_reference 'PAY-0098812', invoice_number 'INV-2026-03-00831',
  invoice_line_no 1 (degenerate dimensions), payment_amount 50000.00,
  days_past_due 4, settlement_lag_days 1, is_reversal FALSE""")]),
          H1("8. Special Dimension Techniques"),
          *bullets(["<b>Conformed dimensions.</b> dim_date, dim_unit, dim_owner, dim_tenant and dim_lease have the same keys "
                    "and values across facts, which enables drill-across (Q12, Q13).",
                    "<b>Role-playing dimension.</b> dim_date is joined under different meanings: invoice, due, paid, "
                    "snapshot, raised, assigned, resolved, verified, event and coverage date. Time attributes always come "
                    "from dim_date, never from arithmetic on date_key (Lab 04 Task 5.1).",
                    "<b>Degenerate dimensions.</b> invoice_number, invoice_line_no, payment_reference and request_number "
                    "identify transactions but have no further attributes, so they stay on the fact (Lab 05 Task 5.2).",
                    "<b>Junk dimension.</b> dim_request_flags combines three low-cardinality yes/no flags into 8 rows "
                    "instead of three tiny dimensions.",
                    "<b>Inferred members.</b> A fact that arrives before its tenant record links to a placeholder row "
                    "(is_inferred = TRUE) that is updated when the record arrives.",
                    "<b>Star, not snowflake.</b> The location hierarchy lives inside dim_unit, so every question needs one "
                    "join; a snowflaked Building, City and Region chain was considered and rejected."]),
          H1("9. Attribute Placement Decisions (Lab 05 Task 8.3)"),
          *bullets(["<b>Payment method</b> becomes a small dimension, because Q5 reuses it with a Method → Channel group "
                    "hierarchy and typical settlement days.",
                    "<b>Request status</b> stays on the accumulating snapshot as a degenerate attribute, because it changes "
                    "at every milestone and belongs to the request.",
                    "<b>Emergency, recurring and tenant-caused flags</b> go into a junk dimension, because they have low "
                    "cardinality and are used together as filters.",
                    "<b>Owner</b> is an owner_key on each fact, not an attribute of dim_unit, because ownership changes and "
                    "the owner at the event date must be kept.",
                    "<b>Arrears</b> is a measure (on the occupancy snapshot, and derived from invoices and payments), "
                    "because a balance is a measurement, not a description of the tenant.",
                    "<b>Weather</b> becomes a dimension (city × day), because it is reusable descriptive context and keeps "
                    "the maintenance fact narrow."]),
          H1("10. Reversals and Credit Notes (Lab 05 Scenario A)"),
          P("Credit notes are invoice lines with charge type “Credit note” and a negative net_amount. A bounced cheque is a "
            "new payment row with a negative amount and is_reversal = TRUE. Original rows are never edited. Reversals share "
            "the grain and dimensions of the original transactions, so keeping them in the same fact lets SUM return the "
            "correct net figure. A separate returns fact was considered and rejected."),
          H1("11. Late-Arriving Data"),
          *bullets(["<b>Late-arriving dimension.</b> An invoice for tenant T-0912 arrives before the tenant record. Insert an "
                    "inferred tenant row and link the fact to it; update that row in place when the real record arrives.",
                    "<b>Late-arriving fact.</b> A JazzCash payment made on 2 March arrives on 14 March. Load it at its true "
                    "paid date, look up the tenant version valid on 2 March, and re-derive the affected occupancy days.",
                    "<b>Late milestone.</b> A request resolved last week is marked resolved today. Update the accumulating "
                    "snapshot row with the true resolved date."])]
    build(os.path.join(OUT, "04_Fact_Dimension_Identification.pdf"), "Fact and Dimension Identification", s)


def grain_doc():
    s = cover("Grain Definition",
              "The grain is the contract of a fact table: one sentence stating what a single row represents, precise "
              "enough that two developers would build the same table (Lab 04 Task 3.1, Lab 05 Section 4). The grains "
              "were fixed before any measures or dimensions were chosen, and each sentence below is used word for word "
              "in the diagrams and the data dictionary.")
    s += [H1("1. Summary of Fact Grains"),
          *[KeepTogether([P(f"<b>{esc(f['name'])}</b> — <i>{esc(f['type'])}</i>"), grain(esc(f["grain"]))]) for f in FACTS],
          H1("2. Source Grains (Lab 05 Task 3.1)"),
          P("Source grains were profiled first. Invoice headers and invoice lines have different grains, just like order "
            "headers and order lines in Lab 05, so they are never loaded into one fact."),
          *bullets([f"<b>{esc(t)}</b> ({esc(src)}): {esc(g)}. <i>Natural key: {esc(k)}.</i>" for src, t, g, k in SOURCE_TABLES]),
          H1("3. Grain Rules Applied"),
          *bullets(["Facts of different grains are never mixed in one table. Invoicing and payment are two facts because "
                    "one invoice line can be paid in several instalments and one payment can cover several lines.",
                    "Every dimension attached to a fact is true at that fact's grain, for example the tenant version valid "
                    "on the paid date.",
                    "Measures are classified by additivity before any aggregation is written (Lab 05 Section 6).",
                    "A grain check query is defined for every fact and runs after each load."])]
    mbf = {}
    for fact, m, add, rule in ADDITIVITY:
        mbf.setdefault(fact, []).append((m, add, rule))
    for i, f in enumerate(FACTS, 1):
        dims = [f"{c['name']} → {c['ref']}" for c in f["cols"] if c["ref"] and c["ref"].startswith("dim_")]
        ex = "\n".join(f"{c['name']:<28} {c['ex']}" for c in f["cols"] if not c["tech"])
        s += [PageBreak(),
              H1(f"{i + 3}. {f['name']}"),
              P(f"<b>Grain</b> ({esc(f['type'])}):"),
              grain(esc(f["grain"])),
              field("Business process", esc(f["process"])),
              field("Primary key", esc(f["pk"])),
              field("Load pattern", esc(f["load"])),
              field("Expected rows (3 years)", esc(f["rows"])),
              field("This grain answers", esc(B.CAN_CANNOT[f["name"]][0])),
              field("This grain cannot answer", esc(B.CAN_CANNOT[f["name"]][1])),
              H2("Dimensions at this grain"),
              *bullets([esc(d) for d in dims]),
              H2("Measures and additivity"),
              *bullets([f"<b>{esc(m)}</b> — {esc(a)}. {esc(r)}." for m, a, r in mbf[f["name"]]]),
              KeepTogether([H2("Example row"), code(ex)]),
              KeepTogether([H2("Grain check, run after every load"), code(GRAIN_CHECKS[f["name"]])])]
    build(os.path.join(OUT, "05_Grain_Definition.pdf"), "Grain Definition", s)


if __name__ == "__main__":
    proposal()
    brd()
    questions()
    fact_dim()
    grain_doc()
    print("done")
