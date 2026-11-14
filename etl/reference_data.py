"""Fixed reference data shared by the SQL loaders and the data generator.

One place for the small static members (decision D19-style: no drift between documents and code).
Every value follows the frozen Phase 1 pack (docs/phase1/07_Data_Dictionary.xlsx, tools/model.py).
sql/30_dimensions/01_reference_dimensions.sql loads the same members into lue_dw;
scripts/test_reference.py fails if the two ever differ.

The codes are the business keys. The source system S1 (LUE-PMS) must use the same codes in
src_pms.payment_methods, src_pms.charge_types and src_pms.lease_events.event_code.
"""

from datetime import date, timedelta

# (method_code, method_name, channel_group, typical_settlement_days), in dimension key order 1..6.
PAYMENT_METHODS = [
    ("CASH", "Cash", "Cash", 0),
    ("CHEQUE", "Cheque", "Cheque", 3),
    ("BANK", "Bank transfer", "Bank", 1),
    ("RAAST", "Raast", "Instant payment", 0),
    ("JAZZ", "JazzCash", "Mobile wallet", 1),
    ("EASY", "Easypaisa", "Mobile wallet", 1),
]

# (charge_code, charge_type_name, charge_category), in dimension key order 1..6.
CHARGE_TYPES = [
    ("RENT", "Rent", "Rent"),
    ("SERVICE", "Service charge", "Ancillary"),
    ("LATEFEE", "Late fee", "Penalty"),
    ("UTILITY", "Utility", "Ancillary"),
    ("CREDIT", "Credit note", "Credit"),
    ("DEPADJ", "Deposit adjustment", "Credit"),
]

# (event_code, event_name, is_exit_event), in dimension key order 1..4.
LEASE_EVENT_TYPES = [
    ("SIGN", "Signed", False),
    ("RENEW", "Renewed", False),
    ("NOTICE", "Notice given", True),
    ("TERM", "Terminated", True),
]


def flags_label(is_emergency: bool, is_recurring: bool, is_tenant_caused: bool) -> str:
    """Readable label of one request-flags combination (dictionary example, middle dot)."""
    return " \u00b7 ".join(
        [
            "Emergency" if is_emergency else "Not emergency",
            "Recurring" if is_recurring else "Not recurring",
            "Tenant-caused" if is_tenant_caused else "Not tenant-caused",
        ]
    )


# Dimension key order for dim_request_flags: false before true, emergency varying slowest.
REQUEST_FLAG_COMBINATIONS = [
    (e, r, t) for e in (False, True) for r in (False, True) for t in (False, True)
]


# ----------------------------------------------------------------------------------------------
# Added in US-2.2. Shared by the S2 workbook (sla_policy sheet), the S4 ticket generator (US-2.5)
# and the maintenance-category and calendar loaders (US-6.x).
# ----------------------------------------------------------------------------------------------
CALENDAR_START = date(2023, 7, 1)  # dim_date range (frozen Phase 1 pack)
CALENDAR_END = date(2027, 6, 30)

# Vendor trades, one per maintenance category (category "Other" is served by General maintenance).
TRADES = [
    "Plumbing",
    "Electrical",
    "HVAC",
    "Civil",
    "Pest control",
    "General maintenance",
]

# (subcategory_code, subcategory_name, category_name, default_sla_hours): 30 rows, 6 categories.
# Codes are at most 10 characters (dim_maintenance_category.subcategory_code is VARCHAR(10)).
MAINTENANCE_SUBCATEGORIES = [
    ("PLB-LEAK", "Leak", "Plumbing", 48),
    ("PLB-BLOCK", "Blockage", "Plumbing", 24),
    ("PLB-SEWER", "Sewerage overflow", "Plumbing", 24),
    ("PLB-TAP", "Tap or fixture repair", "Plumbing", 72),
    ("PLB-TANK", "Water tank or pump", "Plumbing", 48),
    ("PLB-GEYSER", "Geyser repair", "Plumbing", 72),
    ("ELE-OUT", "Power outage", "Electrical", 12),
    ("ELE-WIRE", "Wiring fault", "Electrical", 24),
    ("ELE-SWITCH", "Switch or socket", "Electrical", 48),
    ("ELE-LIGHT", "Lighting", "Electrical", 72),
    ("ELE-BRKR", "Breaker or panel", "Electrical", 24),
    ("ELE-GEN", "Generator or UPS", "Electrical", 24),
    ("HVC-AC", "AC not cooling", "HVAC", 48),
    ("HVC-GAS", "AC gas refill", "HVAC", 72),
    ("HVC-DUCT", "Ventilation or duct", "HVAC", 96),
    ("HVC-CHLR", "Chiller or central plant", "HVAC", 24),
    ("HVC-FAN", "Exhaust fan", "HVAC", 72),
    ("CIV-SEEP", "Wall seepage", "Civil", 96),
    ("CIV-CRACK", "Cracks or plaster", "Civil", 120),
    ("CIV-PAINT", "Painting", "Civil", 168),
    ("CIV-DOOR", "Door or window", "Civil", 72),
    ("CIV-FLOOR", "Flooring or tiles", "Civil", 120),
    ("CIV-ROOF", "Roof repair", "Civil", 96),
    ("PST-INSECT", "Insects", "Pest control", 48),
    ("PST-ROD", "Rodents", "Pest control", 48),
    ("PST-FUM", "Fumigation", "Pest control", 72),
    ("OTH-LIFT", "Lift fault", "Other", 12),
    ("OTH-SEC", "Security or CCTV", "Other", 24),
    ("OTH-CLEAN", "Common area cleaning", "Other", 24),
    ("OTH-MISC", "Other", "Other", 96),
]

# Public-holiday and Ramadan register (the S2 holidays sheet), covering the whole calendar.
# SYNTHETIC: fixed-date holidays are exact; the lunar-calendar events (Eids, Ashura, Milad-un-Nabi,
# Ramadan) are approximate (a day either way) and are not an official government calendar.
_FIXED_HOLIDAYS = [
    (2, 5, "Kashmir Solidarity Day"),
    (3, 23, "Pakistan Day"),
    (5, 1, "Labour Day"),
    (8, 14, "Independence Day"),
    (12, 25, "Quaid-e-Azam Day"),
]
_LUNAR_HOLIDAYS = {
    "Ashura": [
        (2023, 7, 28),
        (2023, 7, 29),
        (2024, 7, 16),
        (2024, 7, 17),
        (2025, 7, 5),
        (2025, 7, 6),
        (2026, 6, 25),
        (2026, 6, 26),
        (2027, 6, 15),
        (2027, 6, 16),
    ],
    "Eid Milad-un-Nabi": [(2023, 9, 28), (2024, 9, 16), (2025, 9, 5), (2026, 8, 26)],
    "Eid ul-Fitr": [
        (2024, 4, 10),
        (2024, 4, 11),
        (2024, 4, 12),
        (2025, 3, 31),
        (2025, 4, 1),
        (2025, 4, 2),
        (2026, 3, 20),
        (2026, 3, 21),
        (2026, 3, 22),
        (2027, 3, 10),
        (2027, 3, 11),
        (2027, 3, 12),
    ],
    "Eid ul-Adha": [
        (2023, 7, 1),
        (2024, 6, 17),
        (2024, 6, 18),
        (2024, 6, 19),
        (2025, 6, 7),
        (2025, 6, 8),
        (2025, 6, 9),
        (2026, 5, 27),
        (2026, 5, 28),
        (2026, 5, 29),
        (2027, 5, 17),
        (2027, 5, 18),
        (2027, 5, 19),
    ],
}
_RAMADAN = [  # (first day, last day)
    (date(2024, 3, 12), date(2024, 4, 9)),
    (date(2025, 3, 2), date(2025, 3, 30)),
    (date(2026, 2, 19), date(2026, 3, 19)),
    (date(2027, 2, 9), date(2027, 3, 9)),
]


def _build_holidays() -> list[tuple[date, str | None, bool, bool]]:
    """(date, holiday_name or None, is_public_holiday, is_ramadan), one row per date, sorted."""
    names: dict[date, str] = {}
    for year in range(CALENDAR_START.year, CALENDAR_END.year + 1):
        for month, day, name in _FIXED_HOLIDAYS:
            names[date(year, month, day)] = name
    for name, days in _LUNAR_HOLIDAYS.items():
        for y, m, d in days:
            names[date(y, m, d)] = name
    ramadan: set[date] = set()
    for first, last in _RAMADAN:
        for k in range((last - first).days + 1):
            ramadan.add(first + timedelta(days=k))
    rows = []
    for day in sorted(set(names) | ramadan):
        if CALENDAR_START <= day <= CALENDAR_END:
            rows.append((day, names.get(day), day in names, day in ramadan))
    return rows


HOLIDAYS = _build_holidays()
