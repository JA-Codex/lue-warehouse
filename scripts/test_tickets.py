#!/usr/bin/env python3
"""Acceptance tests for US-2.5 (S4 maintenance tickets, S6 incentive log). No database needed.

    python scripts/test_tickets.py

Generates the small and the full profile into temporary folders and checks the tickets and the
incentive log against the plan's acceptance criteria, against the master data generated beside them
(US-2.2) and against the frozen Phase 1 pack (column widths come from docs/phase1/tools/model.py).
"""

import csv
import importlib.util
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import etl.gen_tickets as gt  # noqa: E402
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402
from etl import reference_data as ref  # noqa: E402

results: list[bool] = []
STATUS_ORDER = ["Raised", "Assigned", "Resolved", "Verified"]


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def load_model():
    spec = importlib.util.spec_from_file_location(
        "phase1_model", ROOT / "docs" / "phase1" / "tools" / "model.py"
    )
    module = importlib.util.module_from_spec(spec)
    # No __pycache__ inside the frozen pack: it would make the manifest check fail (extra file).
    dont_write, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = dont_write
    return module


def width(model, table: str, column: str) -> int:
    typ = next(c["type"] for c in model.TABLES[table]["cols"] if c["name"] == column)
    return int(re.match(r"(?:VAR)?CHAR\((\d+)\)", typ).group(1))


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_sheet(path: Path, name: str) -> list[dict]:
    from openpyxl import load_workbook

    book = load_workbook(path, read_only=True, data_only=True)
    try:  # a read-only workbook keeps its file open until closed (Windows cannot delete it then)
        rows = [list(r) for r in book[name].iter_rows(values_only=True)]
    finally:
        book.close()
    return [dict(zip(rows[0], r, strict=True)) for r in rows[1:]]


def as_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def run_checks(label: str, profile: cfg.Profile, out: Path, model) -> dict:
    print(f"{label} profile: {profile.units} units, {profile.months} months")
    manifest = json.loads((out / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
    check(
        manifest["stages"].index("tickets_incentives") > manifest["stages"].index("master_data"),
        "the tickets_incentives stage ran, after master_data",
    )

    units = {(u["building_code"], u["unit_no"]): u for u in read_csv(out / "s1" / "units.csv")}
    vendors = {v["vendor_code"]: v for v in read_sheet(out / "s2" / "registers.xlsx", "vendors")}
    sla = read_sheet(out / "s2" / "registers.xlsx", "sla_policy")
    subcats = {c: (n, cat, h) for c, n, cat, h in ref.MAINTENANCE_SUBCATEGORIES}
    first = datetime.combine(profile.window_start, datetime.min.time())
    export = datetime.combine(profile.window_end, datetime.min.time()) + timedelta(
        hours=23, minutes=59, seconds=59
    )

    print("  S4 tickets (s4/tickets.json)")
    raw = (out / "s4" / "tickets.json").read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    tickets = doc["tickets"]
    check(
        len(tickets) == profile.target_tickets == doc["export"]["ticket_count"],
        f"{len(tickets)} tickets, as the config asks",
    )
    check(raw.endswith(b"\n") and b"\r\n" not in raw, "UTF-8 JSON with \\n line ends")

    ids = [t["ticket_id"] for t in tickets]
    w_req = width(model, "fact_maintenance_request", "request_number")
    check(
        len(set(ids)) == len(ids)
        and all(re.fullmatch(r"MR-\d{4}-\d{5}", i) for i in ids)
        and max(map(len, ids)) <= w_req,
        f"ticket ids are unique MR-<year>-<5 digits>, at most {w_req} characters",
    )
    raised = [datetime.fromisoformat(t["status_history"][0]["at"]) for t in tickets]
    check(
        raised == sorted(raised) and all(i[3:7] == str(r.year) for i, r in zip(ids, raised)),
        "ids follow the raised time, and carry the year raised",
    )
    seq_ok = all(
        int(i[-5:]) == n
        for year in {r.year for r in raised}
        for n, i in enumerate([i for i in ids if i[3:7] == str(year)], start=1)
    )
    check(seq_ok, "the sequence restarts at 00001 each year, with no gaps")

    check(
        all((t["building_code"], t["unit_no"]) in units for t in tickets),
        "every ticket references a real unit (building_code + unit_no)",
    )
    check(
        all(
            t["subcategory_code"] in subcats
            and subcats[t["subcategory_code"]][:2] == (t["subcategory"], t["category"])
            for t in tickets
        ),
        "every ticket references a real subcategory and its category",
    )
    assigned = [t for t in tickets if t["vendor_code"] is not None]
    check(
        all(t["vendor_code"] in vendors for t in assigned),
        "every assigned ticket references a real vendor",
    )
    check(
        all(
            t["vendor_code"] in vendors
            and vendors[t["vendor_code"]]["trade"] == gt.TRADE_FOR_CATEGORY.get(t["category"])
            for t in assigned
        ),
        "the vendor's trade serves the ticket's category",
    )
    check(
        all(
            len(t["building_code"]) <= width(model, "dim_unit", "building_code")
            and len(t["unit_no"]) <= width(model, "dim_unit", "unit_no")
            and len(t["subcategory_code"])
            <= width(model, "dim_maintenance_category", "subcategory_code")
            and (
                t["vendor_code"] is None
                or len(t["vendor_code"]) <= width(model, "dim_vendor", "vendor_code")
            )
            for t in tickets
        ),
        "codes fit the warehouse columns (Phase 1 widths)",
    )

    hist_ok = order_ok = vendor_ok = True
    for t in tickets:
        h = t["status_history"]
        names = [e["status"] for e in h]
        times = [datetime.fromisoformat(e["at"]) for e in h]
        if names != STATUS_ORDER[: len(names)] or t["status"] != names[-1]:
            hist_ok = False
        if times != sorted(times) or len(set(times)) != len(times):
            order_ok = False
        if not all(first <= x <= export for x in times):
            order_ok = False
        has_assigned = "Assigned" in names
        e_assigned = next((e for e in h if e["status"] == "Assigned"), {})
        if (
            has_assigned != (t["vendor_code"] is not None)
            or (has_assigned and e_assigned.get("vendor_code") != t["vendor_code"])
            or (t["estimate"] is not None) != has_assigned
            or (t["final_cost"] is not None) != ("Resolved" in names)
        ):
            vendor_ok = False
    check(
        hist_ok, "status history starts with Raised and runs Raised, Assigned, Resolved, Verified"
    )
    check(order_ok, "status times strictly increase and lie inside the window")
    check(vendor_ok, "vendor and estimate appear with Assigned, final cost with Resolved")
    w_status = width(model, "fact_maintenance_request", "request_status")
    check(
        all(len(t["status"]) <= w_status for t in tickets),
        f"statuses fit request_status ({w_status} characters)",
    )
    check(
        all(
            isinstance(t[k], bool)
            for t in tickets
            for k in ("is_emergency", "is_recurring", "is_tenant_caused")
        )
        and all(
            t[k] is None or (isinstance(t[k], int) and t[k] > 0)
            for t in tickets
            for k in ("estimate", "final_cost")
        ),
        "flags are true/false; costs are positive whole rupees (no floats, rule 4)",
    )
    check(
        all(
            t["is_emergency"] == (t["priority"] == "Emergency")
            and t["priority"] in ("Emergency", "High", "Normal")
            for t in tickets
        ),
        "is_emergency is true exactly when the priority is Emergency",
    )

    last: dict[tuple, datetime] = {}
    recurring_ok = True
    for t, r in zip(tickets, raised):
        key = (t["building_code"], t["unit_no"], t["subcategory_code"])
        expected = key in last and r - last[key] <= timedelta(days=gt.RECURRING_DAYS)
        recurring_ok &= t["is_recurring"] == expected
        last[key] = r
    check(
        recurring_ok,
        f"is_recurring is exactly 'same unit and problem within {gt.RECURRING_DAYS} days before'",
    )
    recurring_share = sum(t["is_recurring"] for t in tickets) / len(tickets)
    check(0.03 <= recurring_share <= 0.25, f"{recurring_share:.0%} of tickets are recurring")

    unit_ok = True
    for t, r in zip(tickets, raised):
        u = units.get((t["building_code"], t["unit_no"]))
        if u is None:
            unit_ok = False
            continue
        if datetime.fromisoformat(u["updated_at"]) > r:
            unit_ok = False
        if t["subcategory_code"] in gt.APARTMENT_ONLY and u["unit_type"] != "Apartment":
            unit_ok = False
    check(unit_ok, "no ticket predates its unit's record; geyser repairs only in apartments")

    def sla_hours(code: str, day: date) -> int:
        rows = [s for s in sla if s["subcategory_code"] == code and as_date(s["valid_from"]) <= day]
        return max(rows, key=lambda s: as_date(s["valid_from"]))["default_sla_hours"] if rows else 0

    done = [(t, r) for t, r in zip(tickets, raised) if t["status"] in ("Resolved", "Verified")]
    breaches = sum(
        (datetime.fromisoformat(t["status_history"][2]["at"]) - r).total_seconds() / 3600
        > sla_hours(t["subcategory_code"], r.date())
        for t, r in done
    )
    stats = {
        "breach_rate": breaches / len(done) if done else 0.0,
        "open": sum(t["status"] in ("Raised", "Assigned") for t in tickets),
        "status": Counter(t["status"] for t in tickets),
        "tickets": tickets,
        "raised": raised,
    }

    print("  S6 incentives (s6/offers.csv, s6/incentive_log.csv)")
    offers = read_csv(out / "s6" / "offers.csv")
    codes = [o["offer_code"] for o in offers]
    check(len(set(codes)) == len(codes) == len(gt.OFFERS), f"{len(codes)} offers, unique codes")
    check(
        all(
            len(o["offer_code"]) <= width(model, "dim_incentive", "incentive_code")
            and len(o["offer_type"]) <= width(model, "dim_incentive", "incentive_type")
            and len(o["description"]) <= width(model, "dim_incentive", "incentive_description")
            for o in offers
        ),
        "offer codes, types and descriptions fit dim_incentive",
    )
    check(
        all(
            o["offer_type"] in ("Rent-free days", "Discount", "Free maintenance")
            and 0 <= float(o["discount_pct"]) <= 50
            and 0 <= int(o["rent_free_days"]) <= 60
            and (float(o["discount_pct"]) > 0) == (o["offer_type"] == "Discount")
            and (int(o["rent_free_days"]) > 0) == (o["offer_type"] == "Rent-free days")
            for o in offers
        ),
        "types are the dictionary's three; discount 0-50, rent-free 0-60, matching the type",
    )
    log = read_csv(out / "s6" / "incentive_log.csv")
    # Since US-2.6 the offers come from the lease simulation (posted on vacant units), so the
    # count is about the target, not exactly it.
    tolerance = 0.15 if profile.name == "full" else 1.0
    check(
        len(log) >= 1 and abs(len(log) / profile.target_incentive_offers - 1) <= tolerance,
        f"{len(log)} incentive log rows, about the {profile.target_incentive_offers} asked for",
    )
    check(
        all((r["building_code"], r["unit_no"]) in units and r["offer_code"] in codes for r in log),
        "every row references a real unit and a real offer",
    )
    spans = [(as_date(r["start_date"]), as_date(r["end_date"])) for r in log]
    check(
        all(profile.window_start <= s <= e <= profile.window_end for s, e in spans),
        "every incentive window lies inside the data window",
    )
    keys = [(r["building_code"], r["unit_no"], r["offer_code"], r["start_date"]) for r in log]
    check(len(set(keys)) == len(keys), "the S6 grain (building + unit + offer + start) is unique")
    per_unit = defaultdict(list)
    for r, (s, e) in zip(log, spans):
        per_unit[(r["building_code"], r["unit_no"])].append((s, e))
    overlap = any(a[1] >= b[0] for v in per_unit.values() for a, b in zip(sorted(v), sorted(v)[1:]))
    check(not overlap, "no unit has two offers at the same time (coverage key stays unique)")
    allowed = {o[0]: o[5] for o in gt.OFFERS}
    check(
        all(
            (r["building_code"], r["unit_no"]) in units
            and r["offer_code"] in allowed
            and units[(r["building_code"], r["unit_no"])]["unit_type"] in allowed[r["offer_code"]]
            for r in log
        ),
        "each offer suits its unit type (no two-month rent-free on a flat)",
    )
    # US-2.6: an offer is posted on a VACANT unit and ends by the next move-in.
    unit_id = {k: int(u["unit_id"]) for k, u in units.items()}
    let = defaultdict(list)
    for r in read_csv(out / "s1" / "leases.csv"):
        let[int(r["unit_id"])].append((as_date(r["start_date"]), as_date(r["end_date"])))
    leases_of = [let[unit_id[(r["building_code"], r["unit_no"])]] for r in log]
    check(
        all(
            not any(ls <= e and s <= le for ls, le in held)
            for held, (s, e) in zip(leases_of, spans, strict=True)
        ),
        f"every offer runs while its unit is vacant (no lease overlaps it; "
        f"{sum(map(len, leases_of))} leases compared)",
    )
    return stats


def main() -> int:
    print("=" * 70)
    print(" US-2.5 acceptance tests: maintenance tickets and incentives")
    print("=" * 70)
    model = load_model()
    with tempfile.TemporaryDirectory(prefix="lue_tickets_") as tmp_name:
        tmp = Path(tmp_name)
        # The clean control batch: US-2.6 plants its defects on top (scripts/test_defects.py).
        small = cfg.clean_profile(cfg.get_profile("small"))
        full = cfg.clean_profile(cfg.get_profile("full"))
        gd.run(small, cfg.DEFAULT_SEED, tmp / "small")
        run_checks("Small", small, tmp / "small", model)
        gd.run(full, cfg.DEFAULT_SEED, tmp / "full")
        stats = run_checks("Full", full, tmp / "full", model)

        print("Realism (full profile)")
        rate = stats["breach_rate"]
        check(0.10 <= rate <= 0.40, f"{rate:.0%} of resolved tickets breach the SLA in force")
        check(
            stats["open"] >= 1,
            f"{stats['open']} tickets are still open at the export moment "
            "(the fact's -2 'not yet happened' dates get exercised)",
        )
        check(
            stats["status"]["Verified"] > 0.8 * len(stats["tickets"]),
            f"most tickets are verified ({stats['status']['Verified']})",
        )
        hvac = Counter(
            r.month for t, r in zip(stats["tickets"], stats["raised"]) if t["category"] == "HVAC"
        )
        summer, winter = sum(hvac[m] for m in (6, 7, 8)), sum(hvac[m] for m in (12, 1, 2))
        check(
            summer > 2 * winter,
            f"AC tickets peak in summer ({summer} in Jun-Aug, {winter} in Dec-Feb)",
        )
        em = [t for t in stats["tickets"] if t["priority"] == "Emergency" and t["vendor_code"]]
        nm = [t for t in stats["tickets"] if t["priority"] == "Normal" and t["vendor_code"]]

        def median_assign(ts):
            hours = sorted(
                (
                    datetime.fromisoformat(t["status_history"][1]["at"])
                    - datetime.fromisoformat(t["status_history"][0]["at"])
                ).total_seconds()
                / 3600
                for t in ts
            )
            return hours[len(hours) // 2]

        check(
            median_assign(em) < median_assign(nm) / 3,
            f"emergencies are assigned faster (median {median_assign(em):.1f} h vs "
            f"{median_assign(nm):.1f} h)",
        )

        print("Reproducibility and independence")
        gd.run(small, cfg.DEFAULT_SEED, tmp / "again")
        files = ("s4/tickets.json", "s6/offers.csv", "s6/incentive_log.csv")
        same = all(
            (tmp / "small" / f).read_bytes() == (tmp / "again" / f).read_bytes() for f in files
        )
        check(same, "same seed: byte-identical tickets and incentive files")
        gd.run(small, cfg.DEFAULT_SEED + 1, tmp / "other")
        check(
            (tmp / "small" / files[0]).read_bytes() != (tmp / "other" / files[0]).read_bytes(),
            "a different seed gives different tickets",
        )
        (tmp / "cached").mkdir()
        (tmp / "cached" / "weather_cache.json").write_text('{"not": "used"}\n', encoding="utf-8")
        m_cached = gd.run(small, cfg.DEFAULT_SEED, tmp / "cached")
        m_plain = json.loads((tmp / "small" / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
        check(
            m_cached["content_hash"] == m_plain["content_hash"]
            and (tmp / "cached" / "weather_cache.json").exists(),
            "a weather_cache.json inside --out is neither read nor deleted: output is the same",
        )
        # Since US-2.6 the rain-driven leaks read the COMMITTED cache (etl/patterns.py), never the
        # network: no download code is reachable from the generator.
        code = "".join(
            (ROOT / "etl" / f).read_text(encoding="utf-8").split('"""', 2)[2]
            for f in ("gen_tickets.py", "patterns.py")
        )
        check(
            all(word not in code for word in ("urlopen", "urllib", "download(", "fetch_part")),
            "the generator never downloads: tickets read only the committed weather cache",
        )

    print("=" * 70)
    print(
        f" RESULT: {sum(results)}/{len(results)} checks passed"
        + ("" if results and all(results) else " - FAILED")
    )
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
