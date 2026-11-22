#!/usr/bin/env python3
"""E13 checks that need no database (run by CI in make gen-test).

    python scripts/test_powerbi_contract.py

  US-13.1  docs/powerbi/model.json names only objects and columns that sql/50_reporting/01_reporting.sql
           creates; every relationship runs from a dimension to a fact, so every filter path has one step
           and none is ambiguous; docs/powerbi/measures.dax defines the plan's measures, each with a
           format, and refers only to tables, columns and measures that exist; the theme is valid
  US-13.5  scripts/powerbi_expected.py evaluates exactly the numeric measures of measures.dax;
           docs/powerbi/validation.dax is generated from the same list (up to date); the recorded
           expected values (docs/evidence/us-13.1) have every measure and selection; the build guide
           names every table, relationship and page
"""

# ruff: noqa: E501  (long assertions and messages read better on one line)

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import powerbi_expected as pe  # noqa: E402
import test_reporting_contract as rc  # noqa: E402

PBI = ROOT / "docs" / "powerbi"
EVIDENCE = ROOT / "docs" / "evidence" / "us-13.1"
PLAN_MEASURES = ["Billed", "Collected (Cohort)", "Collection Rate", "Cash Received", "Arrears Ratio", "Occupancy %",
                 "Active Leases", "Avg Days to Resolve", "SLA Breach %"]  # fmt: skip
FORMATS = {"PKR", "percent", "whole number", "decimal", "text"}
PAGES = ["Executive Overview", "Detailed Analysis", "Decision Page"]
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def code(dax: str) -> str:
    """DAX without comments and string literals."""
    dax = re.sub(r"//[^\n]*", "", dax)
    return re.sub(r'"[^"]*"', '""', dax)


def bodies(dax: str) -> dict[str, str]:
    """{measure: expression} for every MEASURE of the file."""
    parts = re.split(r"\bMEASURE\s+'_Measures'\[([^\]]+)\]\s*=", code(dax).split("EVALUATE")[0])
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def main() -> int:
    print("=" * 70)
    print(" E13 contract tests: the dashboard's model and measures (no database)")
    print("=" * 70)
    objs = rc.objects(rc.SQL.read_text(encoding="utf-8"))
    model = json.loads((PBI / "model.json").read_text(encoding="utf-8"))
    tables = model["tables"]

    print("US-13.1 The model")
    missing = sorted(t for t in tables if t not in objs)
    check(not missing and model["connection"]["user"] == "lue_reader" and model["connection"]["mode"] == "Import" and model["connection"]["schema"] == "lue_reporting",
          f"{len(tables)} tables, all in lue_reporting, loaded in Import mode as lue_reader" + (f": not in the reporting layer {missing}" if missing else ""))
    named = []
    for t, spec in tables.items():
        cols = set(objs.get(t, ("", [], None))[1])
        named += [(t, c) for c in spec.get("hidden", []) if c not in cols]
        named += [(t, c) for pair in spec.get("sort_by", {}).items() for c in pair if c not in cols]
        if spec.get("mark_as_date_table") and spec["mark_as_date_table"] not in cols:
            named.append((t, spec["mark_as_date_table"]))
    refs = [pe_ref.rstrip("]").split("[") for r in model["relationships"] for pe_ref in (r["from"], r["to"])]
    named += [(t, c) for t, c in refs if c not in set(objs.get(t, ("", [], None))[1]) or t not in tables]
    check(not named, "every hidden, sort-by, date-table and relationship column exists in its object" + (f": unknown {named}" if named else ""))
    ones = {r["from"].split("[")[0] for r in model["relationships"]}
    manys = {r["to"].split("[")[0] for r in model["relationships"]}
    pairs = [(r["from"].split("[")[0], r["to"].split("[")[0]) for r in model["relationships"]]
    dims = {t for t, s in tables.items() if s["role"] in ("dimension", "parameter")}
    check(not ones & manys and ones <= dims and manys <= set(tables) - dims and len(pairs) == len(set(pairs))
          and "Single" in model["relationship_defaults"]["cross_filter_direction"],
          f"{len(model['relationships'])} relationships, single direction, each from a dimension to a fact, none twice: no table is on both sides, so every filter path is one step and none is ambiguous")
    marked = [t for t, s in tables.items() if s.get("mark_as_date_table")]
    check(marked == ["vw_dim_date"] and "date_key > 0" in tables["vw_dim_date"]["filter"] and all("vw_dim_date[date_key]" == r["from"] for r in model["relationships"] if r["to"].endswith("[month_key]")),
          "one date table (vw_dim_date, marked on full_date, without the special rows), related to every month_key")

    print("US-13.1 The measures")
    dax = (PBI / "measures.dax").read_text(encoding="utf-8")
    fmts = pe.dax_measures(dax)
    body = bodies(dax)
    count = int(re.search(r'ROW \( "Measures defined", (\d+) \)', dax).group(1))
    check(list(fmts) == list(body) and len(body) == count and set(fmts.values()) <= FORMATS,
          f"measures.dax defines {len(body)} measures (as its EVALUATE line says), each with a format ({', '.join(sorted(FORMATS))})")
    check(all(m in body for m in PLAN_MEASURES), "the plan's measures are there: " + ", ".join(PLAN_MEASURES))
    cols = {t: set(objs[t][1]) for t in tables if t in objs}
    bad_cols, bad_measures, unbalanced = [], [], []
    for name, expr in body.items():
        for t, c in re.findall(r"\b([A-Za-z_]\w*)\[([^\]]+)\]", expr):
            if c not in cols.get(t, set()):
                bad_cols.append(f"{name}: {t}[{c}]")
        for m in re.findall(r"(?<![\w\]'])\[([^\]]+)\]", expr):
            if not m.startswith("@") and m not in body:
                bad_measures.append(f"{name}: [{m}]")
        if expr.count("(") != expr.count(")") or expr.count("{") != expr.count("}"):
            unbalanced.append(name)
    check(not bad_cols, "every Table[column] a measure uses is a column of a model table" + (f": {bad_cols}" if bad_cols else ""))
    check(not bad_measures and not unbalanced, "every [Measure] a measure uses is defined in the file, and every expression's brackets balance" + (f": {bad_measures} {unbalanced}" if bad_measures or unbalanced else ""))
    semi = [m for m in ("Arrears", "Active Leases", "Units", "Occupied Units", "Rent Roll") if "LastMonth = MAX" not in body[m]]
    ratios = [m for m in ("Collection Rate", "Arrears Ratio", "Occupancy %", "Avg Days to Resolve", "SLA Breach %", "Avg Vacancy Days") if "DIVIDE" not in body[m] or "AVERAGE" in body[m]]
    check(not semi and not ratios and "SAMEPERIODLASTYEAR" in body["Cash Received PY"],
          "month-end measures take the last month of the selection; every rate is DIVIDE of two sums (no AVERAGE); the prior year comes from SAMEPERIODLASTYEAR")
    texts = [m for m, f in fmts.items() if f == "text" and m.startswith("D") and m.endswith("Text")]
    words = all(all(w in dax.split(f"MEASURE '_Measures'[{m}]")[1].split("MEASURE '_Measures'")[0] for w in ("Action:", "Owner:", "Expected effect:", "FORMAT")) for m in texts)
    check(len(texts) == 3 and words, "three decision texts (D1 to D3), each built in DAX from the selection, with a figure, an action, an owner and an expected effect")
    theme = json.loads((PBI / "lue_theme.json").read_text(encoding="utf-8"))
    hexes = [theme.get(k) for k in ("background", "foreground", "tableAccent", "good", "bad", "neutral")] + theme.get("dataColors", [])
    check(theme.get("name") and len(theme.get("dataColors", [])) >= 6 and all(isinstance(h, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", h) for h in hexes),
          f"the theme (lue_theme.json) is valid JSON with a name, {len(theme.get('dataColors', []))} data colours and the sentiment colours")

    guide = (PBI / "README.md").read_text(encoding="utf-8")
    rows = {m.group(1): [x.strip() for x in m.group(2).split(",")] for m in re.finditer(r"^\| (PKR|percent|whole number|decimal|text) \|[^|]*\| ([^|]+) \|$", guide, re.M)}
    listed = {n: f for f, names in rows.items() for n in names}
    check(listed == fmts, f"the guide's format table (step 5) lists every measure once, under the format measures.dax gives it ({len(listed)})"
          + ("" if listed == fmts else f": differ {sorted(set(listed.items()) ^ set(fmts.items()))}"))

    print("US-13.5 Validation")
    engine = list(pe.Model({k: [] for k in pe.LOADS}).fn)
    check(engine == list(pe.numeric()), f"scripts/powerbi_expected.py evaluates exactly the {len(engine)} numeric measures of measures.dax, in order"
          + ("" if engine == list(pe.numeric()) else f": only in the script {sorted(set(engine) - set(pe.numeric()))}, only in the DAX {sorted(set(pe.numeric()) - set(engine))}"))
    current = pe.VALIDATION.read_text(encoding="utf-8") == pe.validation_dax()
    check(current and all(f"CALCULATE ( [Billed], {f} )" in pe.validation_dax() for f, _s in list(pe.SLICES.values())[1:]),
          f"docs/powerbi/validation.dax is generated from the same list and is up to date ({len(pe.numeric())} measures x {len(pe.SLICES)} selections, and the decision texts)")
    with (EVIDENCE / "expected_measures.csv").open(encoding="utf-8", newline="") as fh:
        rec = list(csv.DictReader(fh))
    check([r["measure"] for r in rec] == list(pe.numeric()) and all(s in rec[0] for s in pe.SLICES) and (EVIDENCE / "decisions.txt").is_file(),
          f"the recorded expected values (docs/evidence/us-13.1) have every measure and selection ({len(rec)} x {len(pe.SLICES)}) and the decision texts")
    absent = [t for t in tables if f"`{t}`" not in guide] + [r["from"] for r in model["relationships"] if f"`{r['from']}`" not in guide and r["from"] not in guide]
    absent += [p for p in PAGES if p not in guide]
    check(not absent and all(s in guide for s in ("lue_reader", "localhost:5432", "Import", "measures.dax", "validation.dax", "Mark as date table", "Drill through", "lue_theme.json")),
          "the build guide (docs/powerbi/README.md) names every table, relationship and the three pages, the connection, the measures, the validation and the theme" + (f": missing {absent}" if absent else ""))
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
