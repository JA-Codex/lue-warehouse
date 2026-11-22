#!/usr/bin/env python3
"""The value every dashboard measure must show, computed from the marts (US-13.1, US-13.5).

    python scripts/powerbi_expected.py              print the expected values and the decision texts
    python scripts/powerbi_expected.py --out DIR    also write DIR/expected_measures.csv and DIR/decisions.txt
    python scripts/powerbi_expected.py --dax        write docs/powerbi/validation.dax from the same list
    python scripts/powerbi_expected.py --check      exit 1 if docs/powerbi/validation.dax is out of date

It connects as lue_reader, the dashboard's role, and reads the same lue_reporting objects as Power BI
(docs/powerbi/model.json), then evaluates each measure of docs/powerbi/measures.dax the way the DAX does
it: a ratio of sums; a month-end value at the last month in the selection; the portfolio measures without
the building, unit type, vendor and category filters; the three decision texts picked and worded by the
same rules. Four selections: the whole window, the month 2025-03, the fiscal year FY2024-25 and the city
Lahore. In Power BI, docs/powerbi/validation.dax shows the same table; each value must match.
scripts/test_powerbi.py checks these values against queries written on the facts.
"""

# ruff: noqa: E501  (messages and DAX text: long lines read better)

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.ingest.base import settings  # noqa: E402

DAX = ROOT / "docs" / "powerbi" / "measures.dax"
VALIDATION = ROOT / "docs" / "powerbi" / "validation.dax"
SLICES = {  # name: (DAX filter, the selection)
    "Window": ("", {}),
    "Month 2025-03": ('vw_dim_date[year_month] = "2025-03"', {"year_month": "2025-03"}),
    "FY2024-25": ('vw_dim_date[fiscal_year_label] = "FY2024-25"', {"fiscal_year_label": "FY2024-25"}),
    "Lahore": ('vw_dim_building[city] = "Lahore"', {"city": "Lahore"}),
}
PLACEHOLDER_BUILDINGS = {"N/A", "Unknown"}  # filtered out in Power Query (model.json)
PLACEHOLDER_UNIT_TYPES = {"Not applicable", "Unknown"}
MIN_RESOLVED, MIN_UNITS = 20, 10  # the decision rules' floors (measures.dax: D2 Vendor, D3 Segment)
LOADS = {
    "months": "SELECT month_key, year_month, fiscal_year_label FROM lue_reporting.vw_dim_month ORDER BY month_key",
    "buildings": "SELECT building_code, building_name, city FROM lue_reporting.vw_dim_building",
    "unit_types": "SELECT unit_type FROM lue_reporting.vw_dim_unit_type",
    "vendors": "SELECT vendor_key, vendor_code, vendor_name, trade, is_current FROM lue_reporting.vw_dim_vendor",
    "C": "SELECT month_key, building_code, invoice_lines, billed_due, collected_cohort, cash_received, arrears_month_end FROM lue_reporting.mart_collections_monthly",
    "O": "SELECT month_key, building_code, unit_type, unit_days, occupied_days, vacant_days, completed_vacancy_spells, active_leases, units_month_end, occupied_units_month_end, rent_roll_month_end FROM lue_reporting.mart_occupancy_monthly",
    "M": "SELECT month_key, building_code, unit_type, vendor_key, requests, resolved_requests, days_to_resolve_sum, sla_breached, actual_cost FROM lue_reporting.mart_maintenance_monthly",
    "OW": "SELECT month_key, rent_collected, management_fee, noi FROM lue_reporting.mart_owner_portfolio_monthly",
    "TB": "SELECT tenant_code, building_code, payer_segment, billed_due, total_collected, current_arrears, payments, late_payments FROM lue_reporting.vw_tenant_by_building",
}


def dax_measures(text: str | None = None) -> dict[str, str]:
    """{measure: format} in the order of docs/powerbi/measures.dax (the format is on the comment above it)."""
    text = DAX.read_text(encoding="utf-8") if text is None else text
    out = {}
    for fmt, name in re.findall(r"// format: (\w[\w ]*?)[.\n](?:.*\n)*?\s*MEASURE '_Measures'\[([^\]]+)\]", text):
        out[name] = fmt.strip()
    return out


@dataclass(frozen=True)
class Ctx:
    """A filter context: None means not filtered."""

    months: frozenset | None = None
    buildings: frozenset | None = None
    unit_types: frozenset | None = None
    vendors: frozenset | None = None  # vendor keys

    def keep(self, r: dict) -> bool:
        return ((self.months is None or "month_key" not in r or r["month_key"] in self.months)
                and (self.buildings is None or "building_code" not in r or r["building_code"] in self.buildings)
                and (self.unit_types is None or "unit_type" not in r or r["unit_type"] in self.unit_types)
                and (self.vendors is None or "vendor_key" not in r or r["vendor_key"] in self.vendors))  # fmt: skip


def div(a, b):
    """DAX DIVIDE: blank when either part is blank or the divisor is zero."""
    return None if a is None or b is None or b == 0 else Decimal(a) / Decimal(b)


class Model:
    """The marts as Power BI loads them, and the measures evaluated on them."""

    def __init__(self, data: dict[str, list[dict]]):
        self.d = data
        self.d["buildings"] = [b for b in data["buildings"] if b["building_code"] not in PLACEHOLDER_BUILDINGS]
        self.d["unit_types"] = [u for u in data["unit_types"] if u["unit_type"] not in PLACEHOLDER_UNIT_TYPES]
        self.universe = [m["month_key"] for m in data["months"]]
        self.fn = self.measures()

    @classmethod
    def load(cls, cur) -> Model:
        data = {}
        for name, sql in LOADS.items():
            cur.execute(sql)
            cols = [c[0] for c in cur.description]
            data[name] = [dict(zip(cols, r)) for r in cur.fetchall()]
        return cls(data)

    # ------------------------------------------------------------------ selections
    def ctx(self, selection: dict) -> Ctx:
        months = None
        for col in ("year_month", "fiscal_year_label"):
            if col in selection:
                months = frozenset(m["month_key"] for m in self.d["months"] if m[col] == selection[col])
        buildings = None
        if "city" in selection:
            buildings = frozenset(b["building_code"] for b in self.d["buildings"] if b["city"] == selection["city"])
        return Ctx(months=months, buildings=buildings)

    def rows(self, table: str, ctx: Ctx) -> list[dict]:
        return [r for r in self.d[table] if ctx.keep(r)]

    def total(self, table: str, col: str, ctx: Ctx):
        """DAX SUM: blank over no rows."""
        r = self.rows(table, ctx)
        return sum((x[col] for x in r), Decimal(0)) if r else None

    def last(self, table: str, col: str, ctx: Ctx):
        """The semi-additive pattern: the sum at the last month in the selection."""
        r = self.rows(table, ctx)
        if not r:
            return None
        month = max(x["month_key"] for x in r)
        return sum((x[col] for x in r if x["month_key"] == month), Decimal(0))

    def count_codes(self, ctx: Ctx, segment: str | None = None):
        codes = {r["tenant_code"] for r in self.rows("TB", ctx) if segment is None or r["payer_segment"] == segment}
        return len(codes) or None

    def billed_to_date(self, ctx: Ctx):
        """Billed from the window start to the last month in the selection (the date filter removed)."""
        r = self.rows("C", ctx)
        if not r:
            return None
        month = max(x["month_key"] for x in r)
        return self.total("C", "billed_due", replace(ctx, months=frozenset(m for m in self.universe if m <= month)))

    def py_cash(self, ctx: Ctx):
        months = sorted(ctx.months if ctx.months is not None else self.universe)
        if not months or months[0] - 10000 < self.universe[0]:  # EDATE(first day, -12) before the data
            return None
        shifted = frozenset(m - 10000 for m in months) & frozenset(self.universe)
        return self.total("C", "cash_received", replace(ctx, months=shifted))

    def measures(self) -> dict:
        t, last = self.total, self.last
        everywhere = {"buildings": None, "unit_types": None, "vendors": None}
        m = {
            "Invoice Lines": lambda c: t("C", "invoice_lines", c),
            "Billed": lambda c: t("C", "billed_due", c),
            "Collected (Cohort)": lambda c: t("C", "collected_cohort", c),
            "Collection Rate": lambda c: div(t("C", "collected_cohort", c), t("C", "billed_due", c)),
            "Cash Received": lambda c: t("C", "cash_received", c),
            "Cash Received PY": self.py_cash,
            "Cash Received YoY %": lambda c: None if self.py_cash(c) is None else div(t("C", "cash_received", c) - self.py_cash(c), self.py_cash(c)),
            "Arrears": lambda c: last("C", "arrears_month_end", c),
            "Billed to Date": self.billed_to_date,
            "Arrears Ratio": lambda c: div(last("C", "arrears_month_end", c), self.billed_to_date(c)),
            "Unit Days": lambda c: t("O", "unit_days", c),
            "Occupied Days": lambda c: t("O", "occupied_days", c),
            "Occupancy %": lambda c: div(t("O", "occupied_days", c), t("O", "unit_days", c)),
            "Avg Vacancy Days": lambda c: div(t("O", "vacant_days", c), t("O", "completed_vacancy_spells", c)),
            "Active Leases": lambda c: last("O", "active_leases", c),
            "Units": lambda c: last("O", "units_month_end", c),
            "Occupied Units": lambda c: last("O", "occupied_units_month_end", c),
            "Rent Roll": lambda c: last("O", "rent_roll_month_end", c),
            "Avg Contract Rent": lambda c: div(last("O", "rent_roll_month_end", c), last("O", "occupied_units_month_end", c)),
            "Requests": lambda c: t("M", "requests", c),
            "Resolved Requests": lambda c: t("M", "resolved_requests", c),
            "Avg Days to Resolve": lambda c: div(t("M", "days_to_resolve_sum", c), t("M", "resolved_requests", c)),
            "SLA Breaches": lambda c: t("M", "sla_breached", c),
            "SLA Breach %": lambda c: div(t("M", "sla_breached", c), t("M", "resolved_requests", c)),
            "Maintenance Cost": lambda c: t("M", "actual_cost", c),
            "Maintenance Cost per Unit-Month": lambda c: div(t("M", "actual_cost", c), t("O", "units_month_end", c)),
            "Rent Collected": lambda c: t("OW", "rent_collected", c),
            "Management Fee": lambda c: t("OW", "management_fee", c),
            "NOI": lambda c: t("OW", "noi", c),
            "Tenants": lambda c: self.count_codes(c),
            "Chronically Late Tenants": lambda c: self.count_codes(c, "Chronically late"),
            "Tenant Billed": lambda c: t("TB", "billed_due", c),
            "Tenant Collected": lambda c: t("TB", "total_collected", c),
            "Tenant Arrears": lambda c: t("TB", "current_arrears", c),
            "Tenant Arrears Ratio": lambda c: div(t("TB", "current_arrears", c), t("TB", "billed_due", c)),
            "Late Payment Share": lambda c: div(t("TB", "late_payments", c), t("TB", "payments", c)),
        }
        m["Collection Rate (Portfolio)"] = lambda c: m["Collection Rate"](replace(c, buildings=None))
        m["Arrears (Portfolio)"] = lambda c: m["Arrears"](replace(c, buildings=None))
        m["Arrears Ratio (Portfolio)"] = lambda c: m["Arrears Ratio"](replace(c, buildings=None))
        m["Occupancy % (Portfolio)"] = lambda c: m["Occupancy %"](replace(c, buildings=None, unit_types=None))
        m["Avg Days to Resolve (Portfolio)"] = lambda c: m["Avg Days to Resolve"](replace(c, **everywhere))
        m["SLA Breach % (Portfolio)"] = lambda c: m["SLA Breach %"](replace(c, **everywhere))
        m["Trade Avg Days to Resolve"] = self.trade_days
        m["Days vs Trade"] = lambda c: div(m["Avg Days to Resolve"](c), self.trade_days(c))
        return m

    def trade_days(self, ctx: Ctx):
        """For one vendor (SELECTEDVALUE of its code): the average days of every vendor of its current trade."""
        if ctx.vendors is None:
            return None
        codes = {v["vendor_code"] for v in self.d["vendors"] if v["vendor_key"] in ctx.vendors}
        if len(codes) != 1:
            return None
        trade = self.current(codes.pop(), "trade")
        keys = frozenset(v["vendor_key"] for v in self.d["vendors"] if v["trade"] == trade)
        return self.value("Avg Days to Resolve", replace(ctx, vendors=keys))

    def value(self, name: str, ctx: Ctx):
        return self.fn[name](ctx)

    # ------------------------------------------------------------------ the decision page (US-13.4)
    def d1(self, ctx: Ctx) -> dict:
        codes = [b["building_code"] for b in self.d["buildings"] if ctx.buildings is None or b["building_code"] in ctx.buildings]
        scored = [(self.value("Arrears Ratio", replace(ctx, buildings=frozenset([c]))), c) for c in codes]
        scored = [(r, c) for r, c in scored if r is not None]
        if not scored:
            return {"code": None, "text": "No building has billing in this selection."}
        ratio, code = min(scored, key=lambda x: (-x[0], x[1]))
        one = replace(ctx, buildings=frozenset([code]))
        name = next(b["building_name"] for b in self.d["buildings"] if b["building_code"] == code)
        rate, owed = self.value("Collection Rate", one), self.value("Arrears", one)
        port_rate = self.value("Collection Rate (Portfolio)", ctx)
        gap = (port_rate - rate) * 100
        text = (f"Concentrate arrears follow-up on {name} ({code}). Its arrears ratio is {fmt(ratio, '0.0%')} against "
                f"{fmt(self.value('Arrears Ratio (Portfolio)', ctx), '0.0%')} for the portfolio, and its collection rate of {fmt(rate, '0.0%')}"
                + (f" trails the portfolio's {fmt(port_rate, '0.0%')} by {fmt(gap, '0.0')} points." if gap > 0 else f" is level with or above the portfolio's {fmt(port_rate, '0.0%')}.")
                + " Action: a weekly call list and payment plans for its chronically late tenants."
                + f" Owner: finance head (credit control). Expected effect: recovering half of its PKR {fmt(owed, '#,0')} arrears cuts portfolio arrears by "
                + f"{fmt(div(owed / 2, self.value('Arrears (Portfolio)', ctx)), '0%')}.")
        return {"code": code, "ratio": ratio, "rate": rate, "portfolio_rate": port_rate, "arrears": owed, "text": text}

    def vendor_scores(self, ctx: Ctx, codes) -> list[tuple]:
        out = []
        for code in codes:
            keys = frozenset(v["vendor_key"] for v in self.d["vendors"] if v["vendor_code"] == code)
            one = replace(ctx, vendors=keys if ctx.vendors is None else keys & ctx.vendors)
            n = self.value("Resolved Requests", one)
            if n is not None and n >= MIN_RESOLVED:
                out.append((self.value("Avg Days to Resolve", one), code, one, self.value("Days vs Trade", one)))
        return out

    def current(self, code: str, col: str):
        return next(v[col] for v in self.d["vendors"] if v["vendor_code"] == code and v["is_current"])

    def d2(self, ctx: Ctx) -> dict:
        codes = sorted({v["vendor_code"] for v in self.d["vendors"] if ctx.vendors is None or v["vendor_key"] in ctx.vendors} - {"Unknown", "N/A"})
        scored = self.vendor_scores(ctx, codes)
        if not scored:
            return {"code": None, "text": f"No vendor has {MIN_RESOLVED} or more resolved requests in this selection."}
        days, code, one, gap = min(scored, key=lambda x: (-x[3], x[1]))
        trade_days = self.trade_days(one)
        name, trade = self.current(code, "vendor_name"), self.current(code, "trade")
        breach, resolved = self.value("SLA Breach %", one), self.value("Resolved Requests", one)
        port_breach = self.value("SLA Breach % (Portfolio)", ctx)
        peers = sorted({v["vendor_code"] for v in self.d["vendors"] if v["trade"] == trade and (ctx.vendors is None or v["vendor_key"] in ctx.vendors)} - {code})
        scored_peers = self.vendor_scores(ctx, peers)
        best = min(scored_peers, key=lambda x: (x[0], x[1])) if scored_peers else None
        who = f"{self.current(best[1], 'vendor_name')} ({best[1]}), the fastest {trade} vendor," if best else f"another {trade} vendor"
        ref = best[0] if best else self.value("Avg Days to Resolve (Portfolio)", ctx)
        saved = max(Decimal(0), (days - ref) * resolved)
        pace = self.current(best[1], "vendor_name") if best else "all vendors"
        text = (f"Move urgent {trade} work away from {name} ({code}). It takes {fmt(days, '0.0')} days on average to resolve a request, "
                f"{fmt(div(days, trade_days), '0.0')} times the {fmt(trade_days, '0.0')} days of all {trade} vendors, and breaches the SLA on {fmt(breach, '0.0%')} of its jobs "
                f"({fmt(port_breach, '0.0%')} for all vendors). Action: give its urgent jobs to {who} and review its contract. Owner: maintenance manager. "
                f"Expected effect: at the speed of {pace}, its {fmt(resolved, '#,0')} requests would have waited about {fmt(saved, '#,0')} fewer days in all over this period.")
        return {"code": code, "days": days, "gap": gap, "breach": breach, "best": best[1] if best else None, "text": text}

    def d3(self, ctx: Ctx) -> dict:
        buildings = [b for b in self.d["buildings"] if ctx.buildings is None or b["building_code"] in ctx.buildings]
        types = [u["unit_type"] for u in self.d["unit_types"] if ctx.unit_types is None or u["unit_type"] in ctx.unit_types]
        scored = []
        for city in sorted({b["city"] for b in buildings}):
            in_city = frozenset(b["building_code"] for b in buildings if b["city"] == city)
            for ut in types:
                one = replace(ctx, buildings=in_city, unit_types=frozenset([ut]))
                occ, units = self.value("Occupancy %", one), self.value("Units", one)
                if occ is not None and units is not None and units >= MIN_UNITS:
                    scored.append((occ, city, ut, units, one))
        if not scored:
            return {"segment": None, "text": f"No city and unit type has {MIN_UNITS} or more units in this selection."}
        occ, city, ut, units, one = min(scored, key=lambda x: (x[0], x[1], x[2]))
        port = self.value("Occupancy % (Portfolio)", ctx)
        more = max(Decimal(0), (port - occ) * units).quantize(Decimal(1), ROUND_HALF_UP)
        rent = self.value("Avg Contract Rent", one)
        if rent is None:  # none of the segment's units is let: the unit type's rent across the portfolio
            rent = self.value("Avg Contract Rent", replace(ctx, buildings=None, unit_types=frozenset([ut])))
        vacancy = self.value("Avg Vacancy Days", one)
        text = (f"Fill vacant {ut.lower()}s in {city}. Their occupancy is {fmt(occ, '0.0%')} against {fmt(port, '0.0%')} for the portfolio"
                + ("." if vacancy is None else f", and a vacancy lasts {fmt(vacancy, '0')} days on average.")
                + " Action: a vacancy incentive (rent-free weeks) on them, marketed before the summer moving peak."
                + " Owner: leasing manager. Expected effect: "
                + (("they are at the portfolio's occupancy already" + ("." if rent is None else f"; each one let adds about PKR {fmt(rent, '#,0')} of rent a month."))
                   if more == 0 else
                   (f"reaching the portfolio's occupancy fills about {fmt(more, '0')}" + (" more unit" if more == 1 else " more units")
                    + ("." if rent is None else f", about PKR {fmt(more * rent, '#,0')} of rent a month."))))
        return {"segment": f"{ut} in {city}", "occupancy": occ, "text": text}


def fmt(x, pattern: str) -> str:
    """DAX FORMAT for the patterns the measures use (halves round away from zero)."""
    if x is None:
        return ""
    x = Decimal(x)
    if pattern.endswith("%"):
        places = len(pattern.split(".")[1]) - 1 if "." in pattern else 0
        return f"{(x * 100).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP):f}%"
    places = len(pattern.split(".")[1]) if "." in pattern else 0
    q = x.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    return f"{q:,f}" if pattern.startswith("#,") else f"{q:f}"


def shown(x, kind: str) -> str:
    """The value as the dashboard's format shows it (README, step 5)."""
    if x is None:
        return "(blank)"
    return {"PKR": lambda: "PKR " + fmt(x, "#,0"), "percent": lambda: fmt(x, "0.0%"), "whole number": lambda: fmt(x, "#,0"),
            "decimal": lambda: fmt(x, "0.0")}[kind]()


def numeric() -> dict[str, str]:
    """The measures with a number (not the text ones): {measure: format}."""
    return {n: f for n, f in dax_measures().items() if f != "text"}


def validation_dax() -> str:
    """docs/powerbi/validation.dax: the same table, in Power BI's DAX query view."""
    lines = ["// docs/powerbi/validation.dax: the dashboard's validation table (US-13.1, US-13.5).",
             "// Generated by python scripts/powerbi_expected.py --dax from docs/powerbi/measures.dax; do not edit.",
             "// Paste into DAX query view and Run: the first table must equal docs/evidence/us-13.1/expected_measures.csv",
             "// (or the output of python scripts/powerbi_expected.py on your warehouse), the second the decision texts.",
             "", "EVALUATE", "UNION ("]  # fmt: skip
    rows = []
    for i, name in enumerate(numeric(), 1):
        cells = [f'"Row", {i}', f'"Measure", "{name}"']
        for s, (flt, _) in SLICES.items():
            expr = f"[{name}]" if not flt else f"CALCULATE ( [{name}], {flt} )"
            cells.append(f'"{s}", CONVERT ( {expr}, DOUBLE )')
        rows.append("    ROW ( " + ", ".join(cells) + " )")
    lines += [",\n".join(rows), ")", "ORDER BY [Row]", "", "EVALUATE", "UNION ("]
    rows = []
    for s, (flt, _) in SLICES.items():
        cells = [f'"Selection", "{s}"']
        for d in ("D1 Text", "D2 Text", "D3 Text"):
            cells.append(f'"{d}", ' + (f"[{d}]" if not flt else f"CALCULATE ( [{d}], {flt} )"))
        rows.append("    ROW ( " + ", ".join(cells) + " )")
    lines += [",\n".join(rows), ")", ""]
    return "\n".join(lines)


def expected(model: Model) -> tuple[list[dict], list[dict]]:
    """The validation table ({measure, format, slice: value}) and the decision texts per slice."""
    ctxs = {s: model.ctx(sel) for s, (_f, sel) in SLICES.items()}
    table = [{"measure": n, "format": f, **{s: model.value(n, c) for s, c in ctxs.items()}} for n, f in numeric().items()]
    decisions = [{"selection": s, "D1": model.d1(c), "D2": model.d2(c), "D3": model.d3(c)} for s, c in ctxs.items()]
    return table, decisions


def raw(x) -> str:
    return "" if x is None else f"{Decimal(x).quantize(Decimal('0.000001'), ROUND_HALF_UP):f}"


def connect_reader():
    import psycopg2

    s = settings()
    return psycopg2.connect(host=s.get("PGHOST", "localhost"), port=int(s.get("PGPORT", "5432")),
                            user=s.get("LUE_READER_USER", "lue_reader"), password=s.get("LUE_READER_PASSWORD", ""),
                            dbname="lue_warehouse", connect_timeout=10, application_name="lue_powerbi_expected")  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write expected_measures.csv and decisions.txt here")
    ap.add_argument("--dax", action="store_true", help="write docs/powerbi/validation.dax")
    ap.add_argument("--check", action="store_true", help="exit 1 if docs/powerbi/validation.dax is out of date")
    a = ap.parse_args(argv)
    if a.check:
        same = VALIDATION.is_file() and VALIDATION.read_text(encoding="utf-8") == validation_dax()
        print("docs/powerbi/validation.dax is " + ("up to date" if same else "out of date: run python scripts/powerbi_expected.py --dax"))
        return 0 if same else 1
    if a.dax:
        VALIDATION.write_text(validation_dax(), encoding="utf-8", newline="\n")
        print(f"wrote {VALIDATION.relative_to(ROOT)} ({len(numeric())} measures x {len(SLICES)} selections)")
        return 0
    try:
        conn = connect_reader()
    except Exception as exc:  # noqa: BLE001  (any connection failure: say what to check)
        print(f"cannot connect as lue_reader: {str(exc).strip()}. Check .env (LUE_READER_PASSWORD) and that the warehouse is loaded.")
        return 1
    try:
        with conn.cursor() as cur:
            model = Model.load(cur)
            cur.execute("SELECT window_start, window_end FROM lue_reporting.vw_reporting_window")
            start, end = cur.fetchone()
    finally:
        conn.close()
    table, decisions = expected(model)
    width = max(len(r["measure"]) for r in table)
    print(f"Expected dashboard values (lue_reader; data window {start} to {end})")
    print(f"{'Measure':<{width}}  " + "  ".join(f"{s:>18}" for s in SLICES))
    for r in table:
        print(f"{r['measure']:<{width}}  " + "  ".join(f"{shown(r[s], r['format']):>18}" for s in SLICES))
    texts = []
    for d in decisions:
        texts.append(f"[{d['selection']}]")
        texts += [f"  {k}: {d[k]['text']}" for k in ("D1", "D2", "D3")]
    print("\nDecision page texts\n" + "\n".join(texts))
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        with (a.out / "expected_measures.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["measure", "format", *SLICES])
            w.writerows([r["measure"], r["format"], *(raw(r[s]) for s in SLICES)] for r in table)
        (a.out / "decisions.txt").write_text(f"Decision page texts (data window {start} to {end})\n" + "\n".join(texts) + "\n", encoding="utf-8", newline="\n")
        print(f"\nwrote {a.out / 'expected_measures.csv'} and {a.out / 'decisions.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
