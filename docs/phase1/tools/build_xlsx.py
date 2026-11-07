"""Build the Excel data dictionary from model.py."""
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from model import (SCHEMA_DW, DIMENSIONS, FACTS, AUDIT, SOURCES, SOURCE_TABLES, QUESTIONS, KPIS, HIERARCHIES, ADDITIVITY,
                   BUS_DIMS, bus_matrix, PROJECT, VERSION, DATE, AUTHORS, COURSE)

OUT = sys.argv[1]
F = "Arial"
HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
HEAD_FONT = Font(name=F, bold=True, color="FFFFFF", size=10)
BODY = Font(name=F, size=10)
BOLD = Font(name=F, size=10, bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Side(style="thin", color="C8CED6")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BAND = PatternFill("solid", fgColor="F3F6FA")
FACT_FILL = PatternFill("solid", fgColor="E8F0FB")

wb = Workbook()


def sheet(title, headers, rows, widths, band_key=None):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font, c.alignment, c.border = HEAD_FILL, HEAD_FONT, WRAP, BORDER
    for r in rows:
        ws.append(list(r))
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font, c.alignment, c.border = BODY, WRAP, BORDER
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "B2" if len(headers) > 4 else "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 30
    return ws


def scd_label(c):
    if c["key"] == "PK" or c["tech"] or c["name"] in ("effective_from", "effective_to", "is_current"):
        return "n/a (key or technical)"
    if c["ref"]:
        return "n/a (foreign key)"
    return {"0": "Type 0 (retain original)", "1": "Type 1 (overwrite)", "2": "Type 2 (new version)"}.get(
        c["scd"], "Type 1 (overwrite)")


# ---------------- README
ws = wb.active
ws.title = "README"
info = [
    (PROJECT, ""),
    ("Data Dictionary", ""),
    ("Course", COURSE),
    ("Version", VERSION),
    ("Date", DATE),
    ("Prepared by", AUTHORS),
    ("", ""),
    ("Sheet", "What it contains"),
    ("Tables", "Every warehouse and audit table: type, grain, keys, source, load pattern, column count"),
    ("Columns", "Every column: data type, PK/FK, reference, nullable, SCD type, description, source, example, business rule"),
    ("Bus_Matrix", "Facts × conformed dimensions (Kimball bus matrix), with date roles"),
    ("SCD_Policy", "SCD type and business reason for every descriptive dimension attribute"),
    ("Measures", "Additivity of every fact measure and the correct aggregation"),
    ("Hierarchies", "Drill-down / roll-up paths per dimension"),
    ("Sources", "The six source systems (S1–S6): format, owner, contents, ingestion, typical defects"),
    ("Source_Grains", "What one row of each source table or file represents, and its natural key"),
    ("KPIs", "KPI formulas built from additive parts, facts used, question answered"),
    ("Questions", "The 14 business questions traced to facts, dimensions, measures and OLAP operations"),
    ("", ""),
    ("Conventions", ""),
    ("Surrogate keys", "Integer *_key columns; -1 = Unknown, -2 = Not applicable / not yet happened"),
    ("Natural keys", "Source business keys are kept in every dimension for lineage and lookups"),
    ("SCD Type 2 columns", "effective_from, effective_to (9999-12-31 while current), is_current"),
    ("Lineage columns", "source_system, batch_id, loaded_at on every dimension and fact"),
    ("Grain wording", "Grain sentences are identical in this workbook, the grain document and the diagrams"),
    ("Physical model", "sql/physical_model.sql (PostgreSQL 16+) is generated from the same definitions"),
    ("", ""),
    ("Model summary", "Count"),
    ("Dimension tables", "=COUNTIF(Tables!C:C,\"Dimension\")"),
    ("Fact tables", "=COUNTIF(Tables!C:C,\"Fact\")"),
    ("Audit tables", "=COUNTIF(Tables!C:C,\"Audit\")"),
    ("Columns documented", "=COUNTA(Columns!B:B)-1"),
    ("SCD Type 2 attributes", "=COUNTIF(SCD_Policy!C:C,\"Type 2*\")"),
    ("Business questions", "=COUNTA(Questions!A:A)-1"),
]
for r in info:
    ws.append(list(r))
ws.column_dimensions["A"].width = 26
ws.column_dimensions["B"].width = 110
for row in ws.iter_rows():
    for c in row:
        c.font, c.alignment = BODY, Alignment(wrap_text=True, vertical="top")
ws["A1"].font = Font(name=F, size=16, bold=True, color="1F3A5F")
ws["A2"].font = Font(name=F, size=13, bold=True)
for r in (8, 20, 28):
    for c in ws[r]:
        c.font, c.fill = HEAD_FONT, HEAD_FILL
for r in range(29, 35):
    ws.cell(r, 2).alignment = Alignment(horizontal="left")

# ---------------- Tables
rows = []
for t in DIMENSIONS:
    pk = [c["name"] for c in t["cols"] if "PK" in c["key"]][0]
    rows.append([SCHEMA_DW, t["name"], "Dimension", "", t["grain"], pk, t["nk"], t["rows"], t["source"],
                 "SCD Type 2 load (expire + insert)" if any(c["scd"] == "2" for c in t["cols"]) else "SCD Type 1 merge",
                 t["hierarchy"], ""])
for t in FACTS:
    rows.append([SCHEMA_DW, t["name"], "Fact", t["type"], t["grain"], t["pk"], "—", t["rows"],
                 "Silver layer, lue_staging.stg_* (see Source_Grains)", t["load"], "—", ""])
for a in AUDIT:
    sch, name = a["name"].split(".")
    pk = ", ".join(c["name"] for c in a["cols"] if "PK" in c["key"])
    rows.append([sch, name, "Audit", "", a["grain"], pk, "—", "Grows per run", "Pipeline", "Insert per run", "—", ""])
ws = sheet("Tables", ["Schema", "Table", "Table type", "Fact type", "Grain (one row represents…)", "Primary key",
                      "Natural / business key", "Expected rows (3 yrs)", "Source", "Load pattern", "Hierarchy",
                      "Columns"], rows, [11, 30, 11, 22, 60, 26, 26, 18, 30, 40, 40, 9])
for r in range(2, ws.max_row + 1):
    ws.cell(r, 12).value = f'=COUNTIF(Columns!A:A,B{r})'
    if ws.cell(r, 3).value == "Fact":
        for c in ws[r]:
            c.fill = FACT_FILL

# ---------------- Columns
rows = []
for t in DIMENSIONS + FACTS:
    for c in t["cols"]:
        rows.append([t["name"], c["name"], c["type"], c["key"], c["ref"] or "", "Yes" if c["null"] else "No",
                     scd_label(c) if t in DIMENSIONS else "n/a (fact)", c["desc"], c["src"], c["ex"], c["rule"],
                     "Yes" if c["tech"] else "No"])
for a in AUDIT:
    for c in a["cols"]:
        rows.append([a["name"].split(".")[1], c["name"], c["type"], c["key"], c["ref"] or "",
                     "Yes" if c["null"] else "No", "n/a (audit)", c["desc"], "Pipeline", c["ex"], c["rule"], "Yes"])
ws = sheet("Columns", ["Table", "Column", "Data type (PostgreSQL)", "Key", "References", "Nullable", "SCD type",
                       "Description", "Source system and column", "Example value", "Business rule / validation",
                       "Technical column"], rows, [28, 24, 16, 8, 24, 9, 22, 55, 34, 22, 40, 10])

# ---------------- Bus matrix
rows = [[f] + r for f, r in bus_matrix()]
ws = sheet("Bus_Matrix", ["Fact \\ Dimension"] + BUS_DIMS, rows, [30] + [16] * len(BUS_DIMS))
for row in ws.iter_rows(min_row=2, min_col=2):
    for c in row:
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if c.value:
            c.fill = FACT_FILL

# ---------------- SCD policy
rows = []
for t in DIMENSIONS:
    for c in t["cols"]:
        if c["key"] or c["tech"] or c["name"] in ("effective_from", "effective_to", "is_current", "is_inferred"):
            continue
        lab = scd_label(c)
        reason = c["scd_reason"] or {"Type 0 (retain original)": "Fixed by definition or contract",
                                     "Type 1 (overwrite)": "Corrections or current value only; no analytical history",
                                     "Type 2 (new version)": "History needed"}[lab]
        rows.append([t["name"], c["name"], lab, reason])
sheet("SCD_Policy", ["Dimension", "Attribute", "SCD type", "Business reason"], rows, [28, 26, 24, 80])

# ---------------- Measures
sheet("Measures", ["Fact table", "Measure(s)", "Additivity", "Correct aggregation"],
      ADDITIVITY, [32, 48, 20, 60])

# ---------------- Hierarchies
sheet("Hierarchies", ["Dimension", "Hierarchy", "Levels (lowest → highest)"], HIERARCHIES, [28, 22, 70])

# ---------------- Sources
sheet("Sources", ["ID", "Source system", "Format", "Owner team", "Contents", "Ingestion (to Bronze, lue_staging.brz_*)", "Typical defects"],
      [(s["id"], s["name"], s["fmt"], s["owner"], s["content"], s["ingest"], s["defects"]) for s in SOURCES],
      [6, 32, 30, 20, 60, 30, 50])
sheet("Source_Grains", ["Source", "Table / file", "One row represents…", "Natural key"], SOURCE_TABLES, [8, 34, 60, 40])

# ---------------- KPIs and questions
sheet("KPIs", ["KPI", "Formula (from additive parts)", "Facts used", "Question"], KPIS, [30, 80, 44, 10])
sheet("Questions", ["#", "Question", "Process", "Stakeholder", "Fact table(s)", "Key dimensions", "Measures",
                    "OLAP operation"], QUESTIONS, [6, 60, 9, 22, 40, 36, 30, 48])

wb.save(OUT)
print("saved", OUT)
