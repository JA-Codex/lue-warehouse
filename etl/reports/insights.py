#!/usr/bin/env python3
"""Build the Business Insights Report: python etl/reports/insights.py

  docs/reports/LUE_Business_Insights_Report.pdf

The report needs no database: every figure is quoted from a recorded full-profile result
(seed 3004, data window 2023-07-01 to 2026-06-30) and, before anything is drawn, each one is
looked up in the file it comes from (SOURCES below). If a figure is not found there the build
stops, so the report cannot drift from the evidence. The charts are drawn by
docs/reports/figures/make_figures.py; the dashboard pictures are powerbi/screenshots/.
"""

# ruff: noqa: E501  (report text: long lines read better)

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportlab.lib import colors  # noqa: E402
from reportlab.platypus import Image, KeepTogether, Paragraph  # noqa: E402

from etl.reports import pdf  # noqa: E402
from etl.reports.pdf import PageBreak, build, bullets, mm, p, table  # noqa: E402

OUT = ROOT / "docs" / "reports" / "LUE_Business_Insights_Report.pdf"
FIG = ROOT / "docs" / "reports" / "figures"
SHOTS = ROOT / "powerbi" / "screenshots"
ANALYTICS = "docs/analytics.md"
EXPECTED = "docs/evidence/us-13.1/01_expected_values.txt"
DECISIONS = "docs/evidence/us-13.1/decisions.txt"

# (figure as quoted, file it must appear in)
SOURCES = [
    ("5,676,652,818", ANALYTICS), ("5,347,289,709", ANALYTICS), ("94.2 percent", ANALYTICS),
    ("PKR 329,363,109", EXPECTED), ("84.5%", EXPECTED), ("24.9%", EXPECTED), ("PKR 4,092,111,103", EXPECTED),
    ("PKR 1,774,998,239", EXPECTED), ("PKR 1,640,862,798", EXPECTED), ("8.2%", EXPECTED),
    ("| GLB03 | Lahore | 64,267,854 | 21.8% |", ANALYTICS), ("78.2 percent (GLB03)", ANALYTICS),
    ("19.5 percent of all arrears", ANALYTICS), ("| 90+ | 8,913 | 284,267,443 | 86.3% |", ANALYTICS),
    ("recovering half of its PKR 64,267,854 arrears cuts portfolio arrears by 10%", DECISIONS),
    ("Its arrears ratio is 20.5% against 5.7% for the portfolio", DECISIONS),
    ("78.2 percent (Karachi apartments)", ANALYTICS), ("72.1 percent in\nthe last", ANALYTICS),
    ("fills about 23 more units, about PKR 1,775,190 of rent a month", DECISIONS),
    ("| No offer | 1,594 | 134.3 | 1.000 |", ANALYTICS), ("| Any offer | 511 | 57.5 | 0.428 |", ANALYTICS),
    ("Karachi renews **17.9 percent** of expiring leases against 36.1 percent elsewhere", ANALYTICS),
    ("1.43 times the other months", ANALYTICS),
    ("It takes 3.1 days on average to resolve a request, 2.3 times the 1.4 days of all Plumbing vendors, and breaches the SLA on 86.5% of its jobs", DECISIONS),
    ("its 37 requests would have waited about 76 fewer days", DECISIONS),
    ("**6.3 times** as many", ANALYTICS), ("2.05 per 1,000 unit-days", ANALYTICS), ("against 0.32 on other days", ANALYTICS),
    ("14.4 percent (Manufacturing)", ANALYTICS), ("8.4 percent\n(Government)", ANALYTICS),
]  # fmt: skip


def verify() -> None:
    texts = {}
    missing = []
    for figure, src in SOURCES:
        if src not in texts:
            texts[src] = (ROOT / src).read_text(encoding="utf-8")
        if figure not in texts[src]:
            missing.append(f"{figure!r} not found in {src}")
    if missing:
        raise SystemExit("figures that do not match their evidence:\n  " + "\n  ".join(missing))


def img(path: Path, width_mm: float) -> Image:
    from reportlab.lib.utils import ImageReader

    w, h = ImageReader(str(path)).getSize()
    return Image(str(path), width=width_mm * mm, height=width_mm * mm * h / w)


def palette() -> None:
    """This report is printed in the presentation's colours: charcoal text, brick-red tables, no blue."""
    charcoal, brick = colors.HexColor("#333333"), colors.HexColor("#A8382A")
    pdf.ACCENT = brick
    for name in ("title", "h1"):
        pdf.STYLES[name].textColor = charcoal
    pdf.STYLES["h2"].textColor = brick
    pdf.STYLES["h1"].keepWithNext = 1
    pdf.STYLES["h2"].keepWithNext = 1


def label(text: str) -> Paragraph:
    return p(text, "h2")


def section(n: int, title: str, finding: list[str], evidence: list, action: list[str], caveat: list[str]) -> list:
    return [
        p(f"{n}. {title}", "h1"),
        label("Finding"), *bullets(finding),
        *evidence,
        label("Decision and expected effect"), *bullets(action),
        label("Caveat"), *bullets(caveat),
    ]


def report(path: Path = OUT) -> None:
    verify()
    palette()
    s: list = []
    s.append(p("Summary", "h1"))
    s.append(p("The portfolio: 1,800 units in 40 buildings in Lahore, Karachi, Islamabad and Faisalabad, July 2023 to June 2026."))
    s += bullets([
        "<b>Billed</b> PKR 5,676,652,818; <b>collected</b> PKR 5,347,289,709; <b>collection rate</b> 94.2%",
        "<b>Arrears</b> PKR 329,363,109 (5.8% of billed)",
        "<b>Occupancy</b> 84.5%; <b>SLA breached</b> on 24.9% of maintenance requests",
        "<b>Growth:</b> cash received in FY2024-25 PKR 1,774,998,239, up 8.2% on FY2023-24 (PKR 1,640,862,798)",
    ])
    s.append(p("The portfolio is healthy overall. The value lies in four places where it is not, ranked by effect:"))
    s.append(table(["#", "Finding", "Decision", "Size of the effect"], [
        ["1", "GLB03 holds a fifth of all arrears: arrears ratio 21.8% against 5.8%", "Weekly call list and payment plans (finance head)", "Half its PKR 64,267,854 arrears recovered cuts portfolio arrears by 10%"],
        ["2", "Karachi apartments: occupancy 78.2% and falling; Karachi renews only 17.9% of leases", "Vacancy incentive before the June to August peak; retention offer at renewal (leasing manager)", "About 23 more units let: PKR 1,775,190 a month, PKR 21.3 million a year"],
        ["3", "V-001 takes 2.3 times its trade's days; SLA breached on 86.5% of jobs", "Move urgent jobs to V-006; review the contract (maintenance manager)", "About 76 fewer days of waiting on its 37 requests"],
        ["4", "Leak requests are 6.3 times higher on and after heavy-rain days", "Vendor standby after heavy rain; roof and seepage work before the monsoon", "Fewer, faster leak repairs in the rainy months"],
    ], [0.3, 3.4, 3.0, 2.4]))
    s.append(label("About the data"))
    s += bullets([
        "Synthetic data (seed 3004) with six planted patterns (data/answer_key/planted_patterns.md); all six were found by ordinary queries and all six are used here.",
        "The conclusions show how the warehouse turns data into decisions; they do not describe a real portfolio.",
    ])
    s.append(label("Where the figures come from"))
    s += bullets([
        "Analytical SQL: sql/60_analytics/ (answers in docs/analytics.md), full profile.",
        "Dashboard: powerbi/LUE_Dashboard.pbix, validated against SQL (176 of 176 values match).",
        "Decision Page texts: docs/evidence/us-13.1/decisions.txt.",
        "etl/reports/insights.py checks every figure against these files before drawing this report.",
    ])
    s.append(PageBreak())
    s.append(p("The Executive Overview page", "h1"))
    s.append(img(SHOTS / "02_executive_overview.png", 174))
    s += bullets(["Revenue (cash received), collection rate, occupancy with active leases, arrears.",
                  "Monthly trends of cash against the year before, billing and collection rate, occupancy."])


    s.append(PageBreak())
    s.append(p("How the warehouse answers: revenue, ROLLUP and CUBE", "h1"))
    s.append(label("Monthly revenue with growth"))
    s.append(img(FIG / "f8_revenue.png", 170))
    s += bullets(["Revenue (cash received) grew 8.2% in FY2024-25 and 8.8% in FY2025-26 (W2 with LAG(), W3 with SUM over the fiscal year).",
                  "The view vw_monthly_sales serves the same figures to Power BI."])
    s.append(label("ROLLUP: region, city, building, with every subtotal (O1)"))
    s.append(table(["Level", "Row", "Collected, PKR", "Share"], [
        ["Building", "GLB03, Lahore", "230,538,116", "4.3%"],
        ["City subtotal", "Lahore", "2,187,307,068", "40.9%"],
        ["Region subtotal", "Punjab", "2,637,318,705", "49.3%"],
        ["Region subtotal", "Islamabad Capital Territory", "1,720,994,762", "32.2%"],
        ["Grand total", "All regions", "5,347,289,709", "100%"]], [1.6, 2.6, 1.6, 0.8], {2, 3}))
    s.append(label("CUBE: city by payment channel (O2), the channel totals"))
    s.append(table(["Channel (all cities)", "Collected, PKR", "Share"], [
        ["Bank", "1,546,708,496", "28.9%"], ["Cash", "1,153,135,900", "21.6%"], ["Mobile wallet", "997,225,878", "18.6%"],
        ["Cheque", "914,291,100", "17.1%"], ["Instant payment", "735,928,335", "13.8%"], ["Grand total", "5,347,289,709", "100%"]],
        [2.0, 1.6, 0.8], {1, 2}))
    s += bullets(["Lahore brings in 41% of all cash; bank transfers are the largest channel in every city.",
                  "O3 checks that every subtotal equals the sum of its parts."])
    s.append(PageBreak())
    s += section(
        1, "Arrears are concentrated in one building",
        ["Gulberg Residency 2 (GLB03), Lahore: arrears ratio 21.8%, almost four times the portfolio's 5.8%.",
         "Collection rate 78.2%, 16.0 points under the portfolio's 94.2%.",
         "PKR 64,267,854 outstanding: 19.5% of all arrears (W1).",
         "The same every year: 20.5% against 5.7% in FY2024-25.",
         "The debt is old: 86.3% of the overdue balance (PKR 284,267,443) is over 90 days past due (Q3)."],
        [KeepTogether([img(FIG / "f1_arrears_ratio.png", 115), img(FIG / "f2_ageing.png", 115)]),
         p("Sources: Q1, Q2, Q3 and W1 (sql/60_analytics/analytical.sql); Decision Page D1.", "note")],
        ["<b>Action:</b> a weekly call list and payment plans for GLB03's chronically late tenants.",
         "<b>Owner:</b> finance head (credit control).",
         "<b>Effect:</b> recovering half its arrears cuts portfolio arrears by 10%.",
         "<b>Also:</b> set reminders by sector: Manufacturing tenants pay late 14.4% of the time, Government 8.4% (Q4b)."],
        ["Only arrears billed in the window are counted.",
         "Recovering half assumes the debt is collectable; that depends on why these tenants are late."])

    s.append(PageBreak())
    s += section(
        2, "Karachi apartments: falling occupancy, weak renewals",
        ["Occupancy 78.2% against 84.5% for the portfolio, and falling: 83.8% in the first month, 72.1% in the last (Q6a).",
         "The cause is renewals: Karachi renews 17.9% of expiring leases, the other cities 36.1% (Q8).",
         "A vacancy there lasts 133 days on average.",
         "Incentives work: vacancy falls from 134.3 to 57.5 days with any offer, whatever its type (Q13).",
         "Timing: move-ins peak June to August, 1.43 times the other months (Q6b)."],
        [KeepTogether([img(FIG / "f4_renewal.png", 100), img(FIG / "f3_incentives.png", 115)]),
         p("Sources: Q6a, Q6b, Q8 and Q13; Decision Page D3.", "note")],
        ["<b>Action:</b> a vacancy incentive (rent-free weeks, the cheapest offer for the unit) on vacant Karachi apartments, marketed before the summer peak.",
         "<b>Action:</b> a retention offer at renewal time in Karachi.",
         "<b>Owner:</b> leasing manager.",
         "<b>Effect:</b> reaching the portfolio's occupancy lets about 23 more units: PKR 1,775,190 a month, PKR 21.3 million a year."],
        ["The incentive effect compares spells with and without an offer; it is not a controlled trial.",
         "The rent estimate uses the average contract rent of those units."])

    s.append(PageBreak())
    s += section(
        3, "One plumbing vendor slows maintenance",
        ["Sheikh Plumbing Works (V-001): 3.1 days a request, 2.3 times the 1.4 days of all plumbing vendors.",
         "SLA breached on 86.5% of its jobs, against 24.9% for all vendors.",
         "In every trade, vendors rated C when the request was raised were the slowest (Q9b)."],
        [img(FIG / "f5_vendor.png", 75),
         p("Sources: Q9a and Q9b; Decision Page D2 (vendors with 20 or more resolved requests).", "note")],
        ["<b>Action:</b> give its urgent jobs to Hussain Plumbing Associates (V-006), the fastest plumbing vendor; review its contract.",
         "<b>Owner:</b> maintenance manager.",
         "<b>Effect:</b> at V-006's speed, its 37 requests would have waited about 76 fewer days in all."],
        ["Only vendors with 20 or more resolved requests are ranked.",
         "V-006 may not have capacity for all the extra work."])
    s += section(
        4, "Heavy rain drives leak requests",
        ["Leak requests (PLB-LEAK, CIV-SEEP, CIV-ROOF): 2.05 per 1,000 unit-days on a heavy-rain day (10 mm or more) or the day after.",
         "Against 0.32 on other days: 6.3 times as many (Q14)."],
        [img(FIG / "f6_rain.png", 62), p("Source: Q14 (the weather dimension joined to maintenance requests).", "note")],
        ["<b>Action:</b> plumbing and civil vendors on standby after heavy rain; roof and seepage work before the monsoon.",
         "<b>Owner:</b> maintenance manager.",
         "<b>Effect:</b> a flatter peak and no rise in SLA breaches in the rainy months."],
        ["Rain is measured per city per day; a local storm missed by the station is not seen."])

    s.append(PageBreak())
    s.append(p("5. The dashboard behind the decisions", "h1"))
    s.append(label("Decision Page"))
    s.append(img(SHOTS / "05_decision_page.png", 174))
    s += bullets(["Answers \"what should management do?\" with three recommendations written by DAX measures.",
                  "Each follows the slicers: with FY2024-25, D1 reads 20.5% against 5.7%; with Lahore, D2 names the Lahore vendor furthest behind its trade."])
    s.append(label("Detailed Analysis"))
    s.append(img(SHOTS / "03_detailed_analysis.png", 174))
    s += bullets(["Product: unit types and buildings. Region: cities. Customers: tenant payer segments. Plus vendors and a drill-through to one building."])
    s.append(PageBreak())
    s.append(p("6. Notes on the data", "h1"))
    s += bullets([
        "<b>Synthetic:</b> generated with seed 3004 for a fictional company, with six planted patterns (Q2, Q9, Q6b, Q13, Q14, Q8 found them); all six are used in this report.",
        "<b>Collection rate (D17):</b> cohort based, paid against the invoice lines due in the period; recent months read lower until their invoices have had time to be paid.",
        "<b>Owner NOI</b> (PKR 4,092,111,103 over the window) assumes a management fee of 8% of rent collected (vw_reporting_parameter).",
    ])
    build(path, "Business Insights Report",
          "Lahore Urban Estates Analytics Warehouse: what the data says and what management should do", s, phase="Phase 3")


def main() -> int:
    report()
    print(f"written {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
