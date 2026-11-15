#!/usr/bin/env python3
"""Acceptance tests for US-2.4 (payments, allocations, invoice status, bank and wallet settlements).

    python scripts/test_payments.py

No database needed. Generates the small and the full profile into temporary folders and checks the
S1 payment files and the S3 settlement files against the plan's acceptance criteria, the frozen
Phase 1 pack (columns and widths come from docs/phase1/tools/model.py) and the contracts written
in etl/gen_payments.py.
"""

import csv
import importlib.util
import itertools
import re
import statistics
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
import etl.gen_payments as gp  # noqa: E402
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402

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
    spec.loader.exec_module(module)
    return module


def width(sql_type: str):
    m = re.match(r"(?:VAR)?CHAR\((\d+)\)", sql_type)
    return int(m.group(1)) if m else None


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def paisa(text: str) -> int:
    sign = -1 if text.startswith("-") else 1
    whole, _, frac = text.lstrip("-").partition(".")
    return sign * (int(whole) * 100 + int(frac.ljust(2, "0")))


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def run_checks(label: str, profile: cfg.Profile, out: Path, model) -> None:
    print(f"{label} profile ({profile.buildings} buildings, {profile.units} units)")
    erd = model.SOURCE_ERD
    ws, we = profile.window_start, profile.window_end
    loose = profile.name == "small"
    manifest = gd.json.loads((out / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
    check(
        manifest["stages"].index("payments") > manifest["stages"].index("leases_invoices"),
        "the payments stage ran after the leases stage",
    )

    tables = {}
    for table in ("payments", "payment_allocations"):
        path = out / "s1" / f"{table}.csv"
        with path.open(encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        tables[table] = read_csv(path)
        check(
            header == [c[1] for c in erd[table]],
            f"s1/{table}.csv: columns equal src_pms.{table} in the Phase 1 source ERD",
        )
    pays, allocs = tables["payments"], tables["payment_allocations"]
    wide = [
        (t, n)
        for t in tables
        for sql_type, n, _k in erd[t]
        if width(sql_type) and any(len(r[n] or "") > width(sql_type) for r in tables[t])
    ]
    check(not wide, "every text value fits its column width in the source ERD")
    check(
        all(re.fullmatch(r"-?\d+\.\d\d", r["amount"]) for r in pays)
        and all(re.fullmatch(r"-?\d+\.\d\d", r["allocated_amount"]) for r in allocs)
        and all(re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", r["paid_at"]) for r in pays),
        "amounts have two decimals; paid_at is a timestamp",
    )

    invoices = read_csv(out / "s1" / "invoices.csv")
    lines = read_csv(out / "s1" / "invoice_lines.csv")
    leases = {r["lease_number"]: r for r in read_csv(out / "s1" / "leases.csv")}
    tenants = {t["tenant_code"]: t for t in read_csv(out / "s1" / "tenants.csv")}
    methods = {r["method_code"] for r in read_csv(out / "s1" / "payment_methods.csv")}
    inv_by_no = {r["invoice_number"]: r for r in invoices}
    line_net = {(r["invoice_number"], int(r["line_no"])): paisa(r["net_amount"]) for r in lines}
    invoice_total = defaultdict(int)
    for (number, _n), net in line_net.items():
        invoice_total[number] += net
    owner_of = {n: leases[r["lease_number"]]["tenant_code"] for n, r in inv_by_no.items()}

    # ---- payments
    refs = [r["payment_reference"] for r in pays]
    paid_at = [datetime.fromisoformat(r["paid_at"]) for r in pays]
    check(
        len(set(refs)) == len(refs) and len(pays) > 0,
        f"{len(pays)} payments with unique references",
    )
    check(
        refs == [f"PAY-{i:07d}" for i in range(1, len(refs) + 1)] and paid_at == sorted(paid_at),
        "references run PAY-0000001.. in order of paid_at",
    )
    check(
        all(r["tenant_code"] in tenants for r in pays)
        and {r["method_code"] for r in pays} <= methods,
        "every payment names an existing tenant and a payment method",
    )
    check(
        all(ws <= p.date() <= we for p in paid_at),
        f"every payment is dated inside the window ({ws} to {we})",
    )
    check(
        all(
            p.date() >= datetime.fromisoformat(tenants[r["tenant_code"]]["updated_at"]).date()
            for r, p in zip(pays, paid_at, strict=True)
        ),
        "no payment is dated before its tenant's record",
    )
    check(
        {r["status"] for r in pays} <= {"Cleared", "Bounced"}
        and all((paisa(r["amount"]) < 0) == (r["status"] == "Bounced") for r in pays)
        and all(paisa(r["amount"]) != 0 for r in pays),
        "Cleared payments are positive; Bounced payments are negative reversals",
    )
    by_ref = {r["payment_reference"]: r for r in pays}
    reversals = [r for r in pays if r["status"] == "Bounced"]
    original_use = Counter(r["reversal_of"] for r in reversals)
    ok = True
    for r in reversals:
        o = by_ref.get(r["reversal_of"])
        ok &= (
            o is not None
            and o["status"] == "Cleared"
            and o["tenant_code"] == r["tenant_code"]
            and o["method_code"] == "CHEQUE" == r["method_code"]
            and paisa(o["amount"]) == -paisa(r["amount"])
            and 3
            <= (date.fromisoformat(r["paid_at"][:10]) - date.fromisoformat(o["paid_at"][:10])).days
            <= 7
        )
    check(
        ok
        and all(c == 1 for c in original_use.values())
        and all(not r["reversal_of"] for r in pays if r["status"] == "Cleared"),
        f"{len(reversals)} bounced cheques: each reverses one earlier cheque of the same tenant "
        f"for the same amount, 3 to 7 days later",
    )
    share = len(reversals) / max(
        1, sum(r["method_code"] == "CHEQUE" and r["status"] == "Cleared" for r in pays)
    )
    check(
        0.0 < share < 0.15 if not loose else share < 0.20,
        f"bounced cheques are {share:.1%} of cheques",
    )
    method_mix = Counter(r["method_code"] for r in pays if r["status"] == "Cleared")
    check(
        set(method_mix) == methods or loose,
        f"all six payment methods are used ({dict(method_mix)})",
    )

    # ---- allocations
    keys = [(r["payment_reference"], r["invoice_number"], int(r["line_no"])) for r in allocs]
    check(
        len(set(keys)) == len(keys) and keys == sorted(keys),
        f"{len(allocs)} allocations, key unique",
    )
    check(
        all(r["payment_reference"] in by_ref for r in allocs)
        and all((r["invoice_number"], int(r["line_no"])) in line_net for r in allocs),
        "every allocation names an existing payment and an existing invoice line",
    )
    alloc_sum = defaultdict(int)
    for r in allocs:
        alloc_sum[r["payment_reference"]] += paisa(r["allocated_amount"])
    check(
        all(alloc_sum[r["payment_reference"]] == paisa(r["amount"]) for r in pays)
        and all(
            (paisa(a["allocated_amount"]) < 0)
            == (by_ref[a["payment_reference"]]["status"] == "Bounced")
            for a in allocs
        ),
        "a payment's amount is exactly the sum of its allocations (negative for a reversal)",
    )
    per_pay_invoices = defaultdict(set)
    for r in allocs:
        per_pay_invoices[r["payment_reference"]].add(r["invoice_number"])
    check(
        all(len(v) == 1 for v in per_pay_invoices.values())
        and all(
            owner_of[next(iter(per_pay_invoices[r["payment_reference"]]))] == r["tenant_code"]
            for r in pays
        ),
        "each payment pays one invoice, and an invoice of the tenant who paid",
    )
    check(
        all(
            paid_at_of.date()
            >= datetime.fromisoformat(
                inv_by_no[r["invoice_number"]]["invoice_date"] + "T00:00:00"
            ).date()
            for r in allocs
            for paid_at_of in [datetime.fromisoformat(by_ref[r["payment_reference"]]["paid_at"])]
        ),
        "no payment is dated before the invoice it pays was issued",
    )
    line_paid = defaultdict(int)
    for r in allocs:
        line_paid[(r["invoice_number"], int(r["line_no"]))] += paisa(r["allocated_amount"])
    check(
        all(0 <= v <= line_net[k] for k, v in line_paid.items()),
        "ACCEPTANCE: no invoice line is ever paid more than its net amount (after reversals)",
    )
    lines_per_payment = Counter(
        sum(1 for _ in g)
        for _k, g in itertools.groupby(allocs, key=lambda r: r["payment_reference"])
    )
    check(
        any(n > 1 for n in lines_per_payment),
        f"one payment is split across several invoice lines "
        f"({dict(sorted(lines_per_payment.items()))})",
    )

    # ---- invoice status as at the end of the window
    invoice_paid = defaultdict(int)
    for (number, _n), v in line_paid.items():
        invoice_paid[number] += v
    status_ok = True
    for number, r in inv_by_no.items():
        paid = invoice_paid.get(number, 0)
        want = "Paid" if paid == invoice_total[number] else "Partial" if paid > 0 else "Overdue"
        status_ok &= r["status"] == want
    check(
        status_ok,
        "invoice status: Paid when fully allocated, Partial when part-paid, Overdue when unpaid",
    )
    mix = Counter(r["status"] for r in invoices)
    billed = sum(invoice_total.values())
    collected = sum(invoice_paid.values())
    rate = collected / billed
    check(
        0.88 <= rate <= 0.99 and mix["Overdue"] > 0 and mix["Partial"] > 0,
        f"collection rate {rate:.1%} of billed; {mix['Paid']} Paid, {mix['Partial']} Partial, "
        f"{mix['Overdue']} Overdue invoices",
    )
    tolerance = 0.25 if loose else 0.10
    check(
        abs(len(pays) / profile.target_payments - 1) <= tolerance,
        f"{len(pays):,} payments against a target of {profile.target_payments:,} (within "
        f"{tolerance:.0%})",
    )

    # ---- behaviour profiles, through the object API that rebuilds the same data
    ctx = gd.Context(profile, manifest["seed"], out)
    master = gm.build_master(profile, ctx.rng)
    billing = gl.build_billing(profile, master, ctx.rng)
    built = gp.build_payments(profile, master, billing, ctx.rng)
    check(
        [p.reference for p in built.pays] == refs and built.payment_rows[0][0] == refs[0],
        "build_payments() rebuilds exactly the payments in the files",
    )
    due = {r["invoice_number"]: date.fromisoformat(r["due_date"]) for r in invoices}
    late = defaultdict(list)
    unpaid = Counter()
    seen = Counter()
    first_paid = {}
    for r in allocs:
        pay = by_ref[r["payment_reference"]]
        if pay["status"] == "Cleared" and r["invoice_number"] not in first_paid:
            first_paid[r["invoice_number"]] = datetime.fromisoformat(pay["paid_at"]).date()
    for number, row in inv_by_no.items():
        who = built.behaviour[leases[row["lease_number"]]["tenant_code"]]
        seen[who] += 1
        if number in first_paid:
            late[who].append((first_paid[number] - due[number]).days)
        else:
            unpaid[who] += 1
    behaviour_count = Counter(built.behaviour.values())
    check(
        set(behaviour_count) == set(gp.BEHAVIOURS) or loose,
        f"all five behaviours are present ({dict(behaviour_count)})",
    )
    if not loose:
        on_time = late["on_time"]
        check(
            statistics.median(on_time) <= 0 and sum(x > 0 for x in on_time) / len(on_time) < 0.02,
            f"on_time tenants pay by the due date (median {statistics.median(on_time):.0f} days)",
        )
        occ = late["occasionally_late"]
        late_share = sum(x > 0 for x in occ) / len(occ)
        check(
            0.12 <= late_share <= 0.30 and max(occ) <= gp.LATE_MAX_DAYS,
            f"occasionally_late tenants are late in {late_share:.0%} of months, never beyond "
            f"{gp.LATE_MAX_DAYS} days",
        )
        chronic = late["chronically_late"]
        check(
            8 <= statistics.median(chronic) <= 20
            and sum(x > 0 for x in chronic) / len(chronic) > 0.97,
            f"chronically_late tenants are late every time (median "
            f"{statistics.median(chronic):.0f} days, "
            f"90th percentile {pct(chronic, 0.9)})",
        )
        partial_pays = Counter()
        for r in pays:
            if r["status"] == "Cleared" and built.behaviour[r["tenant_code"]] == "partial_payer":
                partial_pays[next(iter(per_pay_invoices[r["payment_reference"]]))] += 1
        two = sum(v >= 2 for v in partial_pays.values()) / max(1, len(partial_pays))
        check(
            0.4 <= two <= 0.9 and unpaid["partial_payer"] / seen["partial_payer"] < 0.1,
            f"partial_payer tenants pay in two parts on {two:.0%} of invoices they pay",
        )
        open_share = defaultdict(lambda: [0, 0])
        for number, row in inv_by_no.items():
            who = built.behaviour[leases[row["lease_number"]]["tenant_code"]]
            open_share[who][0] += invoice_total[number] - invoice_paid.get(number, 0)
            open_share[who][1] += invoice_total[number]
        arrears = {k: v[0] / v[1] for k, v in open_share.items()}
        check(
            arrears["defaulter"] > 0.30
            and arrears["on_time"] < 0.03
            and arrears["defaulter"] > 4 * arrears["partial_payer"] / 2,
            "arrears by behaviour: defaulters "
            + f"{arrears['defaulter']:.0%}, partial payers {arrears['partial_payer']:.0%}, "
            + f"chronically late {arrears['chronically_late']:.0%}, "
            + f"on time {arrears['on_time']:.1%}",
        )
        corp = [r for r in tenants.values() if r["tenant_type"] == "Corporate"]
        corp_on_time = sum(built.behaviour[c["tenant_code"]] == "on_time" for c in corp) / len(corp)
        ind = [r for r in tenants.values() if r["tenant_type"] == "Individual"]
        ind_on_time = sum(built.behaviour[c["tenant_code"]] == "on_time" for c in ind) / len(ind)
        check(
            corp_on_time > ind_on_time,
            f"corporate tenants are more often on time ({corp_on_time:.0%} against "
            f"{ind_on_time:.0%})",
        )

    # ---- S3 settlements
    files = sorted((out / "s3").glob("settlement_*.csv"))
    check(len(files) > 0, f"{len(files)} settlement files, one per channel per day")
    name_ok = all(
        re.fullmatch(r"settlement_(bank|raast|jazzcash|easypaisa)_\d{4}-\d\d-\d\d\.csv", f.name)
        for f in files
    )
    check(name_ok, "files are named settlement_<channel>_<date>.csv with the four channels")
    channel_method = {v: k for k, v in gp.ELECTRONIC.items()}
    rows = []
    header_ok = True
    for f in files:
        with f.open(encoding="utf-8", newline="") as fh:
            header_ok &= next(csv.reader(fh)) == gp.SETTLEMENT_COLS
        channel, day = f.stem.split("_")[1], f.stem.split("_")[2]
        for r in read_csv(f):
            r["channel"], r["file_day"] = channel, day
            rows.append(r)
    check(header_ok, "every settlement file has the columns " + ", ".join(gp.SETTLEMENT_COLS))
    check(
        all(r["settlement_date"] == r["file_day"] for r in rows)
        and len({(r["channel"], r["settlement_id"]) for r in rows}) == len(rows),
        f"{len(rows)} settlements; each is in the file of its settlement date; channel + "
        f"settlement_id is unique",
    )
    cleared = {r["payment_reference"]: r for r in pays if r["status"] == "Cleared"}
    refs_s3 = Counter(r["payment_reference"] for r in rows)
    ok = True
    for r in rows:
        p = cleared.get(r["payment_reference"])
        ok &= p is not None and p["method_code"] == channel_method[r["channel"]]
        if p is not None:
            gross, fee, net = (
                paisa(r["gross_amount"]),
                paisa(r["fee_amount"]),
                paisa(r["net_amount"]),
            )
            ok &= gross == paisa(p["amount"]) and net == gross - fee
            ok &= fee == gp.fee_paisa(p["method_code"], gross)
            ok &= r["transaction_date"] == p["paid_at"][:10]
    check(
        ok and all(c == 1 for c in refs_s3.values()),
        "every settlement matches one electronic payment: same channel, same gross amount, "
        "net = gross - fee, one settlement per payment",
    )
    electronic = [r for r in cleared.values() if r["method_code"] in gp.ELECTRONIC]
    missing = [r for r in electronic if r["payment_reference"] not in refs_s3]
    check(
        all(
            r["method_code"] in gp.ELECTRONIC
            for r in cleared.values()
            if r["payment_reference"] in refs_s3
        )
        and {r["method_code"] for r in pays if r["method_code"] in ("CASH", "CHEQUE")}
        and not any(
            r["payment_reference"] in refs_s3
            for r in pays
            if r["method_code"] in ("CASH", "CHEQUE")
        ),
        "cash and cheque payments never appear in the settlement files",
    )
    miss_share = len(missing) / len(electronic)
    check(
        (0.0 <= miss_share <= 0.08) if loose else (0.01 <= miss_share <= 0.04),
        f"{len(missing)} of {len(electronic)} electronic payments ({miss_share:.1%}) have "
        f"no settlement: "
        f"the unmatched share",
    )
    lag = defaultdict(list)
    for r in rows:
        lag[r["channel"]].append(
            (
                date.fromisoformat(r["settlement_date"]) - date.fromisoformat(r["transaction_date"])
            ).days
        )
    mean = {k: sum(v) / len(v) for k, v in lag.items()}
    if not loose:
        check(
            mean["raast"] < 0.2 < 1.0 < mean["bank"] < mean["jazzcash"] < mean["easypaisa"] < 2.0
            and all(0 <= x <= 3 for v in lag.values() for x in v),
            "settlement lag by channel: "
            + ", ".join(f"{k} {v:.2f} days" for k, v in sorted(mean.items(), key=lambda kv: kv[1])),
        )
    check(
        all(date.fromisoformat(r["settlement_date"]) <= we + timedelta(days=3) for r in rows),
        "settlements fall at most three days after the window closes",
    )


def main() -> int:
    print("=" * 70)
    print(" US-2.4 acceptance tests: payments, allocations and settlements")
    print("=" * 70)
    model = load_model()
    with tempfile.TemporaryDirectory(prefix="lue_pay_test_") as tmp:
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
        other = gd.run(cfg.get_profile("small"), 3005, tmp / "other")
        mine = ["s1/payments.csv", "s1/payment_allocations.csv", "s1/invoices.csv"]
        s3 = sorted(k for k in again["files"] if k.startswith("s3/"))
        check(
            all(again["files"][k] == runs["small"][0]["files"][k] for k in mine)
            and [again["files"][k] for k in s3] == [runs["small"][0]["files"][k] for k in s3]
            and again["content_hash"] == runs["small"][0]["content_hash"],
            f"same seed: identical hashes for the payment files and all {len(s3)} settlement files",
        )
        check(
            all(other["files"][k] != again["files"][k] for k in mine[:2]),
            "a different seed changes the payments",
        )
        check(
            all(
                again["files"][f"s1/{n}.csv"] == runs["small"][0]["files"][f"s1/{n}.csv"]
                for n in ("leases", "lease_events", "invoice_lines", "tenants")
            ),
            "leases, lease events, invoice lines and tenants are produced by earlier "
            "stages unchanged",
        )
        check(
            runs["small"][1] < 60 and runs["full"][1] < 60,
            f"both profiles generate in under a minute (small {runs['small'][1]:.1f}s, "
            f"full {runs['full'][1]:.1f}s)",
        )
        check(
            gp.fee_paisa("BANK", 8_000_000) == 2500
            and gp.fee_paisa("RAAST", 100_000) == 500
            and gp.fee_paisa("RAAST", 8_000_000) == 4000
            and gp.fee_paisa("JAZZ", 8_000_000) == 80_000
            and gp.fee_paisa("EASY", 8_000_000) == 96_000
            and gp.allocate([300, 200, 100], 450) == [(1, 300), (2, 150)],
            "fee schedule and allocation order helpers",
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
