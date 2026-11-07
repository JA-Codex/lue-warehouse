#!/usr/bin/env python3
"""Repository quality gates for US-0.3.

    python scripts/ci_checks.py            run every check
    python scripts/ci_checks.py --sql      parse every .sql file with pglast
    python scripts/ci_checks.py --manifest verify docs/phase1 against MANIFEST.sha256

Works the same on Windows, Linux and the CI runner, so `make` is not required.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIRS = ["sql", "docs/phase1/sql"]
FROZEN = ROOT / "docs" / "phase1"
MANIFEST = FROZEN / "MANIFEST.sha256"


def strip_psql_meta(text: str) -> str:
    """Blank out psql meta-commands (\\c, \\i, \\set ...). pglast parses SQL only.
    Lines are blanked, not removed, so error line numbers stay correct."""
    return "\n".join("" if line.lstrip().startswith("\\") else line for line in text.splitlines())


def check_sql(allow_missing: bool = False) -> int:
    try:
        from pglast import parse_sql
    except ImportError:
        if allow_missing:
            print("SKIP  pglast is not installed (pip install -r requirements-ci.txt)")
            return 0
        print("FAIL  pglast is not installed (pip install -r requirements-ci.txt)")
        return 1
    files = []
    for d in SQL_DIRS:
        base = ROOT / d
        if base.is_dir():
            files += sorted(base.rglob("*.sql"))
    failures = 0
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        try:
            parse_sql(strip_psql_meta(f.read_text(encoding="utf-8")))
        except Exception as exc:  # pglast raises ParseError; keep this version-proof
            failures += 1
            print(f"FAIL  {rel}: {exc}")
    print(f"sql: parsed {len(files)} file(s), {failures} failure(s)")
    return 1 if failures else 0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest() -> int:
    if not MANIFEST.is_file():
        print("FAIL  docs/phase1/MANIFEST.sha256 is missing")
        return 1
    listed = {}
    for n, line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        m = re.match(r"^([0-9a-f]{64}) [ *](.+)$", line)
        if not m:
            print(f"FAIL  MANIFEST.sha256 line {n} is not 'hash  path'")
            return 1
        listed[m.group(2).removeprefix("./")] = m.group(1)
    failures = 0
    for rel, expected in sorted(listed.items()):
        p = FROZEN / rel
        if not p.is_file():
            failures += 1
            print(f"FAIL  missing from docs/phase1: {rel}")
        elif sha256(p) != expected:
            failures += 1
            print(f"FAIL  changed since the freeze: {rel}")
    actual = {
        p.relative_to(FROZEN).as_posix() for p in FROZEN.rglob("*") if p.is_file()
    } - {"MANIFEST.sha256"}
    for rel in sorted(actual - set(listed)):
        failures += 1
        print(f"FAIL  not in the manifest (extra file): {rel}")
    print(f"manifest: {len(listed)} file(s) checked, {failures} problem(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--sql", action="store_true")
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument(
        "--allow-missing-pglast", action="store_true", help="local use only; CI must not skip"
    )
    a = ap.parse_args()
    run_all = not (a.sql or a.manifest)
    rc = 0
    if a.sql or run_all:
        rc |= check_sql(a.allow_missing_pglast)
    if a.manifest or run_all:
        rc |= check_manifest()
    print("RESULT:", "PASS" if rc == 0 else "FAIL")
    return rc


if __name__ == "__main__":
    sys.exit(main())
