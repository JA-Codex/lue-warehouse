#!/usr/bin/env python3
"""Acceptance tests for US-2.2 (master data and registers). No database needed.

    python scripts/test_master_data.py

Generates the small and the full profile into temporary folders and checks the S1 CSV files and the
S2 workbook against the plan's acceptance criteria and against the frozen Phase 1 pack (column names
and widths come from docs/phase1/tools/model.py, so the two can never drift apart).
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
import etl.gen_master as gm  # noqa: E402
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402
from etl import reference_data as ref  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def load_model():
    spec = importlib.util.spec_from_file_location(
        "phase1_model", ROOT / "docs" / "phase1" / "tools" / "model.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def width(sql_type: str):
    m = re.match(r"(?:VAR)?CHAR\((\d+)\)", sql_type)
    return int(m.group(1)) if m else None


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_workbook(path: Path) -> dict[str, list[list]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=False, data_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def as_dicts(rows: list[list]) -> list[dict]:
    header = rows[0]
    return [dict(zip(header, r, strict=True)) for r in rows[1:]]


def to_date(v) -> date | None:
    if v is None or v == "":
        return None
    return v.date() if isinstance(v, datetime) else v


def run_checks(label: str, profile: cfg.Profile, out: Path, model) -> None:
    print(f"{label} profile ({profile.buildings} buildings, {profile.units} units)")
    erd = model.SOURCE_ERD
    manifest = gd.json.loads((out / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
    check("master_data" in manifest["stages"], "the master_data stage ran")

    # ---- S1 files: columns follow the source ERD of the frozen pack
    files = {
        "buildings": "buildings.csv",
        "units": "units.csv",
        "tenants": "tenants.csv",
        "charge_types": "charge_types.csv",
        "payment_methods": "payment_methods.csv",
    }
    tables = {}
    for table, fname in files.items():
        path = out / "s1" / fname
        with path.open(encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        tables[table] = read_csv(path)
        check(
            header == [c[1] for c in erd[table]],
            f"s1/{fname}: columns equal src_pms.{table} in the Phase 1 source ERD",
        )

    buildings, units, tenants = tables["buildings"], tables["units"], tables["tenants"]
    widest_ok = True
    for table in ("buildings", "units", "tenants"):
        for _type, name, _key in erd[table]:
            limit = width(_type)
            if limit and any(len(r[name] or "") > limit for r in tables[table]):
                widest_ok = False
                print(f"       too wide: {table}.{name} (limit {limit})")
    check(widest_ok, "every S1 text value fits its column width in the source ERD")

    # ---- counts match the configuration
    check(len(buildings) == profile.buildings, f"{profile.buildings} buildings, as configured")
    check(len(units) == profile.units, f"{profile.units} units, as configured")
    check(len(tenants) == profile.tenants, f"{profile.tenants} tenants, as configured")
    cities = Counter(b["city"] for b in buildings)
    expected_cities = [c[0] for c in gm.CITIES[: profile.cities]]
    check(
        sorted(cities) == sorted(expected_cities),
        f"exactly {profile.cities} cities, each with a building: {', '.join(sorted(cities))}",
    )
    check(
        len(tables["charge_types"]) == 6 and len(tables["payment_methods"]) == 6,
        "6 charge types and 6 payment methods",
    )
    check(
        [(r["charge_code"], r["name"], r["category"]) for r in tables["charge_types"]]
        == list(ref.CHARGE_TYPES)
        and [(r["method_code"], r["name"]) for r in tables["payment_methods"]]
        == [(c, n) for c, n, _g, _d in ref.PAYMENT_METHODS],
        "charge types and payment methods equal etl/reference_data.py (the loaders' source)",
    )

    # ---- buildings
    codes = [b["building_code"] for b in buildings]
    check(len(set(codes)) == len(codes), "building codes are unique")
    check(
        all(re.fullmatch(r"[A-Z0-9]{3}\d{2}", c) for c in codes),
        "building codes look like GLB01 (3 letters or digits, 2-digit sequence)",
    )
    check(
        len({b["building_name"] for b in buildings}) == len(buildings), "building names are unique"
    )
    check(
        {b["building_class"] for b in buildings} <= {"A", "B", "C"}
        and all(1980 <= int(b["year_built"]) <= 2023 for b in buildings),
        "building class is A, B or C and year built is 1980 to 2023",
    )

    # ---- units: every unit belongs to a building and a city
    by_code = {b["building_code"]: b for b in buildings}
    check(
        all(u["building_code"] in by_code for u in units),
        "every unit belongs to an existing building",
    )
    check(
        all(by_code[u["building_code"]]["city"] in expected_cities for u in units),
        "every unit therefore has a city, one of the configured cities",
    )
    check(
        len({u["unit_id"] for u in units}) == len(units)
        and [int(u["unit_id"]) for u in units] == list(range(1, len(units) + 1)),
        "unit_id runs 1..N without gaps",
    )
    keys = [(u["building_code"], u["unit_no"]) for u in units]
    check(len(set(keys)) == len(keys), "unit_no is unique inside a building")
    check(
        all(len(c + u) <= 20 for c, u in keys),
        "building code + unit number fits the 20 characters of dim_unit.unit_nk",
    )
    per_building = Counter(u["building_code"] for u in units)
    check(
        set(per_building) == set(by_code) and min(per_building.values()) >= 10,
        "every building has at least 10 units",
    )
    check(
        {u["unit_type"] for u in units} <= {"Apartment", "Office", "Shop"},
        "unit type is Apartment, Office or Shop",
    )
    check(
        all((int(u["bedrooms"]) >= 1) == (u["unit_type"] == "Apartment") for u in units)
        and all(0 <= int(u["bedrooms"]) <= 4 for u in units),
        "bedrooms: 1 to 4 for apartments, 0 for offices and shops",
    )
    check(
        all(float(u["area_sqft"]) > 0 for u in units)
        and all(int(u["floor_no"]) >= 0 for u in units)
        and all(u["furnished"] in ("true", "false") for u in units),
        "area is positive, floor is not negative, furnished is true or false",
    )
    check(
        all(u["unit_type"] != "Shop" or u["furnished"] == "false" for u in units),
        "no shop is let furnished",
    )
    go_live = gm.GO_LIVE
    stamps = [datetime.fromisoformat(u["updated_at"]) for u in units]
    check(
        all(go_live <= s < go_live + timedelta(days=gm.GO_LIVE_DAYS) for s in stamps),
        "units carry an updated_at inside the go-live fortnight",
    )

    # ---- tenants
    t_codes = [t["tenant_code"] for t in tenants]
    check(
        t_codes == [f"T-{i:04d}" for i in range(1, len(tenants) + 1)],
        "tenant codes run T-0001.. in order",
    )
    created = [datetime.fromisoformat(t["updated_at"]) for t in tenants]
    check(created == sorted(created), "tenant codes follow the order the tenants were created")
    check(
        all(c >= go_live for c in created)
        and all(c <= datetime.combine(profile.window_end, datetime.min.time()) for c in created),
        "tenants are created between go-live and the end of the window",
    )
    opened = datetime.combine(profile.window_start, datetime.min.time())
    pre = sum(c < opened for c in created) / len(created)
    check(
        0.25 <= pre <= 0.65,
        f"{pre:.0%} of tenants exist when the window opens (enough to staff the opening leases)",
    )
    check(
        {t["tenant_type"] for t in tenants} == {"Individual", "Corporate"}
        and {t["contact_channel"] for t in tenants} <= {"Phone", "WhatsApp", "Email"},
        "tenant type and contact channel use the pack's values",
    )
    check(
        len({t["phone"] for t in tenants}) == len(tenants)
        and all(re.fullmatch(r"03\d\d-\d{7}", t["phone"]) for t in tenants),
        "tenant phone numbers look like 0300-1234567 and are unique",
    )
    missing_sector = sum(t["employer_sector"] == "" for t in tenants) / len(tenants)
    check(
        0.0 < missing_sector < 0.12 if profile.name == "small" else 0.03 <= missing_sector <= 0.07,
        f"about 5% of tenants lack an employer sector ({missing_sector:.1%}), mapped to Unknown",
    )
    people = [t["full_name"] for t in tenants if t["tenant_type"] == "Individual"]
    first_names = set(gm.MALE_NAMES) | set(gm.FEMALE_NAMES)
    check(
        all(n.split(" ")[0] in first_names and n.split(" ")[1] in gm.SURNAMES for n in people),
        "every individual name is a curated first name plus a curated surname (no real people)",
    )

    # ---- S2 workbook
    book = read_workbook(out / "s2" / "registers.xlsx")
    check(
        list(book) == ["owners", "ownership", "vendors", "sla_policy", "holidays"],
        "the workbook has the sheets owners, ownership, vendors, sla_policy, holidays",
    )
    check(
        book["owners"][0] == gm.OWNER_COLS
        and book["ownership"][0] == gm.OWNERSHIP_COLS
        and book["vendors"][0] == gm.VENDOR_COLS
        and book["sla_policy"][0] == gm.SLA_COLS
        and book["holidays"][0] == gm.HOLIDAY_COLS,
        "every sheet has its header row",
    )
    owners = as_dicts(book["owners"])
    ownership = as_dicts(book["ownership"])
    vendors = as_dicts(book["vendors"])
    sla = as_dicts(book["sla_policy"])
    holidays = as_dicts(book["holidays"])
    dims = {d["name"]: {c["name"]: c for c in d["cols"]} for d in model.DIMENSIONS}

    check(len(owners) == profile.owners, f"{profile.owners} owners, as configured")
    check(len(vendors) == profile.vendors, f"{profile.vendors} vendors, as configured")
    check(
        len({o["owner_code"] for o in owners}) == len(owners)
        and {o["owner_type"] for o in owners} == {"Individual", "Company"},
        "owner codes are unique; owner type is Individual or Company",
    )
    fits = (
        all(len(o["owner_code"]) <= width(dims["dim_owner"]["owner_code"]["type"]) for o in owners)
        and all(
            len(o["owner_name"]) <= width(dims["dim_owner"]["owner_name"]["type"]) for o in owners
        )
        and all(
            len(v["vendor_code"]) <= width(dims["dim_vendor"]["vendor_code"]["type"])
            for v in vendors
        )
        and all(
            len(v["vendor_name"]) <= width(dims["dim_vendor"]["vendor_name"]["type"])
            for v in vendors
        )
        and all(len(v["phone"]) <= width(dims["dim_vendor"]["phone"]["type"]) for v in vendors)
        and all(
            len(s["subcategory_code"])
            <= width(dims["dim_maintenance_category"]["subcategory_code"]["type"])
            and len(s["subcategory_name"])
            <= width(dims["dim_maintenance_category"]["subcategory_name"]["type"])
            for s in sla
        )
    )
    check(fits, "owner, vendor and subcategory text fits the dimension column widths")

    # ---- ownership: contiguous, no overlap, every unit and owner covered
    unit_keys = set(keys)
    check(
        all((r["building_code"], r["unit_no"]) in unit_keys for r in ownership)
        and {r["owner_code"] for r in ownership} <= {o["owner_code"] for o in owners},
        "every ownership period names an existing unit and an existing owner",
    )
    periods = defaultdict(list)
    for r in ownership:
        periods[(r["building_code"], r["unit_no"])].append(
            (to_date(r["valid_from"]), to_date(r["valid_to"]), r["owner_code"])
        )
    check(set(periods) == unit_keys, "every unit has an ownership history")
    check(
        {r["owner_code"] for r in ownership} == {o["owner_code"] for o in owners},
        "every owner holds at least one unit at some point",
    )
    contiguous = no_open_gap = ordered = different = opens_early = True
    for plist in periods.values():
        plist.sort(key=lambda p: p[0])
        opens_early &= plist[0][0] <= date(2023, 6, 30) <= profile.window_start
        no_open_gap &= plist[-1][1] is None and all(p[1] is not None for p in plist[:-1])
        for a, b in zip(plist, plist[1:], strict=False):
            contiguous &= a[1] == b[0]
            ordered &= a[0] < a[1]
            different &= a[2] != b[2]
    check(contiguous, "ownership periods are contiguous: each ends the day the next begins")
    check(
        no_open_gap and ordered, "only the last period is open-ended, and every period has length"
    )
    check(
        different and opens_early,
        "the owner changes at each transfer, and the first period starts before the window opens",
    )
    transfers = [p for p in periods.values() if len(p) > 1]
    share = len(transfers) / len(periods)
    check(
        0.04 <= share <= 0.25,
        f"{share:.0%} of units change owner inside the window (planted for the owner dimension)",
    )
    check(
        all(profile.window_start <= p[1][0] <= profile.window_end for p in transfers),
        "every transfer date lies inside the window",
    )

    # ---- vendors
    trades = Counter(v["trade"] for v in vendors)
    check(
        sorted(trades) == sorted(ref.TRADES) and min(trades.values()) >= 2,
        "every trade has at least 2 vendors",
    )
    check(
        {v["rating"] for v in vendors} <= {"A", "B", "C"}
        and len({v["vendor_code"] for v in vendors}) == len(vendors),
        "vendor ratings are A, B or C; vendor codes are unique",
    )
    changed = [v for v in vendors if v["previous_rating"]]
    check(
        len(changed) >= 1
        and all(v["previous_rating"] != v["rating"] for v in changed)
        and all(
            profile.window_start <= to_date(v["rating_changed_on"]) <= profile.window_end
            for v in changed
        )
        and all(v["rating_changed_on"] is None for v in vendors if not v["previous_rating"]),
        f"{len(changed)} vendors changed rating inside the window (SCD2 test data for dim_vendor)",
    )

    # ---- SLA policy
    codes_ref = [c[0] for c in ref.MAINTENANCE_SUBCATEGORIES]
    base = [s for s in sla if to_date(s["valid_from"]) == gm.POLICY_START]
    check(
        sorted(s["subcategory_code"] for s in base) == sorted(codes_ref) and len(codes_ref) == 30,
        "30 subcategories each have an initial policy, equal to etl/reference_data.py",
    )
    check(
        {s["category_name"] for s in sla}
        == {"Plumbing", "Electrical", "HVAC", "Civil", "Pest control", "Other"},
        "6 maintenance categories",
    )
    newer = [s for s in sla if to_date(s["valid_from"]) != gm.POLICY_START]
    initial = {s["subcategory_code"]: s["default_sla_hours"] for s in base}
    check(
        len(newer) >= 1
        and all(s["default_sla_hours"] < initial[s["subcategory_code"]] for s in newer)
        and all(
            profile.window_start <= to_date(s["valid_from"]) <= profile.window_end for s in newer
        )
        and all(s["default_sla_hours"] > 0 for s in sla),
        f"{len(newer)} subcategories tighten their SLA inside the window (SCD2 test data)",
    )

    # ---- holidays
    days = [to_date(h["holiday_date"]) for h in holidays]
    check(
        days == sorted(set(days))
        and days[0] >= ref.CALENDAR_START
        and days[-1] <= ref.CALENDAR_END,
        "holidays are unique dates in order, inside the dim_date range",
    )
    check(
        all(bool(h["holiday_name"]) == bool(h["is_public_holiday"]) for h in holidays)
        and all(h["is_public_holiday"] or h["is_ramadan"] for h in holidays),
        "a holiday has a name exactly when it is public; every other row is a Ramadan day",
    )
    by_day = {to_date(h["holiday_date"]): h for h in holidays}
    check(
        all(date(y, 8, 14) in by_day for y in (2023, 2024, 2025, 2026))
        and by_day[date(2025, 3, 23)]["is_public_holiday"]
        and by_day[date(2025, 3, 23)]["is_ramadan"],
        "Independence Day is listed every year; Pakistan Day 2025 falls in Ramadan and is both",
    )
    ramadan_days = sum(bool(h["is_ramadan"]) for h in holidays)
    check(
        110 <= ramadan_days <= 120,
        f"4 Ramadan periods of 29 to 30 days are listed ({ramadan_days} days)",
    )
    check(
        all(isinstance(h["holiday_date"], (date, datetime)) for h in holidays),
        "holiday and policy dates are real Excel dates, not text",
    )


def main() -> int:
    print("=" * 70)
    print(" US-2.2 acceptance tests: master data and registers")
    print("=" * 70)
    model = load_model()
    with tempfile.TemporaryDirectory(prefix="lue_master_test_") as tmp:
        tmp = Path(tmp)
        runs = {}
        for name in ("small", "full"):
            started = time.perf_counter()
            runs[name] = (
                gd.run(cfg.get_profile(name), 3004, tmp / name),
                time.perf_counter() - started,
            )
        for name in ("small", "full"):
            try:
                run_checks(name.capitalize(), cfg.get_profile(name), tmp / name, model)
            except Exception as exc:  # a broken output must fail the test, not crash it
                check(False, f"{name}: the checks could not finish ({type(exc).__name__}: {exc})")

        print("Determinism and independence")
        again = gd.run(cfg.get_profile("small"), 3004, tmp / "again")
        check(
            again["files"] == runs["small"][0]["files"]
            and again["content_hash"] == runs["small"][0]["content_hash"],
            "same seed: identical hashes for every master-data file, workbook included",
        )
        check(
            (tmp / "again" / "s2" / "registers.xlsx").read_bytes()
            == (tmp / "small" / "s2" / "registers.xlsx").read_bytes(),
            "same seed: the workbook is byte-identical (no save-time stamp)",
        )
        other = gd.run(cfg.get_profile("small"), 3005, tmp / "other")
        differing = [
            k
            for k in other["files"]
            if k.startswith(("s1/", "s2/")) and other["files"][k] != again["files"][k]
        ]
        check(
            {"s1/units.csv", "s1/tenants.csv", "s2/registers.xlsx", "s1/buildings.csv"}
            <= set(differing),
            "a different seed changes the buildings, units, tenants and workbook",
        )
        check(
            not {"s1/charge_types.csv", "s1/payment_methods.csv"} & set(differing),
            "fixed reference tables do not depend on the seed",
        )
        check(
            "logical_hash_files" in again and again["logical_hash_files"] == ["s2/registers.xlsx"],
            "the manifest marks the workbook as hashed by content",
        )
        check(
            runs["small"][1] < 60 and runs["full"][1] < 60,
            f"both profiles generate in under a minute "
            f"(small {runs['small'][1]:.1f}s, full {runs['full'][1]:.1f}s)",
        )
        check(
            gm.allocate(10, [1, 1, 1], 0) == [4, 3, 3]
            and gm.allocate(7, [0.7, 0.2, 0.1], 1) == [4, 2, 1]
            and sum(gm.allocate(1800, [0.4, 0.25, 0.2, 0.15], 1)) == 1800,
            "the allocation helper always sums to the total and honours the minimum",
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
