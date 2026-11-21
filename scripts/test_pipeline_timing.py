"""US-8.4 offline timing contract test.

Verifies that run_pipeline.py has the timing infrastructure expected by US-8.4:
  1. run_pipeline.py exists and contains a timing mechanism
  2. logs/ directory creation is in run_pipeline.py
  3. A summary table is printed at the end of the run
  4. All 8 step names appear in run_pipeline.py

No database required.  Run from the repo root:
    python scripts/test_pipeline_timing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "run_pipeline.py"

STEP_NAMES = [
    "generate",
    "db-setup",
    "db-deploy",
    "db-load-ref",
    "db-load-source",
    "ingest",
    "validate",
    "stage",
    "dims",
    "facts",
    "reports",
]

# The 8 non-generate steps that must exist in run_pipeline.py
REQUIRED_STEPS = [
    "db-setup",
    "db-deploy",
    "db-load-ref",
    "db-load-source",
    "ingest",
    "validate",
    "stage",
    "dims",
    "facts",
    "reports",
]

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f": {detail}"
        print(msg)


# ------------------------------------------------------------------
# 1. run_pipeline.py exists
# ------------------------------------------------------------------
exists = PIPELINE.exists()
check("run_pipeline.py exists", exists)

if exists:
    source = PIPELINE.read_text(encoding="utf-8")
else:
    source = ""

# ------------------------------------------------------------------
# 2. Timing mechanism present (StepResult / time.monotonic / .seconds)
# ------------------------------------------------------------------
has_timing = (
    "time.monotonic" in source
    or "StepResult" in source
    or ".seconds" in source
    or "timedelta" in source
    or "elapsed" in source
)
check(
    "timing mechanism in run_pipeline.py",
    has_timing,
    "expected time.monotonic, StepResult, elapsed, or timedelta",
)

# ------------------------------------------------------------------
# 3. logs/ directory creation present
# ------------------------------------------------------------------
has_logs_mkdir = (
    'logs"' in source
    or '"logs"' in source
    or "logs/" in source
    or 'Path("logs")' in source
    or "mkdir" in source
) and "logs" in source
check(
    "logs/ directory creation in run_pipeline.py",
    has_logs_mkdir,
    "expected mkdir / logs reference",
)

# ------------------------------------------------------------------
# 4. Summary table / timing print section
# ------------------------------------------------------------------
has_summary = (
    "summary" in source.lower()
    or "─" in source
    or "─" in source
    or "table" in source.lower()
    or "duration" in source.lower()
    or "elapsed" in source.lower()
) and ("print" in source or "logger" in source)
check(
    "summary / timing table printed",
    has_summary,
    "expected print + summary/duration/elapsed keyword",
)

# ------------------------------------------------------------------
# 5. All 8 (non-generate) step names appear
# ------------------------------------------------------------------
for step in REQUIRED_STEPS:
    check(f'step "{step}" in run_pipeline.py', step in source)

# ------------------------------------------------------------------
# Result
# ------------------------------------------------------------------
total = passed + failed
print(f"\n{passed}/{total} timing contract checks passed")
sys.exit(0 if failed == 0 else 1)
