"""US-2.6: inject the planted defects and write the answer key.

The last generator stage. The earlier stages write CLEAN files; this one reads them back, plants
the defects at the rates of the profile (etl/generator_config.py DEFECT_RATES, about 1 to 3
percent), rewrites the files it changed and writes the answer key:

    answer_key/defects_answer_key.csv   one row per planted defect (see KEY_COLS); a record id or a
                                        column made of several parts joins them with |
    answer_key/summary.csv              count per defect type, source and table
    answer_key/totals.csv               count per defect type, with its expected handling
    answer_key/expectations.json        the numbers later stories compare with (matching, SCD2,
                                        inferred members, quarantine counts per check)
    answer_key/planted_patterns.json    the six planted business patterns (etl/patterns.py)
    answer_key/planted_patterns.md      the same for people, with how to check them

It also writes two S1 files that model the NEXT extract of the source system (loaded by the
incremental stories, never by scripts/db_load_source.py, which reads s1/<table>.csv only):

    s1/changes/tenants.csv        tenant rows changed inside the window (SCD2 test data, US-6.2)
    s1/late_arriving/tenants.csv  tenant rows held back from this extract (inferred members, US-6.5)

Rules that keep the answer key exact:

* One defect per record: a record that carries a defect never gets a second one, so every
  rejected record fails exactly one check (DQ-01 to DQ-06 in the Phase 1 order).
* Defects are planted only on records nothing else points to (lease events, payment allocations,
  settlement lines, tickets, incentive log rows) or on descriptive text (city, unit type, ticket
  priority). Rejecting one record therefore never orphans another: no cascade, no false positive.
* S1 stays loadable into src_pms: primary keys stay unique, values keep their column type and
  width. Wrong data types are planted only in the file sources (S4, S6), where they can occur.
* Each (table, defect type) has its own seeded stream and its count depends only on its own rate:
  count per table = round(rate x rows), at least 1 when the table has 20 rows or more. Changing one
  rate never changes another defect's count (which records get it may move: one per record).
* A rate of 0 plants nothing: `generate_data.py --clean` gives the clean control batch (US-4.4),
  whose answer key has no rows.

Expected handling: reject (quarantined by the check in expected_rule), warn (a finding, the row
goes on), repair (cleaned in staging, US-5.1) and accept (a valid change the warehouse must keep:
an SCD2 version). The plan names the first three; accept marks the tenant attribute changes.
"""

from __future__ import annotations

import copy
import csv
import io
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import numpy as np

from etl import gen_leases as gl
from etl import gen_master as gm
from etl import patterns as pat
from etl.generate_data import Context, GeneratorError, stage
from etl.generator_config import DEFECT_RATES

MIN_ROWS_FOR_ONE = 20  # a table this big gets at least one of each defect whose rate is not 0
EDGE_DAYS = 14  # tenant changes stay this far from the window's edges
LATE_SETTLEMENT_DAYS = (5, 20)  # a late settlement line arrives this many days after the payment
ORPHAN_PAYMENT_BASE = 9_000_000  # PAY-9000001...: far above any real payment number

KEY_COLS = [
    "defect_id", "source", "table", "record_id", "column", "defect_type",
    "expected_handling", "expected_rule", "detail",
]  # fmt: skip
SUMMARY_COLS = ["defect_type", "source", "table", "expected_handling", "expected_rule", "count"]
TOTAL_COLS = ["defect_type", "expected_handling", "count"]

# defect type -> (expected handling, expected rule). Rules: the Phase 1 checks DQ-01 to DQ-06
# (docs/phase1, Quality and quarantine) or the later step that handles the record.
HANDLING = {
    "null_required_value": ("reject", "DQ-01"),
    "wrong_data_type": ("reject", "DQ-02"),
    "exact_duplicate": ("reject", "DQ-03"),
    "duplicate_settlement_line": ("reject", "DQ-03"),
    "conflicting_duplicate": ("warn", "DQ-03"),
    "orphan_reference": ("reject", "DQ-05"),
    "out_of_range_date": ("reject", "DQ-06"),
    "late_arriving_tenant_reference": ("warn", "DQ-05"),
    "mid_lease_rent_change": ("warn", "DQ-04"),
    "inconsistent_text": ("repair", "US-5.1"),
    "late_arriving_payment": ("warn", "US-5.2"),
    "tenant_attribute_change": ("accept", "US-6.2"),
}
# An S3 line whose payment is not in S1 is not rejected: US-5.2 flags it as unmatched.
S3_ORPHAN = ("warn", "US-5.2")


# ----------------------------------------------------------------------------- the answer key
class AnswerKey:
    def __init__(self) -> None:
        self.rows: list[list] = []

    def add(self, source, table, record_id, column, defect, detail, handling=None) -> None:
        h, rule = handling or HANDLING[defect]
        self.rows.append([source, table, str(record_id), column, defect, h, rule, detail])

    def sorted_rows(self) -> list[list]:
        rows = sorted(self.rows, key=lambda r: (r[0], r[1], r[4], r[2], r[3], r[7]))
        return [[f"D-{i:05d}", *r] for i, r in enumerate(rows, start=1)]


def how_many(rate: float, total: int, pool: int) -> int:
    """Records to damage in a table of `total` rows with `pool` eligible ones."""
    if rate <= 0 or pool <= 0:
        return 0
    n = int(round(rate * total))
    if n == 0 and total >= MIN_ROWS_FOR_ONE:
        n = 1
    return min(n, pool)


def choose(rng: np.random.Generator, pool: list, n: int) -> list:
    """n members of `pool` (kept in pool order), drawn without replacement."""
    if n <= 0:
        return []
    picked = sorted(int(i) for i in rng.choice(len(pool), size=n, replace=False))
    return [pool[i] for i in picked]


def text_variant(rng: np.random.Generator, value: str) -> str:
    """The same word written differently (' lahore ', 'LAHORE', 'lahore', 'Lahore  ')."""
    variants = [f" {value.lower()} ", value.upper(), value.lower(), f"{value}  ", f" {value}"]
    variants = [v for v in variants if v != value]
    return variants[int(rng.integers(len(variants)))]


def shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


# ----------------------------------------------------------------------------- file helpers
def read_csv(ctx: Context, relative: str) -> tuple[list[str], list[list[str]]]:
    with (ctx.out / relative).open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def write_csv(ctx: Context, relative: str, header: list[str], rows: list[list[str]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    ctx.write_text(relative, buffer.getvalue())


class Table:
    """One CSV file being damaged: its rows, and which of them already carry a defect."""

    def __init__(self, ctx: Context, relative: str):
        self.relative = relative
        self.header, self.rows = read_csv(ctx, relative)
        self.col = {c: i for i, c in enumerate(self.header)}
        self.used: set[int] = set()
        self.after: dict[int, list[list[str]]] = defaultdict(list)  # copies to insert after a row
        self.dropped: set[int] = set()
        self.changed = False

    def free(self, keep=lambda row: True) -> list[int]:
        return [i for i, r in enumerate(self.rows) if i not in self.used and keep(r)]

    def take(self, i: int) -> list[str]:
        self.used.add(i)
        self.changed = True
        return self.rows[i]

    def final_rows(self) -> list[list[str]]:
        out = []
        for i, r in enumerate(self.rows):
            if i not in self.dropped:
                out.append(r)
            out.extend(self.after.get(i, []))
        return out

    def save(self, ctx: Context) -> None:
        if self.changed:
            write_csv(ctx, self.relative, self.header, self.final_rows())


# ----------------------------------------------------------------------------- S1
def inject_s1(ctx: Context, key: AnswerKey, rates: dict, billing: gl.Billing) -> dict:
    ws, we = ctx.profile.window_start, ctx.profile.window_end
    tables = {t: Table(ctx, f"s1/{t}.csv") for t in (
        "buildings", "units", "tenants", "leases", "lease_events", "payments",
        "payment_allocations",
    )}  # fmt: skip

    def stream(table: str, defect: str) -> np.random.Generator:
        return ctx.rng(f"defects.s1.{table}.{defect}")

    # Descriptive text written inconsistently (repaired by clean_text in US-5.1).
    for table, column, ident in (("buildings", "city", "building_code"),
                                 ("units", "unit_type", "unit_id")):  # fmt: skip
        t = tables[table]
        rng = stream(table, "inconsistent_text")
        pool = t.free()
        for i in choose(rng, pool, how_many(rates["inconsistent_text"], len(t.rows), len(pool))):
            row = t.take(i)
            old = row[t.col[column]]
            row[t.col[column]] = text_variant(rng, old)
            key.add("S1", table, row[t.col[ident]], column, "inconsistent_text",
                    f"{old!r} written as {row[t.col[column]]!r}")  # fmt: skip

    # Late-arriving tenants: held back from this extract; their leases and payments still name
    # them (flagged, an inferred member is created, US-6.5). They arrive in s1/late_arriving.
    tenants, leases, payments = tables["tenants"], tables["leases"], tables["payments"]
    tc = tenants.col["tenant_code"]
    leased = {r[leases.col["tenant_code"]] for r in leases.rows}
    rng = stream("tenants", "late_arriving_tenant_reference")
    pool = tenants.free(lambda r: r[tc] in leased)
    late = choose(
        rng, pool,
        how_many(rates["late_arriving_tenant_reference"], len(tenants.rows), len(pool)),
    )  # fmt: skip
    late_codes = set()
    late_rows = []
    for i in late:
        row = tenants.take(i)
        tenants.dropped.add(i)
        late_codes.add(row[tc])
        late_rows.append(list(row))
    for table, ident in ((leases, "lease_number"), (payments, "payment_reference")):
        name = "leases" if table is leases else "payments"
        for r in table.rows:
            if r[table.col["tenant_code"]] in late_codes:
                key.add("S1", name, r[table.col[ident]], "tenant_code",
                        "late_arriving_tenant_reference",
                        f"tenant {r[table.col['tenant_code']]} is not in this extract "
                        "(s1/late_arriving/tenants.csv)")  # fmt: skip
    write_csv(ctx, "s1/late_arriving/tenants.csv", tenants.header, late_rows)

    # Tenant attribute changes (SCD2): the next extract carries the changed row.
    rng = stream("tenants", "tenant_attribute_change")
    upd = tenants.col["updated_at"]
    sectors = sorted({r[tenants.col["employer_sector"]] for r in tenants.rows} - {""})
    channels = sorted({r[tenants.col["contact_channel"]] for r in tenants.rows} - {""})
    last_change = datetime.combine(we - timedelta(days=EDGE_DAYS), datetime.min.time())

    def changeable(r: list[str]) -> bool:
        first = max(datetime.fromisoformat(r[upd]), datetime.combine(ws, datetime.min.time()))
        return first + timedelta(days=EDGE_DAYS) < last_change

    pool = tenants.free(changeable)
    changes = []
    for i in choose(rng, pool, how_many(rates["tenant_attribute_change"], len(tenants.rows),
                                        len(pool))):  # fmt: skip
        row = tenants.take(i)
        new = list(row)
        column = "employer_sector" if row[tenants.col["employer_sector"]] else "contact_channel"
        if rng.random() < 0.5:
            column = "contact_channel"
        vocab = sectors if column == "employer_sector" else channels
        options = [v for v in vocab if v != row[tenants.col[column]]]
        new[tenants.col[column]] = options[int(rng.integers(len(options)))]
        first = max(datetime.fromisoformat(row[upd]), datetime.combine(ws, datetime.min.time()))
        first += timedelta(days=EDGE_DAYS)
        span = int((last_change - first).total_seconds())
        moment = first + timedelta(seconds=int(rng.integers(0, span)))
        new[upd] = moment.strftime("%Y-%m-%d %H:%M:%S")
        changes.append(new)
        key.add("S1", "tenants", row[tc], column, "tenant_attribute_change",
                f"{row[tenants.col[column]]!r} -> {new[tenants.col[column]]!r} from "
                f"{new[upd]} (s1/changes/tenants.csv)")  # fmt: skip
    tenants.changed = tenants.changed or bool(late)
    write_csv(ctx, "s1/changes/tenants.csv", tenants.header, changes)

    # Lease events: a leaf table (nothing refers to an event).
    ev = tables["lease_events"]
    lease_numbers = {r[leases.col["lease_number"]] for r in leases.rows}
    for defect in ("null_required_value", "out_of_range_date", "orphan_reference"):
        rng = stream("lease_events", defect)
        pool = ev.free()
        for i in choose(rng, pool, how_many(rates[defect], len(ev.rows), len(pool))):
            row = ev.take(i)
            ident = row[ev.col["event_id"]]
            if defect == "null_required_value":
                old, row[ev.col["event_date"]] = row[ev.col["event_date"]], ""
                key.add("S1", "lease_events", ident, "event_date", defect, f"{old} removed")
            elif defect == "out_of_range_date":
                old = date.fromisoformat(row[ev.col["event_date"]])
                years = -8 if rng.random() < 0.5 else 8
                row[ev.col["event_date"]] = shift_years(old, years).isoformat()
                key.add("S1", "lease_events", ident, "event_date", defect,
                        f"{old} written as {row[ev.col['event_date']]}")  # fmt: skip
            else:
                old = row[ev.col["lease_number"]]
                new = f"L-1999-{old[-5:]}"  # no lease starts in 1999
                assert new not in lease_numbers
                row[ev.col["lease_number"]] = new
                key.add("S1", "lease_events", ident, "lease_number", defect,
                        f"{old} written as {new} (no such lease)")  # fmt: skip

    # Payment allocations: a leaf table too.
    al = tables["payment_allocations"]
    for defect in ("null_required_value", "orphan_reference"):
        rng = stream("payment_allocations", defect)
        pool = al.free()
        for i in choose(rng, pool, how_many(rates[defect], len(al.rows), len(pool))):
            row = al.take(i)
            ident = "|".join(row[: 3])
            if defect == "null_required_value":
                old, row[al.col["allocated_amount"]] = row[al.col["allocated_amount"]], ""
                key.add("S1", "payment_allocations", ident, "allocated_amount", defect,
                        f"{old} removed")  # fmt: skip
            else:
                old = row[al.col["invoice_number"]]
                row[al.col["invoice_number"]] = "INV-2099" + old[8:]  # no invoice is from 2099
                key.add("S1", "payment_allocations", ident, "invoice_number", defect,
                        f"{old} written as {row[al.col['invoice_number']]} (no such invoice)")

    # Mid-lease rent changes: planted inside the lease simulation (gen_leases), so the tenants
    # pay what was billed; listed here, one row per invoice line billed at the changed rent.
    for c in billing.rent_change_lines:
        key.add("S1", "invoice_lines", f"{c['invoice_number']}|{c['line_no']}", "billed_amount",
                "mid_lease_rent_change",
                f"lease {c['lease_number']} signed at {c['lease_rent']}, billed "
                f"{c['billed_rent']} from {c['from_month']:%Y-%m}")  # fmt: skip

    for t in tables.values():
        t.save(ctx)
    return {"late_tenants": sorted(late_codes), "tenant_changes": len(changes)}


# ----------------------------------------------------------------------------- S3
def inject_s3(ctx: Context, key: AnswerKey, rates: dict) -> dict:
    files = sorted(p.name for p in (ctx.out / "s3").glob("settlement_*.csv"))
    data: dict[str, Table] = {name: Table(ctx, f"s3/{name}") for name in files}
    lines = [(name, i) for name in files for i in range(len(data[name].rows))]
    total = len(lines)

    def channel_day(name: str) -> tuple[str, date]:
        stem = name[len("settlement_"): -len(".csv")]
        channel, day = stem.rsplit("_", 1)
        return channel, date.fromisoformat(day)

    def ident(name: str, row: list[str]) -> str:
        return f"{channel_day(name)[0]}:{row[0]}"

    used: set[tuple[str, int]] = set()
    moved: dict[str, list[list[str]]] = defaultdict(list)

    rng = ctx.rng("defects.s3.settlements.duplicate_settlement_line")
    pool = [x for x in lines if x not in used]
    for name, i in choose(rng, pool, how_many(rates["duplicate_settlement_line"], total,
                                              len(pool))):  # fmt: skip
        used.add((name, i))
        t = data[name]
        row = t.take(i)
        t.after[i].append(list(row))
        key.add("S3", "settlements", ident(name, row), "settlement_id",
                "duplicate_settlement_line", f"line repeated in {name}")  # fmt: skip

    rng = ctx.rng("defects.s3.settlements.late_arriving_payment")
    pool = [x for x in lines if x not in used]
    for name, i in choose(rng, pool, how_many(rates["late_arriving_payment"], total, len(pool))):
        used.add((name, i))
        t = data[name]
        row = list(t.take(i))
        t.dropped.add(i)
        channel, day = channel_day(name)
        later = day + timedelta(days=int(rng.integers(LATE_SETTLEMENT_DAYS[0],
                                                      LATE_SETTLEMENT_DAYS[1] + 1)))  # fmt: skip
        row[3] = later.isoformat()
        target = f"settlement_{channel}_{later.isoformat()}.csv"
        moved[target].append(row)
        key.add("S3", "settlements", ident(name, row), "settlement_date",
                "late_arriving_payment",
                f"paid {row[2]}, due in {name}, reported in {target}")  # fmt: skip

    # Settlement lines for payments the source system never recorded (unmatched, US-5.2).
    rng = ctx.rng("defects.s3.settlements.orphan_reference")
    n = how_many(rates["orphan_reference"], total, total)
    extra: dict[str, list[list[str]]] = defaultdict(list)
    for k, (name, i) in enumerate(choose(rng, lines, n), start=1):
        src = data[name].rows[i]
        _channel, day = channel_day(name)
        lag = int(rng.integers(0, 3))
        reference = f"PAY-{ORPHAN_PAYMENT_BASE + k:07d}"
        extra[name].append([None, reference, (day - timedelta(days=lag)).isoformat(),
                            day.isoformat(), src[4], src[5], src[6]])  # fmt: skip

    header = data[files[0]].header if files else []
    for name in sorted(set(moved) | set(extra) | set(files)):
        t = data.get(name)
        rows = t.final_rows() if t else []
        if name in extra:
            prefix = (t.rows[0][0] if t and t.rows else "")[:-4]
            # Number after every line the file ever had, including lines moved out as late
            # (a moved line keeps its id, so reusing its number would duplicate the key).
            seq = max([int(r[0][-4:]) for r in t.rows] + [0])
            for row in extra[name]:
                seq += 1
                row[0] = f"{prefix}{seq:04d}"
                rows.append(row)
                key.add("S3", "settlements", ident(name, row), "payment_reference",
                        "orphan_reference",
                        f"{row[1]} is not a payment of the source system (unmatched)",
                        handling=S3_ORPHAN)  # fmt: skip
        rows.extend(moved.get(name, []))
        if t is None or t.changed or name in extra or name in moved:
            write_csv(ctx, f"s3/{name}", header, rows)
    return {"unmatched_settlements": n}


# ----------------------------------------------------------------------------- S4
def inject_s4(ctx: Context, key: AnswerKey, rates: dict, master: dict) -> None:
    path = ctx.out / "s4" / "tickets.json"
    export = json.loads(path.read_text(encoding="utf-8"))
    tickets = export["tickets"]
    total = len(tickets)
    used: set[int] = set()
    unit_nos = defaultdict(set)
    for u in master["units"]:
        unit_nos[u["building_code"]].add(u["unit_no"])
    inserts: list[tuple[int, dict]] = []  # (position in the original list, ticket to insert)

    def pick(defect: str, keep=lambda t: True) -> tuple[np.random.Generator, list[int]]:
        rng = ctx.rng(f"defects.s4.tickets.{defect}")
        pool = [i for i, t in enumerate(tickets) if i not in used and keep(t)]
        chosen = choose(rng, pool, how_many(rates[defect], total, len(pool)))
        used.update(chosen)
        return rng, chosen

    rng, chosen = pick("exact_duplicate")
    for i in chosen:
        t = tickets[i]
        inserts.append((int(rng.integers(i + 1, total + 1)), copy.deepcopy(t)))
        key.add("S4", "tickets", t["ticket_id"], "ticket_id", "exact_duplicate",
                "the same ticket exported twice")  # fmt: skip

    rng, chosen = pick("conflicting_duplicate", lambda t: len(t["status_history"]) >= 2)
    for i in chosen:
        t = tickets[i]
        k = int(rng.integers(1, len(t["status_history"])))
        old = copy.deepcopy(t)
        old["status_history"] = old["status_history"][:k]
        old["status"] = old["status_history"][-1]["status"]
        reached = {h["status"] for h in old["status_history"]}
        if "Assigned" not in reached:
            old["vendor_code"], old["estimate"] = None, None
        if "Resolved" not in reached:
            old["final_cost"] = None
        inserts.append((int(rng.integers(0, total + 1)), old))
        key.add("S4", "tickets", t["ticket_id"], "status", "conflicting_duplicate",
                f"an older copy with status {old['status']} (latest: {t['status']}); keep the "
                "copy with the latest status time")  # fmt: skip

    rng, chosen = pick("null_required_value")
    for i in chosen:
        t = tickets[i]
        old, t["unit_no"] = t["unit_no"], None
        key.add("S4", "tickets", t["ticket_id"], "unit_no", "null_required_value",
                f"{t['building_code']} {old}: unit removed")  # fmt: skip

    rng, chosen = pick("inconsistent_text")
    for i in chosen:
        t = tickets[i]
        column = "priority" if rng.random() < 0.6 else "category"
        old = t[column]
        t[column] = text_variant(rng, old)
        key.add("S4", "tickets", t["ticket_id"], column, "inconsistent_text",
                f"{old!r} written as {t[column]!r}")  # fmt: skip

    rng, chosen = pick("wrong_data_type", lambda t: t["estimate"] is not None)
    for i in chosen:
        t = tickets[i]
        old = t["estimate"]
        t["estimate"] = f"Rs. {old:,}" if rng.random() < 0.5 else f"{old:,}/-"
        key.add("S4", "tickets", t["ticket_id"], "estimate", "wrong_data_type",
                f"{old} written as the text {t['estimate']!r}")  # fmt: skip

    rng, chosen = pick("out_of_range_date")
    for i in chosen:
        t = tickets[i]
        old = t["status_history"][0]["at"]
        t["status_history"][0]["at"] = "1970-01-01" + old[10:]  # the app's empty-date default
        key.add("S4", "tickets", t["ticket_id"], "status_history[Raised].at",
                "out_of_range_date", f"{old} written as {t['status_history'][0]['at']}")

    rng, chosen = pick("orphan_reference")
    for i in chosen:
        t = tickets[i]
        old = t["unit_no"]
        new = f"Z-{old[2:]}" if len(old) > 2 else f"Z-{old}"
        while new in unit_nos[t["building_code"]]:
            new = "Z" + new
        t["unit_no"] = new
        key.add("S4", "tickets", t["ticket_id"], "unit_no", "orphan_reference",
                f"{t['building_code']} {old} written as {new} (no such unit)")  # fmt: skip

    if not inserts and not used:
        return
    out = []
    by_pos = defaultdict(list)
    for pos, t in inserts:
        by_pos[pos].append(t)
    for i in range(total + 1):
        out.extend(by_pos.get(i, []))
        if i < total:
            out.append(tickets[i])
    export["tickets"] = out
    export["export"]["ticket_count"] = len(out)
    ctx.write_text("s4/tickets.json", json.dumps(export, indent=2, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------------- S6
def inject_s6(ctx: Context, key: AnswerKey, rates: dict) -> None:
    t = Table(ctx, "s6/incentive_log.csv")
    c = t.col

    def ident(row: list[str]) -> str:
        return "|".join(row[c[k]] for k in ("building_code", "unit_no", "offer_code",
                                            "start_date"))  # fmt: skip

    for defect in ("exact_duplicate", "null_required_value", "inconsistent_text",
                   "wrong_data_type", "out_of_range_date"):  # fmt: skip
        rng = ctx.rng(f"defects.s6.incentive_log.{defect}")
        pool = t.free()
        for i in choose(rng, pool, how_many(rates[defect], len(t.rows), len(pool))):
            row = t.take(i)
            rid = ident(row)
            if defect == "exact_duplicate":
                t.after[i].append(list(row))
                key.add("S6", "incentive_log", rid, "", defect, "the same row logged twice")
            elif defect == "null_required_value":
                row[c["offer_code"]] = ""
                key.add("S6", "incentive_log", rid, "offer_code", defect, "offer code removed")
            elif defect == "inconsistent_text":
                d = date.fromisoformat(row[c["start_date"]])
                row[c["start_date"]] = d.strftime("%d/%m/%Y")
                key.add("S6", "incentive_log", rid, "start_date", defect,
                        f"{d} written as {row[c['start_date']]} (day first)")  # fmt: skip
            elif defect == "wrong_data_type":
                old = date.fromisoformat(row[c["end_date"]])
                row[c["end_date"]] = "TBD" if rng.random() < 0.5 else f"{old:%Y-%m}-32"
                key.add("S6", "incentive_log", rid, "end_date", defect,
                        f"{old} written as {row[c['end_date']]!r} (not a date)")  # fmt: skip
            else:
                for col in ("start_date", "end_date"):
                    d = date.fromisoformat(row[c[col]])
                    row[c[col]] = shift_years(d, -10).isoformat()
                key.add("S6", "incentive_log", rid, "start_date|end_date", defect,
                        "both dates written 10 years early")  # fmt: skip
    t.save(ctx)


# ----------------------------------------------------------------------------- expectations
def settlement_counts(ctx: Context) -> dict:
    """Electronic payments without a settlement line, and lines without a payment (final files)."""
    from etl import gen_payments as gp

    _h, pays = read_csv(ctx, "s1/payments.csv")
    refs = {r[0] for r in pays}
    electronic = {r[0] for r in pays if r[3] in gp.ELECTRONIC and r[5] == "Cleared"}
    settled = set()
    lines = 0
    for p in sorted((ctx.out / "s3").glob("settlement_*.csv")):
        _h, rows = read_csv(ctx, f"s3/{p.name}")
        lines += len(rows)
        settled.update(r[1] for r in rows)
    return {
        "settlement_lines": lines,
        "unsettled_electronic_payments": len(electronic - settled),
        "unmatched_settlement_references": len(settled - refs),
    }


def patterns_markdown(profile, described: dict) -> str:
    d = described
    rows = [
        ("High-arrears building", f"building `{d['high_arrears_building']['building_code']}`",
         d["high_arrears_building"]["expected"]),
        ("Slow vendor", f"vendor `{d['slow_vendor']['vendor_code']}` ({d['slow_vendor']['trade']})",
         d["slow_vendor"]["expected"]),
        ("Seasonal move-ins",
         "months " + ", ".join(map(str, d["seasonal_move_ins"]["peak_months"])),
         d["seasonal_move_ins"]["expected"]),
        ("Incentive shortens vacancy", "offers in `s6/incentive_log.csv`",
         d["incentive_shortens_vacancy"]["expected"]),
        ("Rain-driven leak tickets",
         ", ".join(d["rain_driven_leaks"]["codes"])
         + f" after {d['rain_driven_leaks']['threshold_mm']} mm of rain or more",
         d["rain_driven_leaks"]["expected"]),
        ("Renewal churn", f"city `{d['renewal_churn_city']['city']}`",
         d["renewal_churn_city"]["expected"]),
    ]  # fmt: skip
    lines = [
        "# Planted business patterns",
        "",
        f"Profile `{profile.name}`. Written by `etl/gen_defects.py` (US-2.6) from",
        "`etl/patterns.py`.",
        "The patterns are part of the clean data: a clean control batch has them too. Measure them",
        "with `python scripts/check_patterns.py --data <the generated folder>`.",
        "",
        "| # | Pattern | Where | Expected effect |",
        "|---|---|---|---|",
        *[f"| {i} | {name} | {where} | {effect} |" for i, (name, where, effect) in
          enumerate(rows, start=1)],
        "",
        "The small profile (2 buildings, 3 months) is too small to measure most effects; the",
        "thresholds apply to the full profile.",
        "",
    ]  # fmt: skip
    return "\n".join(lines)


STAGE_NAME = "defects_answer_key"


@stage(STAGE_NAME, "Planted defects and the answer key (US-2.6)")
def defects_answer_key(ctx: Context) -> None:
    profile = ctx.profile
    needed = ("s1/payments.csv", "s1/lease_events.csv", "s4/tickets.json", "s6/incentive_log.csv")
    missing = [f for f in needed if not (ctx.out / f).is_file()]
    if missing:
        raise GeneratorError(
            f"{STAGE_NAME} must run after the stages that write {', '.join(missing)} "
            "(it is the last name in generate_data.STAGE_ORDER)"
        )
    rates = {name: float(profile.defect_rates.get(name, 0.0)) for name in DEFECT_RATES}
    master = gm.build_master(profile, ctx.rng)
    billing = gl.build_billing(profile, master, ctx.rng)
    key = AnswerKey()
    s1 = inject_s1(ctx, key, rates, billing)
    s3 = inject_s3(ctx, key, rates)
    inject_s4(ctx, key, rates, master)
    inject_s6(ctx, key, rates)

    rows = key.sorted_rows()
    ctx.write_csv("answer_key/defects_answer_key.csv", KEY_COLS, rows)
    groups = Counter((r[5], r[1], r[2], r[6], r[7]) for r in rows)
    ctx.write_csv(
        "answer_key/summary.csv",
        SUMMARY_COLS,
        [[d, s, t, h, rule, n] for (d, s, t, h, rule), n in sorted(groups.items())],
    )
    totals = Counter((r[5], r[6]) for r in rows)
    ctx.write_csv(
        "answer_key/totals.csv",
        TOTAL_COLS,
        [[d, h, totals[(d, h)]] for d, h in sorted(totals)]
        + [["all", "reject", sum(n for (_d, h), n in totals.items() if h == "reject")],
           ["all", "all", len(rows)]],
    )  # fmt: skip
    quarantine = Counter((r[1], r[2], r[7]) for r in rows if r[6] == "reject")
    warnings = Counter((r[1], r[2], r[7]) for r in rows if r[6] == "warn")
    expectations = {
        "profile": profile.name,
        "defect_rates": {k: f"{v:.3f}" for k, v in sorted(rates.items())},
        "records_with_a_defect": len(rows),
        "quarantine_by_check": {
            f"{s}.{t}.{rule}": n for (s, t, rule), n in sorted(quarantine.items())
        },
        "warnings_by_check": {f"{s}.{t}.{rule}": n for (s, t, rule), n in sorted(warnings.items())},
        "matching_us_5_2": settlement_counts(ctx) | s3,
        "inferred_tenants_us_6_5": len(s1["late_tenants"]),
        "late_tenant_codes": s1["late_tenants"],
        "tenant_scd2_versions_us_6_2": s1["tenant_changes"],
        "mid_lease_rent_change_lines": len(billing.rent_change_lines),
    }
    ctx.write_text(
        "answer_key/expectations.json", json.dumps(expectations, indent=2, sort_keys=True) + "\n"
    )
    described = pat.describe(master)
    ctx.write_text(
        "answer_key/planted_patterns.json", json.dumps(described, indent=2, sort_keys=True) + "\n"
    )
    ctx.write_text("answer_key/planted_patterns.md", patterns_markdown(profile, described))
