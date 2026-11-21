#!/usr/bin/env python3
"""Validate bronze (E4): python etl/quality/run.py [--compare] [--data data] [--rules file]

Runs the rule catalogue (etl/quality/rules.toml) on every bronze batch, as one step of a pipeline
run (lue_audit.etl_run_log, step validate_dq). Findings go to lue_audit.dq_result, rejected rows
also to lue_audit.quarantine. Prints the count per check and per rule.

--compare (US-4.4) then compares the findings with the answer key of the generated data
(<data>/answer_key/defects_answer_key.csv) and writes <data>/dq_validation.csv: planted defects
detected and missed, and false positives.

Exit code 0 when the validation ran (and, with --compare, every planted defect was detected with
no false positive), 1 otherwise, 2 when it could not start.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.ingest.base import IngestError, Run  # noqa: E402
from etl.quality import engine  # noqa: E402


def validate(rules_file: Path = engine.RULES_FILE, batches: list[int] | None = None,
             settings: dict | None = None, run: Run | None = None) -> tuple:  # fmt: skip
    """One run with one step; returns (run_id, step result, Summary or None). Inside a pipeline
    run (US-8.1) pass `run`: the step joins that run, which the caller closes."""
    rules = engine.load_rules(rules_file)
    r = run or Run(settings)
    box: dict = {}
    try:
        result = r.step("validate_dq", "bronze",
                        lambda step: box.setdefault("s", engine.validate(step, rules, batches)))
        return r.run_id, result, box.get("s") if result.status != "Failed" else None
    finally:
        if run is None:
            r.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="the generated data folder")
    ap.add_argument("--rules", type=Path, default=engine.RULES_FILE, help="the rule catalogue")
    ap.add_argument("--compare", action="store_true", help="compare with the answer key (US-4.4)")
    args = ap.parse_args(argv)
    try:
        run_id, result, summary = validate(args.rules)
    except (IngestError, engine.RuleError) as exc:
        print(f"[FAIL] {exc}")
        return 2
    print("=" * 78)
    print(f" Data quality run {run_id}: {result.status}")
    print("=" * 78)
    if summary is None:
        print(f"  [FAIL] {result.message}")
        return 1
    rules = {r.id: r for r in engine.load_rules(args.rules)}
    per_check = Counter()
    for rid, c in summary.by_rule.items():
        per_check[(rules[rid].check_name, rules[rid].severity)] += sum(c.values())
    print(f"  rows checked {summary.rows_checked:,}   rules {len(rules)}   rejected "
          f"{summary.rejected:,}   warnings {summary.warned:,}")  # fmt: skip
    for check in engine.CHECKS.values():
        print(f"  {check:22} rejected {per_check[(check, 'reject')]:>7,}   warnings "
              f"{per_check[(check, 'warn')]:>7,}")  # fmt: skip
    print(" Rules that found something")
    for rid, c in summary.by_rule.items():
        n = sum(c.values())
        if n:
            print(f"  {rid:12} {rules[rid].severity:6} {n:>7,}  {rules[rid].table}: "
                  f"{rules[rid].message}")  # fmt: skip
    code = 0
    if args.compare:
        key = args.data / "answer_key" / "defects_answer_key.csv"
        if not key.is_file():
            print(f"[FAIL] {key} not found: run python etl/generate_data.py first")
            return 2
        from etl.ingest.base import WAREHOUSE_DB, connect
        from etl.quality import answer_key

        conn = connect(WAREHOUSE_DB)
        try:
            with conn.cursor() as cur:
                cmp = answer_key.compare(cur, key, run_id)
        finally:
            conn.close()
        out = args.data / "dq_validation.csv"
        answer_key.write(cmp, out)
        print(" Answer key (US-4.4)")
        for row in cmp.rows:
            kind, source, table, defect, handling, rule, expected, detected, missed = row[:9]
            if kind == "false positive":
                print(f"  [FAIL] false positive: {rule} {handling} on {table}: {detected} "
                      f"({row[9]}) {row[10]}")  # fmt: skip
            elif kind == "planted":
                mark = "PASS" if missed == 0 else "FAIL"
                print(f"  [{mark}] {source} {table:20} {defect:31} {handling:6} {rule}: "
                      f"{detected}/{expected}" + (f"  {row[10]}" if row[10] else ""))
            else:
                print(f"  [ -- ] {source} {table:20} {defect:31} {handling:6} {rule}: "
                      f"{expected} (later stage)")  # fmt: skip
        print(f" Detected {cmp.detected:,} of {cmp.expected:,} planted defects in scope; "
              f"{cmp.false_positives} false positives. Written: {out}")  # fmt: skip
        code = 0 if cmp.ok else 1
    print("=" * 78)
    return code


if __name__ == "__main__":
    sys.exit(main())
