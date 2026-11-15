"""US-2.5: maintenance tickets (S4) and the incentive log (S6) for the synthetic LUE portfolio.

Writes, for the chosen profile (etl/generator_config.py):

  S4  s4/tickets.json          the tenant-app export: one ticket per request, with its nested
                               status history (Raised, Assigned, Resolved, Verified)
  S6  s6/offers.csv            the incentive catalogue (the source of dim_incentive)
      s6/incentive_log.csv     one row per offer posted on one unit, with start and end dates

S5 weather is not generated: it is real data, downloaded once by etl/refresh_weather.py into the
committed data/weather_cache.json (decision D12). Nothing here reads the network or the cache,
so the generator runs anywhere and its output depends only on (profile, seed).

The data is CLEAN here (plan US-2.5: valid references "before defect injection"). US-2.6 injects the
defects (missing resolve times, statuses out of order, unit codes without the building prefix, mixed
date formats) and plants the patterns (a slow vendor, rain-driven leaks, an incentive that shortens
vacancy).

Contracts the next stories rely on:

* Every ticket references a real unit (building_code + unit_no, the unit's business key), a real
  subcategory (reference_data.MAINTENANCE_SUBCATEGORIES) and, once assigned, a real vendor whose
  trade serves that category (category "Other" is served by "General maintenance").
* ticket_id is MR-<year raised>-<5-digit sequence in that year>, in order of raised time: 13
  characters (fact_maintenance_request.request_number is VARCHAR(14)).
* status_history is in time order, each status at most once, always starting with Raised; a ticket's
  "status" is its last entry. Events after the export moment (the window's last second) have not
  happened yet, so tickets raised near the end are still open: the fact maps them to -2 dates.
* is_emergency is true exactly when priority is "Emergency". is_recurring is true exactly when the
  same unit had a ticket of the same subcategory raised in the 90 days before. Both feed
  dim_request_flags.
* estimate exists from Assigned onward and final_cost from Resolved onward (whole rupees).
* Tickets carry no tenant: the fact finds the tenant from the lease active on the raised date (E7),
  or -2 for a vacant unit. So US-2.5 needs only the master data (plan dependency: US-2.2).
* Incentive windows lie inside the window, reference real units, and never overlap on one unit.
  Whether the unit was vacant on a day is decided by the coverage fact (E7), from the leases.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from etl import gen_master as gm  # a module reference: also works while gen_master is loading
from etl.generate_data import Context, GeneratorError, stage
from etl.generator_config import Profile
from etl.reference_data import MAINTENANCE_SUBCATEGORIES, TRADES

EXPORT_SYSTEM = "LUE tenant app"
FOLLOW_UP_SHARE = 0.10  # tickets that are a repeat of an earlier one (same unit, same problem)
FOLLOW_UP_DAYS = (5, 80)  # a repeat comes this many days after the first ticket
RECURRING_DAYS = 90  # is_recurring: the same unit and subcategory within this many days before
NEVER_VERIFIED = 0.04  # resolved tickets the building manager never verifies
STAFF_REPORTED = 0.15  # tickets raised by building staff instead of the tenant
COMMON_AREA = ("OTH-LIFT", "OTH-SEC", "OTH-CLEAN")  # always raised by staff

TRADE_FOR_CATEGORY = {
    "Plumbing": "Plumbing",
    "Electrical": "Electrical",
    "HVAC": "HVAC",
    "Civil": "Civil",
    "Pest control": "Pest control",
    "Other": "General maintenance",
}
CATEGORY_SHARE = {  # share of all tickets before seasonality
    "Plumbing": 0.26,
    "Electrical": 0.22,
    "HVAC": 0.15,
    "Civil": 0.17,
    "Pest control": 0.07,
    "Other": 0.13,
}
BASE_COST = {  # typical vendor estimate in PKR
    "Plumbing": 3500,
    "Electrical": 3000,
    "HVAC": 6500,
    "Civil": 9000,
    "Pest control": 4500,
    "Other": 3000,
}
EMERGENCY_SHARE = {
    "ELE-OUT": 0.50, "OTH-LIFT": 0.50, "PLB-SEWER": 0.45, "ELE-BRKR": 0.30, "HVC-CHLR": 0.25,
    "PLB-LEAK": 0.20, "ELE-WIRE": 0.20, "ELE-GEN": 0.20, "PLB-TANK": 0.15,
}  # fmt: skip
DEFAULT_EMERGENCY_SHARE = 0.05
HIGH_SHARE = 0.25  # of the non-emergency tickets
TENANT_CAUSED_SHARE = {
    "PLB-BLOCK": 0.40, "CIV-DOOR": 0.30, "ELE-SWITCH": 0.20, "CIV-FLOOR": 0.20, "PLB-TAP": 0.15,
    "OTH-LIFT": 0.0, "OTH-SEC": 0.0, "OTH-CLEAN": 0.0,
}  # fmt: skip
DEFAULT_TENANT_CAUSED_SHARE = 0.06
APARTMENT_ONLY = ("PLB-GEYSER",)
COMMERCIAL_ONLY = ("HVC-CHLR",)
ASSIGN_MEDIAN_HOURS = {"Emergency": 1.5, "High": 6.0, "Normal": 18.0}
RESOLVE_RATIO_MEDIAN = 0.62  # resolve time as a share of the SLA in force (lognormal median)
RESOLVE_RATIO_SIGMA = 0.55  # gives roughly one ticket in five over its SLA
RATING_WEIGHT = {"A": 1.3, "B": 1.0, "C": 0.7}  # better vendors get more jobs
RATING_SPEED = {"A": 0.85, "B": 1.0, "C": 1.25}  # and finish sooner
CLASS_FACTOR = {"A": 0.8, "B": 1.0, "C": 1.35}  # older, cheaper buildings break more
TYPE_FACTOR = {"Apartment": 1.0, "Office": 0.8, "Shop": 0.6}
LOCATIONS = {
    "Apartment": ("kitchen", "bathroom", "bedroom", "lounge", "balcony", "entrance"),
    "Office": ("office floor", "washroom", "pantry", "meeting room", "reception"),
    "Shop": ("shop front", "storeroom", "washroom", "back office"),
}

# S6 catalogue: (offer_code, offer_type, description, discount_pct, rent_free_days, unit types)
# Widths follow dim_incentive: code 10, type 20, description 80, discount 0-50, rent-free 0-60.
OFFERS = [
    ("RF15", "Rent-free days", "Half a month rent-free on a new lease", "0.00", 15,
     ("Apartment",)),
    ("RF30", "Rent-free days", "First month rent-free on an 11-month lease", "0.00", 30,
     ("Apartment", "Office")),
    ("RF60", "Rent-free days", "Two months rent-free on a 24-month commercial lease", "0.00", 60,
     ("Office", "Shop")),
    ("DISC10", "Discount", "10% off the monthly rent for the first 3 months", "10.00", 0,
     ("Apartment", "Office", "Shop")),
    ("DISC15", "Discount", "15% off the monthly rent for the first 6 months", "15.00", 0,
     ("Apartment", "Office", "Shop")),
    ("DISC25", "Discount", "25% off the first month's rent", "25.00", 0,
     ("Apartment",)),
    ("FREEMAINT", "Free maintenance", "No maintenance charges for the first 6 months", "0.00", 0,
     ("Apartment", "Office", "Shop")),
]  # fmt: skip
OFFER_COLS = ["offer_code", "offer_type", "description", "discount_pct", "rent_free_days"]
LOG_COLS = ["building_code", "unit_no", "offer_code", "start_date", "end_date"]
OFFER_DAYS = (14, 21, 30, 45, 60, 90)  # how long an offer stays posted


# ----------------------------------------------------------------------------- small helpers
def minute(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def working_hours(t: datetime) -> datetime:
    """Move a moment outside 09:00-20:59 to the next 09:00 (building managers work days)."""
    if 9 <= t.hour < 21:
        return t
    day = t.date() if t.hour < 9 else t.date() + timedelta(days=1)
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=9, minutes=t.minute)


def lognormal_hours(rng: np.random.Generator, median: float, sigma: float, low, high) -> float:
    return float(np.clip(median * math.exp(rng.normal(0.0, sigma)), low, high))


def round_to(value: float, step: int) -> int:
    return max(step, int(round(value / step)) * step)


def seasonal(code: str, category: str, month: int) -> float:
    """How much more (or less) common a problem is in a month: summer heat, monsoon, winter."""
    if category == "HVAC" and code != "HVC-CHLR":
        return (
            2.5
            if month in (5, 6, 7, 8)
            else 1.5
            if month in (4, 9)
            else 0.4
            if month in (11, 12, 1, 2)
            else 1.0
        )
    if code == "PLB-GEYSER":
        return 3.0 if month in (12, 1, 2) else 0.3 if month in (5, 6, 7, 8) else 1.0
    if code in ("PLB-LEAK", "PLB-SEWER", "PLB-BLOCK"):
        return 1.6 if month in (7, 8, 9) else 1.0
    if code in ("CIV-SEEP", "CIV-ROOF"):
        return 2.5 if month in (7, 8, 9) else 1.0
    if category == "Pest control":
        return 1.7 if 4 <= month <= 9 else 0.6
    if code in ("ELE-OUT", "ELE-GEN"):
        return 1.6 if month in (5, 6, 7, 8) else 1.0
    return 1.0


def rating_on(vendor: dict, day: date) -> str:
    """The vendor's rating on a day (the S2 register keeps the previous one; SCD Type 2 data)."""
    changed = vendor["rating_changed_on"]
    if changed is not None and day < changed:
        return vendor["previous_rating"]
    return vendor["rating"]


def sla_on(policy: list[dict], code: str, day: date) -> int:
    """The SLA hours in force for a subcategory on a day (latest valid_from on or before it)."""
    hours = None
    for row in policy:  # sorted by (subcategory_code, valid_from)
        if row["subcategory_code"] == code and row["valid_from"] <= day:
            hours = row["default_sla_hours"]
    if hours is None:
        raise GeneratorError(f"no SLA policy for {code} on {day}")
    return hours


# ----------------------------------------------------------------------------- tickets
@dataclass
class Ticket:
    unit: dict
    code: str
    name: str
    category: str
    raised: datetime
    ticket_id: str = ""
    priority: str = "Normal"
    tenant_caused: bool = False
    recurring: bool = False
    reported_via: str = "Tenant app"
    description: str = ""
    vendor_code: str | None = None
    estimate: int | None = None
    final_cost: int | None = None
    history: list | None = None


def unit_weights(units: list[dict], buildings: list, rng: np.random.Generator) -> np.ndarray:
    by_code = {b.code: b for b in buildings}
    w = []
    for u in units:
        b = by_code[u["building_code"]]
        age = 1.0 + max(0, 2026 - b.year_built) / 40
        w.append(CLASS_FACTOR[b.building_class] * age * TYPE_FACTOR[u["unit_type"]])
    return np.asarray(w) * rng.lognormal(0.0, 0.4, len(units))


def raise_moment(rng: np.random.Generator, day: date, emergency_likely: bool) -> datetime:
    if emergency_likely and rng.random() < 0.3:
        hour = int(rng.integers(0, 24))
    else:
        hours = np.arange(24)
        weights = np.where((hours >= 9) & (hours <= 21), 1.0, 0.12)
        hour = int(rng.choice(24, p=weights / weights.sum()))
    return datetime.combine(day, datetime.min.time()) + timedelta(
        hours=hour, minutes=int(rng.integers(0, 60))
    )


def make_tickets(profile: Profile, master: dict, rng: np.random.Generator) -> list[Ticket]:
    """Raised tickets (who, where, what, when); the lifecycle is added by `add_lifecycle`."""
    units, buildings = master["units"], master["buildings"]
    first, last = profile.window_start, profile.window_end
    n_days = (last - first).days + 1
    day_list = [first + timedelta(k) for k in range(n_days)]
    day_w = np.array(
        [
            (1.25 if d.month in (5, 6, 7, 8) else 1.0) * (0.8 if d.weekday() >= 5 else 1.0)
            for d in day_list
        ]
    )
    commercial = {b.code for b in buildings if b.use == "commercial"}
    weights_u = unit_weights(units, buildings, rng)
    subcats = list(MAINTENANCE_SUBCATEGORIES)
    per_category = defaultdict(int)
    for _code, _name, category, _h in subcats:
        per_category[category] += 1

    total = profile.target_tickets
    n_follow = int(round(total * FOLLOW_UP_SHARE)) if total >= 10 else 0
    n_primary = total - n_follow
    tickets: list[Ticket] = []

    def new_primary() -> Ticket:
        day = day_list[int(rng.choice(n_days, p=day_w / day_w.sum()))]
        sw = np.array(
            [
                CATEGORY_SHARE[c] / per_category[c] * seasonal(code, c, day.month)
                for code, _n, c, _h in subcats
            ]
        )
        while True:
            code, name, category, _h = subcats[int(rng.choice(len(subcats), p=sw / sw.sum()))]
            allowed = np.array(
                [
                    0.0
                    if (code in APARTMENT_ONLY and u["unit_type"] != "Apartment")
                    or (code in COMMERCIAL_ONLY and u["building_code"] not in commercial)
                    else 1.0
                    for u in units
                ]
            )
            if allowed.any():
                break
            sw[[s[0] for s in subcats].index(code)] = 0.0  # no unit can have it: drop it
        w = weights_u * allowed
        unit = units[int(rng.choice(len(units), p=w / w.sum()))]
        likely = EMERGENCY_SHARE.get(code, DEFAULT_EMERGENCY_SHARE) >= 0.2
        return Ticket(unit, code, name, category, raise_moment(rng, day, likely))

    tickets = [new_primary() for _ in range(n_primary)]
    end_moment = datetime.combine(last, datetime.min.time()) + timedelta(hours=23, minutes=59)
    attempts = 0
    while len(tickets) < total:
        attempts += 1
        if attempts > 50 * total:  # short windows: fall back to more first-time tickets
            tickets.append(new_primary())
            continue
        base = tickets[int(rng.integers(0, n_primary))]
        later = base.raised + timedelta(
            days=int(rng.integers(*FOLLOW_UP_DAYS)), hours=int(rng.integers(-6, 7))
        )
        if later <= end_moment:
            tickets.append(Ticket(base.unit, base.code, base.name, base.category, minute(later)))
    tickets.sort(key=lambda t: (t.raised, t.unit["unit_id"], t.code))

    per_year: dict[int, int] = defaultdict(int)
    last_seen: dict[tuple[int, str], datetime] = {}
    for t in tickets:
        per_year[t.raised.year] += 1
        t.ticket_id = f"MR-{t.raised.year}-{per_year[t.raised.year]:05d}"
        key = (t.unit["unit_id"], t.code)
        t.recurring = key in last_seen and t.raised - last_seen[key] <= timedelta(RECURRING_DAYS)
        last_seen[key] = t.raised
        p_emergency = EMERGENCY_SHARE.get(t.code, DEFAULT_EMERGENCY_SHARE)
        draw = rng.random()
        t.priority = (
            "Emergency"
            if draw < p_emergency
            else "High"
            if draw < p_emergency + (1 - p_emergency) * HIGH_SHARE
            else "Normal"
        )
        t.tenant_caused = bool(
            rng.random() < TENANT_CAUSED_SHARE.get(t.code, DEFAULT_TENANT_CAUSED_SHARE)
        )
        staff = t.code in COMMON_AREA or rng.random() < STAFF_REPORTED
        t.reported_via = "Building staff" if staff else "Tenant app"
        place = gm.pick(rng, LOCATIONS[t.unit["unit_type"]])
        t.description = (
            f"{t.name} in the common area" if t.code in COMMON_AREA else f"{t.name} in the {place}"
        )
    return tickets


def add_lifecycle(
    profile: Profile, master: dict, tickets: list[Ticket], rng: np.random.Generator
) -> None:
    """Assign, resolve and verify each ticket; drop events after the export moment."""
    vendors_by_trade = defaultdict(list)
    for v in master["vendors"]:
        vendors_by_trade[v["trade"]].append(v)
    for trade in TRADES:
        if not vendors_by_trade[trade]:
            raise GeneratorError(f"no vendor for the trade {trade!r}")
    export = datetime.combine(profile.window_end, datetime.min.time()) + timedelta(
        hours=23, minutes=59, seconds=59
    )
    for t in tickets:
        events = [("Raised", t.raised, None)]
        assigned = minute(
            t.raised
            + timedelta(hours=lognormal_hours(rng, ASSIGN_MEDIAN_HOURS[t.priority], 0.6, 0.1, 240))
        )
        if assigned == t.raised:
            assigned += timedelta(minutes=5)
        pool = vendors_by_trade[TRADE_FOR_CATEGORY[t.category]]
        w = np.array([RATING_WEIGHT[rating_on(v, assigned.date())] for v in pool])
        vendor = pool[int(rng.choice(len(pool), p=w / w.sum()))]
        speed = RATING_SPEED[rating_on(vendor, assigned.date())]
        sla = sla_on(master["sla_policy"], t.code, t.raised.date())
        ratio = RESOLVE_RATIO_MEDIAN * math.exp(rng.normal(0.0, RESOLVE_RATIO_SIGMA)) * speed
        if t.priority == "Emergency":
            ratio *= 0.7
        resolved = minute(
            max(assigned + timedelta(minutes=30), t.raised + timedelta(hours=sla * ratio))
        )
        verified = working_hours(
            minute(resolved + timedelta(hours=lognormal_hours(rng, 20.0, 0.7, 1, 240)))
        )
        never_verified = rng.random() < NEVER_VERIFIED
        base = BASE_COST[t.category] * (1.25 if t.priority == "Emergency" else 1.0)
        estimate = round_to(base * math.exp(rng.normal(0.0, 0.4)), 50)
        final = round_to(estimate * math.exp(rng.normal(0.04, 0.15)), 50)

        events.append(("Assigned", assigned, vendor["vendor_code"]))
        events.append(("Resolved", resolved, None))
        if not never_verified:
            events.append(("Verified", verified, None))
        done = [e for e in events if e[1] <= export]
        t.history = [
            {"status": s, "at": stamp(at)} | ({"vendor_code": v} if v else {}) for s, at, v in done
        ]
        happened = {e[0] for e in done}
        if "Assigned" in happened:
            t.vendor_code = vendor["vendor_code"]
            t.estimate = estimate
        if "Resolved" in happened:
            t.final_cost = final


def ticket_json(t: Ticket) -> dict:
    return {
        "ticket_id": t.ticket_id,
        "building_code": t.unit["building_code"],
        "unit_no": t.unit["unit_no"],
        "category": t.category,
        "subcategory_code": t.code,
        "subcategory": t.name,
        "priority": t.priority,
        "is_emergency": t.priority == "Emergency",
        "is_recurring": t.recurring,
        "is_tenant_caused": t.tenant_caused,
        "reported_via": t.reported_via,
        "description": t.description,
        "vendor_code": t.vendor_code,
        "estimate": t.estimate,
        "final_cost": t.final_cost,
        "status": t.history[-1]["status"],
        "status_history": t.history,
    }


# ----------------------------------------------------------------------------- incentives
def make_incentive_log(profile: Profile, master: dict, rng: np.random.Generator) -> list[dict]:
    """Offers posted on units: inside the window, real units, never two at once on one unit."""
    units, buildings = master["units"], master["buildings"]
    by_code = {b.code: b for b in buildings}
    first, last = profile.window_start, profile.window_end
    span = (last - first).days + 1
    if profile.target_incentive_offers and span < min(OFFER_DAYS):
        raise GeneratorError("the window is shorter than the shortest offer")
    hard_to_let = np.array(
        [
            {"A": 0.7, "B": 1.0, "C": 1.5}[by_code[u["building_code"]].building_class]
            * {"Apartment": 1.0, "Office": 1.2, "Shop": 1.4}[u["unit_type"]]
            for u in units
        ]
    ) * rng.lognormal(0.0, 0.6, len(units))
    taken: dict[int, list[tuple[date, date]]] = defaultdict(list)
    rows, attempts = [], 0
    while len(rows) < profile.target_incentive_offers:
        attempts += 1
        if attempts > 200 * max(1, profile.target_incentive_offers):
            raise GeneratorError("could not place every incentive offer without overlaps")
        u = units[int(rng.choice(len(units), p=hard_to_let / hard_to_let.sum()))]
        days = int(gm.pick(rng, [d for d in OFFER_DAYS if d <= span]))
        start = first + timedelta(int(rng.integers(0, span - days + 1)))
        end = start + timedelta(days - 1)
        if any(start <= e and s <= end for s, e in taken[u["unit_id"]]):
            continue
        choices = [o for o in OFFERS if u["unit_type"] in o[5]]
        offer = choices[int(rng.integers(len(choices)))]
        taken[u["unit_id"]].append((start, end))
        rows.append(
            {
                "building_code": u["building_code"],
                "unit_no": u["unit_no"],
                "offer_code": offer[0],
                "start_date": start,
                "end_date": end,
            }
        )
    rows.sort(key=lambda r: (r["start_date"], r["building_code"], r["unit_no"]))
    return rows


# ----------------------------------------------------------------------------- the whole set
def build_activity(profile: Profile, master: dict, rng_for) -> dict:
    """Tickets and incentive log for a profile. A pure function of (profile, seed)."""
    tickets = make_tickets(profile, master, rng_for("tickets.raised"))
    add_lifecycle(profile, master, tickets, rng_for("tickets.lifecycle"))
    log = make_incentive_log(profile, master, rng_for("incentives.log"))
    return {"tickets": tickets, "incentive_log": log}


@stage("tickets_incentives", "Maintenance tickets (S4 JSON) and the incentive log (S6) (US-2.5)")
def tickets_incentives(ctx: Context) -> None:
    master = gm.build_master(ctx.profile, ctx.rng)
    a = build_activity(ctx.profile, master, ctx.rng)
    export = {
        "export": {
            "system": EXPORT_SYSTEM,
            "exported_at": f"{ctx.profile.window_end.isoformat()}T23:59:59",
            "window_start": ctx.profile.window_start.isoformat(),
            "window_end": ctx.profile.window_end.isoformat(),
            "ticket_count": len(a["tickets"]),
        },
        "tickets": [ticket_json(t) for t in a["tickets"]],
    }
    ctx.write_text("s4/tickets.json", json.dumps(export, indent=2, ensure_ascii=False) + "\n")
    ctx.write_csv("s6/offers.csv", OFFER_COLS, [list(o[:5]) for o in OFFERS])
    ctx.write_csv(
        "s6/incentive_log.csv", LOG_COLS, [[r[c] for c in LOG_COLS] for r in a["incentive_log"]]
    )
