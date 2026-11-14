"""US-2.2: master data and registers for the synthetic LUE portfolio.

Writes, for the chosen profile (etl/generator_config.py):

  S1 (PostgreSQL source src_pms, as CSV files that scripts/db_load_source.py loads)
    s1/buildings.csv, s1/units.csv, s1/tenants.csv, s1/charge_types.csv, s1/payment_methods.csv
  S2 (Excel registers, one sheet per register)
    s2/registers.xlsx with the sheets owners, ownership, vendors, sla_policy and holidays

The data is CLEAN here. Defects are injected later (US-2.6). The one thing that looks like a defect
and is not is a missing tenants.employer_sector (about 5 percent), which the pack maps to 'Unknown'.

Contracts the next stories rely on:

* unit_id runs 1..N in building order; tenants.tenant_code runs in order of tenants.updated_at,
  which is the moment the tenant record was created. US-2.3 must not start a lease before its
  tenant exists (go-live is 2023-06-15; tenants made before the window opened exist at its start).
* ownership.valid_to is EXCLUSIVE (the day the next owner takes over) and empty for the current
  owner. Every unit has an owner from before the window opens onwards, with no gap or overlap.
* vendors.rating is the current rating. previous_rating and rating_changed_on are filled for the
  vendors whose rating changed inside the window (the SCD Type 2 test data for dim_vendor).
* sla_policy has one row per subcategory valid from 2023-01-01, plus a tighter row for a few
  subcategories from a date inside the window (SCD Type 2 test data for dim_maintenance_category).

Every name is built from the curated lists below; no real person or company is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from etl.generate_data import Context, stage
from etl.generator_config import WINDOW_START, Profile
from etl.reference_data import (
    CHARGE_TYPES,
    HOLIDAYS,
    MAINTENANCE_SUBCATEGORIES,
    PAYMENT_METHODS,
    TRADES,
)

GO_LIVE = datetime(2023, 6, 15, 9, 0, 0)  # the PropertyHub system starts holding records
GO_LIVE_DAYS = 14  # records loaded at go-live are spread over this many days
POLICY_START = date(2023, 1, 1)  # SLA policy in force before the window opens
EDGE_DAYS = 14  # changes inside the window stay this far from its edges

# ----------------------------------------------------------------------------- curated lists
# (city, share of buildings, [(locality, 3-letter building prefix, short name for building names)])
CITIES = [
    (
        "Lahore",
        0.40,
        [
            ("Gulberg III", "GLB", "Gulberg"),
            ("DHA Phase 5", "DHL", "DHA Lahore"),
            ("Johar Town", "JHT", "Johar"),
            ("Model Town", "MDT", "Model"),
            ("Bahria Town", "BHT", "Bahria"),
            ("Cantt", "CNT", "Cantt"),
            ("Wapda Town", "WPT", "Wapda"),
            ("Iqbal Town", "IQT", "Iqbal"),
        ],
    ),
    (
        "Karachi",
        0.25,
        [
            ("Clifton", "CLF", "Clifton"),
            ("DHA Phase 6", "DHK", "DHA Karachi"),
            ("Gulshan-e-Iqbal", "GSI", "Gulshan"),
            ("North Nazimabad", "NNZ", "Nazimabad"),
            ("Bahadurabad", "BHD", "Bahadurabad"),
            ("PECHS", "PCH", "PECHS"),
        ],
    ),
    (
        "Islamabad",
        0.20,
        [
            ("F-7", "FS7", "F-7"),
            ("F-10", "F10", "F-10"),
            ("G-11", "G11", "G-11"),
            ("E-11", "E11", "E-11"),
            ("Blue Area", "BLA", "Blue Area"),
            ("DHA Phase 2", "DHI", "DHA Islamabad"),
        ],
    ),
    (
        "Faisalabad",
        0.15,
        [
            ("D Ground", "DGR", "D Ground"),
            ("Peoples Colony", "PCL", "Peoples Colony"),
            ("Madina Town", "MDN", "Madina"),
            ("Susan Road", "SSR", "Susan Road"),
            ("Canal Road", "CNL", "Canal Road"),
        ],
    ),
]
RESIDENTIAL_SUFFIXES = ("Heights", "Towers", "Residency", "Court", "Gardens")
COMMERCIAL_SUFFIXES = ("Plaza", "Centre", "Arcade", "Square", "Business Hub")

MALE_NAMES = (
    "Adeel Ali Bilal Danish Faisal Farhan Hamza Haris Hassan Imran Irfan Jawad Kamran Khalid "
    "Mubashir Naveed Omar Qasim Raza Saad Salman Shahid Talha Usman Waqas Yasir Zain Zubair "
    "Asad Babar Fahad Ghulam Ibrahim Kashif Moin Nadeem Rehan Sameer Tahir Umair Wasim Zeeshan"
).split()
FEMALE_NAMES = (
    "Aisha Amna Ayesha Anum Areeba Bushra Dua Fatima Hafsa Hina Iqra Kiran Komal Laiba Maham "
    "Maryam Mehwish Nadia Nimra Noor Rabia Saba Sana Sara Sidra Tahira Uzma Yusra Zainab Zara"
).split()
SURNAMES = (
    "Khan Malik Sheikh Butt Chaudhry Qureshi Siddiqui Raza Hussain Mirza Baig Awan Gill Rana "
    "Niazi Javed Akhtar Iqbal Anwar Farooq Ghafoor Hashmi Jamil Kazmi Lodhi Mahmood Nawaz Pervez "
    "Rehman Saeed Tariq Yousaf Zaidi Bhatti Cheema Dar Ejaz Gondal Hayat Jutt Khawaja Memon "
    "Naqvi Paracha Rizvi Shah Virk Wattoo Zafar"
).split()
TENANT_COMPANY_WORDS = (
    "Traders",
    "Enterprises",
    "Associates",
    "Solutions",
    "Consultants",
    "Industries",
    "Trading Co",
)
OWNER_COMPANY_WORDS = ("Holdings", "Properties", "Estates", "Investments", "Developers")
VENDOR_SUFFIXES = ("Works", "Services", "Enterprises", "& Sons", "Associates")
TRADE_WORDS = {
    "Plumbing": "Plumbing",
    "Electrical": "Electric",
    "HVAC": "Cooling",
    "Civil": "Construction",
    "Pest control": "Pest Control",
    "General maintenance": "Maintenance",
}
EMPLOYER_SECTORS = (
    "Banking",
    "IT and Software",
    "Education",
    "Healthcare",
    "Government",
    "Manufacturing",
    "Retail",
    "Telecom",
    "Construction",
    "Media",
    "Energy",
    "Hospitality",
    "Logistics",
    "Legal and Consulting",
    "Self-employed",
)
PHONE_PREFIXES = (
    "0300", "0301", "0302", "0303", "0304", "0305", "0311", "0312", "0313", "0321", "0322",
    "0323", "0331", "0332", "0333", "0334", "0345",
)  # fmt: skip

BUILDING_COLS = [
    "building_code",
    "building_name",
    "city",
    "locality",
    "building_class",
    "year_built",
]
UNIT_COLS = [
    "unit_id", "building_code", "unit_no", "floor_no", "unit_type", "area_sqft", "bedrooms",
    "furnished", "updated_at",
]  # fmt: skip
TENANT_COLS = [
    "tenant_code", "full_name", "tenant_type", "employer_sector", "phone", "contact_channel",
    "updated_at",
]  # fmt: skip
OWNER_COLS = ["owner_code", "owner_name", "owner_type"]
OWNERSHIP_COLS = ["building_code", "unit_no", "owner_code", "valid_from", "valid_to"]
VENDOR_COLS = [
    "vendor_code", "vendor_name", "trade", "rating", "phone",
    "previous_rating", "rating_changed_on",
]  # fmt: skip
SLA_COLS = [
    "subcategory_code",
    "subcategory_name",
    "category_name",
    "default_sla_hours",
    "valid_from",
]
HOLIDAY_COLS = ["holiday_date", "holiday_name", "is_public_holiday", "is_ramadan"]


# ----------------------------------------------------------------------------- small helpers
def allocate(total: int, weights, minimum: int = 0) -> list[int]:
    """Split `total` into whole parts proportional to `weights`, each part at least `minimum`.

    Largest-remainder method, so the parts always add up to exactly `total`.
    """
    w = np.asarray(weights, dtype=float)
    n = len(w)
    if minimum * n > total:
        raise ValueError(f"cannot give {n} parts at least {minimum} each out of {total}")
    rest = total - minimum * n
    share = w / w.sum() * rest
    whole = np.floor(share).astype(int)
    order = np.argsort(-(share - whole), kind="stable")
    whole[order[: rest - int(whole.sum())]] += 1
    return [int(x) + minimum for x in whole]


def pick(rng: np.random.Generator, items):
    return items[int(rng.integers(len(items)))]


def pick_weighted(rng: np.random.Generator, items, weights):
    p = np.asarray(weights, dtype=float)
    return items[int(rng.choice(len(items), p=p / p.sum()))]


def random_moment(rng: np.random.Generator, first: datetime, last: datetime) -> datetime:
    """A random second between two datetimes (inclusive)."""
    seconds = int((last - first).total_seconds())
    return first + timedelta(seconds=int(rng.integers(0, seconds + 1)))


def random_day(rng: np.random.Generator, first: date, last: date) -> date:
    return first + timedelta(days=int(rng.integers(0, (last - first).days + 1)))


def person_name(rng: np.random.Generator) -> str:
    first = pick(rng, MALE_NAMES if rng.random() < 0.5 else FEMALE_NAMES)
    return f"{first} {pick(rng, SURNAMES)}"


def unique_phone(rng: np.random.Generator, used: set[str]) -> str:
    while True:
        phone = f"{pick(rng, PHONE_PREFIXES)}-{int(rng.integers(0, 10_000_000)):07d}"
        if phone not in used:
            used.add(phone)
            return phone


# ----------------------------------------------------------------------------- buildings and units
@dataclass
class Building:
    code: str
    name: str
    city: str
    locality: str
    building_class: str
    year_built: int
    use: str  # residential or commercial (decides the unit mix; not stored in S1)


def make_buildings(profile: Profile, rng: np.random.Generator) -> list[Building]:
    cities = CITIES[: profile.cities]
    counts = allocate(profile.buildings, [c[1] for c in cities], minimum=1)
    sequence: dict[str, int] = {}
    names: set[str] = set()
    buildings = []
    for (city, _share, localities), count in zip(cities, counts, strict=True):
        for _ in range(count):
            locality, prefix, short = pick(rng, localities)
            sequence[prefix] = sequence.get(prefix, 0) + 1
            use = "commercial" if rng.random() < 0.25 else "residential"
            suffix = pick(rng, COMMERCIAL_SUFFIXES if use == "commercial" else RESIDENTIAL_SUFFIXES)
            base, name, k = f"{short} {suffix}", f"{short} {suffix}", 2
            while name in names:
                name, k = f"{base} {k}", k + 1
            names.add(name)
            klass = pick_weighted(rng, "ABC", [0.30, 0.45, 0.25])
            low, high = {"A": (2008, 2023), "B": (1995, 2015), "C": (1980, 2005)}[klass]
            buildings.append(
                Building(
                    code=f"{prefix}{sequence[prefix]:02d}",
                    name=name,
                    city=city,
                    locality=locality,
                    building_class=klass,
                    year_built=int(rng.integers(low, high + 1)),
                    use=use,
                )
            )
    return buildings


APARTMENT_AREA = {1: 550, 2: 850, 3: 1250, 4: 1800}


def make_units(profile: Profile, buildings: list[Building], rng: np.random.Generator) -> list[dict]:
    weights = rng.lognormal(0.0, 0.35, len(buildings))
    minimum = max(1, int(0.4 * profile.units / len(buildings)))
    counts = allocate(profile.units, weights, minimum)
    units: list[dict] = []
    for b, n in zip(buildings, counts, strict=True):
        commercial = b.use == "commercial"
        per_floor = 6 if commercial else 4
        shops = round((0.40 if commercial else 0.06) * n)
        types = ["Shop"] * shops + ["Office" if commercial else "Apartment"] * (n - shops)
        blocks = 1 if n <= 60 else 2
        block_size = math.ceil(n / blocks)
        for pos, unit_type in enumerate(types):
            block, in_block = divmod(pos, block_size)
            floor, idx = divmod(in_block, per_floor)
            bedrooms = 0
            if unit_type == "Apartment":
                bedrooms = pick_weighted(rng, [1, 2, 3, 4], [0.25, 0.40, 0.28, 0.07])
                area = APARTMENT_AREA[bedrooms] * float(np.clip(rng.normal(1.0, 0.08), 0.75, 1.3))
                furnished = rng.random() < {"A": 0.30, "B": 0.20, "C": 0.10}[b.building_class]
            elif unit_type == "Office":
                area = float(np.clip(900 * rng.lognormal(0.0, 0.5), 250, 6000))
                furnished = bool(rng.random() < 0.08)
            else:
                area = float(np.clip(450 * rng.lognormal(0.0, 0.5), 120, 2500))
                furnished = False
            units.append(
                {
                    "unit_id": len(units) + 1,
                    "building_code": b.code,
                    "unit_no": f"{'AB'[block]}-{floor}{idx + 1:02d}",
                    "floor_no": floor,
                    "unit_type": unit_type,
                    "area_sqft": round(area, 1),
                    "bedrooms": bedrooms,
                    "furnished": bool(furnished),
                    "updated_at": random_moment(
                        rng, GO_LIVE, GO_LIVE + timedelta(days=GO_LIVE_DAYS) - timedelta(seconds=1)
                    ),
                }
            )
    return units


# ----------------------------------------------------------------------- tenants, owners, vendors
def make_tenants(profile: Profile, rng: np.random.Generator) -> list[dict]:
    """Tenants in order of creation; tenant_code follows that order."""
    # Share of tenants who already exist when the window opens (the 1,500 or so active leases).
    pre_share = min(0.6, 0.9 * profile.target_active_leases / profile.tenants)
    window_open = datetime.combine(profile.window_start, datetime.min.time())
    window_last = datetime.combine(
        max(profile.window_start, profile.window_end - timedelta(days=30)), datetime.min.time()
    ) + timedelta(hours=23, minutes=59, seconds=59)
    go_live_end = GO_LIVE + timedelta(days=GO_LIVE_DAYS) - timedelta(seconds=1)
    if profile.window_start <= WINDOW_START:
        before_last = go_live_end
    else:  # a short profile: tenants who arrived between go-live and the window opening
        before_last = window_open - timedelta(seconds=1)
    used: set[str] = set()
    rows = []
    for _ in range(profile.tenants):
        created = (
            random_moment(rng, GO_LIVE, before_last)
            if rng.random() < pre_share
            else random_moment(rng, window_open, window_last)
        )
        corporate = rng.random() < 0.12
        name = (
            f"{pick(rng, SURNAMES)} {pick(rng, TENANT_COMPANY_WORDS)}"
            if corporate
            else person_name(rng)
        )
        channel_weights = [0.3, 0.1, 0.6] if corporate else [0.5, 0.4, 0.1]
        rows.append(
            {
                "full_name": name,
                "tenant_type": "Corporate" if corporate else "Individual",
                "employer_sector": None if rng.random() < 0.05 else pick(rng, EMPLOYER_SECTORS),
                "phone": unique_phone(rng, used),
                "contact_channel": pick_weighted(
                    rng, ["Phone", "WhatsApp", "Email"], channel_weights
                ),
                "updated_at": created,
            }
        )
    rows.sort(key=lambda r: r["updated_at"])
    for i, row in enumerate(rows, start=1):
        row["tenant_code"] = f"T-{i:04d}"
    return rows


def make_owners(profile: Profile, rng: np.random.Generator) -> list[dict]:
    rows = []
    for i in range(1, profile.owners + 1):
        company = rng.random() < 0.22
        name = (
            f"{pick(rng, SURNAMES)} {pick(rng, OWNER_COMPANY_WORDS)}"
            if company
            else person_name(rng)
        )
        rows.append(
            {
                "owner_code": f"OW-{i:04d}",
                "owner_name": name,
                "owner_type": "Company" if company else "Individual",
            }
        )
    return rows


def make_ownership(
    profile: Profile,
    units: list[dict],
    buildings: list[Building],
    owners: list[dict],
    rng: np.random.Generator,
) -> list[dict]:
    """Ownership periods: every owner holds a unit, some units change hands inside the window."""
    year_built = {b.code: b.year_built for b in buildings}
    n_units, n_owners = len(units), len(owners)
    holdings = np.zeros(n_owners, dtype=int)
    initial = [0] * n_units
    order = rng.permutation(n_units)
    owner_order = rng.permutation(n_owners)
    for k, u in enumerate(order[:n_owners]):  # every owner gets one unit first
        initial[int(u)] = int(owner_order[k])
        holdings[owner_order[k]] += 1
    for u in order[n_owners:]:  # the rest go to owners in proportion to what they already hold
        o = int(rng.choice(n_owners, p=(1.0 + holdings) / (1.0 + holdings).sum()))
        initial[int(u)] = o
        holdings[o] += 1

    first_day = profile.window_start + timedelta(days=EDGE_DAYS)
    last_day = profile.window_end - timedelta(days=EDGE_DAYS)
    span = (last_day - first_day).days
    rows = []
    for u, unit in enumerate(units):
        low = date(max(year_built[unit["building_code"]], 2016), 1, 1)
        start = random_day(rng, low, date(2023, 6, 30))
        draw = rng.random()
        transfers = 2 if draw < 0.02 else 1 if draw < 0.14 else 0
        dates: list[date] = []
        if transfers and span >= 30:
            dates = sorted(random_day(rng, first_day, last_day) for _ in range(transfers))
            if len(dates) == 2 and (dates[1] - dates[0]).days < 45:
                dates = dates[:1]
        owner = initial[u]
        owners_seq = [owner]
        for _ in dates:
            weights = 1.0 + holdings
            weights[owner] = 0.0
            owner = int(rng.choice(n_owners, p=weights / weights.sum()))
            owners_seq.append(owner)
        starts = [start, *dates]
        for k, o in enumerate(owners_seq):
            rows.append(
                {
                    "building_code": unit["building_code"],
                    "unit_no": unit["unit_no"],
                    "owner_code": owners[o]["owner_code"],
                    "valid_from": starts[k],
                    "valid_to": starts[k + 1] if k + 1 < len(starts) else None,
                }
            )
    return rows


def make_vendors(profile: Profile, rng: np.random.Generator) -> list[dict]:
    counts = allocate(profile.vendors, [0.22, 0.22, 0.14, 0.18, 0.08, 0.16], minimum=2)
    used_phones: set[str] = set()
    used_names: set[str] = set()
    rows = []
    for trade, count in zip(TRADES, counts, strict=True):
        for _ in range(count):
            while True:
                name = f"{pick(rng, SURNAMES)} {TRADE_WORDS[trade]} {pick(rng, VENDOR_SUFFIXES)}"
                if name not in used_names:
                    used_names.add(name)
                    break
            rows.append(
                {
                    "vendor_name": name,
                    "trade": trade,
                    "rating": pick_weighted(rng, "ABC", [0.25, 0.50, 0.25]),
                    "phone": unique_phone(rng, used_phones),
                    "previous_rating": None,
                    "rating_changed_on": None,
                }
            )
    for i, row in enumerate(rows, start=1):
        row["vendor_code"] = f"V-{i:03d}"
    first_day = profile.window_start + timedelta(days=EDGE_DAYS)
    last_day = profile.window_end - timedelta(days=EDGE_DAYS)
    changed = rng.choice(len(rows), size=max(1, round(0.12 * len(rows))), replace=False)
    for i in sorted(int(c) for c in changed):
        row = rows[i]
        row["previous_rating"] = pick(rng, [r for r in "ABC" if r != row["rating"]])
        row["rating_changed_on"] = random_day(rng, first_day, last_day)
    return rows


def make_sla_policy(profile: Profile, rng: np.random.Generator) -> list[dict]:
    rows = [
        {
            "subcategory_code": code,
            "subcategory_name": name,
            "category_name": category,
            "default_sla_hours": hours,
            "valid_from": POLICY_START,
        }
        for code, name, category, hours in MAINTENANCE_SUBCATEGORIES
    ]
    first_day = profile.window_start + timedelta(days=EDGE_DAYS)
    last_day = profile.window_end - timedelta(days=EDGE_DAYS)
    tightened = rng.choice(len(rows), size=max(1, round(0.15 * len(rows))), replace=False)
    for i in sorted(int(t) for t in tightened):
        old = dict(rows[i])
        old["default_sla_hours"] = max(6, old["default_sla_hours"] // 2)
        old["valid_from"] = random_day(rng, first_day, last_day)
        rows.append(old)
    rows.sort(key=lambda r: (r["subcategory_code"], r["valid_from"]))
    return rows


# ----------------------------------------------------------------------------- the whole set
def build_master(profile: Profile, rng_for) -> dict[str, list]:
    """Every master table for a profile. `rng_for(name)` returns the seeded stream of one part."""
    buildings = make_buildings(profile, rng_for("master_data.buildings"))
    units = make_units(profile, buildings, rng_for("master_data.units"))
    tenants = make_tenants(profile, rng_for("master_data.tenants"))
    owners = make_owners(profile, rng_for("master_data.owners"))
    ownership = make_ownership(profile, units, buildings, owners, rng_for("master_data.ownership"))
    vendors = make_vendors(profile, rng_for("master_data.vendors"))
    sla = make_sla_policy(profile, rng_for("master_data.sla"))
    return {
        "buildings": buildings,
        "units": units,
        "tenants": tenants,
        "owners": owners,
        "ownership": ownership,
        "vendors": vendors,
        "sla_policy": sla,
    }


@stage("master_data", "Buildings, units, tenants, owners, vendors, SLA policy, holidays (US-2.2)")
def master_data(ctx: Context) -> None:
    t = build_master(ctx.profile, ctx.rng)

    ctx.write_csv(
        "s1/buildings.csv",
        BUILDING_COLS,
        [
            [b.code, b.name, b.city, b.locality, b.building_class, b.year_built]
            for b in t["buildings"]
        ],
    )
    ctx.write_csv(
        "s1/units.csv",
        UNIT_COLS,
        [
            [
                u["unit_id"], u["building_code"], u["unit_no"], u["floor_no"], u["unit_type"],
                f"{u['area_sqft']:.1f}", u["bedrooms"], u["furnished"], u["updated_at"],
            ]
            for u in t["units"]
        ],
    )  # fmt: skip
    ctx.write_csv(
        "s1/tenants.csv",
        TENANT_COLS,
        [[r[c] for c in TENANT_COLS] for r in t["tenants"]],
    )
    ctx.write_csv(
        "s1/charge_types.csv",
        ["charge_code", "name", "category"],
        [[code, name, category] for code, name, category in CHARGE_TYPES],
    )
    ctx.write_csv(
        "s1/payment_methods.csv",
        ["method_code", "name"],
        [[code, name] for code, name, _group, _days in PAYMENT_METHODS],
    )

    ctx.write_workbook(
        "s2/registers.xlsx",
        [
            ("owners", OWNER_COLS, [[r[c] for c in OWNER_COLS] for r in t["owners"]]),
            ("ownership", OWNERSHIP_COLS, [[r[c] for c in OWNERSHIP_COLS] for r in t["ownership"]]),
            ("vendors", VENDOR_COLS, [[r[c] for c in VENDOR_COLS] for r in t["vendors"]]),
            ("sla_policy", SLA_COLS, [[r[c] for c in SLA_COLS] for r in t["sla_policy"]]),
            (
                "holidays",
                HOLIDAY_COLS,
                [[d, name, public, ramadan] for d, name, public, ramadan in HOLIDAYS],
            ),
        ],
    )
