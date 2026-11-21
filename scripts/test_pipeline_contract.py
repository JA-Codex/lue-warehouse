#!/usr/bin/env python3
"""US-8.3: offline contract tests for the pipeline — no database required.

    python scripts/test_pipeline_contract.py

Checks:
  1. run_pipeline.py exists and its syntax is valid (compile())
  2. All 11 step names are defined in the STEPS list in run_pipeline.py
  3. etl/pipeline/reconcile.py exists and defines reconcile() and ReconcileError
  4. --from-step, --only, --skip-generate, --profile, --seed are in argparse help
  5. logs/ directory is created by the pipeline (mkdir call in source)
  6. Step order: generate comes first, reports comes last

Exit 0 when all checks pass, 1 when any fails.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compile_ok(path: Path) -> bool:
    try:
        compile(_source(path), str(path), "exec")
        return True
    except SyntaxError:
        return False


def _steps_list(source: str) -> list[str]:
    """Extract the STEPS list literal from run_pipeline.py source (Assign or AnnAssign)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        # handle both  STEPS = [...]  and  STEPS: list[str] = [...]
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "STEPS":
                if isinstance(value, ast.List):
                    return [
                        elt.value
                        for elt in value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
    return []


def _defines(source: str, name: str) -> bool:
    """True if the source defines a function or class named `name` at module level."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return True
    return False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PIPELINE_PY = ROOT / "run_pipeline.py"
RECONCILE_PY = ROOT / "etl" / "pipeline" / "reconcile.py"

EXPECTED_STEPS = [
    "generate",
    "db-setup",
    "db-deploy",
    "db-load-ref",
    "db-load-src",
    "ingest",
    "validate",
    "stage",
    "dims",
    "facts",
    "reports",
]

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def main() -> int:
    sep = "=" * 68
    print(sep)
    print(" US-8.3 pipeline contract tests (no database)")
    print(sep)

    # 1. run_pipeline.py exists and syntax is valid
    exists = PIPELINE_PY.is_file()
    syntax_ok = _compile_ok(PIPELINE_PY) if exists else False
    check(exists and syntax_ok, "run_pipeline.py exists and its syntax is valid (compile())")

    pipeline_src = _source(PIPELINE_PY) if exists else ""

    # 2. All step names are in STEPS
    steps = _steps_list(pipeline_src)
    missing_steps = [s for s in EXPECTED_STEPS if s not in steps]
    extra_steps: list[str] = []
    check(
        not missing_steps and not extra_steps,
        f"All {len(EXPECTED_STEPS)} step names are defined in STEPS"
        + (f"; missing: {missing_steps}" if missing_steps else "")
        + (f"; unexpected: {extra_steps}" if extra_steps else ""),
    )

    # 3. reconcile.py exists and defines reconcile() and ReconcileError
    rec_exists = RECONCILE_PY.is_file()
    if rec_exists:
        rec_src = _source(RECONCILE_PY)
        has_fn = _defines(rec_src, "reconcile")
        has_err = _defines(rec_src, "ReconcileError")
    else:
        has_fn = has_err = False
    check(
        rec_exists and has_fn and has_err,
        "etl/pipeline/reconcile.py exists and defines reconcile() and ReconcileError"
        + ("" if rec_exists else " [file missing]")
        + ("" if has_fn else " [reconcile() missing]")
        + ("" if has_err else " [ReconcileError missing]"),
    )

    # 4. CLI flags present in argparse help
    flags = [
        "--from-step",
        "--only",
        "--skip-generate",
        "--profile",
        "--seed",
    ]
    missing_flags = [f for f in flags if f not in pipeline_src]
    check(
        not missing_flags,
        "CLI flags --from-step, --only, --skip-generate, --profile, --seed are all present"
        + (f"; missing: {missing_flags}" if missing_flags else ""),
    )

    # 5. logs/ directory is created by the pipeline (mkdir call)
    has_mkdir = "mkdir" in pipeline_src and "logs" in pipeline_src
    check(
        has_mkdir,
        "logs/ directory is created by the pipeline (mkdir + 'logs' found in source)",
    )

    # 6. Step order: generate first, reports last
    if steps:
        generate_first = steps[0] == "generate"
        reports_last = steps[-1] == "reports"
    else:
        generate_first = reports_last = False
    check(
        generate_first and reports_last,
        f"Step order: generate is first ({steps[0] if steps else '?'}), "
        f"reports is last ({steps[-1] if steps else '?'})",
    )

    print(sep)
    n_pass = sum(results)
    n_total = len(results)
    ok = n_pass == n_total
    print(f" {n_pass}/{n_total} pipeline contract checks passed" + ("" if ok else " — FAILED"))
    print(sep)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
