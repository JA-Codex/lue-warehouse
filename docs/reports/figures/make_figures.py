#!/usr/bin/env python3
"""Draw the figures used by the Business Insights Report and the final presentation.

    python docs/reports/figures/make_figures.py      (needs matplotlib)

Every number below is copied from a recorded result, named beside it:
docs/analytics.md (full profile, seed 3004), docs/evidence/us-13.1/decisions.txt and
docs/evidence/us-12.2/summary.csv. The PNGs are written next to this script.
"""

# ruff: noqa: E501  (figure coordinates and labels: long lines read better)

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent
RED, SALMON, ORANGE, YELLOW, DARK, GREY = "#C2412D", "#EE7A73", "#E9913A", "#F2B33E", "#4B4B4B", "#B8B8B8"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#888888"})


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)


def bars(name, labels, values, colors, title, unit, fmt="{:.1f}", ref=None, ref_label=None, horizontal=False):
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    if horizontal:
        b = ax.barh(labels, values, color=colors)
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        for r, v in zip(b, values):
            ax.text(r.get_width() + max(values) * 0.01, r.get_y() + r.get_height() / 2, fmt.format(v),
                    va="center", fontsize=10)
        if ref is not None:
            ax.axvline(ref, color=DARK, ls="--", lw=1)
            ax.text(ref, -0.65, ref_label, fontsize=9, color=DARK)
    else:
        b = ax.bar(labels, values, color=colors)
        ax.set_ylabel(unit)
        for r, v in zip(b, values):
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + max(values) * 0.01, fmt.format(v),
                    ha="center", va="bottom", fontsize=10)
        if ref is not None:
            ax.axhline(ref, color=DARK, ls="--", lw=1)
            ax.text(len(values) - 0.5, ref * 1.04, ref_label, fontsize=9, color=DARK, ha="right")
    ax.set_title(title, fontsize=12, loc="left", color=DARK)
    _save(fig, name)


def figures():
    # Q2: arrears ratio by building, top three, against the portfolio (decisions.txt: 5.8%)
    bars("f1_arrears_ratio.png", ["GLB03 Lahore", "DGR01 Faisalabad", "FS701 Islamabad"], [21.8, 9.9, 9.5],
         [RED, SALMON, SALMON], "Arrears ratio, highest three buildings (Q2)", "percent of billed",
         "{:.1f}%", 5.8, "portfolio 5.8%")
    # Q3: overdue balance by ageing bucket (PKR million)
    bars("f2_ageing.png", ["0-30", "31-60", "61-90", "90+"], [20.77, 13.46, 10.86, 284.27],
         [YELLOW, ORANGE, SALMON, RED], "Overdue balance by days past due (Q3)", "PKR million", "{:,.1f}")
    # Q13: average vacancy days by incentive group
    bars("f3_incentives.png", ["No offer", "Any offer", "Discount", "Rent-free days", "Free maint."],
         [134.3, 57.5, 56.6, 57.8, 59.0], [GREY, RED, SALMON, ORANGE, YELLOW],
         "Average vacancy days, completed spells (Q13)", "days")
    # Q8: renewal rate, Karachi against the other cities
    bars("f4_renewal.png", ["Karachi", "Other cities"], [17.9, 36.1], [RED, GREY],
         "Leases renewed at expiry (Q8)", "percent of expiring leases", "{:.1f}%")
    # Q9 and D2: plumbing vendor days to resolve
    bars("f5_vendor.png", ["V-001 Sheikh Plumbing", "All plumbing vendors"], [3.1, 1.4], [RED, GREY],
         "Average days to resolve a plumbing request (Q9, D2)", "days", horizontal=True)
    # Q14: leak requests per 1,000 unit-days
    bars("f6_rain.png", ["Heavy rain or day after", "Other days"], [2.05, 0.32], [ORANGE, GREY],
         "Leak requests per 1,000 unit-days (Q14)", "requests", "{:.2f}")
    # E12 benchmark (docs/evidence/us-12.2/summary.csv), milliseconds
    q = ["B1", "B2", "B3", "B4", "B5", "B6"]
    before = [210.8, 22.1, 765.0, 61.9, 17.5, 1.23]
    after = [223.6, 4.05, 800.0, 70.0, 0.97, 0.56]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = range(len(q))
    ax.bar([i - 0.2 for i in x], before, 0.4, color=GREY, label="before")
    ax.bar([i + 0.2 for i in x], after, 0.4, color=RED, label="after")
    ax.set_yscale("log")
    ax.set_xticks(list(x), q)
    ax.set_ylabel("execution time, ms (log)")
    ax.legend(frameon=False)
    ax.set_title("EXPLAIN ANALYZE before and after the indexes (E12)", fontsize=12, loc="left", color=DARK)
    _save(fig, "f7_benchmark.png")


def revenue():
    # W2 (docs/evidence/us-11.1/01_analytics_output.txt): cash received by month, PKR million
    cash = [131.0, 139.7, 136.2, 134.4, 132.7, 135.8, 135.9, 138.0, 137.2, 135.0, 137.3, 147.7,
            150.1, 151.8, 149.9, 147.7, 141.9, 147.4, 139.2, 144.4, 149.0, 148.9, 150.7, 154.0,
            158.4, 160.7, 159.0, 161.6, 159.2, 158.0, 162.3, 157.8, 165.0, 161.4, 161.6, 166.5]
    fig, ax = plt.subplots(figsize=(7.6, 2.8))
    colors = [GREY] * 12 + [ORANGE] * 12 + [RED] * 12
    ax.bar(range(36), cash, color=colors)
    ax.set_ylim(100, 175)
    ax.set_xticks([0, 6, 12, 18, 24, 30, 35], ["Jul 23", "Jan 24", "Jul 24", "Jan 25", "Jul 25", "Jan 26", "Jun 26"])
    ax.set_ylabel("PKR million")
    for x, t in ((5.5, "FY2023-24  1,641M"), (17.5, "FY2024-25  1,775M  (+8.2%)"), (29.5, "FY2025-26  1,931M  (+8.8%)")):
        ax.text(x, 170, t, ha="center", fontsize=9, color=DARK)
    ax.set_title("Cash received by month (W2, vw_monthly_sales)", fontsize=12, loc="left", color=DARK)
    _save(fig, "f8_revenue.png")


def box(ax, x, y, w, h, text, fc, tc="white", fs=9.5, bold=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fc, ec="none"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tc, fontsize=fs,
            fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, label=None):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, color=DARK, lw=1.2))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, label, ha="center", fontsize=7.5, color=DARK)


def architecture():
    fig, ax = plt.subplots(figsize=(13.3, 6.2))
    ax.set_xlim(0, 13.3)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    # sources
    ax.text(0.95, 5.85, "SOURCES", ha="center", fontsize=9, color=DARK, fontweight="bold")
    src = ["S1 PMS (PostgreSQL)", "S2 Registers (Excel)", "S3 Settlements (CSV)", "S4 Tickets (JSON)",
           "S5 Weather (JSON)", "S6 Incentives (CSV)"]
    for i, s in enumerate(src):
        box(ax, 0.1, 5.1 - i * 0.82, 1.7, 0.62, s, "#F3F3F3", DARK, 8, False)
    # orchestration band
    box(ax, 2.2, 5.55, 10.9, 0.45, "ORCHESTRATION   python etl/run_pipeline.py  ·  one command, safe to rerun  ·  run log in lue_audit.etl_run_log",
        DARK, fs=8.5)
    # bronze
    box(ax, 2.3, 2.6, 1.6, 2.4, "BRONZE\nlue_staging.brz_*\n\nrows as sent,\nwith load id", "#8C8C8C", fs=8.5)
    for i in range(6):
        arrow(ax, 1.8, 5.41 - i * 0.82, 2.3, 3.8)
    # DQ
    box(ax, 4.3, 2.6, 1.6, 2.4, "DATA QUALITY\n109 rules\nDQ-01 to DQ-07\n\npass / warn /\nreject", YELLOW, DARK, 8.5)
    arrow(ax, 3.9, 3.8, 4.3, 3.8)
    box(ax, 4.3, 0.55, 1.6, 1.4, "QUARANTINE\nlue_audit\nrow + rule +\nreason", RED, fs=8)
    arrow(ax, 5.1, 2.6, 5.1, 1.95, "rejected")
    # silver
    box(ax, 6.3, 2.6, 1.6, 2.4, "SILVER\nlue_staging.stg_*\n\n20 clean,\ntyped tables", ORANGE, fs=8.5)
    arrow(ax, 5.9, 3.8, 6.3, 3.8)
    # SCD
    box(ax, 6.3, 0.55, 1.6, 1.4, "SCD\nType 1 + Type 2\ninferred members", SALMON, fs=8)
    arrow(ax, 7.1, 2.6, 7.1, 1.95)
    # DW
    box(ax, 8.3, 2.6, 2.1, 2.4, "WAREHOUSE  lue_dw\n\n13 dimensions\n6 fact tables\n(occupancy fact\npartitioned by month)", RED, fs=8.5)
    arrow(ax, 7.9, 3.8, 8.3, 3.8)
    arrow(ax, 7.9, 1.25, 8.6, 2.6)
    box(ax, 8.3, 0.55, 2.1, 1.4, "PERFORMANCE\nindexes, EXPLAIN\nANALYZE (E12)", "#8C8C8C", fs=8)
    # gold
    box(ax, 10.8, 3.85, 2.3, 1.15, "GOLD  lue_reporting\n4 monthly marts", ORANGE, fs=8.5)
    box(ax, 10.8, 2.6, 2.3, 1.05, "REPORTING VIEWS\nvw_monthly_sales, ...", YELLOW, DARK, 8)
    arrow(ax, 10.4, 4.2, 10.8, 4.4)
    arrow(ax, 10.4, 3.2, 10.8, 3.1)
    box(ax, 10.8, 1.25, 2.3, 1.1, "ANALYTICS + BI\nSQL Q1-Q14, OLAP,\nPower BI (3 pages)", DARK, fs=8)
    arrow(ax, 11.95, 2.6, 11.95, 2.35)
    box(ax, 10.8, 0.25, 2.3, 0.8, "AUDIT + LINEAGE\nrun log, reconciliation", "#8C8C8C", fs=7.5)
    _save(fig, "f0_architecture.png")


if __name__ == "__main__":
    figures()
    revenue()
    architecture()
    print("figures written to", OUT)
