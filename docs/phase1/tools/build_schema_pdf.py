"""Assemble 06_Schema_Diagrams.pdf from the rendered Mermaid PNGs (one diagram per page)."""
import os
import sys
from PIL import Image as PI
from reportlab.lib.pagesizes import A3, landscape, portrait
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import pdfkit  # registers fonts
from model import PROJECT, COURSE, INSTITUTE, AUTHORS, VERSION, DATE, FACTS

OUT = sys.argv[1]
PNG = os.path.join(OUT, "diagrams", "png")
VEC = sys.argv[2]
NAVY = (0, 0, 0)
QUIET = (0.25, 0.25, 0.25)

PAGES = [("01_conceptual_model", "Conceptual model", "Business entities and relationships only, no attributes. "
          "Payment to invoice line is many-to-many, which is why the logical model splits invoicing and payment into two facts."),
         ("02_conceptual_dimensional_model", "Conceptual dimensional model (bus view)",
          "Five business processes, the six fact tables they produce and the 13 conformed dimensions each fact uses."),
         ("07_hierarchies", "Dimension hierarchies", "Drill-down paths from the lowest to the highest level. All are "
          "flattened into their dimension table (star schema, Lab 04 design rule).")]
for i, f in enumerate(FACTS, 1):
    PAGES.append((f"03_logical_star_{i}_{f['name']}", f"Logical model · star {i} · {f['name']}",
                  f"{f['type']}. Grain: {f['grain']} Logical types (SK, text, money, date, flag); PK/FK, measures with "
                  "additivity, hierarchy levels, SCD Type 2 attributes and degenerate dimensions are annotated."))
for i, f in enumerate(FACTS, 1):
    PAGES.append((f"04_physical_star_{i}_{f['name']}", f"Physical model · star {i} · {f['name']}",
                  f"PostgreSQL 16 data types, primary and foreign keys, nullability and lineage columns, exactly as in "
                  f"sql/physical_model.sql. Grain: {f['grain']}"))
PAGES += [("05_source_erd", "Source ERD · src_pms (Lab 03 style)", "The normalised operational schema of the "
           "PropertyHub source system, with primary keys, foreign keys and cardinalities. Shown to make clear that the "
           "warehouse is designed around business processes, not copied from these tables."),
          ("06_architecture", "End-to-end architecture", "The pipeline mapped to the 11 sections of the reference "
           "architecture diagram: sources, orchestration, Bronze, quality checks and quarantine, Silver, SCD processing, "
           "warehouse, performance, Gold marts, analytics and BI, audit, and lineage.")]


def wrap(c, text, x, y, width, font, size, leading, color=(0, 0, 0)):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c.setFont(font, size)
    c.setFillColorRGB(*color)
    line = ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if stringWidth(trial, font, size) > width:
            c.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


path = os.path.join(OUT, "06_Schema_Diagrams.pdf")
c = canvas.Canvas(path, pagesize=landscape(A3))
c.setTitle(f"{PROJECT} – 06 Schema Diagrams")
c.setAuthor(AUTHORS)

# cover + contents + legend
W, H = landscape(A3)
m = 22 * mm
c.setFillColorRGB(*NAVY)
c.setFont("Sans-Bold", 28)
c.drawString(m, H - 40 * mm, PROJECT)
c.setFillColorRGB(0.11, 0.14, 0.17)
c.setFont("Sans-Bold", 18)
c.drawString(m, H - 52 * mm, "Star Schema Diagrams: conceptual, logical, physical, source ERD and architecture")
c.setFont("Sans", 11)
c.setFillColorRGB(*QUIET)
c.drawString(m, H - 62 * mm, f"{COURSE} · Final Project · {VERSION}")
c.drawString(m, H - 69 * mm, f"{INSTITUTE} · Prepared by: {AUTHORS} · {DATE}")
c.setStrokeColorRGB(*NAVY)
c.setLineWidth(1.5)
c.line(m, H - 75 * mm, W - m, H - 75 * mm)

y = H - 90 * mm
c.setFillColorRGB(*NAVY)
c.setFont("Sans-Bold", 13)
c.drawString(m, y, "Contents")
y -= 8 * mm
c.setFont("Sans", 10)
c.setFillColorRGB(0.11, 0.14, 0.17)
for n, (_, title, _) in enumerate(PAGES, 1):
    c.drawString(m, y, f"Figure {n:>2}   {title}")
    c.drawRightString(W / 2 - 10 * mm, y, f"page {n + 1}")
    y -= 6.2 * mm

x2 = W / 2 + 5 * mm
y = H - 90 * mm
c.setFillColorRGB(*NAVY)
c.setFont("Sans-Bold", 13)
c.drawString(x2, y, "How to read the diagrams")
y -= 9 * mm
legend = [
    "Crow's foot notation: || = exactly one, |o = zero or one, |{ = one or more, o{ = zero or more.",
    "Every star: each dimension connects directly to the fact; a dimension appears once per star and once per date role "
    "(the relationship label names the role, e.g. paid_date, due_date).",
    "PK = primary key (surrogate *_key in dimensions; *_sk or a composite key in facts). FK = foreign key to the dimension named in the note.",
    "Logical types: SK = integer surrogate key, money = PKR amount, flag = yes/no, text, date, integer, decimal.",
    "Annotations: 'measure: Additive / Semi-additive / Non-additive', 'hierarchy L1…L6', 'SCD2' and 'degenerate dimension'.",
    "Physical diagrams show PostgreSQL types, NULL / NOT NULL and the lineage columns source_system, batch_id, loaded_at.",
    "Special members: key -1 = Unknown, key -2 = Not applicable / not yet happened.",
    "Every diagram is generated from Mermaid source in diagrams/mermaid/*.mmd and can be edited and re-rendered "
    "(mermaid.live or the mmdc command line).",
]
for item in legend:
    y = wrap(c, "• " + item, x2, y, W - m - x2, "Sans", 10, 14, (0.11, 0.14, 0.17))
    y -= 3
c.setFont("Sans", 7.5)
c.setFillColorRGB(*QUIET)
c.drawString(m, 12 * mm, f"{PROJECT} · 06 Schema Diagrams")
c.drawRightString(W - m, 12 * mm, "Page 1")
c.showPage()

PLACEMENTS = []
for n, (fname, title, caption) in enumerate(PAGES, 1):
    from pypdf import PdfReader as _R
    _box = _R(os.path.join(VEC, fname + ".pdf")).pages[0].mediabox
    iw, ih = float(_box.width), float(_box.height)
    size = portrait(A3) if ih > iw * 1.15 else landscape(A3)
    W, H = size
    c.setPageSize(size)
    c.setFillColorRGB(*NAVY)
    c.setFont("Sans-Bold", 15)
    c.drawString(m, H - 18 * mm, f"Figure {n}. {title}")
    y = wrap(c, caption, m, H - 26 * mm, W - 2 * m, "Sans", 9.5, 13, QUIET)
    top = y - 4 * mm
    bottom = 18 * mm
    avail_w, avail_h = W - 2 * m, top - bottom
    s = min(avail_w / iw, avail_h / ih)
    dw, dh = iw * s, ih * s
    PLACEMENTS.append((fname, m, bottom, avail_w, avail_h))
    c.setFont("Sans", 7.5)
    c.setFillColorRGB(*QUIET)
    c.drawString(m, 10 * mm, f"{PROJECT} · 06 Schema Diagrams · source: diagrams/mermaid/{fname}.mmd")
    c.drawRightString(W - m, 10 * mm, f"Page {n + 1}")
    c.showPage()
c.save()

# place each vector diagram (rendered by mmdc to PDF) into the reserved area of its page
from pypdf import PdfReader, PdfWriter, Transformation
base = PdfReader(path)
writer = PdfWriter()
writer.add_page(base.pages[0])
for i, (fname, x0, y0, aw, ah) in enumerate(PLACEMENTS, 1):
    page = base.pages[i]
    dia = PdfReader(os.path.join(VEC, fname + ".pdf")).pages[0]
    dw, dh = float(dia.mediabox.width), float(dia.mediabox.height)
    sc = min(aw / dw, ah / dh)
    tx = x0 + (aw - dw * sc) / 2
    ty = y0 + (ah - dh * sc)
    page.merge_transformed_page(dia, Transformation().scale(sc).translate(tx, ty))
    writer.add_page(page)
writer.add_metadata({"/Title": f"{PROJECT} – 06 Schema Diagrams", "/Author": AUTHORS})
writer.compress_identical_objects()
with open(path, "wb") as fh:
    writer.write(fh)
print("saved", path, len(PAGES) + 1, "pages")
