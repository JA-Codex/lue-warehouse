"""US-2.3: leases, lease events, invoices and invoice lines for the synthetic LUE portfolio.

Writes, for the chosen profile (etl/generator_config.py), four S1 files (PostgreSQL source
src_pms, as CSV
files that scripts/db_load_source.py loads):

    s1/leases.csv, s1/lease_events.csv, s1/invoices.csv, s1/invoice_lines.csv

The data is CLEAN here: no defect of any kind. US-2.6 plants the defects and the answer key;
US-2.4 adds the
payments. Everything in this file is a pure function of (profile, seed), so a later stage can
rebuild the
same objects with `build_billing(profile, master, rng_for)` instead of re-reading the CSV files.

How the portfolio behaves (every number is a named constant below):

* Every lease starts on the 1st of a month and ends on the last day of a month. Residential leases
run 11
  months. Commercial leases (offices, shops) run 12, 24 or 36 months.
* The window opens with exactly `profile.target_active_leases` units let. Those OPENING leases are
the leases
  PropertyHub migrated at go-live: they carry start dates before the window (a uniform point of
  their term
  has already passed), so lease ends are spread over the year instead of piling up in one month.
  Their
  tenant records were created at go-live, after the lease started: this is the one place where a
  lease
  starts before its tenant record. No invoice and no lease event ever predates its tenant record.
* A lease that ends before the window ends is resolved: the tenant renews (a new lease starts the
next day,
  same tenant, rent escalated) or leaves (notice, then termination on the end date, then a vacancy
  gap, then
  a new tenant). A lease that ends on or after the last day of the window is still Active and
  unresolved.
  Leases do not end early: a "termination" is a tenant who does not renew at the end of the term.
* Rent is constant inside a lease. It changes only at renewal. `rent_review_type` says how the
NEXT rent is
  set: 'Annual escalation' (12-month commercial leases: contractual 5 to 10 percent uplift at
  renewal) or
  'Fixed' (everything else). Mid-lease rent changes are a defect that US-2.6 plants.
* New tenants move in with a seasonal peak in June to August. Vacancy gaps vary by unit (some
units are
  chronically hard to let).
* One invoice per lease per calendar month, issued on the 1st and due on the 10th. Lines: rent
(always),
  service charge (most leases), utility (some leases: always, sometimes or never). Commercial rent
  and
  service carry 16 percent tax. `discount_amount` is 0: US-2.5 and US-2.6 own incentives.

Added in US-2.6 (etl/patterns.py has the numbers):

* Renewal churn in one city (pattern 6): tenants in patterns.CHURN_CITY renew less often.
* Incentive offers (pattern 4): when a tenant leaves, an offer is posted on the vacant unit in a
  quarter of the cases, and then the next tenant comes sooner. The offers are returned in
  `Billing.offers`; gen_tickets writes them as s6/incentive_log.csv. The offer is not billed as a
  discount (`discount_amount` stays 0): the coverage fact needs the offer windows only.
* Defect mid_lease_rent_change: with a non-zero rate (generator_config.DEFECT_RATES), a few
  leases bill a higher rent from a month inside the lease while the lease record keeps the signed
  rent. A clean control batch (`--clean`, all rates 0) has none, and rent is then constant inside
  every lease as above.

Contracts the next stories rely on (US-2.4 and later):

* lease_number is `L-<start year>-<5-digit sequence>`; the sequence runs in order of (start_date,
unit_id).
  invoice_number is `INV-<yyyy>-<mm>-<4-digit lease sequence>`: 16 characters, the width of the
  column. (The
  data dictionary's example INV-2026-03-00831 has 17 characters and would not fit its own column.)
* A tenant never holds two leases at once, except a corporate tenant, who may hold up to
MAX_CORPORATE_LEASES.
* Every invoice and every lease event is dated on or after its tenant's record
(`tenants.updated_at`).
* invoices.status is 'Issued' when this stage writes it. US-2.4 settles the invoices and
  rewrites the file, so it decides Paid, Partial or Overdue.
* Money is whole rupees in the S1 columns with two decimals ('85000.00'); tax is exact because 16
percent of
  a whole-rupee amount is a whole number of paisa.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from etl import gen_master as gm  # a module reference: also works while gen_master is still loading
from etl import patterns as pat
from etl.generate_data import Context, GeneratorError, stage
from etl.generator_config import Profile
from etl.reference_data import (
    CHARGE_TYPES,
    INCENTIVE_OFFER_DAYS,
    INCENTIVE_OFFERS,
    LEASE_EVENT_TYPES,
)

# ----------------------------------------------------------------------------- constants
RESIDENTIAL_TERM = 11  # months
COMMERCIAL_TERMS = (12, 24, 36)
COMMERCIAL_TERM_WEIGHTS = (0.35, 0.35, 0.30)
DUE_DAY = 10  # invoices are issued on the 1st and due on the 10th
TAX_PERCENT = 16  # on commercial rent and commercial service charge; nothing else is taxed
MAX_SEQUENCE = 9999  # the invoice number has room for a 4-digit lease sequence
MAX_CORPORATE_LEASES = 4  # leases one corporate tenant may hold at the same time

# Market rent: PKR per square foot per month for an apartment of building class B, mid-2023 prices.
RENT_PSF = {"Lahore": 62.0, "Karachi": 68.0, "Islamabad": 88.0, "Faisalabad": 42.0}
CLASS_RENT = {"A": 1.30, "B": 1.00, "C": 0.78}
TYPE_RENT = {"Apartment": 1.0, "Office": 1.35, "Shop": 2.10}
FURNISHED_PREMIUM = 1.18
MARKET_GROWTH = 0.09  # rents grow 9 percent a year
GROWTH_BASE = date(2023, 7, 1)
RENT_STEP = 500  # rents are rounded to the nearest 500 rupees
SERVICE_PSF = {"Apartment": 11.0, "Office": 22.0, "Shop": 28.0}  # PKR per sq ft per month, class B
CLASS_SERVICE = {"A": 1.20, "B": 1.00, "C": 0.80}
SERVICE_STEP = 50
P_SERVICE = {"Residential": 0.90, "Commercial": 0.97}  # share of leases that pay a service charge
UTILITY_MODES = ("none", "sometimes", "always")
UTILITY_MODE_WEIGHTS = (0.40, 0.30, 0.30)  # 'sometimes' bills a utility line in half the months
UTILITY_PSF = {"Residential": 7.5, "Commercial": 12.0}
UTILITY_SEASON = {1: 0.8, 2: 0.8, 3: 1.0, 4: 1.25, 5: 1.25, 6: 1.7, 7: 1.7, 8: 1.7, 9: 1.25,
                  10: 1.0, 11: 0.8, 12: 0.8}  # fmt: skip
UTILITY_STEP = 10

# Renewal: chance that a tenant renews at the end of the term (city, then class, then lease type).
# US-2.6 lowers it in one city (patterns.CHURN_CITY) and raised the others by 0.04 so the
# portfolio-wide share stays where US-2.3 had it.
RENEWAL_BASE = {"Lahore": 0.50, "Karachi": 0.49, "Islamabad": 0.51, "Faisalabad": 0.50}
RENEWAL_CLASS = {"A": 0.03, "B": 0.0, "C": -0.04}
RENEWAL_COMMERCIAL_BONUS = 0.08
RESIDENTIAL_ESCALATION = (0.03, 0.12)  # uniform
ANNUAL_ESCALATION_CHOICES = (0.05, 0.075, 0.10)
FIXED_RENEWAL_ESCALATION = (0.10, 0.18)  # a multi-year fixed lease catches up at renewal

# Vacancy between two tenants, in months: GAP_FLOOR + GAP_MEDIAN * letability * lognormal(0,
# GAP_SIGMA).
GAP_FLOOR = 0.5
GAP_MEDIAN = 1.2
GAP_SIGMA = 0.9
LETABILITY_SIGMA = 0.5  # spread of the per-unit "hard to let" factor
CLASS_LETABILITY = {"A": 0.8, "B": 1.0, "C": 1.3}
COMMERCIAL_LETABILITY = 1.3
# New tenants move in on the 1st of a month; June to August is the peak (relative weights).
MOVE_IN_SEASON = {1: 1.0, 2: 0.9, 3: 0.9, 4: 0.8, 5: 1.0, 6: 2.2, 7: 2.4, 8: 2.2, 9: 0.9,
                  10: 0.7, 11: 0.6, 12: 0.6}  # fmt: skip
MOVE_IN_LOOKAHEAD = 6  # months a new tenant may wait for a better month
MOVE_IN_DECAY = 0.75  # each extra month of waiting is this much less likely
DECISION_LEAD_DAYS = (30, 60)  # notice or renewal is agreed this long before the end date
SIGN_LEAD_DAYS = (7, 30)  # a new lease is signed this long before the move-in

# Who holds the lease: share of NEW leases (not renewals) taken by corporate tenants.
P_CORPORATE = {"Residential": 0.07, "Commercial": 0.45}

LEASE_COLS = [
    "lease_number", "unit_id", "tenant_code", "lease_type", "start_date", "end_date",
    "monthly_rent", "rent_review_type", "previous_lease_number", "status",
]  # fmt: skip
EVENT_COLS = ["event_id", "lease_number", "event_code", "event_date"]
INVOICE_COLS = ["invoice_number", "lease_number", "invoice_date", "due_date", "status"]
LINE_COLS = [
    "invoice_number", "line_no", "charge_code", "billed_amount", "tax_amount",
    "discount_amount", "net_amount",
]  # fmt: skip
EVENT_ORDER = {code: i for i, (code, _name, _exit) in enumerate(LEASE_EVENT_TYPES)}
CHARGE_CODES = {code for code, _name, _category in CHARGE_TYPES}


# ----------------------------------------------------------------------------- small helpers
def first_of_month(d: date) -> date:
    return d.replace(day=1)


def add_months(first: date, n: int) -> date:
    """The 1st of the month n months after (before, if n is negative) the month of `first`."""
    index = first.year * 12 + first.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def month_end(first: date) -> date:
    return add_months(first, 1) - timedelta(days=1)


def growth(d: date) -> float:
    """Market growth factor at a date (1.0 on 2023-07-01)."""
    return (1.0 + MARKET_GROWTH) ** ((d - GROWTH_BASE).days / 365.25)


def round_to(value: float, step: int) -> int:
    return max(step, int(round(value / step)) * step)


def money(paisa: int) -> str:
    """Whole paisa as '85000.00' (negative numbers keep the sign in front)."""
    sign = "-" if paisa < 0 else ""
    return f"{sign}{abs(paisa) // 100}.{abs(paisa) % 100:02d}"


def uniform_day(rng: np.random.Generator, first: date, last: date) -> date:
    """A random day between two dates, inclusive (the first date if the range is empty)."""
    if last <= first:
        return first
    return first + timedelta(days=int(rng.integers(0, (last - first).days + 1)))


# ----------------------------------------------------------------------------- the lease object
@dataclass(eq=False)
class Lease:
    unit_id: int
    lease_type: str
    start: date
    end: date
    term: int
    review: str
    rent: int  # whole rupees per month, constant for the whole lease
    service: int  # whole rupees per month, 0 when the lease has no service charge
    utility_mode: str
    legacy: bool  # an opening lease migrated at go-live
    prev: Lease | None = None
    slot: int = 0  # one number per chain of renewals (the tenant is the same along a chain)
    outcome: str = "Active"  # Active, Renewed or Terminated
    decision: date | None = None  # when notice was given or the renewal agreed
    sign_date: date | None = (
        None  # only for the first lease of a chain that starts inside the window
    )
    tenant_idx: int = -1
    tenant_code: str = ""
    seq: int = 0
    number: str = ""
    rent_change: tuple | None = None  # (first month, new rent): a mid-lease change (US-2.6 defect)

    @property
    def status(self) -> str:
        return self.outcome


@dataclass
class Billing:
    """Everything this story generates, as Python objects and as CSV-ready rows."""

    leases: list[Lease]
    lease_rows: list[list]
    event_rows: list[list]
    invoice_rows: list[list]
    line_rows: list[list]
    # US-2.6. Offers posted on vacant units: dicts with unit_id, offer_code, start_date, end_date
    # (gen_tickets writes them to s6/incentive_log.csv). Mid-lease rent changes: one dict per
    # invoice line billed at the changed rent (gen_defects lists them in the answer key).
    offers: list[dict] = field(default_factory=list)
    rent_change_lines: list[dict] = field(default_factory=list)


# ----------------------------------------------------------------------------- unit parameters
@dataclass
class UnitParams:
    unit: dict
    city: str
    klass: str
    lease_type: str
    letability: float  # larger means a longer vacancy
    base_rent: float  # PKR per month at GROWTH_BASE
    base_service: float


def make_unit_params(master: dict, rng: np.random.Generator) -> list[UnitParams]:
    buildings = {b.code: b for b in master["buildings"]}
    params = []
    for unit in master["units"]:
        b = buildings[unit["building_code"]]
        commercial = unit["unit_type"] != "Apartment"
        rent = (
            unit["area_sqft"]
            * RENT_PSF[b.city]
            * CLASS_RENT[b.building_class]
            * TYPE_RENT[unit["unit_type"]]
            * (FURNISHED_PREMIUM if unit["furnished"] else 1.0)
            * (1.0 + 0.012 * min(unit["floor_no"], 8))
            * float(rng.lognormal(0.0, 0.07))
        )
        letability = (
            float(rng.lognormal(0.0, LETABILITY_SIGMA))
            * CLASS_LETABILITY[b.building_class]
            * (COMMERCIAL_LETABILITY if commercial else 1.0)
        )
        params.append(
            UnitParams(
                unit=unit,
                city=b.city,
                klass=b.building_class,
                lease_type="Commercial" if commercial else "Residential",
                letability=letability,
                base_rent=rent,
                base_service=unit["area_sqft"]
                * SERVICE_PSF[unit["unit_type"]]
                * CLASS_SERVICE[b.building_class],
            )
        )
    return params


# ----------------------------------------------------------------------------- phase A: unit
# timelines
def draw_term(rng: np.random.Generator, lease_type: str) -> tuple[int, str]:
    if lease_type == "Residential":
        return RESIDENTIAL_TERM, "Fixed"
    term = gm.pick_weighted(rng, COMMERCIAL_TERMS, COMMERCIAL_TERM_WEIGHTS)
    return term, "Annual escalation" if term == 12 else "Fixed"


def renewal_probability(p: UnitParams) -> float:
    prob = RENEWAL_BASE[p.city] + RENEWAL_CLASS[p.klass]
    if p.city == pat.CHURN_CITY:  # planted pattern 6: renewal churn in one city
        prob -= pat.CHURN_RENEWAL_DROP
    if p.lease_type == "Commercial":
        prob += RENEWAL_COMMERCIAL_BONUS
    return min(0.9, max(0.2, prob))


def draw_gap_days(rng: np.random.Generator, p: UnitParams) -> int:
    months = GAP_FLOOR + GAP_MEDIAN * p.letability * float(rng.lognormal(0.0, GAP_SIGMA))
    return int(round(months * 30.4))


def next_move_in(rng: np.random.Generator, earliest: date) -> date:
    """The 1st of the month a new tenant moves in: the first month on or after "
    "`earliest`, or a better one."""
    first = earliest if earliest.day == 1 else add_months(first_of_month(earliest), 1)
    months = [add_months(first, k) for k in range(MOVE_IN_LOOKAHEAD)]
    weights = [MOVE_IN_SEASON[m.month] * MOVE_IN_DECAY**k for k, m in enumerate(months)]
    return gm.pick_weighted(rng, months, weights)


def new_lease(
    rng: np.random.Generator,
    p: UnitParams,
    start: date,
    legacy: bool,
    term_review: tuple[int, str] | None = None,
) -> Lease:
    """A first lease of a chain: market rent at `start`, a random service and utility set-up."""
    term, review = term_review or draw_term(rng, p.lease_type)
    rent = round_to(p.base_rent * growth(start) * float(rng.uniform(0.97, 1.03)), RENT_STEP)
    has_service = rng.random() < P_SERVICE[p.lease_type]
    service = round_to(p.base_service * growth(start), SERVICE_STEP) if has_service else 0
    return Lease(
        unit_id=p.unit["unit_id"],
        lease_type=p.lease_type,
        start=start,
        end=month_end(add_months(start, term - 1)),
        term=term,
        review=review,
        rent=rent,
        service=service,
        utility_mode=gm.pick_weighted(rng, UTILITY_MODES, UTILITY_MODE_WEIGHTS),
        legacy=legacy,
    )


def renewal_of(rng: np.random.Generator, p: UnitParams, prev: Lease) -> Lease:
    """The lease that follows `prev` for the same tenant: starts the next day, rent escalated."""
    start = prev.end + timedelta(days=1)
    if prev.lease_type == "Residential":
        escalation = float(rng.uniform(*RESIDENTIAL_ESCALATION))
    elif prev.review == "Annual escalation":
        escalation = float(gm.pick(rng, ANNUAL_ESCALATION_CHOICES))
    else:
        escalation = float(rng.uniform(*FIXED_RENEWAL_ESCALATION))
    term, review = draw_term(rng, p.lease_type)
    service = round_to(p.base_service * growth(start), SERVICE_STEP) if prev.service else 0
    return Lease(
        unit_id=prev.unit_id,
        lease_type=prev.lease_type,
        start=start,
        end=month_end(add_months(start, term - 1)),
        term=term,
        review=review,
        rent=max(round_to(prev.rent * (1.0 + escalation), RENT_STEP), prev.rent + RENT_STEP),
        service=service,
        utility_mode=prev.utility_mode,
        legacy=False,
        prev=prev,
        slot=prev.slot,
    )


def simulate_unit(
    p: UnitParams,
    rng: np.random.Generator,
    window_start: date,
    window_end: date,
    occupied_at_open: bool,
    next_slot,
    offer_rng: np.random.Generator | None = None,
    offers: list | None = None,
) -> list[Lease]:
    """The whole lease history of one unit inside the window, oldest first.

    `offer_rng` decides the incentive offers on vacancies (planted pattern 4) and `offers`
    collects them; without them no offer is posted. A stream of its own keeps the offer draws out
    of the timeline stream.
    """
    if occupied_at_open:
        term, review = draw_term(rng, p.lease_type)
        elapsed = 1 + int(
            rng.integers(0, term - 1)
        )  # months of the term already gone (1 to term-1)
        start = add_months(first_of_month(window_start), -elapsed)
        lease = new_lease(rng, p, start, legacy=True, term_review=(term, review))
    else:
        residual = draw_gap_days(rng, p) * float(rng.uniform(0.15, 1.0))  # vacancy already running
        if offer_rng is not None and offer_rng.random() < pat.P_OFFER_ON_VACANCY:
            start = post_offer(offer_rng, p, window_start, int(residual), window_end, offers)
        else:
            start = next_move_in(rng, window_start + timedelta(days=int(residual)))
        if start > window_end:
            return []
        lease = new_lease(rng, p, start, legacy=False)
    lease.slot = next_slot()
    history: list[Lease] = []
    while True:
        history.append(lease)
        if lease.end >= window_end:
            break  # still running when the window closes: unresolved
        lead = int(rng.integers(DECISION_LEAD_DAYS[0], DECISION_LEAD_DAYS[1] + 1))
        decision = lease.end - timedelta(days=lead)
        if decision < window_start:  # the decision fell before go-live: spread it over what is left
            decision = uniform_day(
                rng, window_start, max(window_start, lease.end - timedelta(days=7))
            )
        lease.decision = decision
        if rng.random() < renewal_probability(p):
            lease.outcome = "Renewed"
            lease = renewal_of(rng, p, lease)
        else:
            lease.outcome = "Terminated"
            gap = draw_gap_days(rng, p)
            if offer_rng is not None and offer_rng.random() < pat.P_OFFER_ON_VACANCY:
                start = post_offer(
                    offer_rng, p, lease.end + timedelta(days=1), gap, window_end, offers
                )
            else:
                start = next_move_in(rng, lease.end + timedelta(days=1 + gap))
            if start > window_end:
                break  # empty when the window closes
            lease = new_lease(rng, p, start, legacy=False)
            lease.slot = next_slot()
    return history


def post_offer(
    rng: np.random.Generator,
    p: UnitParams,
    vacant_from: date,
    gap: int,
    window_end: date,
    offers: list | None,
) -> date:
    """Post an incentive offer on a unit vacant from `vacant_from`; return the next move-in.

    Planted pattern 4: with an offer the vacancy is OFFER_GAP_FACTOR as long, and the new tenant
    takes the unit in the first month that is free instead of waiting for a better month.
    `vacant_from` is the day after a move-out (a 1st) or the window's first day.
    """
    lo, hi = pat.OFFER_POST_DAYS
    posted = vacant_from + timedelta(days=int(rng.integers(lo, hi + 1)))
    choices = [o for o in INCENTIVE_OFFERS if p.unit["unit_type"] in o[5]]
    code = choices[int(rng.integers(len(choices)))][0]
    days = int(gm.pick(rng, INCENTIVE_OFFER_DAYS))
    earliest = vacant_from + timedelta(days=max(1, int(round(gap * pat.OFFER_GAP_FACTOR))))
    start = earliest if earliest.day == 1 else add_months(first_of_month(earliest), 1)
    posted = min(posted, start - timedelta(days=1))  # start is a 1st after vacant_from
    if posted <= window_end and offers is not None:
        end = min(posted + timedelta(days=days - 1), start - timedelta(days=1), window_end)
        offer = {"unit_id": p.unit["unit_id"], "offer_code": code}
        offers.append(offer | {"start_date": posted, "end_date": end})
    return start


# ----------------------------------------------------------------------------- phase B: tenants
def assign_tenants(
    leases: list[Lease], tenants: list[dict], rng: np.random.Generator, window_start: date
):
    """Give every chain of renewals one tenant.

    Tenant records exist from `updated_at`. A lease that starts inside the window gets a tenant
    whose record
    already exists on its start date (the most recent applicant who has not rented yet, or a past
    tenant who
    has moved out and comes back). An opening lease gets a tenant whose record was created before
    the window
    opened (the migration at go-live).
    """
    created = [t["updated_at"].date() for t in tenants]
    individuals = [i for i, t in enumerate(tenants) if t["tenant_type"] == "Individual"]
    corporates = [i for i, t in enumerate(tenants) if t["tenant_type"] == "Corporate"]
    old_pool = [i for i in individuals if created[i] < window_start]  # records migrated at go-live
    in_window = [i for i in individuals if created[i] >= window_start]  # in order of creation
    fresh: list[
        int
    ] = []  # applicants created so far who have not rented yet; the last is the newest
    cursor = 0  # next in_window tenant to join `fresh`
    busy: list[tuple[date, int]] = []  # (chain end, tenant) for individuals who hold a lease
    returning: list[int] = []  # individuals whose last lease has ended: they may rent again
    corporate_ends: dict[int, list[date]] = {i: [] for i in corporates}
    state = {"opening_done": False}

    chains: dict[int, list[Lease]] = {}
    for lease in leases:
        chains.setdefault(lease.slot, []).append(lease)
    for chain in chains.values():
        chain.sort(key=lambda lease: lease.start)
    # Opening chains first (in a random order), then the rest as they start.
    order = sorted(chains.values(), key=lambda c: (not c[0].legacy, c[0].start, c[0].unit_id))
    legacy_chains = [c for c in order if c[0].legacy]
    shuffled = [legacy_chains[int(i)] for i in rng.permutation(len(legacy_chains))]
    order = shuffled + [c for c in order if not c[0].legacy]

    def try_individual(start: date, legacy: bool) -> int | None:
        nonlocal cursor
        if legacy:
            return old_pool.pop(int(rng.integers(len(old_pool)))) if old_pool else None
        if not state["opening_done"]:
            old_pool.sort()  # oldest first, so pop() takes the most recent record
            state["opening_done"] = True
        while cursor < len(in_window) and created[in_window[cursor]] <= start:
            fresh.append(in_window[cursor])
            cursor += 1
        if fresh:
            return fresh.pop()
        while busy and busy[0][0] < start:  # lease ended before this move-in: free to rent again
            returning.append(heapq.heappop(busy)[1])
        if returning:
            return returning.pop(int(rng.integers(len(returning))))
        return old_pool.pop() if old_pool else None

    def try_corporate(start: date, legacy: bool) -> int | None:
        pool = [
            i
            for i in corporates
            if (created[i] < window_start if legacy else created[i] <= start)
            and sum(e >= start for e in corporate_ends[i]) < MAX_CORPORATE_LEASES
        ]
        if not pool:
            return None
        weights = [1.0 + sum(e >= start for e in corporate_ends[i]) for i in pool]
        return pool[int(rng.choice(len(pool), p=np.asarray(weights) / sum(weights)))]

    for chain in order:
        head = chain[0]
        chain_end = chain[-1].end
        prefer_corporate = rng.random() < P_CORPORATE[head.lease_type]
        tries = (
            (try_corporate, try_individual) if prefer_corporate else (try_individual, try_corporate)
        )
        idx = None
        for attempt in tries:
            idx = attempt(head.start, head.legacy)
            if idx is not None:
                break
        if idx is None:
            raise GeneratorError(
                "not enough tenants for the leases the simulation produced; "
                "raise `tenants` in the profile or lower the vacancy"
            )
        if tenants[idx]["tenant_type"] == "Corporate":
            corporate_ends[idx].append(chain_end)
        else:
            heapq.heappush(busy, (chain_end, idx))
        for lease in chain:
            lease.tenant_idx = idx
            lease.tenant_code = tenants[idx]["tenant_code"]


# ----------------------------------------------------------------------------- phase C: lease
# events
def make_events(
    leases: list[Lease], tenants: list[dict], rng: np.random.Generator, ws: date, we: date
):
    """(date, lease sequence, event code, lease number) of every event inside the window."""
    events = []
    for lease in leases:  # leases are in sequence order, so the draws are in a fixed order
        created = tenants[lease.tenant_idx]["updated_at"].date()
        if lease.prev is not None:
            events.append((lease.prev.decision, lease.seq, "RENEW", lease.number))
        elif not lease.legacy:
            lead = int(rng.integers(SIGN_LEAD_DAYS[0], SIGN_LEAD_DAYS[1] + 1))
            sign = lease.start - timedelta(days=lead)
            floor = max(created, ws)
            if (
                sign < floor
            ):  # the tenant record or the window starts later: sign between then and move-in
                sign = uniform_day(rng, floor, lease.start)
            lease.sign_date = sign
            events.append((sign, lease.seq, "SIGN", lease.number))
        if lease.outcome == "Terminated":
            events.append((lease.decision, lease.seq, "NOTICE", lease.number))
            events.append((lease.end, lease.seq, "TERM", lease.number))
    events.sort(key=lambda e: (e[0], e[1], EVENT_ORDER[e[2]]))
    if any(not ws <= e[0] <= we for e in events):
        raise GeneratorError("a lease event fell outside the window")
    return events


# ----------------------------------------------------------------------------- phase D: invoices
def make_invoices(
    leases: list[Lease], units: dict[int, dict], rng: np.random.Generator, ws: date, we: date
):
    invoice_rows, line_rows, changed = [], [], []
    for lease in leases:
        area = units[lease.unit_id]["area_sqft"]
        taxed = lease.lease_type == "Commercial"
        first = max(first_of_month(lease.start), first_of_month(ws))
        last = min(first_of_month(lease.end), first_of_month(we))
        month = first
        while month <= last:
            number = f"INV-{month.year}-{month.month:02d}-{lease.seq:04d}"
            invoice_rows.append([number, lease.number, month, month.replace(day=DUE_DAY), "Issued"])
            rent = lease.rent
            if lease.rent_change is not None and month >= lease.rent_change[0]:
                rent = lease.rent_change[1]
                changed.append(
                    {
                        "invoice_number": number,
                        "line_no": 1,
                        "lease_number": lease.number,
                        "from_month": lease.rent_change[0],
                        "lease_rent": lease.rent,
                        "billed_rent": rent,
                    }
                )
            charges = [("RENT", rent, taxed)]
            if lease.service:
                charges.append(("SERVICE", lease.service, taxed))
            show_utility = lease.utility_mode == "always" or (
                lease.utility_mode == "sometimes" and rng.random() < 0.5
            )
            if show_utility:
                amount = (
                    area
                    * UTILITY_PSF[lease.lease_type]
                    * UTILITY_SEASON[month.month]
                    * float(rng.lognormal(0.0, 0.25))
                )
                charges.append(("UTILITY", round_to(amount, UTILITY_STEP), False))
            for line_no, (code, rupees, with_tax) in enumerate(charges, start=1):
                billed = rupees * 100
                tax = rupees * TAX_PERCENT if with_tax else 0  # 16% of whole rupees is whole paisa
                line_rows.append(
                    [
                        number,
                        line_no,
                        code,
                        money(billed),
                        money(tax),
                        money(0),
                        money(billed + tax),
                    ]
                )
            month = add_months(month, 1)
    invoice_rows.sort(key=lambda r: r[0])
    line_rows.sort(key=lambda r: (r[0], r[1]))
    changed.sort(key=lambda r: r["invoice_number"])
    return invoice_rows, line_rows, changed


def plan_rent_changes(
    leases: list[Lease], rng: np.random.Generator, rate: float, ws: date, we: date
) -> None:
    """Defect mid_lease_rent_change (US-2.6): the rent changes inside a lease.

    The lease record keeps the rent it was signed at; from a month inside the lease the invoices
    bill a higher rent (a negotiated mid-term increase the lease record never caught up with). Only
    leases with at least 3 invoices in the window qualify; the change is never in the first or
    last of them. Applied before the payments are generated, so the tenants pay what is billed.
    """
    if rate <= 0:
        return
    eligible = []
    for lease in leases:
        first = max(first_of_month(lease.start), first_of_month(ws))
        last = min(first_of_month(lease.end), first_of_month(we))
        months = (last.year - first.year) * 12 + last.month - first.month + 1
        if months >= 3:
            eligible.append((lease, first, months))
    if not eligible:
        return
    n = min(len(eligible), max(1, int(round(rate * len(eligible)))))
    for i in sorted(int(k) for k in rng.choice(len(eligible), size=n, replace=False)):
        lease, first, months = eligible[i]
        month = add_months(first, int(rng.integers(1, months - 1)))
        new_rent = round_to(lease.rent * (1.0 + float(rng.uniform(0.04, 0.10))), RENT_STEP)
        lease.rent_change = (month, max(new_rent, lease.rent + RENT_STEP))


# ----------------------------------------------------------------------------- the whole set
def build_billing(profile: Profile, master: dict, rng_for) -> Billing:
    """Leases, events, invoices and lines. `rng_for(name)` returns the stream of one part."""
    ws, we = profile.window_start, profile.window_end
    params = make_unit_params(master, rng_for("leases.units"))
    n_units = len(params)
    n_open = min(profile.target_active_leases, n_units)
    open_rng = rng_for("leases.open")
    weights = np.array([1.0 / p.letability for p in params])
    occupied = set(
        int(i)
        for i in open_rng.choice(n_units, size=n_open, replace=False, p=weights / weights.sum())
    )

    slots = iter(range(1, 10**7))
    timeline_rng = rng_for("leases.timeline")
    offer_rng = rng_for("leases.offers")
    leases: list[Lease] = []
    offers: list[dict] = []
    for i, p in enumerate(params):
        leases.extend(
            simulate_unit(
                p, timeline_rng, ws, we, i in occupied, lambda: next(slots), offer_rng, offers
            )
        )

    leases.sort(key=lambda lease: (lease.start, lease.unit_id))
    if len(leases) > MAX_SEQUENCE:
        raise GeneratorError(
            f"{len(leases)} leases: the invoice number has room for {MAX_SEQUENCE}"
        )
    for seq, lease in enumerate(leases, start=1):
        lease.seq = seq
        lease.number = f"L-{lease.start.year}-{seq:05d}"

    assign_tenants(leases, master["tenants"], rng_for("leases.tenants"), ws)
    events = make_events(leases, master["tenants"], rng_for("leases.events"), ws, we)
    units = {u["unit_id"]: u for u in master["units"]}
    plan_rent_changes(
        leases,
        rng_for("defects.mid_lease_rent_change"),
        profile.defect_rates.get("mid_lease_rent_change", 0.0),
        ws,
        we,
    )
    invoice_rows, line_rows, changed = make_invoices(
        leases, units, rng_for("leases.billing"), ws, we
    )
    offers.sort(key=lambda o: (o["start_date"], o["unit_id"]))

    lease_rows = [
        [
            lease.number, lease.unit_id, lease.tenant_code, lease.lease_type, lease.start,
            lease.end,
            money(lease.rent * 100), lease.review,
            lease.prev.number if lease.prev else None, lease.status,
        ]
        for lease in leases
    ]  # fmt: skip
    event_rows = [[i, number, code, day] for i, (day, _seq, code, number) in enumerate(events, 1)]
    return Billing(leases, lease_rows, event_rows, invoice_rows, line_rows, offers, changed)


@stage("leases_invoices", "Leases, lease events, invoices and invoice lines (US-2.3)")
def leases_invoices(ctx: Context) -> None:
    master = gm.build_master(ctx.profile, ctx.rng)
    b = build_billing(ctx.profile, master, ctx.rng)
    ctx.write_csv("s1/leases.csv", LEASE_COLS, b.lease_rows)
    ctx.write_csv("s1/lease_events.csv", EVENT_COLS, b.event_rows)
    ctx.write_csv("s1/invoices.csv", INVOICE_COLS, b.invoice_rows)
    ctx.write_csv("s1/invoice_lines.csv", LINE_COLS, b.line_rows)
