#!/usr/bin/env python3
"""E13 acceptance tests: the dashboard's model and measures on the loaded warehouse (US-13.1 to US-13.5).

    python scripts/test_powerbi.py

  US-13.1  lue_reader loads every table of docs/powerbi/model.json with no access error; every key a
           relationship uses is unique on its one side and found there from every row on its many side
           (no blank member: the placeholder buildings and unit types the model filters out are unused);
           the month-end values have every month, so the last-month pattern is right
  US-13.1  every numeric measure, as scripts/powerbi_expected.py evaluates it from the marts, equals a
           query written on the facts (day by day, not through the marts) for the whole window, the month
           2025-03, the fiscal year FY2024-25 and the city Lahore
  US-13.3  vw_tenant_by_building: one row per tenant version and building; it adds up to vw_tenant_analysis
           by tenant and to Q2's billed and arrears by building
  US-13.4  each decision text picks what the facts pick: the building with the highest arrears ratio (Q2's
           first), the vendor slowest against its own trade (20 or more resolved requests; Q9a's planted
           pattern on the full profile), the city and unit type with the lowest occupancy (10 or more units)
Nothing is changed; the test reads only.
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import powerbi_expected as pe  # noqa: E402
import run_analytics  # noqa: E402

from etl.ingest.base import IngestError, connect  # noqa: E402

MODEL = json.loads((ROOT / "docs" / "powerbi" / "model.json").read_text(encoding="utf-8"))
results: list[bool] = []
WINDOW = "(SELECT min(snapshot_date_key) AS a, max(snapshot_date_key) AS b FROM lue_dw.fact_unit_occupancy_daily)"
MONTH = "(to_char({d}, 'YYYYMM') || '01')::int"


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def same(a, b) -> bool:
    """Equal, blanks included; ratios to 9 places (Decimal division)."""
    if a is None or b is None:
        return a is None and b is None
    return abs(Decimal(a) - Decimal(b)) < Decimal("1e-9")


def split(ref: str) -> tuple[str, str]:
    table, col = ref.rstrip("]").split("[")
    return table, col


class Facts:
    """Each measure written on the facts for a selection (months, buildings): the second route."""

    def __init__(self, cur):
        self.cur = cur
        cur.execute(f"SELECT d0.full_date, d1.full_date FROM {WINDOW} w JOIN lue_dw.dim_date d0 ON d0.date_key = w.a JOIN lue_dw.dim_date d1 ON d1.date_key = w.b")
        self.start, self.end = cur.fetchone()
        cur.execute(f"SELECT DISTINCT {MONTH.format(d='full_date')} FROM lue_dw.dim_date WHERE full_date BETWEEN %s AND %s ORDER BY 1", (self.start, self.end))
        self.months = [r[0] for r in cur.fetchall()]

    def one(self, sql: str, months: list[int], buildings: list[str] | None, extra: dict | None = None):
        args = {"months": months, "b": buildings, "all_b": buildings is None, "end": self.end, **(extra or {})}
        self.cur.execute(sql, args)
        return self.cur.fetchone()[0]

    def month_end(self, months: list[int]):
        last = max(months)
        return min(self.end, scalar(self.cur, "SELECT (to_date(%s::text, 'YYYYMMDD') + interval '1 month' - interval '1 day')::date", (last,)))

    def values(self, months: list[int], buildings: list[str] | None) -> dict:
        B = "(%(all_b)s OR u.building_code = ANY(%(b)s))"
        line = f"FROM lue_dw.fact_rent_invoice_line l JOIN lue_dw.dim_unit u ON u.unit_key = l.unit_key JOIN lue_dw.dim_date d ON d.date_key = l.due_date_key WHERE l.due_date_key > 0 AND {B}"
        pay = (f"FROM lue_dw.fact_payment p JOIN lue_dw.dim_unit u ON u.unit_key = p.unit_key JOIN lue_dw.dim_date dd ON dd.date_key = p.due_date_key "
               f"JOIN lue_dw.dim_date pd ON pd.date_key = p.paid_date_key WHERE p.due_date_key > 0 AND p.paid_date_key > 0 AND {B}")
        occ = f"FROM lue_dw.fact_unit_occupancy_daily f JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key WHERE {B}"
        mnt = f"FROM lue_dw.fact_maintenance_request f JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_date d ON d.date_key = f.raised_date_key WHERE f.raised_date_key > 0 AND {B}"
        in_m = "{m} = ANY(%(months)s)"
        day = {"day": self.month_end(months)}
        v = {}
        v["Invoice Lines"] = self.one(f"SELECT count(*) {line} AND {in_m.format(m=MONTH.format(d='d.full_date'))}", months, buildings)
        v["Billed"] = self.one(f"SELECT coalesce(sum(l.net_amount), 0) {line} AND {in_m.format(m=MONTH.format(d='d.full_date'))}", months, buildings)
        v["Collected (Cohort)"] = self.one(f"SELECT coalesce(sum(p.payment_amount), 0) {pay} AND pd.full_date <= %(end)s AND {in_m.format(m=MONTH.format(d='dd.full_date'))}", months, buildings)
        v["Cash Received"] = self.one(f"SELECT coalesce(sum(p.payment_amount), 0) {pay} AND {in_m.format(m=MONTH.format(d='pd.full_date'))}", months, buildings)
        owed = self.one(f"SELECT sum(l.net_amount) {line} AND d.full_date + 1 <= %(day)s", months, buildings, day)
        paid = self.one(f"SELECT sum(p.payment_amount) {pay} AND greatest(dd.full_date + 1, pd.full_date) <= %(day)s", months, buildings, day)
        v["Arrears"] = (owed or 0) - (paid or 0)
        v["Unit Days"] = self.one(f"SELECT count(*) {occ} AND {in_m.format(m=MONTH.format(d='d.full_date'))}", months, buildings)
        v["Occupied Days"] = self.one(f"SELECT coalesce(sum(f.is_occupied), 0) {occ} AND {in_m.format(m=MONTH.format(d='d.full_date'))}", months, buildings)
        v["Active Leases"] = self.one(f"SELECT count(DISTINCT f.lease_key) FILTER (WHERE f.is_occupied = 1) {occ} AND {MONTH.format(d='d.full_date')} = %(last)s", months, buildings, {"last": max(months)})
        v["Units"] = self.one(f"SELECT count(*) {occ} AND d.full_date = %(day)s", months, buildings, day)
        v["Occupied Units"] = self.one(f"SELECT coalesce(sum(f.is_occupied), 0) {occ} AND d.full_date = %(day)s", months, buildings, day)
        v["Rent Roll"] = self.one(f"SELECT coalesce(sum(f.contract_rent), 0) {occ} AND d.full_date = %(day)s", months, buildings, day)
        unit_months = self.one(f"SELECT count(*) {occ} AND (d.full_date = least((date_trunc('month', d.full_date) + interval '1 month' - interval '1 day')::date, %(end)s)) AND {in_m.format(m=MONTH.format(d='d.full_date'))}", months, buildings)
        m = in_m.format(m=MONTH.format(d="d.full_date"))
        v["Requests"] = self.one(f"SELECT count(*) {mnt} AND {m}", months, buildings) or None
        v["Resolved Requests"] = self.one(f"SELECT count(f.days_to_resolve) {mnt} AND {m}", months, buildings) if v["Requests"] else None
        some = v["Requests"] is not None  # the maintenance mart has rows only where requests were raised
        days = self.one(f"SELECT coalesce(sum(f.days_to_resolve), 0) {mnt} AND {m}", months, buildings) if some else None
        v["SLA Breaches"] = self.one(f"SELECT coalesce(sum(f.sla_breached_flag), 0) {mnt} AND {m}", months, buildings) if some else None
        v["Maintenance Cost"] = self.one(f"SELECT coalesce(sum(f.actual_cost), 0) {mnt} AND {m}", months, buildings) if some else None
        v["Collection Rate"] = pe.div(v["Collected (Cohort)"], v["Billed"])
        v["Billed to Date"] = self.one(f"SELECT coalesce(sum(l.net_amount), 0) {line} AND d.full_date >= date_trunc('month', %(start)s::date) AND {MONTH.format(d='d.full_date')} <= %(last)s", months, buildings, {"start": self.start, "last": max(months)})
        v["Arrears Ratio"] = pe.div(v["Arrears"], v["Billed to Date"])
        v["Occupancy %"] = pe.div(v["Occupied Days"], v["Unit Days"])
        v["Avg Contract Rent"] = pe.div(v["Rent Roll"], v["Occupied Units"])
        v["Avg Days to Resolve"] = pe.div(days, v["Resolved Requests"])
        v["SLA Breach %"] = pe.div(v["SLA Breaches"], v["Resolved Requests"])
        v["Maintenance Cost per Unit-Month"] = pe.div(v["Maintenance Cost"], unit_months)
        shifted = [x - 10000 for x in months if x - 10000 >= self.months[0]]
        v["Cash Received PY"] = None if min(months) - 10000 < self.months[0] else self.one(f"SELECT coalesce(sum(p.payment_amount), 0) {pay} AND {in_m.format(m=MONTH.format(d='pd.full_date'))}", shifted, buildings)
        return v


def main() -> int:
    print("=" * 70)
    print(" E13 acceptance tests: the dashboard's model and measures (database)")
    print("=" * 70)
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    cur = wh.cursor()
    try:
        if not scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment"):
            print("  [FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
            return 1
        print("US-13.1 The model loads as lue_reader")
        try:
            reader = pe.connect_reader()
        except Exception as exc:  # noqa: BLE001
            check(False, f"lue_reader connects: {exc}")
            return 1
        refused = {}
        with reader.cursor() as rc:
            for t in MODEL["tables"]:
                try:
                    rc.execute(f"SELECT count(*) FROM lue_reporting.{t}")
                    rc.fetchone()
                except Exception as exc:  # noqa: BLE001
                    refused[t] = str(exc).strip().splitlines()[0]
                    reader.rollback()
            model = pe.Model.load(rc)
        reader.close()
        check(not refused, f"lue_reader reads all {len(MODEL['tables'])} tables of docs/powerbi/model.json (Import mode) with no access error" + (f": {refused}" if refused else ""))
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "powerbi_expected.py"), "--out", tmp], cwd=ROOT, capture_output=True, text=True)
            wrote = all((Path(tmp) / f).is_file() for f in ("expected_measures.csv", "decisions.txt"))
        check(done.returncode == 0 and wrote, "python scripts/powerbi_expected.py runs as lue_reader and writes expected_measures.csv and decisions.txt"
              + ("" if done.returncode == 0 else f": {done.stdout[-300:]} {done.stderr[-300:]}"))

        # every relationship: unique on the one side, found there from every row of the many side
        keep = {"vw_dim_date": "date_key > 0 AND full_date BETWEEN (SELECT window_start FROM lue_reporting.vw_reporting_window) AND (SELECT window_end FROM lue_reporting.vw_reporting_window)",
                "vw_dim_building": "building_code NOT IN ('N/A', 'Unknown')", "vw_dim_unit_type": "unit_type NOT IN ('Not applicable', 'Unknown')"}  # fmt: skip
        bad = {}
        for r in MODEL["relationships"]:
            (one, k1), (many, k2) = split(r["from"]), split(r["to"])
            where = keep.get(one, "true")
            dupes = scalar(cur, f"SELECT count(*) - count(DISTINCT {k1}) FROM lue_reporting.{one} WHERE {where}")
            orphans = scalar(cur, f"SELECT count(*) FROM lue_reporting.{many} m WHERE NOT EXISTS (SELECT 1 FROM (SELECT * FROM lue_reporting.{one} WHERE {where}) o WHERE o.{k1} = m.{k2})")
            if dupes or orphans:
                bad[f"{r['from']} -> {r['to']}"] = (dupes, orphans)
        check(not bad, f"all {len(MODEL['relationships'])} relationships are many-to-one: the key is unique on the one side (after the model's filters) and every many-side row finds it, so no visual shows a blank member" + (f": {bad}" if bad else ""))
        months = scalar(cur, "SELECT count(*) FROM lue_reporting.vw_dim_month")
        grid = scalar(cur, "SELECT count(*) FROM (SELECT building_code FROM lue_reporting.mart_collections_monthly GROUP BY 1 HAVING count(*) <> %s) x", (months,))
        short = scalar(cur, "SELECT count(*) FROM (SELECT building_code, unit_type FROM lue_reporting.mart_occupancy_monthly GROUP BY 1, 2 HAVING max(month_key) <> (SELECT max(month_key) FROM lue_reporting.vw_dim_month)) x")
        check(grid == 0 and short == 0, f"every building has all {months} months in the collections mart and every building and unit type reaches the last month in the occupancy mart, so a month-end measure at the last month adds every building")

        print("US-13.1 Every measure equals the facts")
        facts = Facts(cur)
        wanted = [n for n in pe.numeric() if n in ("Invoice Lines", "Billed", "Billed to Date", "Collected (Cohort)", "Collection Rate", "Cash Received", "Cash Received PY", "Arrears", "Arrears Ratio",
                                                   "Unit Days", "Occupied Days", "Occupancy %", "Active Leases", "Units", "Occupied Units", "Rent Roll", "Avg Contract Rent",
                                                   "Requests", "Resolved Requests", "Avg Days to Resolve", "SLA Breaches", "SLA Breach %", "Maintenance Cost", "Maintenance Cost per Unit-Month")]  # fmt: skip
        for s, (_f, sel) in pe.SLICES.items():
            ctx = model.ctx(sel)
            ms = sorted(ctx.months) if ctx.months is not None else facts.months
            bs = sorted(ctx.buildings) if ctx.buildings is not None else None
            direct = facts.values(ms, bs)
            wrong = {n: (model.value(n, ctx), direct[n]) for n in wanted if not same(model.value(n, ctx), direct[n])}
            check(not wrong, f"{s}: {len(wanted)} measures (collections, occupancy, maintenance) = the facts; billed {pe.shown(model.value('Billed', ctx), 'PKR')}, "
                  f"collection rate {pe.shown(model.value('Collection Rate', ctx), 'percent')}, arrears {pe.shown(model.value('Arrears', ctx), 'PKR')}, occupancy {pe.shown(model.value('Occupancy %', ctx), 'percent')}"
                  + (f": differ {wrong}" if wrong else ""))
        whole = model.ctx({})
        port = {n: model.value(n, model.ctx({"city": "Lahore"})) == model.value(n, whole) for n in pe.numeric() if n.endswith("(Portfolio)")}
        owners = all(same(model.value(n, model.ctx({"city": "Lahore"})), model.value(n, whole)) for n in ("Rent Collected", "NOI"))
        check(all(port.values()) and owners, "the portfolio measures ignore the city (REMOVEFILTERS on the building), and the owner measures are not filtered by building (no relationship)")

        print("US-13.3 The tenants by building")
        cur.execute("SELECT count(*), count(DISTINCT (tenant_key, building_code)) FROM lue_reporting.vw_tenant_by_building")
        n, distinct = cur.fetchone()
        cur.execute("""SELECT count(*) FROM (SELECT tenant_key, sum(total_collected) AS c, sum(current_arrears) AS a FROM lue_reporting.vw_tenant_by_building GROUP BY 1) b
                       FULL JOIN lue_reporting.vw_tenant_analysis t USING (tenant_key) WHERE b.c IS DISTINCT FROM t.total_collected OR b.a IS DISTINCT FROM t.current_arrears""")
        off = cur.fetchone()[0]
        q2 = next(q for q in run_analytics.all_queries() if q.label == "Q2")
        run_analytics.run(cur, q2)
        cur.execute("SELECT building_code, sum(billed_due), sum(current_arrears) FROM lue_reporting.vw_tenant_by_building GROUP BY 1")
        tb = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        col = {c: i for i, c in enumerate(q2.columns)}
        q2map = {r[col["building_code"]]: (r[col["billed"]] or 0, r[col["arrears"]] or 0) for r in q2.rows}
        check(n == distinct and n > 0 and off == 0 and not q2.error and q2map == {b: (Decimal(x or 0), Decimal(y or 0)) for b, (x, y) in tb.items()},
              f"one row per tenant version and building ({n:,}); by tenant it equals vw_tenant_analysis (collected, arrears); by building it equals Q2's billed and arrears ({len(q2map)} buildings)")

        print("US-13.4 The decision texts pick what the facts pick")
        d1 = model.d1(whole)
        ranked = sorted(q2.rows, key=lambda r: (r[col["arrears_rank"]], r[col["building_code"]]))
        check(d1["code"] == ranked[0][col["building_code"]] and same(round(d1["ratio"], 4), ranked[0][col["arrears_ratio"]]),
              f"D1: {d1['code']}, Q2's highest arrears ratio ({pe.fmt(d1['ratio'], '0.0%')} against the portfolio's {pe.fmt(model.value('Arrears Ratio (Portfolio)', whole), '0.0%')})")
        cur.execute("""WITH r AS (SELECT v.vendor_code, v.trade, f.days_to_resolve FROM lue_dw.fact_maintenance_request f JOIN lue_dw.dim_vendor v ON v.vendor_key = f.vendor_key WHERE f.raised_date_key > 0),
                       cur AS (SELECT vendor_code, trade FROM lue_dw.dim_vendor WHERE is_current),
                       trade AS (SELECT trade, sum(days_to_resolve) / count(days_to_resolve) AS days FROM r GROUP BY 1),
                       vendor AS (SELECT vendor_code, sum(days_to_resolve) / count(days_to_resolve) AS days FROM r GROUP BY 1 HAVING count(days_to_resolve) >= %s)
                       SELECT v.vendor_code, v.days / t.days AS gap FROM vendor v JOIN cur c USING (vendor_code) JOIN trade t ON t.trade = c.trade
                       WHERE v.vendor_code NOT IN ('N/A', 'Unknown') ORDER BY 2 DESC, 1 LIMIT 1""", (pe.MIN_RESOLVED,))
        top = cur.fetchone()
        d2 = model.d2(whole)
        check((top is None and d2["code"] is None) or (top is not None and d2["code"] == top[0] and same(d2["gap"], top[1])),
              f"D2: {d2['code']}, the vendor slowest against its own trade ({pe.fmt(d2['gap'], '0.00')} times its trade's days) of those with {pe.MIN_RESOLVED} or more resolved requests on the facts" if d2["code"]
              else f"D2: no vendor has {pe.MIN_RESOLVED} or more resolved requests on the facts of this profile, and the text says so")
        cur.execute(f"""SELECT u.unit_type || ' in ' || u.city, sum(f.is_occupied)::numeric / count(*) AS occ FROM lue_dw.fact_unit_occupancy_daily f JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
                        GROUP BY u.city, u.unit_type
                        HAVING count(*) FILTER (WHERE f.snapshot_date_key = (SELECT b FROM {WINDOW} w)) >= %s ORDER BY 2, u.city, u.unit_type LIMIT 1""", (pe.MIN_UNITS,))
        low = cur.fetchone()
        d3 = model.d3(whole)
        check(low is not None and d3["segment"] == low[0] and same(d3["occupancy"], low[1]),
              f"D3: {d3['segment']}, the lowest occupancy of the cities and unit types with {pe.MIN_UNITS} or more units on the facts ({pe.fmt(d3['occupancy'], '0.0%')})")
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
