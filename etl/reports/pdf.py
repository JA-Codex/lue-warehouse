"""Shared PDF building blocks for the Phase 2 reports (reportlab)."""

# ruff: noqa: E501  (drawing coordinates: long lines read better)

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


__all__ = ["PageBreak", "Spacer", "bullets", "build", "escape", "flow", "fmt", "keep", "mm", "p", "table"]


def flow(steps: list[tuple[str, str]], side: tuple[int, str, str] | None = None):
    """A left-to-right pipeline diagram: boxes (title, caption) joined by arrows; side = (index of
    the box it hangs from, title, caption) for a branch drawn below that box."""
    from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String

    width, n = 174 * mm, len(steps)
    gap = 7 * mm
    box_w = (width - gap * (n - 1)) / n
    box_h, top = 17 * mm, 34 * mm if side else 20 * mm
    d = Drawing(width, top + 2)
    y = top - box_h
    for i, (title, caption) in enumerate(steps):
        x = i * (box_w + gap)
        d.add(Rect(x, y, box_w, box_h, fillColor=SHADE, strokeColor=ACCENT, strokeWidth=0.8, rx=3, ry=3))
        d.add(String(x + box_w / 2, y + box_h - 6.5 * mm, title, fontName="Helvetica-Bold",
                     fontSize=8.2, fillColor=ACCENT, textAnchor="middle"))  # fmt: skip
        for k, line in enumerate(caption.split("\n")):
            d.add(String(x + box_w / 2, y + box_h - 10.5 * mm - k * 3.2 * mm, line,
                         fontName="Helvetica", fontSize=6.6, fillColor=INK, textAnchor="middle"))  # fmt: skip
        if i < n - 1:
            ax, ay = x + box_w + 1, y + box_h / 2
            d.add(Line(ax, ay, ax + gap - 3, ay, strokeColor=ACCENT, strokeWidth=0.9))
            d.add(Polygon([ax + gap - 2, ay, ax + gap - 5, ay + 2, ax + gap - 5, ay - 2],
                          fillColor=ACCENT, strokeColor=ACCENT))  # fmt: skip
    if side:
        i, title, caption = side
        x = i * (box_w + gap)
        sy = 0
        d.add(Line(x + box_w / 2, y - 1, x + box_w / 2, sy + 10 * mm + 2, strokeColor=colors.HexColor("#b42318"), strokeWidth=0.9))
        d.add(Rect(x, sy, box_w, 10 * mm, fillColor=colors.HexColor("#fdecea"), strokeColor=colors.HexColor("#b42318"), strokeWidth=0.8, rx=3, ry=3))
        d.add(String(x + box_w / 2, sy + 6 * mm, title, fontName="Helvetica-Bold", fontSize=7.6,
                     fillColor=colors.HexColor("#b42318"), textAnchor="middle"))  # fmt: skip
        d.add(String(x + box_w / 2, sy + 2.6 * mm, caption, fontName="Helvetica", fontSize=6.4,
                     fillColor=INK, textAnchor="middle"))  # fmt: skip
    return d
