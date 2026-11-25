#!/usr/bin/env python3
"""Submission packaging manifest checker.

Walks every Phase 2 and Phase 3 deliverable and confirms the code deliverables
are present on disk.  Manual deliverables (PBIX, PPT) are listed but do not
cause a failure — they are built outside the repository toolchain.

Usage:
    python scripts/package_submission.py
    make package

Exit code: 0 when all code deliverables are present, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (description, relative_path_or_glob, is_manual)
DELIVERABLES: list[tuple[str, str, bool]] = [
    # ---- Phase 2 -------------------------------------------------------
    ("DDL SQL scripts",              "sql/10_ddl",                                False),
    ("DW dimension DDL",             "sql/10_ddl/01_dimensions.sql",              False),
    ("DW fact DDL",                  "sql/10_ddl/02_facts.sql",                   False),
    ("Staging SQL (exported)",       "sql/20_staging",                            False),
    ("Dimension load SQL",           "sql/30_dimensions",                         False),
    ("Fact load SQL",                "sql/40_facts",                              False),
    ("ETL ingest scripts",           "etl/ingest",                                False),
    ("ETL quality scripts",          "etl/quality",                               False),
    ("ETL staging scripts",          "etl/staging",                               False),
    ("ETL dimension scripts",        "etl/dimensions",                            False),
    ("ETL fact scripts",             "etl/facts",                                 False),
    ("Pipeline orchestrator",        "etl/run_pipeline.py",                       False),
    ("Data Cleaning Report PDF",     "docs/reports/LUE_Data_Cleaning_Report.pdf", False),
    ("Data Quality Report PDF",      "docs/reports/LUE_Data_Quality_Report.pdf",  False),
    # ---- Phase 3 -------------------------------------------------------
    ("Analytical SQL",               "sql/60_analytics/analytical.sql",           False),
    ("OLAP SQL",                     "sql/60_analytics/olap.sql",                 False),
    ("Reporting views SQL",          "sql/50_reporting/01_reporting.sql",         False),
    ("Indexing Report PDF",          "docs/reports/LUE_Indexing_Report.pdf",      False),
    ("Power BI dashboard PBIX",      "powerbi/LUE_Dashboard.pbix",                False),
    ("Dashboard screenshots PDF",    "powerbi/LUE_Dashboard.pdf",                 False),
    ("Business Insights Report PDF", "etl/reports/insights.py (PDF in the submission zip)", True),
    ("Final presentation PPT",       "submission zip: LUE_Final_Presentation.pptx", True),
    ("Dashboard screenshots PDF",    "submission zip: LUE_Dashboard_Screenshots.pdf", True),
    ("Presentation outline",         "docs/evidence/us-14.3/01_presentation_outline.md", False),
    ("Demo script",                  "docs/evidence/us-14.3/02_demo_script.md",   False),
]


def main() -> int:
    failures: list[str] = []
    manual: list[str] = []

    col = 42
    print(f"{'Deliverable':<{col}}  {'Path':<55}  Status")
    print("-" * (col + 60))

    for desc, rel, is_manual in DELIVERABLES:
        path = ROOT / rel
        exists = path.exists()
        if is_manual:
            status = "in the submission zip"
            manual.append(desc)
        elif exists:
            status = "✓"
        else:
            status = "MISSING"
            failures.append(f"  {desc}: {rel}")

        print(f"{desc:<{col}}  {rel:<55}  {status}")

    print()
    total = len(DELIVERABLES)
    code_total = total - len(manual)
    code_ok = code_total - len(failures)
    print(f"Code deliverables: {code_ok}/{code_total} present")
    print(f"In the submission zip: {len(manual)}")
    if failures:
        print("\nMissing code deliverables:")
        for f in failures:
            print(f)
        print("\nBuild the PDFs: etl/reports/build.py and etl/reports/insights.py")
        return 1

    print(f"\nAll {code_ok} code deliverables present. Ready for submission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
