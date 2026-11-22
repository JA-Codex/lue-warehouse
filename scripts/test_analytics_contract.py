#!/usr/bin/env python3
"""E11 checks that need no database (run by CI in make gen-test).

    python scripts/test_analytics_contract.py

The SQL pack (sql/60_analytics/analytical.sql and olap.sql, parsed with pglast): the 14 questions,
the window analytics and the OLAP queries are all there; each is headed by its question, grain,
tables and definition; every statement only reads; the definitions the plan asks to state are
stated beside their queries (D17, Q7's censoring, Q12's fee and charge type, Q13's comparison
group, Q14's rain threshold); ROLLUP, CUBE and GROUPING() and the window functions are used; and
docs/analytics.md answers every query.
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_analytics as ra  # noqa: E402
from pglast import ast, parse_sql  # noqa: E402

DOC = ROOT / "docs" / "analytics.md"
QUESTIONS = [f"Q{n}" for n in range(1, 15)]
WINDOWS = ["W1", "W2", "W3", "W4"]
OLAP = ["O1", "O2", "O3"]
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def main() -> int:
    print("=" * 70)
    print(" E11 contract tests: the analytical SQL pack (no database)")
    print("=" * 70)
    qs = {q.label: q for q in ra.all_queries()}
    by_q = {re.match(r"[QWO]\d+", k).group(0) for k in qs}

    print("The pack")
    check(set(QUESTIONS) <= by_q and set(WINDOWS) <= by_q and set(OLAP) <= by_q,
          f"all 14 questions (Q1 to Q14), the window analytics (W1 to W4) and the OLAP queries (O1 to O3): {len(qs)} queries"
          + (f": missing {sorted((set(QUESTIONS) | set(WINDOWS) | set(OLAP)) - by_q)}" if not (set(QUESTIONS) | set(WINDOWS) | set(OLAP)) <= by_q else ""))
    files = {q.file for k, q in qs.items() if k.startswith("O")}, {q.file for k, q in qs.items() if not k.startswith("O")}
    check(files == ({"olap.sql"}, {"analytical.sql"}), "the questions and window analytics are in analytical.sql, the OLAP queries in olap.sql (US-11.5)")
    headless = [k for k, q in qs.items() if not (q.title and all(q.header.get(h) for h in ("Grain", "Tables", "Definition")))]
    check(not headless, "every query is headed by its question, grain, tables used and definition" + (f": incomplete {headless}" if headless else ""))
    writes = [k for k, q in qs.items() for s in parse_sql(q.sql) if not isinstance(s.stmt, ast.SelectStmt)]
    check(not writes, "every statement is a SELECT: the pack only reads" + (f": {writes}" if writes else ""))
    tables = {k: set(re.findall(r"\b(?:lue_dw|lue_reporting)\.(\w+)", q.sql)) for k, q in qs.items()}
    named = [k for k, q in qs.items() if not all(t in q.header["Tables"] for t in tables[k] if not t.startswith("vw_reporting_"))]
    check(not named, "each header names the tables its query reads" + (f": not named in {named}" if named else ""))

    print("Definitions stated beside their queries")
    d = {k: q.header["Definition"] for k, q in qs.items()}
    check("D17" in d["Q1"] and "cohort" in d["Q1"].lower() and "Agrees with mart_collections_monthly and vw_monthly_collections" in d["Q1"],
          "Q1 uses the cohort collection rate (D17) and names what it agrees with")
    check("CENSORING RULE" in d["Q7"] and "first day" in d["Q7"] and "last day" in d["Q7"] and "s.first_day > w.window_start AND s.last_day < w.window_end" in qs["Q7"].sql,
          "Q7 states its censoring rule (completed spells only, not begun on the first day or open on the last) and applies it")
    check("FEE ASSUMPTION" in d["Q12"] and "8 percent" in d["Q12"] and "c.charge_code = 'RENT'" in qs["Q12"].sql,
          "Q12 filters on charge type RENT and states the fee assumption (8 percent of rent collected)")
    check("COMPARISON GROUP" in d["Q13"] and "'No offer'" in qs["Q13"].sql and "RAIN THRESHOLD" in d["Q14"] and "rainfall_mm >= 10.0" in qs["Q14"].sql,
          "Q13 states its comparison group (spells with no offer); Q14 its rain threshold (10.0 mm or more), as applied")
    check("15 days" in d["Q4a"] and "days_past_due > 15" in qs["Q4a"].sql and "12 months" in d["Q4a"] and "interval '12 months'" in qs["Q4a"].sql,
          "Q4 states its lateness threshold (more than 15 days) and period (12 months), as applied")

    print("OLAP and window functions")
    o1, o2 = qs["O1"].sql, qs["O2"].sql
    check("ROLLUP (region, city, building_code)" in o1 and "GROUPING(" in o1 and "CUBE (city, channel_group)" in o2 and "GROUPING(" in o2,
          "O1 is a ROLLUP over region, city and building; O2 a CUBE over city and channel group; both labelled with GROUPING()")
    check("differing" in qs["O3"].sql and "max_difference" in qs["O3"].sql, "O3 verifies the subtotals (differences counted and measured)")
    text = "\n".join(q.sql for q in qs.values())
    used = {f: bool(re.search(p, text)) for f, p in (("RANK", r"\brank\(\)"), ("DENSE_RANK", r"dense_rank\(\)"), ("LAG", r"\blag\("),
                                                   ("running total", r"sum\([^)]*\) OVER \(PARTITION BY [^)]*ORDER BY"),
                                                   ("3-month moving average", r"ROWS BETWEEN 2 PRECEDING AND CURRENT ROW"))}  # fmt: skip
    check(all(used.values()), "window analytics: " + ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in used.items()))

    print("Answers")
    doc = DOC.read_text(encoding="utf-8")
    missing = [k for k in qs if not re.search(rf"^### {k}\b", doc, re.M)]
    check(not missing, f"docs/analytics.md answers every query with its result and interpretation ({len(qs)})" + (f": missing {missing}" if missing else ""))
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
