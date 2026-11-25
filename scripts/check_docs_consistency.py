#!/usr/bin/env python3
"""Offline documentation consistency audit.

Checks:
  C1  Every docs/stories/US-X.X.md file has a matching entry in docs/stories/README.md.
  C2  Every CREATE TABLE name in sql/10_ddl/ appears in at least one story doc.
  C3  Every Makefile target has a '## <description>' comment (make help convention).
  C4  Every evidence folder reference in a story doc has a matching folder in docs/evidence/.

Usage:
    python scripts/check_docs_consistency.py
    make consistency-check

Exit code: 0 when all checks pass, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES_DIR = ROOT / "docs" / "stories"
EVIDENCE_DIR = ROOT / "docs" / "evidence"
DDL_DIR = ROOT / "sql" / "10_ddl"
MAKEFILE = ROOT / "Makefile"


# ---------------------------------------------------------------------------
def _story_files() -> list[Path]:
    return sorted(p for p in STORIES_DIR.glob("US-*.md") if p.is_file())


def _story_log() -> str:
    readme = STORIES_DIR / "README.md"
    return readme.read_text(encoding="utf-8") if readme.exists() else ""


def check_c1_story_log(story_files: list[Path], log: str) -> tuple[int, int, list[str]]:
    """C1: every US-X.X.md appears in README.md."""
    failures: list[str] = []
    for sf in story_files:
        stem = sf.stem  # e.g. "US-13.2"
        if stem not in log:
            failures.append(f"  MISSING in story log: {stem}")
    return len(story_files) - len(failures), len(story_files), failures


_PARTITION_SUFFIX = re.compile(r"_\d{4}_\d{2}$")


def check_c2_ddl_tables(story_files: list[Path]) -> tuple[int, int, list[str]]:
    """C2: every CREATE TABLE name in sql/10_ddl/ appears in at least one story doc.

    Partition child tables (e.g. fact_unit_occupancy_daily_2023_07) are skipped;
    only the base table name (without the YYYY_MM suffix) is checked.
    """
    # Collect all table names from DDL
    table_names: list[str] = []
    for ddl in sorted(DDL_DIR.rglob("*.sql")):
        text = ddl.read_text(encoding="utf-8", errors="replace")
        pat = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+\.\w+|\w+)", re.IGNORECASE)
        for m in pat.finditer(text):
            name = m.group(1).lower()
            # Strip YYYY_MM partition suffix so partitions don't create false failures
            name = _PARTITION_SUFFIX.sub("", name)
            if name not in table_names:
                table_names.append(name)

    # Collect all story doc text
    all_story_text = " ".join(
        sf.read_text(encoding="utf-8", errors="replace").lower() for sf in story_files
    )

    failures: list[str] = []
    for tname in table_names:
        short = tname.split(".")[-1]  # strip schema prefix for matching
        if short not in all_story_text and tname not in all_story_text:
            failures.append(f"  NOT referenced in any story: {tname}")

    total = len(table_names)
    return total - len(failures), total, failures


def check_c3_makefile_comments() -> tuple[int, int, list[str]]:
    """C3: every Makefile target has a '## description' comment."""
    if not MAKEFILE.exists():
        return 0, 0, ["  Makefile not found"]
    text = MAKEFILE.read_text(encoding="utf-8")
    targets: list[str] = []
    failures: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^([a-z][a-z0-9_-]+):(.*)$", line)
        if m:
            tname = m.group(1)
            rest = m.group(2)
            if tname in ("PHONY",):
                continue
            targets.append(tname)
            if "##" not in rest:
                failures.append(f"  no ## comment: {tname}")
    return len(targets) - len(failures), len(targets), failures


def check_c4_evidence_folders(story_files: list[Path]) -> tuple[int, int, list[str]]:
    """C4: every ../evidence/us-X.X/ reference in a story doc has a matching folder."""
    failures: list[str] = []
    checked = 0
    for sf in story_files:
        text = sf.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\.\./evidence/(us-[\d.]+)/", text):
            ref = m.group(1)  # e.g. "us-13.2"
            checked += 1
            folder = EVIDENCE_DIR / ref
            if not folder.exists():
                failures.append(
                    f"  MISSING evidence folder: docs/evidence/{ref}/ (referenced in {sf.name})"
                )
    return checked - len(failures), checked, failures


# ---------------------------------------------------------------------------
def main() -> int:
    story_files = _story_files()
    log = _story_log()

    checks = [
        ("C1", "story log completeness", check_c1_story_log(story_files, log)),
        ("C2", "DDL table names", check_c2_ddl_tables(story_files)),
        ("C3", "Makefile target comments", check_c3_makefile_comments()),
        ("C4", "evidence folders", check_c4_evidence_folders(story_files)),
    ]

    overall_pass = 0
    overall_total = len(checks)
    all_ok = True

    for cid, label, (passed, total, failures) in checks:
        status = "✓" if not failures else "✗"
        print(f"Checking {cid}: {label} ...  {passed}/{total}  {status}")
        if failures:
            all_ok = False
            for f in failures:
                print(f)
        else:
            overall_pass += 1

    print(f"\n{overall_pass}/{overall_total} consistency checks passed")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
