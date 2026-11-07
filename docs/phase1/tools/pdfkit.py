"""Shared ReportLab layout for the LUE Phase 1 PDFs."""
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
                                Preformatted, KeepTogether, Image, PageBreak, CondPageBreak)
from model import PROJECT, COURSE, INSTITUTE, INSTRUCTOR, AUTHORS, VERSION, DATE

D = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", D + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", D + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Oblique", D + "DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("Sans-BoldOblique", D + "DejaVuSans-BoldOblique.ttf"))
pdfmetrics.registerFont(TTFont("Mono", D + "DejaVuSansMono.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Oblique", boldItalic="Sans-BoldOblique")

NAVY = colors.HexColor("#1F3A5F")
BLUE_TINT = colors.HexColor("#E8F0FB")
GREY_LINE = colors.HexColor("#C8CED6")
BAND = colors.HexColor("#F5F7FA")
INK = colors.HexColor("#1D232B")
QUIET = colors.HexColor("#5B6573")

ST = {
    "title": ParagraphStyle("title", fontName="Sans-Bold", fontSize=20, leading=25, textColor=NAVY, spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", fontName="Sans-Bold", fontSize=13, leading=17, textColor=INK, spaceAfter=8),
    "meta": ParagraphStyle("meta", fontName="Sans", fontSize=8.5, leading=12, textColor=QUIET),
    "h1": ParagraphStyle("h1", fontName="Sans-Bold", fontSize=13.5, leading=17, textColor=NAVY, spaceBefore=12,
                         spaceAfter=5, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=8,
                         spaceAfter=3, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Sans", fontSize=9, leading=13, textColor=INK, spaceAfter=5,
                           alignment=TA_LEFT),
    "bullet": ParagraphStyle("bullet", fontName="Sans", fontSize=9, leading=12.5, textColor=INK, leftIndent=12,
                             bulletIndent=2, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=7.6, leading=9.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Sans-Bold", fontSize=7.6, leading=9.6, textColor=INK),
    "head": ParagraphStyle("head", fontName="Sans-Bold", fontSize=7.6, leading=9.6, textColor=colors.white),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=6.9, leading=8.6, textColor=INK),
    "callout": ParagraphStyle("callout", fontName="Sans-Bold", fontSize=9.5, leading=13.5, textColor=NAVY),
    "caption": ParagraphStyle("caption", fontName="Sans-Oblique", fontSize=8, leading=10.5, textColor=QUIET,
                              spaceAfter=6),
}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def esc(s):
    return escape(str(s))


def P(text, style="body"):
    return Paragraph(text, ST[style])


def H1(text):
    return P(esc(text), "h1")


def H2(text):
    return P(esc(text), "h2")


def bullets(items):
    return [Paragraph(t, ST["bullet"], bulletText="•") for t in items]


def numbered(items):
    return [Paragraph(t, ST["bullet"], bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def table(rows, widths, header=True, bold_first_col=False, raw=False, highlight_rows=()):
    """rows: list of lists of strings (escaped unless raw=True). widths: fractions of content width."""
    data = []
    for r_i, r in enumerate(rows):
        out = []
        for c_i, c in enumerate(r):
            if isinstance(c, (Paragraph, Table, Preformatted)):
                out.append(c)
                continue
            txt = str(c) if raw else esc(c)
            if header and r_i == 0:
                out.append(Paragraph(txt, ST["head"]))
            elif bold_first_col and c_i == 0:
                out.append(Paragraph(txt, ST["cellb"]))
            else:
                out.append(Paragraph(txt, ST["cell"]))
        data.append(out)
    t = Table(data, colWidths=[w * CONTENT_W for w in widths], repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, GREY_LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    for i in highlight_rows:
        style.append(("BACKGROUND", (0, i), (-1, i), BLUE_TINT))
    t.setStyle(TableStyle(style))
    return t


def callout(text, label="Grain"):
    inner = Paragraph(f'<font color="#5B6573" size="7.5">{esc(label.upper())}</font><br/>{text}', ST["callout"])
    t = Table([[inner]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE_TINT), ("LINEBEFORE", (0, 0), (0, -1), 3, NAVY),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def code(text):
    pre = Preformatted(text, ST["code"])
    t = Table([[pre]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND), ("BOX", (0, 0), (-1, -1), 0.4, GREY_LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def image(path, max_w=CONTENT_W, max_h=200 * mm):
    from PIL import Image as PI
    w, h = PI.open(path).size
    s = min(max_w / w, max_h / h)
    return Image(path, width=w * s, height=h * s)


def cover_block(doc_title, purpose):
    rows = [
        P(esc(PROJECT), "title"),
        P(esc(doc_title), "subtitle"),
        P(esc(f"{COURSE} · Final Project · {VERSION}"), "meta"),
        P(esc(INSTITUTE), "meta"),
        P(esc(INSTRUCTOR), "meta"),
        P(esc(f"Prepared by: {AUTHORS} · {DATE}"), "meta"),
        Spacer(1, 6),
    ]
    t = Table([[rows]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return [t, Spacer(1, 8), P(purpose, "body")]


def build(path, doc_title, story):
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Sans", 7)
        canvas.setFillColor(QUIET)
        canvas.drawString(MARGIN, 10 * mm, f"{PROJECT} · {doc_title}")
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(GREY_LINE)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                          bottomMargin=18 * mm, title=f"{PROJECT} – {doc_title}", author=AUTHORS,
                          subject="DL3004 Final Project Phase 1")
    frame = Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - MARGIN - 18 * mm, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=footer)])
    doc.build(story)
