"""Shared PDF building blocks for the Phase 2 reports (reportlab)."""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,  # fmt: skip
    TableStyle,
)

INK = colors.HexColor("#1f2933")
ACCENT = colors.HexColor("#1d4e89")
RULE = colors.HexColor("#c9d3dd")
SHADE = colors.HexColor("#eef2f6")

_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=_base["Title"], fontName="Helvetica-Bold", fontSize=20,
                            leading=24, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", parent=_base["Normal"], fontSize=10.5, leading=14,
                               textColor=INK, spaceAfter=10),
    "h1": ParagraphStyle("h1", parent=_base["Heading1"], fontName="Helvetica-Bold", fontSize=13.5,
                         leading=17, textColor=ACCENT, spaceBefore=12, spaceAfter=5),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontName="Helvetica-Bold", fontSize=11,
                         leading=14, textColor=INK, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", parent=_base["BodyText"], fontName="Helvetica", fontSize=9.3,
                           leading=12.6, textColor=INK, spaceAfter=5),
    "bullet": ParagraphStyle("bullet", parent=_base["BodyText"], fontName="Helvetica",
                             fontSize=9.3, leading=12.6, textColor=INK, leftIndent=12,
                             bulletIndent=3, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.8, leading=9.6, textColor=INK),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7.8, leading=9.6,
                           textColor=colors.white),
    "note": ParagraphStyle("note", parent=_base["BodyText"], fontName="Helvetica-Oblique",
                           fontSize=8.2, leading=10.5, textColor=colors.HexColor("#52606d"),
                           spaceAfter=6),
}  # fmt: skip


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullets(items: list[str]) -> list[Paragraph]:
    return [Paragraph(t, STYLES["bullet"], bulletText="•") for t in items]


def table(header: list[str], rows: list[list], widths: list[float], numeric: set[int] | None = None,
          raw: bool = False) -> Table:
    """A shaded-header table; cells wrap. raw=True keeps markup in cells (already escaped)."""
    numeric = numeric or set()
    body = [[Paragraph(escape(h), STYLES["head"]) for h in header]]
    for r in rows:
        cells = []
        for i, v in enumerate(r):
            text = fmt(v) if raw else escape(fmt(v))
            style = ParagraphStyle("c", parent=STYLES["cell"], alignment=2 if i in numeric else 0)
            cells.append(Paragraph(text, style))
        body.append(cells)
    total = sum(widths)
    t = Table(body, colWidths=[w / total * 174 * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SHADE]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))  # fmt: skip
    return t


def keep(*flowables) -> KeepTogether:
    return KeepTogether(list(flowables))


def build(path, title: str, subtitle: str, story: list) -> None:
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#7b8794"))
        canvas.drawString(18 * mm, 10 * mm, f"Lahore Urban Estates Analytics Warehouse · {title}")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=title,
                            author="LUE Warehouse team", subject=subtitle)  # fmt: skip
    head = [p(escape(title), "title"),
            p(escape(subtitle) + "<br/>DL3004 Data Warehousing and Business Intelligence · "
              f"Phase 2 · {date.today():%d %B %Y}", "subtitle")]  # fmt: skip
    doc.build(head + story, onFirstPage=footer, onLaterPages=footer)


__all__ = ["PageBreak", "Spacer", "bullets", "build", "escape", "fmt", "keep", "mm", "p", "table"]
