"""Build frontend/data.js for the owner portal from the recorded full-profile warehouse outputs.

Sources (all produced by the pipeline, nothing typed by hand):
  docs/evidence/us-11.1/01_analytics_output.txt   Q1..Q14, W1..W4 results (psql output of sql/60_analytics)
  docs/evidence/us-13.1/{expected_measures.csv,decisions.txt}   dashboard measures, decision texts
  data/s1/buildings.csv, data/s2/registers.xlsx    building master, owner and ownership registers

Run:  python frontend/build_data.py      (stdlib + openpyxl)
Live version: replace this file with queries against lue_reporting as lue_reader (see frontend/README.md).
"""
import csv, json, re, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "docs/evidence/us-11.1/01_analytics_output.txt"
END = datetime(2026, 6, 30)


def num(s):
    s = s.strip()
    if s == "":
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() and "." not in s else f
    except ValueError:
        return s


def sections(text):
    out, cur = {}, None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("=" * 20) and i + 2 < len(lines) and lines[i + 2].startswith("=" * 20):
            label = lines[i + 1].split()[0]
            cur = out.setdefault(label, {"title": lines[i + 1], "lines": []})
            i += 3
            continue
        if cur is not None:
            cur["lines"].append(lines[i])
        i += 1
    return out


def table(lines):
    for j, l in enumerate(lines):
        if re.match(r"^-{3,}(\s+-{3,})*\s*$", l) and j > 0:
            head_line, dash = lines[j - 1], l
            spans = [m.span() for m in re.finditer(r"-+", dash)]
            cols = [head_line[a:b].strip() for a, b in spans]
            rows = []
            for r in lines[j + 1:]:
                if not r.strip():
                    break
                rows.append({c: num(r[a:b]) for c, (a, b) in zip(cols, spans)})
            return rows
    return []


def main():
    sec = sections(EV.read_text(encoding="utf-8"))
    T = {k: table(v["lines"]) for k, v in sec.items()}

    import openpyxl
    wb = openpyxl.load_workbook(ROOT / "data/s2/registers.xlsx", read_only=True)
    owners = {r[0]: {"name": r[1], "type": r[2]} for r in list(wb["owners"].iter_rows(values_only=True))[1:]}
    held = {}
    for b, u, o, vf, vt in list(wb["ownership"].iter_rows(values_only=True))[1:]:
        if vf <= END and (vt is None or vt > END):
            held.setdefault(o.strip().upper(), []).append((b.strip().upper(), u.strip().upper()))
    units = {}
    with open(ROOT / "data/s1/units.csv", newline="") as f:
        for r in csv.DictReader(f):
            units[(r["building_code"].strip().upper(), r["unit_no"].strip().upper())] = r
    bld = {}
    with open(ROOT / "data/s1/buildings.csv", newline="") as f:
        for r in csv.DictReader(f):
            bld[r["building_code"]] = r

    bld_rows = [{"building_code": c, "building_name": r["building_name"], "building_class": r["building_class"],
                 "locality": r["locality"], "city": r["city"]} for c, r in bld.items()]
    hold_rows = []
    for owner_code, items in held.items():
        counts = {}
        for bc, un in items:
            key = (bc, units[(bc, un)]["unit_type"].strip().title())  # raw source has dirty values; staging cleans them the same way
            counts[key] = counts.get(key, 0) + 1
        hold_rows += [{"owner_code": owner_code, "building_code": bc, "unit_type": ut, "units": n} for (bc, ut), n in counts.items()]

    measures = {}
    with open(ROOT / "docs/evidence/us-13.1/expected_measures.csv", newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            measures[r[0]] = r[1:]
    dec = {}
    cur = None
    for l in (ROOT / "docs/evidence/us-13.1/decisions.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\[(.+)\]$", l.strip())
        if m:
            cur = m.group(1); dec[cur] = {}
        m = re.match(r"^\s*(D\d): (.*)$", l)
        if m and cur:
            dec[cur][m.group(1)] = m.group(2)

    sys.path.insert(0, str(ROOT / "frontend"))
    from portal_data import assemble
    data = assemble(T, bld_rows, hold_rows, measures, dec,
                    {"from": "2023-07-01", "to": "2026-06-30", "profile": "full", "seed": 3004},
                    total_owners=900, source="snapshot")  # Q12 returns one row per owner (900); the evidence keeps the first 40
    bad = [o["code"] for o in data["owners"] if not o["units_check"]]
    if bad:
        print("WARNING: ownership register and Q12 unit counts differ for", bad, file=sys.stderr)
    out = ROOT / "frontend/data.js"
    out.write_text("window.LUE = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("wrote", out, {k: (len(v) if hasattr(v, "__len__") else v) for k, v in data.items()})


main()
