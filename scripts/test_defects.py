#!/usr/bin/env python3
"""Acceptance tests for US-2.6 (planted defects, answer key, planted patterns). No database needed.

    python scripts/test_defects.py

For the small and the full profile it generates the data twice into temporary folders: once
without the last stage (the files as the earlier stages wrote them) and once with it. Every
difference between the two must be a row of the answer key, every row of the answer key must be
a real difference of the kind it names, and nothing else may change. Then: the defect counts
follow the configured rates, S1 still loads into src_pms (types, widths, primary keys of the frozen
source ERD), the clean control batch has no defect, the answer key is reproducible, and the six
planted patterns show their expected effect (scripts/check_patterns.py, pandas).
"""

import csv
import dataclasses
import importlib.util
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import etl.gen_defects as gdf  # noqa: E402
import etl.gen_master as gm  # noqa: E402
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402
from etl import patterns as pat  # noqa: E402

results: list[bool] = []
STAGE = "defects_answer_key"
S1_TABLES = (
    "buildings", "units", "tenants", "charge_types", "payment_methods", "leases", "lease_events",
    "invoices", "invoice_lines", "payments", "payment_allocations",
)  # fmt: skip
# How the answer key names a record of each S1 table (its primary key, or the row's position for
# the allocations, whose key contains the column an orphan changes).
S1_IDENT = {
    "buildings": ("building_code",),
    "units": ("unit_id",),
    "lease_events": ("event_id",),
    "payment_allocations": ("payment_reference", "invoice_number", "line_no"),
}
DERIVED = {"late_arriving_tenant_reference", "mid_lease_rent_change", "tenant_attribute_change"}


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


def rows_of(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def dicts_of(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run_without_defects(profile, seed: int, out: Path) -> None:
    """The files exactly as the stages before US-2.6's wrote them."""
    saved = dict(gd.STAGES)
    try:
        del gd.STAGES[STAGE]
        gd.run(profile, seed, out)
    finally:
        gd.STAGES.clear()
        gd.STAGES.update(saved)


def is_iso_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
        return len(text) == 10
    except ValueError:
        return False


def fits(erd_type: str, value: str) -> bool:
    """Would COPY ... NULL '' accept this text for a column of this type?"""
    if value == "":
        return True
    t = erd_type.upper()
    try:
        if t.startswith(("VARCHAR(", "CHAR(")):
            return len(value) <= int(re.search(r"\((\d+)\)", t).group(1))
        if t in ("INT", "SMALLINT"):
            return -(2**15 if t == "SMALLINT" else 2**31) <= int(value) < 2**31
        if t.startswith("NUMERIC("):
            p, s = (int(x) for x in t[8:-1].split(","))
            d = Decimal(value)
            return d == d.quantize(Decimal(1).scaleb(-s)) and abs(d) < Decimal(10) ** (p - s)
        if t == "DATE":
            return is_iso_date(value)
        if t == "TIMESTAMP":
            datetime.fromisoformat(value)
            return True
        if t == "BOOLEAN":
            return value in ("true", "false")
    except (ValueError, InvalidOperation):
        return False
    return False


def expected_count(rate: float, rows: int) -> int:
    """The documented rule, written out again here (not imported) so the test can catch it."""
    n = int(round(rate * rows)) if rate > 0 else 0
    return 1 if rate > 0 and n == 0 and rows >= 20 else n


def text_variant_of(new: str, old: str) -> bool:
    return new != old and new.strip().casefold() == old.casefold()


# ----------------------------------------------------------------------------- one profile
def run_checks(label: str, profile, before: Path, after: Path, model) -> dict:
    print(f"{label} profile ({profile.buildings} buildings, {profile.units} units)")
    ws, we = profile.window_start, profile.window_end
    rates = profile.defect_rates
    manifest = json.loads((after / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
    key_path = after / "answer_key" / "defects_answer_key.csv"
    header, raw = rows_of(key_path)
    key = [dict(zip(header, r, strict=True)) for r in raw]

    print("  The answer key")
    check(manifest["stages"][-1] == STAGE, "the defects_answer_key stage runs last")
    check(header == gdf.KEY_COLS, "defects_answer_key.csv has the documented columns")
    check(
        [k["defect_id"] for k in key] == [f"D-{i:05d}" for i in range(1, len(key) + 1)],
        f"{len(key):,} defects, numbered D-00001 onwards without a gap",
    )
    records = Counter((k["source"], k["table"], k["record_id"]) for k in key)
    check(
        all(n == 1 for n in records.values()),
        "one defect per record: no record appears twice in the key",
    )
    types = {k["defect_type"] for k in key}
    check(
        types == set(cfg.DEFECT_RATES),
        f"all {len(cfg.DEFECT_RATES)} defect types of the configuration are planted",
    )
    expected_handling = all(
        (k["expected_handling"], k["expected_rule"])
        == (
            gdf.S3_ORPHAN
            if (k["source"], k["defect_type"]) == ("S3", "orphan_reference")
            else gdf.HANDLING[k["defect_type"]]
        )
        for k in key
    )
    check(expected_handling, "each row carries its type's expected handling and rule")
    check(
        {k["expected_handling"] for k in key} <= {"reject", "warn", "repair", "accept"},
        "expected handling is reject, warn, repair or accept",
    )
    summary = dicts_of(after / "answer_key" / "summary.csv")
    by_group = Counter((k["defect_type"], k["source"], k["table"]) for k in key)
    check(
        {(s["defect_type"], s["source"], s["table"]): int(s["count"]) for s in summary}
        == dict(by_group),
        "summary.csv counts every (type, source, table) of the key",
    )
    totals = {(t["defect_type"], t["expected_handling"]): int(t["count"]) for t in
              dicts_of(after / "answer_key" / "totals.csv")}  # fmt: skip
    check(
        totals[("all", "all")] == len(key)
        and totals[("all", "reject")] == sum(k["expected_handling"] == "reject" for k in key),
        f"totals.csv: {totals[('all', 'all')]:,} defects, {totals[('all', 'reject')]:,} to reject",
    )

    keyed = defaultdict(dict)  # (source, table) -> record id -> key row
    for k in key:
        keyed[(k["source"], k["table"])][k["record_id"]] = k

    # ---- S1
    print("  S1: every change is in the key, every key row is a change")
    s1_before = {t: rows_of(before / "s1" / f"{t}.csv") for t in S1_TABLES}
    s1_after = {t: rows_of(after / "s1" / f"{t}.csv") for t in S1_TABLES}
    lease_numbers = {r[0] for r in s1_before["leases"][1]}
    line_keys = {(r[0], r[1]) for r in s1_before["invoice_lines"][1]}
    exact = True
    detail_ok = True
    for table in S1_TABLES:
        if table == "tenants":
            continue
        cols, b_rows = s1_before[table]
        _c, a_rows = s1_after[table]
        if len(a_rows) != len(b_rows):
            exact = False
            continue
        col = {c: i for i, c in enumerate(cols)}
        ident = S1_IDENT.get(table)
        changed = {}
        for b, a in zip(b_rows, a_rows, strict=True):
            if a != b:
                rid = "|".join(b[col[c]] for c in ident) if ident else "?"
                changed[rid] = (b, a)
        planted = {
            r: k
            for r, k in keyed[("S1", table)].items()
            if k["defect_type"] not in DERIVED
        }
        exact &= set(changed) == set(planted)
        for rid, (b, a) in changed.items():
            k = planted.get(rid)
            if k is None:
                continue
            i = col[k["column"]]
            d = k["defect_type"]
            if d == "null_required_value":
                detail_ok &= a[i] == "" and b[i] != ""
            elif d == "out_of_range_date":
                detail_ok &= is_iso_date(a[i]) and not ws <= date.fromisoformat(a[i]) <= we
            elif d == "orphan_reference" and table == "lease_events":
                detail_ok &= a[i] not in lease_numbers
            elif d == "orphan_reference":
                detail_ok &= (a[i], a[col["line_no"]]) not in line_keys
            elif d == "inconsistent_text":
                detail_ok &= text_variant_of(a[i], b[i])
            else:
                detail_ok = False
            detail_ok &= [x for j, x in enumerate(a) if j != i] == [
                x for j, x in enumerate(b) if j != i
            ]
    check(exact, "S1: the changed rows are exactly the key's S1 rows (no more, no fewer)")
    check(detail_ok, "S1: each change is the named defect in the named column, nothing else")

    t_cols, t_before = s1_before["tenants"]
    _c, t_after = s1_after["tenants"]
    _c, late_rows = rows_of(after / "s1" / "late_arriving" / "tenants.csv")
    late = {r[0] for r in late_rows}
    by_code = {r[0]: r for r in t_before}
    check(
        {r[0] for r in t_after} == set(by_code) - late
        and all(r == by_code[r[0]] for r in t_after)
        and all(r == by_code[r[0]] for r in late_rows),
        f"{len(late)} late-arriving tenants moved, unchanged, from s1/tenants.csv to "
        "s1/late_arriving/tenants.csv; every other tenant row is untouched",
    )
    late_refs = {
        (k["table"], k["record_id"])
        for k in key
        if k["defect_type"] == "late_arriving_tenant_reference"
    }
    wanted = {("leases", r[0]) for r in s1_before["leases"][1] if r[2] in late} | {
        ("payments", r[0]) for r in s1_before["payments"][1] if r[1] in late
    }
    check(
        late_refs == wanted and len(late) >= 1,
        f"every lease and payment of a late tenant is keyed ({len(wanted)} rows, flagged warn)",
    )
    _c, changes = rows_of(after / "s1" / "changes" / "tenants.csv")
    change_keys = {k["record_id"]: k for k in key if k["defect_type"] == "tenant_attribute_change"}
    tracked = {t_cols.index("employer_sector"), t_cols.index("contact_channel")}
    upd = t_cols.index("updated_at")
    ok = len(changes) == len(change_keys) >= 1
    for r in changes:
        base = by_code.get(r[0])
        k = change_keys.get(r[0])
        if base is None or k is None or r[0] in late:
            ok = False
            continue
        diff = {i for i, (x, y) in enumerate(zip(base, r, strict=True)) if x != y}
        moment = datetime.fromisoformat(r[upd])
        ok &= (
            diff - {upd} == {t_cols.index(k["column"])}
            and diff - {upd} <= tracked
            and moment > datetime.fromisoformat(base[upd])
            and datetime.combine(ws, datetime.min.time()) <= moment
            and moment.date() <= we - timedelta(days=gdf.EDGE_DAYS)
        )
    check(
        ok,
        f"{len(changes)} tenant changes in s1/changes/tenants.csv: one tracked attribute and "
        "updated_at each, dated inside the window after the record existed (SCD2 test data)",
    )

    lease_rent = {r[0]: int(Decimal(r[6]) * 100) for r in s1_after["leases"][1]}
    inv_lease = {r[0]: r[1] for r in s1_after["invoices"][1]}
    off_rent = {
        f"{r[0]}|{r[1]}"
        for r in s1_after["invoice_lines"][1]
        if r[2] == "RENT" and int(Decimal(r[3]) * 100) != lease_rent[inv_lease[r[0]]]
    }
    mid = {k["record_id"] for k in key if k["defect_type"] == "mid_lease_rent_change"}
    raised = all(
        int(Decimal(r[3]) * 100) > lease_rent[inv_lease[r[0]]]
        for r in s1_after["invoice_lines"][1]
        if f"{r[0]}|{r[1]}" in mid
    )
    check(
        mid == off_rent and raised and len(mid) >= 1,
        f"mid-lease rent changes: exactly the {len(mid)} keyed rent lines bill more than the "
        "lease rent (and the tenants were billed and paid that)",
    )

    erd = model.SOURCE_ERD
    loadable = True
    for table in S1_TABLES:
        cols, rows = s1_after[table]
        types = {name: typ for typ, name, _k in erd[table]}
        loadable &= cols == [name for _t, name, _k in erd[table]]
        loadable &= all(fits(types[c], v) for r in rows for c, v in zip(cols, r, strict=True))
        pk = [cols.index(name) for _t, name, k in erd[table] if "PK" in k]
        keys = [tuple(r[i] for i in pk) for r in rows]
        loadable &= len(set(keys)) == len(keys) and all(all(x for x in kk) for kk in keys)
    check(
        loadable,
        "S1 still loads into src_pms: every value fits its ERD type and width, primary keys "
        "stay unique and filled",
    )

    # ---- S3
    print("  S3 settlement files")

    def settlement_lines(folder: Path) -> dict:
        out = defaultdict(list)
        for p in sorted((folder / "s3").glob("settlement_*.csv")):
            channel, day = p.stem[len("settlement_"):].rsplit("_", 1)
            for r in rows_of(p)[1]:
                out[f"{channel}:{r[0]}"].append((day, r))
        return out

    sb, sa = settlement_lines(before), settlement_lines(after)
    pay_refs = {r[0] for r in s1_after["payments"][1]}
    changed = {i for i in set(sa) | set(sb) if sa.get(i) != sb.get(i)}
    planted = keyed[("S3", "settlements")]
    check(set(changed) == set(planted), "S3: the changed lines are exactly the key's S3 rows")
    ok = True
    for rid, k in planted.items():
        b, a = sb.get(rid, []), sa.get(rid, [])
        d = k["defect_type"]
        if d == "duplicate_settlement_line":
            ok &= len(b) == 1 and a == b + b
        elif d == "late_arriving_payment":
            if len(b) != 1 or len(a) != 1:
                ok = False
                continue
            (bday, brow), (aday, arow) = b[0], a[0]
            lag = (date.fromisoformat(aday) - date.fromisoformat(bday)).days
            ok &= (
                5 <= lag <= 20  # written out, not imported, so a change to the code is caught
                and arow[3] == aday
                and arow[:3] + arow[4:] == brow[:3] + brow[4:]
            )
        elif d == "orphan_reference":
            ok &= not b and len(a) == 1 and a[0][1][1] not in pay_refs
        else:
            ok = False
    check(ok, "S3: duplicates are exact copies, late lines arrive 5 to 20 days later, unmatched "
          "lines name no real payment")  # fmt: skip
    repeated = {i for i, v in sa.items() if len(v) > 1}
    dups = {r for r, k in planted.items() if k["defect_type"] == "duplicate_settlement_line"}
    check(
        repeated == dups,
        "S3 natural key (channel + settlement_id) is unique except the planted duplicates",
    )

    # ---- S4
    print("  S4 tickets")
    tb = json.loads((before / "s4" / "tickets.json").read_text(encoding="utf-8"))
    ta = json.loads((after / "s4" / "tickets.json").read_text(encoding="utf-8"))
    one = {t["ticket_id"]: t for t in tb["tickets"]}
    copies = defaultdict(list)
    for t in ta["tickets"]:
        copies[t["ticket_id"]].append(t)
    changed = {i for i in one if copies.get(i) != [one[i]]} | (set(copies) - set(one))
    planted = keyed[("S4", "tickets")]
    check(set(changed) == set(planted), "S4: the changed tickets are exactly the key's S4 rows")
    unit_nos = defaultdict(set)
    for r in s1_after["units"][1]:
        unit_nos[r[1]].add(r[2])
    ok = ta["export"]["ticket_count"] == len(ta["tickets"])
    for rid, k in planted.items():
        b, got = one[rid], copies[rid]
        d = k["defect_type"]
        if d == "exact_duplicate":
            ok &= got == [b, b]
            continue
        if d == "conflicting_duplicate":
            other = [t for t in got if t != b]
            ok &= len(got) == 2 and len(other) == 1
            if len(other) == 1:
                h = other[0]["status_history"]
                ok &= (
                    0 < len(h) < len(b["status_history"])
                    and h == b["status_history"][: len(h)]
                    and other[0]["status"] == h[-1]["status"]
                )
            continue
        if len(got) != 1:
            ok = False
            continue
        a = got[0]
        diff = {c for c in b if a[c] != b[c]}
        if d == "null_required_value":
            ok &= diff == {"unit_no"} and a["unit_no"] is None
        elif d == "orphan_reference":
            ok &= diff == {"unit_no"} and a["unit_no"] not in unit_nos[a["building_code"]]
        elif d == "inconsistent_text":
            ok &= len(diff) == 1 and text_variant_of(a[k["column"]], b[k["column"]])
        elif d == "wrong_data_type":
            ok &= diff == {"estimate"} and isinstance(a["estimate"], str)
        elif d == "out_of_range_date":
            ok &= (
                diff == {"status_history"}
                and a["status_history"][0]["at"].startswith("1970-01-01T")
                and a["status_history"][1:] == b["status_history"][1:]
            )
        else:
            ok = False
    check(ok, "S4: each changed ticket shows the named defect (copies, removed or unknown unit, "
          "text, a number as text, a 1970 raise time)")  # fmt: skip

    # ---- S6
    print("  S6 incentive log")
    c6, lb = rows_of(before / "s6" / "incentive_log.csv")
    _c, la = rows_of(after / "s6" / "incentive_log.csv")
    col = {c: i for i, c in enumerate(c6)}

    def rid6(r):
        return "|".join(r[col[c]] for c in ("building_code", "unit_no", "offer_code", "start_date"))

    planted = keyed[("S6", "incentive_log")]
    seen, j, ok = set(), 0, True
    for i, a in enumerate(la):
        dup = planted.get(rid6(a), {}).get("defect_type") == "exact_duplicate"
        if i and a == la[i - 1] and dup:
            seen.add(rid6(a))
            continue
        if j >= len(lb):
            ok = False
            break
        b = lb[j]
        j += 1
        if a == b:
            continue
        k = planted.get(rid6(b))
        if k is None:
            ok = False
            continue
        seen.add(rid6(b))
        d = k["defect_type"]
        diff = {c for c in c6 if a[col[c]] != b[col[c]]}
        if d == "null_required_value":
            ok &= diff == {"offer_code"} and a[col["offer_code"]] == ""
        elif d == "inconsistent_text":
            ok &= diff == {"start_date"} and datetime.strptime(
                a[col["start_date"]], "%d/%m/%Y"
            ).date() == date.fromisoformat(b[col["start_date"]])
        elif d == "wrong_data_type":
            ok &= diff == {"end_date"} and not is_iso_date(a[col["end_date"]])
        elif d == "out_of_range_date":
            ok &= diff == {"start_date", "end_date"} and all(
                is_iso_date(a[col[c]]) and date.fromisoformat(a[col[c]]) < ws for c in diff
            )
        else:
            ok = False
    ok &= j == len(lb)
    check(
        ok and seen == set(planted),
        f"S6: the {len(planted)} keyed rows are the only changes, each the named defect",
    )

    # ---- counts follow the rates
    print("  Counts follow the configured rates")
    sizes = {("S1", t): len(s1_before[t][1]) for t in S1_TABLES}
    sizes[("S3", "settlements")] = sum(len(v) for v in sb.values())
    sizes[("S4", "tickets")] = len(tb["tickets"])
    sizes[("S6", "incentive_log")] = len(lb)
    ok = True
    for (d, source, table), n in by_group.items():
        if d in ("late_arriving_tenant_reference", "mid_lease_rent_change"):
            continue
        total = sizes[(source, "tenants" if d == "tenant_attribute_change" else table)]
        ok &= n == expected_count(rates[d], total)
    late_want = expected_count(rates["late_arriving_tenant_reference"], len(t_before))
    check(
        ok and len(late) == late_want,
        "every (type, table) count is round(rate x rows), at least 1 in a table of 20+ rows",
    )

    # ---- expectations for the later stories
    print("  expectations.json")
    exp = json.loads((after / "answer_key" / "expectations.json").read_text(encoding="utf-8"))
    electronic = {
        r[0] for r in s1_after["payments"][1] if r[3] in ("BANK", "RAAST", "JAZZ", "EASY")
        and r[5] == "Cleared"
    }  # fmt: skip
    settled_before = {r[1] for v in sb.values() for _day, r in v}
    orphans = sum(k["defect_type"] == "orphan_reference" for k in planted_values(keyed, "S3"))
    m = exp["matching_us_5_2"]
    check(
        m["unmatched_settlements"] == m["unmatched_settlement_references"] == orphans
        and m["unsettled_electronic_payments"] == len(electronic - settled_before),
        f"US-5.2 numbers: {orphans} unmatched settlements, "
        f"{m['unsettled_electronic_payments']} unsettled electronic payments (as before US-2.6)",
    )
    check(
        exp["inferred_tenants_us_6_5"] == len(late)
        and sorted(exp["late_tenant_codes"]) == sorted(late)
        and exp["tenant_scd2_versions_us_6_2"] == len(changes)
        and exp["mid_lease_rent_change_lines"] == len(mid),
        "US-6.5 inferred tenants, US-6.2 SCD2 versions and the rent lines match the files",
    )
    check(
        sum(exp["quarantine_by_check"].values())
        == sum(k["expected_handling"] == "reject" for k in key)
        and sum(exp["warnings_by_check"].values())
        == sum(k["expected_handling"] == "warn" for k in key),
        "quarantine and warning counts per check add up to the key (US-4.4)",
    )
    master = gm.build_master(profile, gd.Context(profile, manifest["seed"], after).rng)
    chosen = json.loads((after / "answer_key" / "planted_patterns.json").read_text("utf-8"))
    check(
        chosen == json.loads(json.dumps(pat.describe(master), sort_keys=True))
        and chosen["high_arrears_building"]["building_code"]
        in {b.code for b in master["buildings"]}
        and chosen["slow_vendor"]["vendor_code"] in {v["vendor_code"] for v in master["vendors"]},
        "planted_patterns.json names a real building, vendor and city, as etl/patterns.py chose",
    )
    check(
        (after / "answer_key" / "planted_patterns.md").read_text("utf-8").startswith(
            "# Planted business patterns"
        ),
        "planted_patterns.md is written next to the answer key",
    )
    check(
        manifest["inputs"]["data/weather_cache.json"]
        == gd.sha256_file(ROOT / "data" / "weather_cache.json"),
        "the manifest records the weather cache the rain-driven leaks were read from",
    )
    return {"key": key, "manifest": manifest}


def planted_values(keyed: dict, source: str):
    return [k for (s, _t), rows in keyed.items() if s == source for k in rows.values()]


def key_rows(folder: Path) -> list[list[str]]:
    return rows_of(folder / "answer_key" / "defects_answer_key.csv")[1]


def main() -> int:
    print("=" * 70)
    print(" US-2.6 acceptance tests: planted defects, answer key, patterns")
    print("=" * 70)
    model = load_model()
    seed = cfg.DEFAULT_SEED
    with tempfile.TemporaryDirectory(prefix="lue_defects_") as tmp_name:
        tmp = Path(tmp_name)
        small, full = cfg.get_profile("small"), cfg.get_profile("full")
        for name, profile in (("small", small), ("full", full)):
            run_without_defects(profile, seed, tmp / f"{name}_before")
            gd.run(profile, seed, tmp / name)
            run_checks(name.capitalize(), profile, tmp / f"{name}_before", tmp / name, model)

        print("Clean control batch (every rate 0, US-4.4)")
        clean = cfg.clean_profile(full)
        gd.run(clean, seed, tmp / "clean")
        _c, late = rows_of(tmp / "clean" / "s1" / "late_arriving" / "tenants.csv")
        _c, changes = rows_of(tmp / "clean" / "s1" / "changes" / "tenants.csv")
        check(
            not key_rows(tmp / "clean") and not late and not changes,
            "no defect is planted: the answer key, the late tenants and the changes are empty",
        )
        same = all(
            (tmp / "clean" / f).read_bytes() == (tmp / "full_before" / f).read_bytes()
            for f in ("s4/tickets.json", "s6/incentive_log.csv", "s1/tenants.csv")
        )
        check(same, "the clean batch has the tickets, offers and tenants of the run before US-2.6")
        exp = json.loads((tmp / "clean" / "answer_key" / "expectations.json").read_text("utf-8"))
        check(
            exp["records_with_a_defect"] == 0
            and exp["matching_us_5_2"]["unmatched_settlements"] == 0,
            "its expectations: 0 defects, 0 unmatched settlements (only the unsettled payments)",
        )

        print("Reproducibility and configurable rates")
        gd.run(small, seed, tmp / "again")
        same = all(
            (tmp / "small" / "answer_key" / f).read_bytes()
            == (tmp / "again" / "answer_key" / f).read_bytes()
            for f in ("defects_answer_key.csv", "summary.csv", "totals.csv", "expectations.json")
        )
        check(same, "same seed: byte-identical answer key and totals (plan acceptance)")
        gd.run(small, seed + 1, tmp / "other")
        check(
            key_rows(tmp / "other") != key_rows(tmp / "small"),
            "a different seed plants different defects",
        )
        doubled = dataclasses.replace(
            full, defect_rates=full.defect_rates | {"exact_duplicate": 0.02}
        )
        gd.run(doubled, seed, tmp / "doubled")

        def counts(folder: Path) -> Counter:
            return Counter((r[5], r[1], r[2]) for r in key_rows(folder))

        a, b = counts(tmp / "full"), counts(tmp / "doubled")
        dup_a = {g: n for g, n in a.items() if g[0] == "exact_duplicate"}
        dup_b = {g: n for g, n in b.items() if g[0] == "exact_duplicate"}
        check(
            all(abs(dup_b[g] - 2 * n) <= 1 for g, n in dup_a.items())
            and {g: n for g, n in a.items() if g[0] != "exact_duplicate"}
            == {g: n for g, n in b.items() if g[0] != "exact_duplicate"},
            f"doubling one rate doubles that defect ({sum(dup_a.values())} -> "
            f"{sum(dup_b.values())} exact duplicates) and leaves every other count alone",
        )

        saved_cache = pat.WEATHER_CACHE
        pat.WEATHER_CACHE = tmp / "no_such_cache.json"
        try:
            gd.run(small, seed, tmp / "nocache")
            message = ""
        except gd.GeneratorError as exc:
            message = str(exc)
        finally:
            pat.WEATHER_CACHE = saved_cache
        check(
            "git checkout data/weather_cache.json" in message,
            "without the committed weather cache the generator stops with a clear message",
        )

        print("Planted patterns (scripts/check_patterns.py, pandas, clean full profile)")
        import check_patterns as cp

        for r in cp.measure(tmp / "clean"):
            ratio = f"{r.value:.2f}" if r.value == r.value else "n/a"
            check(r.ok, f"{r.number} {r.pattern}: ratio {ratio}; {r.measured}")

    print("=" * 70)
    print(
        f" RESULT: {sum(results)}/{len(results)} checks passed"
        + ("" if results and all(results) else " - FAILED")
    )
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
