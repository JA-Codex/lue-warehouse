#!/usr/bin/env python3
"""Acceptance tests for US-2.3 (leases, lease events, invoices, invoice lines). No database.

    python scripts/test_leases.py

Generates the small and the full profile into temporary folders and checks the four S1 files
against the
plan's acceptance criteria, against the frozen Phase 1 pack (column names and widths come from
docs/phase1/tools/model.py) and against the contracts that US-2.4 and the loaders rely on.
"""

import csv
import importlib.util
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import etl.gen_leases as gl  # noqa: E402
import etl.gen_master as gm  # noqa: E402
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402
from etl import reference_data as ref  # noqa: E402


def clean_profile(name: str):
    """The clean control batch (every defect rate 0). These checks prove the clean contract; the
    defects US-2.6 plants on top are checked by scripts/test_defects.py against the answer key."""
    return cfg.clean_profile(cfg.get_profile(name))


results: list[bool] = []
failures: list[str] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    if not ok:
        failures.append(text)
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


def width(sql_type: str):
    m = re.match(r"(?:VAR)?CHAR\((\d+)\)", sql_type)
    return int(m.group(1)) if m else None


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def d(text: str) -> date:
    return date.fromisoformat(text)


def paisa(text: str) -> int:
    """'1234.50' as 123450 (exact: no floats)."""
    sign = -1 if text.startswith("-") else 1
    whole, _, frac = text.lstrip("-").partition(".")
    return sign * (int(whole) * 100 + int(frac.ljust(2, "0")))


def month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def is_month_end(day: date) -> bool:
    return (day + timedelta(days=1)).day == 1


def run_checks(label: str, profile: cfg.Profile, out: Path, model) -> None:
    print(f"{label} profile ({profile.buildings} buildings, {profile.units} units)")
    erd = model.SOURCE_ERD
    ws, we = profile.window_start, profile.window_end
    manifest = gd.json.loads((out / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
    check("leases_invoices" in manifest["stages"], "the leases_invoices stage ran")

    # ---- files: columns follow the source ERD of the frozen pack
    tables = {}
    for table in ("leases", "lease_events", "invoices", "invoice_lines"):
        path = out / "s1" / f"{table}.csv"
        with path.open(encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        tables[table] = read_csv(path)
        check(
            header == [c[1] for c in erd[table]],
            f"s1/{table}.csv: columns equal src_pms.{table} in the Phase 1 source ERD",
        )
    leases, events = tables["leases"], tables["lease_events"]
    invoices, lines = tables["invoices"], tables["invoice_lines"]
    fits = True
    for table in tables:
        for sql_type, name, _key in erd[table]:
            limit = width(sql_type)
            if limit and any(len(r[name] or "") > limit for r in tables[table]):
                fits = False
                print(f"       too wide: {table}.{name} (limit {limit})")
    check(fits, "every text value fits its column width in the source ERD (invoice numbers: 16)")
    check(
        all(len(r[n]) <= 12 for r in lines for n in ("billed_amount",))
        and all(re.fullmatch(r"-?\d+\.\d\d", r[n]) for r in lines for n in gl.LINE_COLS[3:]),
        "money columns are written with exactly two decimals and fit NUMERIC(12,2)",
    )

    masters = {
        "units": {int(u["unit_id"]): u for u in read_csv(out / "s1" / "units.csv")},
        "tenants": {t["tenant_code"]: t for t in read_csv(out / "s1" / "tenants.csv")},
    }
    units, tenants = masters["units"], masters["tenants"]
    # A tenant code that does not exist gets a record day in the far future, so the checks fail
    # instead of crashing.
    record_day = defaultdict(lambda: date.max)
    tenant_type = defaultdict(lambda: "Individual")
    for c, t in tenants.items():
        record_day[c] = datetime.fromisoformat(t["updated_at"]).date()
        tenant_type[c] = t["tenant_type"]
    lease_by_no = {r["lease_number"]: r for r in leases}

    # ---- leases: identity, shape and the calendar rules
    numbers = [r["lease_number"] for r in leases]
    check(
        len(set(numbers)) == len(numbers) and len(leases) > 0,
        f"{len(leases)} leases with unique numbers",
    )
    check(
        all(re.fullmatch(r"L-\d{4}-\d{5}", n) for n in numbers)
        and all(r["lease_number"][2:6] == r["start_date"][:4] for r in leases),
        "lease numbers look like L-2025-00831 and carry the start year",
    )
    order = [(r["start_date"], int(r["unit_id"])) for r in leases]
    check(
        order == sorted(order)
        and [int(n[-5:]) for n in numbers] == list(range(1, len(leases) + 1)),
        "the sequence in a lease number runs 1..N in order of (start_date, unit_id)",
    )
    check(
        all(int(r["unit_id"]) in units for r in leases)
        and all(r["tenant_code"] in tenants for r in leases),
        "every lease names an existing unit and an existing tenant",
    )
    check(
        all(
            (r["lease_type"] == "Residential")
            == (units[int(r["unit_id"])]["unit_type"] == "Apartment")
            for r in leases
        ),
        "apartments are let on Residential leases; offices and shops on Commercial leases",
    )
    starts = [d(r["start_date"]) for r in leases]
    ends = [d(r["end_date"]) for r in leases]
    check(
        all(s.day == 1 for s in starts) and all(is_month_end(e) for e in ends),
        "every lease starts on the 1st of a month and ends on the last day of a month",
    )
    terms = [month_index(e) - month_index(s) + 1 for s, e in zip(starts, ends, strict=True)]
    check(
        all(
            t == 11 if r["lease_type"] == "Residential" else t in (12, 24, 36)
            for r, t in zip(leases, terms, strict=True)
        ),
        "residential leases run 11 months; commercial leases 12, 24 or 36",
    )
    check(
        all(
            (r["rent_review_type"] == "Annual escalation")
            == (r["lease_type"] == "Commercial" and t == 12)
            for r, t in zip(leases, terms, strict=True)
        ),
        "rent review is 'Annual escalation' for 12-month commercial leases and 'Fixed' otherwise",
    )
    rents = [paisa(r["monthly_rent"]) for r in leases]
    check(
        all(p > 0 and p % 50_000 == 0 for p in rents),
        "monthly rent is positive and a multiple of 500 rupees",
    )
    by_type = defaultdict(list)
    for r, p in zip(leases, rents, strict=True):
        by_type[r["lease_type"]].append(p / 100)
    median = {k: sorted(v)[len(v) // 2] for k, v in by_type.items()}
    check(
        20_000 <= median["Residential"] <= 150_000
        and median["Residential"] < 3 * median["Commercial"],
        f"rents look like Lahore, Karachi, Islamabad and Faisalabad: median residential PKR "
        f"{median['Residential']:,.0f}, commercial PKR {median['Commercial']:,.0f}",
    )

    # ---- acceptance: zero overlapping leases per unit
    per_unit = defaultdict(list)
    for r in leases:
        per_unit[int(r["unit_id"])].append((d(r["start_date"]), d(r["end_date"]), r))
    overlaps = 0
    for history in per_unit.values():
        history.sort(key=lambda h: h[0])
        overlaps += sum(b[0] <= a[1] for a, b in zip(history, history[1:], strict=False))
    check(overlaps == 0, "ACCEPTANCE: zero overlapping leases per unit")

    # ---- the window
    check(
        all(s <= we for s in starts) and sum(s > ws for s in starts) > 0,
        f"no lease starts after the window closes ({we}); leases keep starting inside it",
    )
    opening = [r for r in leases if d(r["start_date"]) < ws]
    active_open = sum(d(r["start_date"]) < ws <= d(r["end_date"]) for r in leases)
    check(
        len(opening) == active_open == profile.target_active_leases,
        f"the window opens with exactly {profile.target_active_leases} leases running "
        f"(the opening leases migrated at go-live)",
    )
    check(
        all(record_day[r["tenant_code"]] < ws for r in opening),
        "every opening lease belongs to a tenant whose record was created before the window opened",
    )
    check(
        all(
            record_day[r["tenant_code"]] <= d(r["start_date"])
            for r in leases
            if d(r["start_date"]) >= ws
        ),
        "every lease that starts inside the window starts on or after its tenant's record",
    )
    first_months = []
    month = ws.replace(day=1)
    while month <= we:
        first_months.append(month)
        month = gl.add_months(month, 1)
    active = [sum(s <= m <= e for s, e in zip(starts, ends, strict=True)) for m in first_months]
    mean_active = sum(active) / len(active)
    tolerance = 0.06 if profile.name == "full" else 0.12
    check(
        abs(mean_active / profile.target_active_leases - 1) <= tolerance,
        f"about {profile.target_active_leases} leases are active at any time "
        f"(average {mean_active:.0f}, within {tolerance:.0%})",
    )
    check(
        min(active) >= 0.85 * profile.target_active_leases,
        f"active leases never drop below 85% of target (low {min(active)})",
    )

    # ---- renewal chains and statuses
    renewals = [r for r in leases if r["previous_lease_number"]]
    check(
        all(r["previous_lease_number"] in lease_by_no for r in renewals),
        "every previous_lease_number names an existing lease",
    )
    chain_ok = rent_up = True
    successors = Counter(r["previous_lease_number"] for r in renewals)
    for r in renewals:
        prev = lease_by_no[r["previous_lease_number"]]
        chain_ok &= (
            prev["unit_id"] == r["unit_id"]
            and prev["tenant_code"] == r["tenant_code"]
            and d(r["start_date"]) == d(prev["end_date"]) + timedelta(days=1)
            and prev["status"] == "Renewed"
        )
        rent_up &= paisa(r["monthly_rent"]) >= paisa(prev["monthly_rent"]) * 1.02
    check(
        chain_ok,
        "a renewal is the same unit and tenant and starts the day after the lease it renews",
    )
    check(rent_up, "a renewal escalates the rent (at least 2 percent)")
    check(
        all(c == 1 for c in successors.values())
        and {n for n, r in lease_by_no.items() if r["status"] == "Renewed"} == set(successors),
        "a lease is Renewed exactly when one renewal follows it, and only one",
    )
    check(
        {r["status"] for r in leases} <= {"Active", "Renewed", "Terminated"}
        and all((r["status"] == "Active") == (d(r["end_date"]) >= we) for r in leases),
        "a lease is Active exactly when it runs on to the end of the window; the others "
        "are resolved",
    )
    share = len(renewals) / max(1, sum(r["status"] in ("Renewed", "Terminated") for r in leases))
    check(
        0.30 <= share <= 0.65,
        f"{share:.0%} of resolved leases were renewed (the rest are terminations)",
    )

    # ---- tenants: nobody holds two leases at once, except corporate tenants (up to 4)
    spans = defaultdict(list)
    for r in leases:
        spans[r["tenant_code"]].append((d(r["start_date"]), d(r["end_date"])))
    clash = widest = 0
    for code, held in spans.items():
        points = sorted([(s, 1) for s, _ in held] + [(e + timedelta(days=1), -1) for _, e in held])
        running = peak = 0
        for _, step in points:
            running += step
            peak = max(peak, running)
        widest = max(widest, peak) if tenant_type[code] == "Corporate" else widest
        clash += peak > (gl.MAX_CORPORATE_LEASES if tenant_type[code] == "Corporate" else 1)
    check(
        clash == 0,
        f"no individual holds two leases at once; corporate tenants hold at most {widest}",
    )
    used = len(spans) / len(tenants)
    check(
        used >= (0.75 if profile.name == "full" else 0.40),
        f"{used:.0%} of tenant records belong to a lease (the rest are applicants who "
        f"never signed)",
    )

    # ---- lease events
    ids = [int(e["event_id"]) for e in events]
    check(ids == list(range(1, len(events) + 1)), f"{len(events)} events, event_id runs 1..N")
    check(
        {e["event_code"] for e in events} <= {c for c, _n, _x in ref.LEASE_EVENT_TYPES}
        and all(e["lease_number"] in lease_by_no for e in events),
        "event codes are SIGN, RENEW, NOTICE or TERM; every event names an existing lease",
    )
    dates = [d(e["event_date"]) for e in events]
    check(
        dates == sorted(dates) and all(ws <= x <= we for x in dates),
        "events are in date order and all inside the window",
    )
    by_lease = defaultdict(dict)
    dup = False
    for e in events:
        dup |= e["event_code"] in by_lease[e["lease_number"]]
        by_lease[e["lease_number"]][e["event_code"]] = d(e["event_date"])
    check(not dup, "no lease has the same event twice")
    shape_ok = date_ok = True
    for r in leases:
        got = by_lease.get(r["lease_number"], {})
        start, end = d(r["start_date"]), d(r["end_date"])
        if r["previous_lease_number"]:
            want = {"RENEW"} | ({"NOTICE", "TERM"} if r["status"] == "Terminated" else set())
        elif start < ws:
            want = {"NOTICE", "TERM"} if r["status"] == "Terminated" else set()
        else:
            want = {"SIGN"} | ({"NOTICE", "TERM"} if r["status"] == "Terminated" else set())
        shape_ok &= set(got) == want
        if "SIGN" in got:
            date_ok &= got["SIGN"] <= start and got["SIGN"] >= record_day[r["tenant_code"]]
        if "RENEW" in got:
            prev = lease_by_no[r["previous_lease_number"]]
            date_ok &= got["RENEW"] < d(prev["end_date"]) and got["RENEW"] >= ws
        if "NOTICE" in got:
            date_ok &= ws <= got["NOTICE"] < end and got["TERM"] == end
            date_ok &= got["NOTICE"] >= end - timedelta(days=60) or got["NOTICE"] < ws + timedelta(
                days=60
            )
    check(
        shape_ok,
        "each lease has the events its life implies: SIGN for a new tenant, RENEW for a renewal, "
        "NOTICE and TERM for a termination, nothing for an opening or active lease",
    )
    check(
        date_ok,
        "SIGN is before move-in and after the tenant record; RENEW and NOTICE are before "
        "the end date; "
        "TERM is on the end date",
    )
    check(
        all(
            d(e["event_date"]) >= record_day[lease_by_no[e["lease_number"]]["tenant_code"]]
            for e in events
        ),
        "no lease event is dated before its tenant's record",
    )

    # ---- invoices
    inv_numbers = [r["invoice_number"] for r in invoices]
    check(
        len(set(inv_numbers)) == len(inv_numbers) and inv_numbers == sorted(inv_numbers),
        f"{len(invoices)} invoices with unique numbers, in order",
    )
    check(
        all(re.fullmatch(r"INV-\d{4}-\d\d-\d{4}", n) for n in inv_numbers),
        "invoice numbers look like INV-2026-03-0831 (16 characters, the width of the column)",
    )
    seq = {r["lease_number"]: int(r["lease_number"][-5:]) for r in leases}
    check(
        all(r["lease_number"] in lease_by_no for r in invoices)
        and all(
            int(r["invoice_number"][-4:]) == seq[r["lease_number"]]
            and r["invoice_number"][4:11] == r["invoice_date"][:7]
            for r in invoices
        ),
        "every invoice names an existing lease; its number carries the month and the "
        "lease sequence",
    )
    check(
        all(d(r["invoice_date"]).day == 1 for r in invoices)
        and all(d(r["due_date"]) == d(r["invoice_date"]).replace(day=gl.DUE_DAY) for r in invoices)
        and {r["status"] for r in invoices} <= {"Paid", "Partial", "Overdue"},
        f"invoices are issued on the 1st and due on the {gl.DUE_DAY}th; status is Paid, "
        f"Partial or Overdue (set by US-2.4)",
    )
    billed_months = defaultdict(list)
    for r in invoices:
        billed_months[r["lease_number"]].append(d(r["invoice_date"]))
    continuous = True
    for r in leases:
        first = max(d(r["start_date"]).replace(day=1), ws.replace(day=1))
        last = min(d(r["end_date"]).replace(day=1), we.replace(day=1))
        want = []
        m = first
        while m <= last:
            want.append(m)
            m = gl.add_months(m, 1)
        continuous &= sorted(billed_months.get(r["lease_number"], [])) == want
    check(
        continuous,
        "every lease is invoiced once for every month it runs inside the window, and no other",
    )
    check(
        all(
            d(r["invoice_date"]) >= record_day[lease_by_no[r["lease_number"]]["tenant_code"]]
            for r in invoices
        ),
        "no invoice is dated before its tenant's record",
    )

    # ---- invoice lines
    keys = [(r["invoice_number"], int(r["line_no"])) for r in lines]
    check(
        len(set(keys)) == len(keys), f"{len(lines)} invoice lines, (invoice_number, line_no) unique"
    )
    per_invoice = defaultdict(list)
    for r in lines:
        per_invoice[r["invoice_number"]].append(r)
    check(
        set(per_invoice) == set(inv_numbers)
        and all(
            [int(x["line_no"]) for x in group] == list(range(1, len(group) + 1))
            and group[0]["charge_code"] == "RENT"
            and [x["charge_code"] for x in group].count("RENT") == 1
            for group in per_invoice.values()
        ),
        "every invoice has lines numbered 1.., line 1 is its one RENT line",
    )
    codes = Counter(r["charge_code"] for r in lines)
    check(
        set(codes) <= {"RENT", "SERVICE", "UTILITY"} and set(codes) <= gl.CHARGE_CODES,
        f"charge codes are RENT, SERVICE and UTILITY from charge_types ({dict(codes)})",
    )
    tax_ok = sum_ok = True
    commercial_lease = {r["lease_number"]: r["lease_type"] == "Commercial" for r in leases}
    lease_of = {r["invoice_number"]: r["lease_number"] for r in invoices}
    for r in lines:
        billed, tax, disc, net = (paisa(r[c]) for c in gl.LINE_COLS[3:])
        taxed = r["charge_code"] != "UTILITY" and commercial_lease[lease_of[r["invoice_number"]]]
        tax_ok &= tax == (billed * gl.TAX_PERCENT // 100 if taxed else 0) and billed > 0
        sum_ok &= disc == 0 and net == billed + tax - disc
    check(
        sum_ok,
        "net_amount = billed_amount + tax_amount - discount_amount on every line (discount is 0)",
    )
    check(
        tax_ok,
        f"tax is {gl.TAX_PERCENT}% on commercial rent and service charge and nothing "
        f"else; amounts are positive",
    )

    # ---- acceptance: invoice totals equal lease rent times months active
    months_billed = Counter(r["lease_number"] for r in invoices)
    rent_billed = defaultdict(int)
    each_rent_equal = True
    for r in lines:
        if r["charge_code"] == "RENT":
            lease = lease_by_no[lease_of[r["invoice_number"]]]
            each_rent_equal &= paisa(r["billed_amount"]) == paisa(lease["monthly_rent"])
            rent_billed[lease["lease_number"]] += paisa(r["billed_amount"])
    check(
        all(
            rent_billed[n] == paisa(lease_by_no[n]["monthly_rent"]) * months_billed[n]
            for n in months_billed
        )
        and each_rent_equal,
        "ACCEPTANCE: the rent billed on a lease's invoices equals its monthly rent times "
        "the months billed",
    )
    n_inv = len(invoices)
    service = codes["SERVICE"] / n_inv
    utility = codes["UTILITY"] / n_inv
    loose = profile.name == "small"
    check(
        (0.70 if loose else 0.84) <= service <= (1.0 if loose else 0.97)
        and (0.20 if loose else 0.35) <= utility <= (0.70 if loose else 0.55),
        f"service charge on {service:.0%} of invoices (most), utility on {utility:.0%} "
        f"(occasional)",
    )
    tolerance = 0.20 if loose else 0.08
    check(
        abs(len(lines) / profile.target_invoice_lines - 1) <= tolerance,
        f"{len(lines):,} invoice lines against a target of {profile.target_invoice_lines:,} "
        f"(within {tolerance:.0%})",
    )

    # ---- seasonal move-in peaks (a three-month window cannot show a season)
    if profile.name == "full":
        move_ins = Counter(
            d(r["start_date"]).month
            for r in leases
            if not r["previous_lease_number"] and d(r["start_date"]) >= ws
        )
        peak = sum(move_ins[m] for m in (6, 7, 8)) / 3
        rest = sum(move_ins[m] for m in range(1, 13) if m not in (6, 7, 8)) / 9
        check(
            peak >= 1.3 * rest,
            f"ACCEPTANCE: seasonal move-in peak: June to August average {peak:.0f} new "
            f"tenants a month "
            f"against {rest:.0f} in the other months ({peak / rest:.1f}x)",
        )

    # ---- the object API that US-2.4 will call gives the same data as the files
    ctx = gd.Context(profile, manifest["seed"], out)
    b = gl.build_billing(profile, gm.build_master(profile, ctx.rng), ctx.rng)
    check(
        len(b.leases) == len(leases)
        and [r[0] for r in b.lease_rows] == numbers
        and len(b.line_rows) == len(lines)
        and all(x.tenant_code in tenants for x in b.leases),
        "build_billing() rebuilds exactly the leases and lines in the files",
    )


def main() -> int:
    print("=" * 70)
    print(" US-2.3 acceptance tests: leases, lease events, invoices and lines")
    print("=" * 70)
    model = load_model()
    with tempfile.TemporaryDirectory(prefix="lue_lease_test_") as tmp:
        tmp = Path(tmp)
        runs = {}
        for name in ("small", "full"):
            started = time.perf_counter()
            runs[name] = (
                gd.run(clean_profile(name), 3004, tmp / name),
                time.perf_counter() - started,
            )
        for name in ("small", "full"):
            try:
                run_checks(name.capitalize(), clean_profile(name), tmp / name, model)
            except Exception as exc:  # a broken output must fail the test, not crash it
                check(False, f"{name}: the checks could not finish ({type(exc).__name__}: {exc})")

        print("Determinism and independence")
        again = gd.run(clean_profile("small"), 3004, tmp / "again")
        mine = [f"s1/{t}.csv" for t in ("leases", "lease_events", "invoices", "invoice_lines")]
        check(
            all(again["files"][k] == runs["small"][0]["files"][k] for k in mine)
            and again["content_hash"] == runs["small"][0]["content_hash"],
            "same seed: identical hashes for the four lease and billing files",
        )
        other = gd.run(clean_profile("small"), 3005, tmp / "other")
        check(
            all(other["files"][k] != again["files"][k] for k in mine),
            "a different seed changes all four files",
        )
        check(
            all(
                again["files"][f"s1/{n}.csv"] == runs["small"][0]["files"][f"s1/{n}.csv"]
                for n in ("buildings", "units", "tenants")
            ),
            "the master data files are unaffected by this stage",
        )
        check(
            runs["small"][1] < 60 and runs["full"][1] < 60,
            f"both profiles generate in under a minute (small {runs['small'][1]:.1f}s, "
            f"full {runs['full'][1]:.1f}s)",
        )
        check(
            gl.add_months(date(2025, 12, 1), 1) == date(2026, 1, 1)
            and gl.add_months(date(2026, 1, 1), -2) == date(2025, 11, 1)
            and gl.month_end(date(2024, 2, 1)) == date(2024, 2, 29)
            and gl.money(-12345) == "-123.45"
            and gl.money(8_500_000) == "85000.00",
            "month arithmetic and money formatting helpers",
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
