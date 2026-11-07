"""Write Mermaid (.mmd) sources for every Phase 1 diagram."""
import os
import sys
from model import DIMENSIONS, FACTS, TABLES, ADDITIVITY, SOURCE_ERD, SOURCE_RELS, HIERARCHIES

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

HIER = {
    "dim_date": {"full_date": "Day level (calendar and fiscal)", "month_name": "Calendar L2 Month",
                 "quarter_no": "Calendar L3 Quarter", "year_no": "Calendar L4 Year",
                 "fiscal_month_no": "Fiscal L2 Month", "fiscal_quarter_no": "Fiscal L3 Quarter",
                 "fiscal_year_label": "Fiscal L4 Year (Jul-Jun)"},
    "dim_unit": {"unit_nk": "Location L1 Unit", "floor_no": "Location L2 Floor", "building_name": "Location L3 Building",
                 "locality": "Location L4 Locality", "city": "Location L5 City", "region": "Location L6 Region"},
    "dim_payment_method": {"method_name": "L1 Method", "channel_group": "L2 Channel group"},
    "dim_charge_type": {"charge_type_name": "L1 Charge type", "charge_category": "L2 Category"},
    "dim_maintenance_category": {"subcategory_name": "L1 Subcategory", "category_name": "L2 Category"},
    "dim_vendor": {"vendor_name": "L1 Vendor", "trade": "L2 Trade"},
    "dim_tenant": {"tenant_name": "L1 Tenant", "tenant_type": "L2 Tenant type"},
    "dim_owner": {"owner_name": "L1 Owner", "owner_type": "L2 Owner type"},
    "dim_incentive": {"incentive_description": "L1 Incentive", "incentive_type": "L2 Incentive type"},
}

MEASURE_NOTE = {}
for fact, measures, add, rule in ADDITIVITY:
    for m in measures.split(", "):
        MEASURE_NOTE[(fact, m)] = add


def logical_type(c):
    t = c["type"].upper()
    if c["key"] or (c["name"].endswith("_key") or c["name"].endswith("_sk")):
        return "SK" if t in ("INT", "BIGINT") else "text"
    if t.startswith("NUMERIC(12") or t.startswith("NUMERIC(16"):
        return "money"
    if t.startswith("NUMERIC"):
        return "decimal"
    if t.startswith(("VARCHAR", "CHAR")):
        return "text"
    if t == "DATE":
        return "date"
    if t == "BOOLEAN":
        return "flag"
    if t in ("SMALLINT", "INT", "BIGINT"):
        return "integer"
    if t == "TIMESTAMP":
        return "timestamp"
    return t.lower()


def keys(c):
    k = c["key"].replace(" ", "")
    return k if k else ""


def clean(s):
    return s.replace('"', "'").replace("→", "to").replace("−", "-").replace("–", "-").replace("·", "-")


def attr_line(t, c, physical):
    typ = c["type"].replace(" ", "") if physical else logical_type(c)
    k = keys(c)
    notes = []
    tname = t["name"]
    if physical:
        notes.append("NULL" if c["null"] else "NOT NULL")
        if c["ref"]:
            notes.append("FK to " + c["ref"])
    else:
        if c["ref"]:
            notes.append("FK to " + c["ref"])
        if (tname, c["name"]) in MEASURE_NOTE:
            notes.append("measure: " + MEASURE_NOTE[(tname, c["name"])])
        if tname in HIER and c["name"] in HIER[tname]:
            notes.append("hierarchy " + HIER[tname][c["name"]])
        if c.get("scd") == "2":
            notes.append("SCD2")
        if c["name"] in ("invoice_number", "invoice_line_no", "payment_reference", "request_number"):
            notes.append("degenerate dimension")
    note = clean("; ".join(notes))
    k = (" " + k) if k else ""
    return f'        {typ} {c["name"]}{k} "{note}"' if note else f"        {typ} {c['name']}{k}"


def entity(t, physical):
    cols = t["cols"] if physical else [c for c in t["cols"] if not c["tech"]]
    lines = [f"    {t['name']} {{"] + [attr_line(t, c, physical) for c in cols] + ["    }"]
    return "\n".join(lines)


def star(fact, physical, n):
    dims = []
    rels = []
    for c in fact["cols"]:
        if c["ref"] and c["ref"].startswith("dim_"):
            if c["ref"] not in dims:
                dims.append(c["ref"])
            role = c["name"].replace("_key", "")
            rels.append(f"    {c['ref']} ||--o{{ {fact['name']} : {role}")
    level = "Physical" if physical else "Logical"
    title = clean(f"{level} star {n} - {fact['name']} ({fact['type']}). Grain: {fact['grain']}")
    body = ["---", f"title: \"{title}\"", "---", "erDiagram"] + rels + [entity(fact, physical)] + \
           [entity(TABLES[d], physical) for d in dims]
    return "\n".join(body) + "\n"


files = {}

# 01 conceptual model: business entities and relationships, no attributes
files["01_conceptual_model.mmd"] = """---
title: Conceptual model - LUE business entities and relationships (no attributes)
---
erDiagram
    BUILDING ||--|{ UNIT : contains
    OWNER ||--o{ OWNERSHIP_PERIOD : holds
    UNIT ||--|{ OWNERSHIP_PERIOD : "owned during"
    TENANT ||--o{ LEASE : signs
    UNIT ||--o{ LEASE : "let under"
    LEASE ||--o{ LEASE_EVENT : records
    LEASE ||--o{ INVOICE_LINE : "billed by"
    TENANT ||--o{ PAYMENT : makes
    PAYMENT }|--|{ INVOICE_LINE : "allocated to"
    PAYMENT_METHOD ||--o{ PAYMENT : "used by"
    UNIT ||--o{ MAINTENANCE_REQUEST : raises
    VENDOR ||--o{ MAINTENANCE_REQUEST : resolves
    MAINTENANCE_CATEGORY ||--o{ MAINTENANCE_REQUEST : classifies
    WEATHER_DAY ||--o{ MAINTENANCE_REQUEST : "conditions on"
    INCENTIVE ||--o{ INCENTIVE_OFFER_DAY : "offered as"
    UNIT ||--o{ INCENTIVE_OFFER_DAY : "receives while vacant"
    UNIT ||--o{ OCCUPANCY_DAY : "is occupied or vacant on"
"""

# 02 conceptual dimensional model (bus view): processes -> facts -> conformed dimensions, one column each
lines = ["---", "title: Conceptual dimensional model - 5 business processes, 6 facts, 13 conformed dimensions", "---",
         "flowchart LR"]
proc = {"fact_rent_invoice_line": "P1", "fact_payment": "P1", "fact_unit_occupancy_daily": "P2",
        "fact_maintenance_request": "P3", "fact_lease_event": "P4", "fact_vacancy_incentive_coverage": "P5"}
pn = {"P1": "P1 Rent invoicing and payment", "P2": "P2 Unit occupancy", "P3": "P3 Maintenance",
      "P4": "P4 Lease lifecycle", "P5": "P5 Vacancy marketing"}
for k, v in pn.items():
    lines.append(f'    {k}["{v}"]')
for f in FACTS:
    lines.append(f'    {f["name"]}(["{f["name"]}<br/><i>{f["type"]}</i>"])')
for d in DIMENSIONS:
    lines.append(f'    {d["name"]}["{d["name"]}"]')
for f in FACTS:
    lines.append(f"    {proc[f['name']]} --> {f['name']}")
for f in FACTS:
    seen = []
    for c in f["cols"]:
        if c["ref"] and c["ref"].startswith("dim_") and c["ref"] not in seen:
            seen.append(c["ref"])
            lines.append(f"    {f['name']} --- {c['ref']}")
lines.append("    classDef proc fill:#F4F4F4,stroke:#888")
lines.append("    classDef fact fill:#E8F0FB,stroke:#2F5D9A,stroke-width:1.5px")
lines.append("    classDef dim fill:#FFFFFF,stroke:#666")
lines.append("    class " + ",".join(pn) + " proc")
lines.append("    class " + ",".join(f["name"] for f in FACTS) + " fact")
lines.append("    class " + ",".join(d["name"] for d in DIMENSIONS) + " dim")
files["02_conceptual_dimensional_model.mmd"] = "\n".join(lines) + "\n"

# 03 logical stars and 04 physical stars
for i, f in enumerate(FACTS, 1):
    files[f"03_logical_star_{i}_{f['name']}.mmd"] = star(f, False, i)
    files[f"04_physical_star_{i}_{f['name']}.mmd"] = star(f, True, i)

# 05 source ERD (Lab 03 style, normalised operational schema)
src = ["---", "title: Source ERD - src_pms normalised operational schema (S1 PropertyHub)", "---", "erDiagram"]
for a, card, b, label in SOURCE_RELS:
    src.append(f'    {a} {card} {b} : "{label}"')
for tname, cols in SOURCE_ERD.items():
    src.append(f"    {tname} {{")
    for typ, name, k in cols:
        k = k.replace(" ", "")
        src.append(f"        {typ} {name}{(' ' + k) if k else ''}")
    src.append("    }")
files["05_source_erd.mmd"] = "\n".join(src) + "\n"

# 06 architecture (mirrors the 11 sections of the reference diagram)
files["06_architecture.mmd"] = """---
title: LUE end-to-end architecture - mapped to the 11 sections of the reference diagram
---
flowchart TB
    subgraph S1[1. Source systems]
        direction LR
        SRC1[(S1 PropertyHub<br/>PostgreSQL src_pms)]
        SRC2[S2 Owner, vendor, SLA,<br/>holiday registers - Excel]
        SRC3[S3 Bank and wallet<br/>settlements - CSV]
        SRC4[S4 Tenant app<br/>tickets - JSON]
        SRC5[S5 Weather<br/>Open-Meteo REST API]
        SRC6[S6 Incentive log<br/>leasing CSV]
    end

    subgraph S2[2. Pipeline orchestration - run_pipeline.py]
        direction LR
        O1[Ingest] --> O2[Validate] --> O3[Transform] --> O4[Load dims] --> O5[Load facts] --> O6[Build marts] --> O7[Test and reconcile] --> O8[Log run]
    end

    subgraph S3["3. Bronze - raw landing (lue_staging.brz_*)"]
        direction LR
        B1[lue_staging.brz_* as-is copies] --> B2[+ batch_id, source_system, loaded_at]
    end

    subgraph S4[4. Data quality and validation]
        direction LR
        Q1[NULL] --> Q2[Data type] --> Q3[Duplicate] --> Q4[Business rule] --> Q5[Referential] --> Q6[Range]
    end

    subgraph REJ[4b. Reject / quarantine - lue_audit.quarantine]
        direction LR
        R1[Rejected row as JSON] --> R2[Check and reason] --> R3[Source + batch_id] --> R4[Rejected at]
    end

    subgraph S5["5. Silver - cleaned and standardised (lue_staging.stg_*)"]
        direction LR
        V1[Cleaning] --> V2[Standardisation<br/>casing, dates, unit codes] --> V3[Deduplication] --> V4[Business transformations<br/>allocations, days past due] --> V5[Incremental load<br/>watermark per source]
    end

    subgraph SCD[SCD processing - dimensions.sql]
        direction LR
        C1{Detect change} -->|Type 1| C2[Overwrite in place]
        C1 -->|Type 2| C3[Expire current row,<br/>insert new version]
        C1 -->|Missing member| C4[Inferred member,<br/>deferred update]
    end

    subgraph S6[6. Dimensional data warehouse - schema lue_dw]
        direction LR
        subgraph DIMS[13 conformed dimensions]
            direction TB
            D1[dim_date - role-playing]
            D2[dim_unit SCD2 - dim_tenant SCD2]
            D3[dim_lease - dim_owner - dim_vendor SCD2]
            D4[dim_payment_method - dim_charge_type]
            D5[dim_maintenance_category SCD2 - dim_weather]
            D6[dim_lease_event_type - dim_request_flags junk - dim_incentive]
        end
        subgraph FACTS[6 fact tables]
            direction TB
            F1[fact_rent_invoice_line - transaction]
            F2[fact_payment - transaction]
            F3[fact_unit_occupancy_daily - periodic snapshot]
            F4[fact_maintenance_request - accumulating snapshot]
            F5[fact_lease_event - factless event]
            F6[fact_vacancy_incentive_coverage - factless coverage]
        end
        DIMS --> FACTS
    end

    subgraph S7[7. Warehouse performance]
        direction LR
        P1[Monthly partitions] --> P2[FK and composite indexes] --> P3[EXPLAIN ANALYZE before and after] --> P4[Performance comparison]
    end

    subgraph S8["8. Gold - data marts and materialized views (lue_reporting)"]
        direction LR
        G1[mart_collections_monthly]
        G2[mart_occupancy_monthly]
        G3[mart_maintenance_monthly]
        G4[mart_owner_portfolio_monthly]
    end

    subgraph S9[9. Analytics and BI]
        direction LR
        A1[Analytical SQL] --> A2[ROLLUP / CUBE / GROUPING] --> A3[Window functions] --> A4[Power BI - 5 pages] --> A5[Business decisions]
    end

    subgraph S10[10. Audit, monitoring and reconciliation]
        direction LR
        M1[etl_run_log] --> M2[Rows read] --> M3[Inserted / updated] --> M4[Rejected] --> M5[Source vs DW reconciliation] --> M6[Pipeline status]
    end

    subgraph S11[11. Metadata and data lineage]
        direction LR
        L1[Source] --> L2[Bronze] --> L3[Silver] --> L4[DW] --> L5[Gold] --> L6[Power BI]
    end

    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 -->|Valid| S5
    S4 -.->|Invalid| REJ
    S5 --> SCD
    SCD --> S6
    S6 -.-> S7
    S6 --> S8
    S8 --> S9
    S6 -.-> S10
    S9 -.-> S11
"""

# 07 hierarchies
h = ["---", "title: Dimension hierarchies used for drill-down and roll-up", "---", "flowchart LR"]
for i, (dim, name, chain) in enumerate(HIERARCHIES):
    levels = [x.strip() for x in chain.split("→")]
    h.append(f'    subgraph H{i}["{dim} - {name}"]')
    h.append("        direction LR")
    ids = [f"H{i}L{j}" for j in range(len(levels))]
    for idn, lvl in zip(ids, levels):
        h.append(f'        {idn}["{lvl}"]')
    h.append("        " + " --> ".join(ids))
    h.append("    end")
files["07_hierarchies.mmd"] = "\n".join(h) + "\n"

for name, text in files.items():
    open(os.path.join(OUT, name), "w").write(text)
print("\n".join(sorted(files)))
