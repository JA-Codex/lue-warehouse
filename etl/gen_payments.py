"""US-2.4: payments, payment allocations and bank and wallet settlements.

Writes, for the chosen profile (etl/generator_config.py):

    s1/payments.csv, s1/payment_allocations.csv     PostgreSQL source src_pms (loaded by
    db_load_source.py)
    s1/invoices.csv                                  rewritten: `status` is now decided from the
    payments
    s3/settlement_<channel>_<date>.csv               S3, one file per channel per day

The data is CLEAN. US-2.6 (etl/gen_defects.py) plants the defects afterwards (duplicate and late
settlement lines, settlement lines with no payment, allocations with no invoice line, late tenants)
and the answer key. The stage rebuilds the master data and the billing with
the same
seeds as US-2.2 and US-2.3 (pure functions), so it never reads another stage's files.

US-2.6 adds one planted pattern here (etl/patterns.py): the tenants of one building (the
high-arrears building) draw their behaviour from patterns.ARREARS_WEIGHTS instead, so that building
has far more late and unpaid rent. A tenant who also rents elsewhere keeps that behaviour there.

How tenants pay. Every tenant has one behaviour for the whole window:

    on_time            pays between the 1st and the due date (the 10th)
    occasionally_late  on time in 80 percent of months, late (1 to 30 days) in the rest
    chronically_late   always late: median 12 days, sometimes more than two months
    partial_payer      pays 40 to 90 percent first, the rest 15 to 75 days later (65 percent of
    months)
    defaulter          pays like an occasional late payer for a few months, then stops; now and
    then pays
                       an old invoice 45 to 120 days late

A tenant also has a favourite payment method (used 85 percent of the time). Corporate tenants
are more on
time and pay by cheque or bank transfer. In 7 percent of months the tenant pays the rent line
first and the
rest a few days later. A cheque bounces now and then: the bank returns it 3 to 7 days after the
tenant paid
and the source system records a NEGATIVE payment (status 'Bounced', `reversal_of` the original
receipt)
with negative allocations on the same lines. The original receipt keeps status 'Cleared'. Four in
five
tenants then pay again (cash, bank transfer or Raast) 5 to 25 days later.

Contracts for the stories that follow:

* payment_reference is `PAY-<7 digits>`, numbered in order of paid_at, then tenant, then creation
  order.
* A payment's amount is exactly the sum of its allocations. Allocations are applied to the lines
  of ONE
  invoice, in line order (rent first). No line is ever paid more than its net_amount, and a line's
  allocations add up to between 0 and net_amount after reversals.
* Nothing is paid after the window closes, and no payment is dated before its invoice was issued.
* invoices.status is as at the end of the window: 'Paid' (fully allocated), 'Partial' (some
  allocated) or
  'Overdue' (nothing allocated; every due date falls inside the window). 'Issued' no longer occurs.
* S3: one settlement per electronic payment (BANK, RAAST, JAZZ, EASY), 2 percent of them left out on
  purpose (unmatched). Cash and cheques never settle. A settlement dated after the window closes
  is still
  written (it is a file for a day that has not come yet for the portfolio, but the bank has it).
  Columns: settlement_id, payment_reference, transaction_date, settlement_date, gross_amount,
  fee_amount,
  net_amount. The channel is in the file name (bank, raast, jazzcash, easypaisa); the natural key is
  channel + settlement_id.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from etl import gen_leases as gl
from etl import gen_master as gm
from etl import patterns as pat
from etl.generate_data import Context, stage
from etl.generator_config import Profile
from etl.reference_data import PAYMENT_METHODS

# ----------------------------------------------------------------------------- constants
BEHAVIOURS = ("on_time", "occasionally_late", "chronically_late", "partial_payer", "defaulter")
BEHAVIOUR_WEIGHTS = {
    "Individual": (0.55, 0.20, 0.10, 0.10, 0.05),
    "Corporate": (0.72, 0.14, 0.05, 0.07, 0.02),
}
METHOD_CODES = tuple(code for code, _name, _group, _days in PAYMENT_METHODS)
METHOD_WEIGHTS = {  # CASH, CHEQUE, BANK, RAAST, JAZZ, EASY
    "Individual": (0.24, 0.12, 0.25, 0.15, 0.12, 0.12),
    "Corporate": (0.05, 0.40, 0.45, 0.10, 0.0, 0.0),
}
FAVOURITE_SHARE = 0.85  # share of payments made with the tenant's favourite method
REPLACEMENT_METHODS = ("CASH", "BANK", "RAAST")

ON_TIME_OFFSET = (
    -2.0,
    2.5,
    -9,
    0,
)  # normal(mean, sd) days after the due date, clipped to (low, high)
OCCASIONAL_LATE_SHARE = 0.20
LATE_EXPONENTIAL_MEAN = 7.0  # days late for an occasional late payment
LATE_MAX_DAYS = 30
CHRONIC_MEDIAN_DAYS = 12.0
CHRONIC_SIGMA = 0.6
CHRONIC_CLIP = (3, 60)
CHRONIC_VERY_LATE_SHARE = 0.05  # 61 to 99 days late
PARTIAL_FIRST_SHARE = (0.40, 0.90)
PARTIAL_FIRST_OFFSET = (2.0, 4.0, -5, 12)
PARTIAL_REST_SHARE = 0.65
PARTIAL_REST_DAYS = (15, 75)
DEFAULT_PAID_MONTHS = (0, 9)  # a defaulter pays this many invoices before stopping (low, high)
DEFAULT_LATE_PAY_SHARE = 0.08
DEFAULT_LATE_DAYS = (45, 120)
SPLIT_SHARE = 0.07  # rent first, the rest a few days later
SPLIT_DAYS = (1, 6)
BOUNCE_DAYS = (3, 7)
BOUNCE_SHARE = {
    "normal": 0.04,
    "risky": 0.10,
}  # of cheques; chronic late payers and defaulters are risky
REPAY_SHARE = 0.80
REPAY_DAYS = (5, 25)

ELECTRONIC = {"BANK": "bank", "RAAST": "raast", "JAZZ": "jazzcash", "EASY": "easypaisa"}
SETTLEMENT_PREFIX = {"BANK": "BNK", "RAAST": "RST", "JAZZ": "JZC", "EASY": "EPY"}
SETTLEMENT_LAG = {  # (days, weights)
    "BANK": ((1, 2, 3), (0.70, 0.25, 0.05)),
    "RAAST": ((0, 1), (0.95, 0.05)),
    "JAZZ": ((1, 2, 3), (0.60, 0.30, 0.10)),
    "EASY": ((1, 2, 3), (0.50, 0.35, 0.15)),
}
P_NO_SETTLEMENT = 0.02  # electronic payments with no row in the settlement files


def fee_paisa(method: str, gross: int) -> int:
    """Fee in paisa: bank 25 rupees flat, Raast 0.05% (min 5), JazzCash 1%, Easypaisa 1.2%."""
    if method == "BANK":
        return 2500
    if method == "RAAST":
        return max(500, gross * 5 // 10_000)
    return gross * (100 if method == "JAZZ" else 120) // 10_000


PAYMENT_COLS = [
    "payment_reference", "tenant_code", "paid_at", "method_code", "amount", "status", "reversal_of",
]  # fmt: skip
ALLOCATION_COLS = ["payment_reference", "invoice_number", "line_no", "allocated_amount"]
SETTLEMENT_COLS = [
    "settlement_id", "payment_reference", "transaction_date", "settlement_date",
    "gross_amount", "fee_amount", "net_amount",
]  # fmt: skip


# ----------------------------------------------------------------------------- objects
@dataclass(eq=False)
class Pay:
    tenant_idx: int
    tenant_code: str
    day: date
    second: int  # seconds after midnight
    method: str
    amount: int  # paisa; negative for a bounced-cheque reversal
    status: str  # Cleared or Bounced
    allocations: list[tuple[str, int, int]]  # (invoice_number, line_no, paisa)
    reversal_of: Pay | None = None
    order: int = 0
    reference: str = ""

    @property
    def paid_at(self) -> datetime:
        return datetime.combine(self.day, datetime.min.time()) + timedelta(seconds=self.second)


@dataclass
class Payments:
    pays: list[Pay]
    behaviour: dict[str, str]  # tenant_code -> behaviour
    payment_rows: list[list]
    allocation_rows: list[list]
    invoice_rows: list[list]  # invoices with their final status
    settlements: dict[tuple[str, date], list[list]] = field(default_factory=dict)
    unmatched: list[Pay] = field(default_factory=list)  # electronic payments left out of S3


def clipped_normal(rng: np.random.Generator, spec) -> int:
    mean, sd, low, high = spec
    return int(min(high, max(low, round(float(rng.normal(mean, sd))))))


# ----------------------------------------------------------------------------- behaviour plans
def plan(behaviour: str, rng: np.random.Generator, index: int, stop_after: int) -> list[tuple]:
    """Payments one tenant makes for one invoice: (days after due date, kind, value).

    kind 'rest' pays whatever is still open, 'share' pays a share of the invoice total.
    """
    if behaviour == "defaulter":
        if index >= stop_after:
            if rng.random() < DEFAULT_LATE_PAY_SHARE:
                return [
                    (int(rng.integers(DEFAULT_LATE_DAYS[0], DEFAULT_LATE_DAYS[1] + 1)), "rest", 1.0)
                ]
            return []
        behaviour = "occasionally_late"
    if behaviour == "on_time":
        return [(clipped_normal(rng, ON_TIME_OFFSET), "rest", 1.0)]
    if behaviour == "occasionally_late":
        if rng.random() >= OCCASIONAL_LATE_SHARE:
            return [(clipped_normal(rng, ON_TIME_OFFSET), "rest", 1.0)]
        late = 1 + int(rng.exponential(LATE_EXPONENTIAL_MEAN))
        return [(min(LATE_MAX_DAYS, late), "rest", 1.0)]
    if behaviour == "chronically_late":
        if rng.random() < CHRONIC_VERY_LATE_SHARE:
            return [(int(rng.integers(61, 100)), "rest", 1.0)]
        late = float(rng.lognormal(math.log(CHRONIC_MEDIAN_DAYS), CHRONIC_SIGMA))
        return [(int(min(CHRONIC_CLIP[1], max(CHRONIC_CLIP[0], round(late)))), "rest", 1.0)]
    # partial_payer
    first = clipped_normal(rng, PARTIAL_FIRST_OFFSET)
    events = [(first, "share", float(rng.uniform(*PARTIAL_FIRST_SHARE)))]
    if rng.random() < PARTIAL_REST_SHARE:
        gap = int(rng.integers(PARTIAL_REST_DAYS[0], PARTIAL_REST_DAYS[1] + 1))
        events.append((first + gap, "rest", 1.0))
    return events


def allocate(remaining: list[int], amount: int) -> list[tuple[int, int]]:
    """Apply `amount` paisa to the open lines in line order; updates `remaining`."""
    out = []
    for i, open_amount in enumerate(remaining):
        if amount <= 0:
            break
        take = min(open_amount, amount)
        if take:
            remaining[i] -= take
            amount -= take
            out.append((i + 1, take))
    return out


# ----------------------------------------------------------------------------- the whole set
def build_payments(profile: Profile, master: dict, billing: gl.Billing, rng_for) -> Payments:
    """Payments, allocations, final invoice statuses and settlements for a profile."""
    we = profile.window_end
    tenants = master["tenants"]
    behaviour_rng = rng_for("payments.behaviour")
    behaviour = {}
    favourite = {}
    stop_after = {}
    for t in tenants:  # in tenant order: a fixed number of draws per tenant
        kind = t["tenant_type"]
        behaviour[t["tenant_code"]] = gm.pick_weighted(
            behaviour_rng, BEHAVIOURS, BEHAVIOUR_WEIGHTS[kind]
        )
        favourite[t["tenant_code"]] = gm.pick_weighted(
            behaviour_rng, METHOD_CODES, METHOD_WEIGHTS[kind]
        )
        stop_after[t["tenant_code"]] = int(
            behaviour_rng.integers(DEFAULT_PAID_MONTHS[0], DEFAULT_PAID_MONTHS[1] + 1)
        )
    tenant_index = {t["tenant_code"]: i for i, t in enumerate(tenants)}
    # Planted pattern 1 (US-2.6): every tenant who rents in the high-arrears building draws the
    # behaviour again from ARREARS_WEIGHTS, on a stream of its own (the other tenants keep theirs).
    arrears_code = pat.arrears_building(master)
    unit_building = {u["unit_id"]: u["building_code"] for u in master["units"]}
    in_arrears_building = {
        lease.tenant_code
        for lease in billing.leases
        if unit_building[lease.unit_id] == arrears_code
    }
    arrears_rng = rng_for("payments.arrears")
    for t in tenants:  # tenant order: a fixed number of draws
        draw = gm.pick_weighted(arrears_rng, BEHAVIOURS, pat.ARREARS_WEIGHTS)
        if t["tenant_code"] in in_arrears_building:
            behaviour[t["tenant_code"]] = draw

    lines_of: dict[str, list[list]] = defaultdict(list)
    for row in billing.line_rows:
        lines_of[row[0]].append(row)
    lease_of = {lease.number: lease for lease in billing.leases}
    work = sorted(
        billing.invoice_rows,
        key=lambda r: (lease_of[r[1]].tenant_code, r[2], r[0]),
    )

    rng = rng_for("payments.pay")
    pays: list[Pay] = []
    invoice_paid: dict[str, int] = {}
    seen_invoices: defaultdict[str, int] = defaultdict(int)  # invoices met so far per tenant

    def make_pay(code, day, method, amount, remaining, invoice_number, status="Cleared"):
        pay = Pay(
            tenant_idx=tenant_index[code],
            tenant_code=code,
            day=day,
            second=0,
            method=method,
            amount=amount,
            status=status,
            allocations=[
                (invoice_number, line_no, paisa) for line_no, paisa in allocate(remaining, amount)
            ],
        )
        if method in ("CASH", "CHEQUE"):
            pay.second = int(rng.integers(9 * 3600, 18 * 3600))
        else:
            pay.second = int(rng.integers(0, 86_400))
        pay.order = len(pays)
        pays.append(pay)
        return pay

    for number, lease_number, invoice_date, due_date, _status in work:
        code = lease_of[lease_number].tenant_code
        kind = behaviour[code]
        index = seen_invoices[code]
        seen_invoices[code] += 1
        lines = lines_of[number]
        net = [gl_paisa(row[6]) for row in lines]
        remaining = list(net)
        events = plan(kind, rng, index, stop_after[code])
        if events and events[0][1] == "rest" and len(net) > 1 and rng.random() < SPLIT_SHARE:
            offset = events[0][0]
            low, high = SPLIT_DAYS
            events = [
                (offset, "first_line", net[0]),
                (offset + int(rng.integers(low, high + 1)), "rest", 1.0),
            ]
        for offset, how, value in events:
            day = max(due_date + timedelta(days=offset), invoice_date)
            if day > we or not sum(remaining):
                continue
            open_total = sum(remaining)
            if how == "rest":
                amount = open_total
            elif how == "first_line":
                amount = remaining[0]
            else:
                amount = min(open_total, int(round(sum(net) * value / 100)) * 100)
            if amount <= 0:
                continue
            if rng.random() < FAVOURITE_SHARE:
                method = favourite[code]
            else:
                method = gm.pick_weighted(
                    rng, METHOD_CODES, METHOD_WEIGHTS[tenants[tenant_index[code]]["tenant_type"]]
                )
            pay = make_pay(code, day, method, amount, remaining, number)
            if method != "CHEQUE":
                continue
            risky = kind in ("chronically_late", "defaulter")
            bounce_day = day + timedelta(days=int(rng.integers(BOUNCE_DAYS[0], BOUNCE_DAYS[1] + 1)))
            if bounce_day > we or rng.random() >= BOUNCE_SHARE["risky" if risky else "normal"]:
                continue
            reversal = Pay(
                tenant_idx=pay.tenant_idx,
                tenant_code=code,
                day=bounce_day,
                second=int(rng.integers(9 * 3600, 18 * 3600)),
                method="CHEQUE",
                amount=-pay.amount,
                status="Bounced",
                allocations=[(n, ln, -p) for n, ln, p in pay.allocations],
                reversal_of=pay,
                order=len(pays),
            )
            pays.append(reversal)
            for _n, line_no, paisa in pay.allocations:
                remaining[line_no - 1] += paisa
            repay_day = bounce_day + timedelta(
                days=int(rng.integers(REPAY_DAYS[0], REPAY_DAYS[1] + 1))
            )
            if repay_day <= we and rng.random() < REPAY_SHARE:
                repay_method = gm.pick(rng, REPLACEMENT_METHODS)
                make_pay(code, repay_day, repay_method, pay.amount, remaining, number)

    pays.sort(key=lambda p: (p.paid_at, p.tenant_idx, p.order))
    for n, pay in enumerate(pays, start=1):
        pay.reference = f"PAY-{n:07d}"
    for pay in pays:
        for number, _line_no, paisa in pay.allocations:
            invoice_paid[number] = invoice_paid.get(number, 0) + paisa

    payment_rows = [
        [
            p.reference, p.tenant_code, p.paid_at, p.method, gl.money(p.amount), p.status,
            p.reversal_of.reference if p.reversal_of else None,
        ]
        for p in pays
    ]  # fmt: skip
    allocation_rows = sorted(
        [p.reference, number, line_no, gl.money(paisa)]
        for p in pays
        for number, line_no, paisa in p.allocations
    )
    totals = {number: sum(gl_paisa(r[6]) for r in rows) for number, rows in lines_of.items()}
    invoice_rows = []
    for number, lease_number, invoice_date, due_date, _status in billing.invoice_rows:
        paid = invoice_paid.get(number, 0)
        status = "Paid" if paid >= totals[number] else "Partial" if paid > 0 else "Overdue"
        invoice_rows.append([number, lease_number, invoice_date, due_date, status])

    settlements, unmatched = build_settlements(pays, rng_for("payments.settlement"))
    return Payments(
        pays, behaviour, payment_rows, allocation_rows, invoice_rows, settlements, unmatched
    )


def gl_paisa(text: str) -> int:
    whole, _, frac = text.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def build_settlements(pays: list[Pay], rng: np.random.Generator):
    """One settlement per electronic payment, grouped by (channel file name, settlement date)."""
    records: dict[tuple[str, date], list[tuple]] = defaultdict(list)
    unmatched = []
    for pay in pays:  # in reference order: a fixed number of draws per electronic payment
        if pay.method not in ELECTRONIC or pay.status != "Cleared":
            continue
        days, weights = SETTLEMENT_LAG[pay.method]
        lag = int(gm.pick_weighted(rng, days, weights))
        if rng.random() < P_NO_SETTLEMENT:
            unmatched.append(pay)
            continue
        fee = fee_paisa(pay.method, pay.amount)
        records[(pay.method, pay.day + timedelta(days=lag))].append((pay, fee))
    files: dict[tuple[str, date], list[list]] = {}
    for (method, day), items in sorted(records.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        items.sort(key=lambda it: it[0].reference)
        files[(ELECTRONIC[method], day)] = [
            [
                f"{SETTLEMENT_PREFIX[method]}{day:%Y%m%d}{i:04d}", pay.reference, pay.day, day,
                gl.money(pay.amount), gl.money(fee), gl.money(pay.amount - fee),
            ]
            for i, (pay, fee) in enumerate(items, start=1)
        ]  # fmt: skip
    return files, unmatched


@stage("payments", "Payments, allocations, invoice status and bank and wallet settlements (US-2.4)")
def payments(ctx: Context) -> None:
    master = gm.build_master(ctx.profile, ctx.rng)
    billing = gl.build_billing(ctx.profile, master, ctx.rng)
    result = build_payments(ctx.profile, master, billing, ctx.rng)
    ctx.write_csv("s1/payments.csv", PAYMENT_COLS, result.payment_rows)
    ctx.write_csv("s1/payment_allocations.csv", ALLOCATION_COLS, result.allocation_rows)
    ctx.write_csv(
        "s1/invoices.csv", gl.INVOICE_COLS, result.invoice_rows
    )  # same rows, final status
    for (channel, day), rows in result.settlements.items():
        ctx.write_csv(f"s3/settlement_{channel}_{day.isoformat()}.csv", SETTLEMENT_COLS, rows)
