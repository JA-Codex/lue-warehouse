#!/usr/bin/env python3
"""Owner portal checks that need no database (run by CI in make gen-test; also: make frontend-test).

    python scripts/test_frontend.py

frontend/data.js is the portal's data. These checks fail if it drifts from what the warehouse recorded:

  D1  data.js parses and holds the expected sections, 40 buildings and 36 months
  D2  every owner: NOI = rent - maintenance - fee, margin = NOI / rent, ranks run 1..n, units held
      (ownership register) equal the units Q12 reports
  D3  the 40 buildings add up to the portfolio: billed, arrears and maintenance cost against the
      recorded dashboard values (docs/evidence/us-13.1/expected_measures.csv)
  D4  the 36 monthly cash figures add up to the portfolio's Cash Received
  D5  the decision texts of the Decision Page are present
  H1  index.html has the five pages, loads data.js, and calls no host except Google Fonts
  L1  live mode, no database: the assembler turns database values and rows into the portal's JSON
  L2  live mode, no database: the local server serves /api/data, keeps the last good read, refuses writes
      and serves only index.html, data.js and /api/data
  L3  sql/50_reporting/02_owner_portal.sql is up to date with analytical.sql (scripts/export_portal_sql.py)
"""

# ruff: noqa: E501  (assertions and messages read better on one line)

import csv
import http.client
import http.server
import json
import re
import sys
import threading
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "frontend"
EVIDENCE = ROOT / "docs" / "evidence" / "us-13.1" / "expected_measures.csv"
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {text}")


def load_data() -> dict:
    raw = (FRONT / "data.js").read_text(encoding="utf-8")
    m = re.fullmatch(r"window\.LUE = (.*);\s*", raw, re.S)
    if not m:
        raise SystemExit("[FAIL] frontend/data.js is not 'window.LUE = {...};'")
    return json.loads(m.group(1))


def expected() -> dict[str, float]:
    with open(EVIDENCE, newline="", encoding="utf-8") as f:
        return {r["measure"]: float(r["Window"]) for r in csv.DictReader(f) if r["Window"]}


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def main() -> int:
    d = load_data()
    exp = expected()

    need = ["window", "owners", "buildings", "ageing", "late_payers", "move_in_season", "vacancy_by_type",
            "vendors", "incentives", "rain", "cash_by_month", "measures", "decisions"]
    check(all(k in d for k in need) and len(d["buildings"]) == 40 and len(d["cash_by_month"]) == 36 and d["owners"],
          f"D1  data.js has every section, {len(d['buildings'])} buildings, {len(d['cash_by_month'])} months, {len(d['owners'])} owners")

    bkeys = ["arrears_ratio", "renewal_rate", "sla_rate", "cost_per_unit_month", "billed", "arrears", "maint_cost"]
    check(all(b.get(k) is not None for b in d["buildings"].values() for k in bkeys),
          "D1  every building has arrears, renewal, SLA and maintenance-cost figures")
    check(all(b["city"] in {"Lahore", "Karachi", "Islamabad", "Faisalabad"} for b in d["buildings"].values()),
          "D1  every building's city is one of the four clean city names")

    bad_noi = [o["code"] for o in d["owners"] if not close(o["noi"], o["rent"] - o["maint"] - o["fee"], 0.02)]
    check(not bad_noi, "D2  NOI = rent - maintenance - fee for every owner" + (f": {bad_noi}" if bad_noi else ""))
    bad_fee = [o["code"] for o in d["owners"] if not close(o["fee"], 0.08 * o["rent"], 0.02)]
    check(not bad_fee, "D2  management fee = 8 percent of rent for every owner (decision A3 assumption)" + (f": {bad_fee}" if bad_fee else ""))
    bad_margin = [o["code"] for o in d["owners"] if not close(o["margin"], o["noi"] / o["rent"], 0.0001)]
    check(not bad_margin, "D2  NOI margin = NOI / rent for every owner" + (f": {bad_margin}" if bad_margin else ""))
    ranks = [o["rank"] for o in d["owners"]]
    check(ranks == sorted(ranks) and ranks[0] == 1 and len(set(ranks)) == len(ranks), "D2  owners are in NOI rank order, rank 1 first, no ties in the list")
    bad_units = [o["code"] for o in d["owners"] if sum(o["unit_mix"].values()) != o["units"] or not o["units_check"]]
    check(not bad_units, "D2  the units held in the ownership register equal the units Q12 reports" + (f": {bad_units}" if bad_units else ""))
    known = set(d["buildings"])
    check(all(b["code"] in known for o in d["owners"] for b in o["buildings"]), "D2  every building an owner holds is one of the 40 buildings")

    bl = d["buildings"].values()
    check(close(sum(b["billed"] for b in bl), exp["Billed"], 1), f"D3  buildings' billed sums to the dashboard's Billed ({exp['Billed']:,.0f})")
    check(close(sum(b["arrears"] for b in bl), exp["Arrears"], 1), f"D3  buildings' arrears sum to the dashboard's Arrears ({exp['Arrears']:,.0f})")
    check(close(sum(b["maint_cost"] for b in bl), exp["Maintenance Cost"], 1), f"D3  buildings' maintenance cost sums to the dashboard's Maintenance Cost ({exp['Maintenance Cost']:,.0f})")
    check(close(sum(b["resolved"] for b in bl), exp["Resolved Requests"], 0), f"D3  buildings' resolved requests sum to the dashboard's ({exp['Resolved Requests']:,.0f})")
    check(close(sum(b["sla_breaches"] for b in bl), exp["SLA Breaches"], 0), f"D3  buildings' SLA breaches sum to the dashboard's ({exp['SLA Breaches']:,.0f})")
    check(close(sum(b["arrears"] for b in bl) / sum(b["billed"] for b in bl), exp["Arrears Ratio"], 0.0001), "D3  portfolio arrears ratio equals the dashboard's Arrears Ratio")

    cash = sum(m["cash_received"] for m in d["cash_by_month"])
    check(close(cash, exp["Cash Received"], 1), f"D4  36 monthly cash figures sum to the dashboard's Cash Received ({exp['Cash Received']:,.0f})")

    dec = d["decisions"].get("Window", {})
    check(all(dec.get(k) for k in ("D1", "D2", "D3")), "D5  the three Decision Page texts are present")

    html = (FRONT / "index.html").read_text(encoding="utf-8")
    pages = ["portfolio", "collections", "leasing", "maintenance", "actions"]
    check(all(f'data-p="{p}"' in html and f"{p}()" in html for p in pages), "H1  index.html has the five pages: " + ", ".join(pages))
    check('<script src="data.js">' in html, "H1  index.html loads data.js")
    hosts = set(re.findall(r"https?://([^/\"'\s)]+)", html))
    check(hosts <= {"fonts.googleapis.com"}, f"H1  index.html calls no host except Google Fonts (found: {sorted(hosts)})")


    live_checks()
    print(f"\nRESULT: {sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


def live_checks() -> None:
    sys.path.insert(0, str(FRONT))
    sys.path.insert(0, str(ROOT / "scripts"))
    import export_portal_sql
    import portal_data
    import serve

    check(portal_data.plain(Decimal("12")) == 12 and isinstance(portal_data.plain(Decimal("12")), int)
          and portal_data.plain(Decimal("0.0589")) == 0.0589 and portal_data.plain(date(2026, 6, 30)) == "2026-06-30",
          "L1  database values (Decimal, date) become JSON numbers and text")

    def row(**k):
        return k

    T = {"Q2": [row(building_code="B1", billed=100, arrears=10, arrears_ratio=0.1, arrears_rank=1)],
         "Q8": [row(building_code="B1", leases_expired=5, renewed=1, renewal_rate=0.2, lost_at_renewal=4)],
         "Q10": [row(building_code="B1", resolved_requests=9, sla_breaches=3, sla_breach_rate=0.33)],
         "Q11": [row(building_code="B1", actual_cost=50, cost_per_unit_month=5, requests=7)],
         "Q12": [row(owner_code="OW-1", owner_name="A", owner_type="Individual", units_owned_at_end=3, rent_collected=100,
                     maintenance_cost=10, management_fee=8, noi=82, noi_margin=0.82, noi_rank=1),
                 row(owner_code="OW-2", owner_name="B", owner_type="Company", units_owned_at_end=0, rent_collected=0,
                     maintenance_cost=0, management_fee=0, noi=0, noi_margin=None, noi_rank=2)],
         "Q4a": [row(tenant_code=f"T{i}") for i in range(60)]}
    for k in ("Q3", "Q6b", "Q7", "Q9a", "Q13", "Q14", "W2"):
        T[k] = []
    bld = [row(building_code="B1", building_name=" Tower ", building_class="A", locality="Gulberg", city="lahore"),
           row(building_code="N/A", building_name="n/a", building_class="", locality="", city="")]
    hold = [row(owner_code="OW-1", building_code="B1", unit_type="Apartment", units=2),
            row(owner_code="OW-1", building_code="B1", unit_type="Shop", units=1)]
    d = portal_data.assemble(T, bld, hold, {}, {}, {"from": "a", "to": "b"},
                             series={"OW-1": {"m": ["2026-06"], "rent": [1], "noi": [1]}}, source="live")
    o1, o2 = d["owners"]
    check(list(d["buildings"]) == ["B1"] and d["buildings"]["B1"]["city"] == "Lahore" and d["buildings"]["B1"]["name"] == "Tower"
          and o1["unit_mix"] == {"Apartment": 2, "Shop": 1} and o1["units_check"] and "series" in o1
          and o2["margin"] == 0 and o2["units_check"] and "series" not in o2
          and len(d["late_payers"]) == portal_data.LATE_PAYERS_SHOWN and d["source"] == "live" and d["total_owners"] == 2,
          "L1  the assembler keeps in-scope buildings, cleans names, counts units, adds monthly series, caps late payers")

    calls = {"n": 0, "fail": False}

    def provider():
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("connection refused")
        return d

    def request(port, method, path):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(method, path)
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())

    def serve_on(cache):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(cache))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, srv.server_address[1]

    cache = serve.Cache(provider, ttl=60)
    srv, port = serve_on(cache)
    try:
        st, body, _ = request(port, "GET", "/api/data")
        again, _, _ = request(port, "GET", "/api/data")
        ok_data = st == 200 and json.loads(body)["owners"][0]["code"] == "OW-1" and again == 200 and calls["n"] == 1
        request(port, "GET", "/api/data?refresh=1")
        ok_refresh = calls["n"] == 2
        calls["fail"] = True
        st2, _, hdr = request(port, "GET", "/api/data?refresh=1")
        ok_stale = st2 == 200 and "connection refused" in hdr.get("X-Stale-Reason", "")
        ok_write = all(request(port, m, "/api/data")[0] == 405 for m in ("POST", "PUT", "DELETE"))
        ok_files = (request(port, "GET", "/")[0] == 200 and request(port, "GET", "/data.js")[0] == 200
                    and all(request(port, "GET", p)[0] == 404 for p in ("/build_data.py", "/live_data.py", "/../.env", "/%2e%2e/.env")))
    finally:
        srv.shutdown()
    check(ok_data and ok_refresh, "L2  /api/data returns the JSON, is cached for the ttl, and ?refresh=1 reads again")
    check(ok_stale, "L2  when the warehouse read fails the last good read is served with the reason in X-Stale-Reason")
    check(ok_write and ok_files, "L2  POST/PUT/DELETE give 405; only index.html, data.js and /api/data are served")
    first_fail = serve.Cache(provider, ttl=60)
    srv, port = serve_on(first_fail)
    try:
        st3, body3, _ = request(port, "GET", "/api/data")
    finally:
        srv.shutdown()
    srv, port = serve_on(None)
    try:
        st4 = request(port, "GET", "/api/data")[0]
    finally:
        srv.shutdown()
    check(st3 == 503 and "connection refused" in json.loads(body3)["error"] and st4 == 404,
          "L2  a failing first read answers 503 with the reason; snapshot mode (no --live) answers 404")

    check(export_portal_sql.TARGET.read_text(encoding="utf-8") == export_portal_sql.render(),
          "L3  02_owner_portal.sql equals what scripts/export_portal_sql.py generates from analytical.sql")


if __name__ == "__main__":
    sys.exit(main())
