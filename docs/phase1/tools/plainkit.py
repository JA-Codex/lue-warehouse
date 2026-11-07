"""Plain-text document layout: black text, headings by size and weight, no colour fills or boxes."""
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
                                Preformatted, KeepTogether, Image, PageBreak, CondPageBreak)
from model import PROJECT, COURSE, INSTITUTE, INSTRUCTOR, AUTHORS, VERSION, DATE

D = "/usr/share/fonts/truetype/dejavu/"
for name, f in [("Sans", "DejaVuSans.ttf"), ("Sans-Bold", "DejaVuSans-Bold.ttf"), ("Sans-Oblique", "DejaVuSans-Oblique.ttf"),
                ("Sans-BoldOblique", "DejaVuSans-BoldOblique.ttf"), ("Mono", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(name, D + f))
registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Oblique", boldItalic="Sans-BoldOblique")

BLACK = colors.black
ST = {
    "title": ParagraphStyle("title", fontName="Sans-Bold", fontSize=18, leading=23, spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", fontName="Sans-Bold", fontSize=13, leading=17, spaceAfter=8),
    "meta": ParagraphStyle("meta", fontName="Sans", fontSize=9, leading=13),
    "h1": ParagraphStyle("h1", fontName="Sans-Bold", fontSize=14, leading=18, spaceBefore=14, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="Sans-BoldOblique", fontSize=10, leading=13.5, spaceBefore=6, spaceAfter=2,
                         keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Sans", fontSize=10, leading=14.5, spaceAfter=6),
    "item": ParagraphStyle("item", fontName="Sans", fontSize=10, leading=14.5, leftIndent=14, spaceAfter=1),
    "bullet": ParagraphStyle("bullet", fontName="Sans", fontSize=10, leading=14.5, leftIndent=14, bulletIndent=3,
                             spaceAfter=2),
    "note": ParagraphStyle("note", fontName="Sans-Oblique", fontSize=9, leading=13, spaceAfter=6),
    "grain": ParagraphStyle("grain", fontName="Sans-BoldOblique", fontSize=10.5, leading=15, leftIndent=14,
                            spaceBefore=2, spaceAfter=8),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=7.8, leading=10, leftIndent=14),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=8.5, leading=11),
    "cellb": ParagraphStyle("cellb", fontName="Sans-Bold", fontSize=8.5, leading=11),
}
PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def esc(s):
    return escape(str(s))


def P(text, style="body"):
    return Paragraph(text, ST[style])


def H1(t):
    return P(esc(t), "h1")


def H2(t):
    return P(esc(t), "h2")


def H3(t):
    return P(esc(t), "h3")


def note(t):
    return P(t, "note")


def bullets(items):
    return [Paragraph(t, ST["bullet"], bulletText="•") for t in items]


def numbered(items):
    return [Paragraph(t, ST["bullet"], bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def field(label, value):
    """A labelled line: bold label, plain value."""
    return P(f"<b>{esc(label)}:</b> {value}", "item")


def entry(title, fields=(), text=None):
    """A bold entry title followed by indented labelled lines; kept on one page."""
    parts = [P(f"<b>{title}</b>", "body")]
    if text:
        parts.append(P(text, "item"))
    for k, v in fields:
        parts.append(field(k, v))
    parts.append(Spacer(1, 4))
    return KeepTogether(parts)


def grain(text):
    return P(text, "grain")


def code(text):
    return Preformatted(text, ST["code"])


def grid(rows, widths):
    """Plain black-line table for genuinely tabular content; bold header, no fills."""
    data = [[Paragraph(esc(c), ST["cellb"] if i == 0 or j == 0 else ST["cell"]) for j, c in enumerate(r)]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * CONTENT_W for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, BLACK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def image(path, max_w=CONTENT_W, max_h=200 * mm):
    from PIL import Image as PI
    w, h = PI.open(path).size
    s = min(max_w / w, max_h / h)
    return Image(path, width=w * s, height=h * s)


def cover(doc_title, purpose):
    return [P(esc(PROJECT), "title"), P(esc(doc_title), "subtitle"),
            P(esc(f"{COURSE} — Final Project — {VERSION}"), "meta"), P(esc(INSTITUTE), "meta"),
            P(esc(INSTRUCTOR), "meta"), P(esc(f"Prepared by: {AUTHORS}"), "meta"), P(esc(f"Date: {DATE}"), "meta"),
            Spacer(1, 14), P(purpose, "body")]


def build(path, doc_title, story):
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Sans", 8)
        canvas.drawString(MARGIN, 11 * mm, f"{PROJECT} — {doc_title}")
        canvas.drawRightString(PAGE_W - MARGIN, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                          bottomMargin=20 * mm, title=f"{PROJECT} – {doc_title}", author=AUTHORS)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(MARGIN, 20 * mm, CONTENT_W, PAGE_H - MARGIN - 20 * mm)],
                                       onPage=footer)])
    doc.build(story)
