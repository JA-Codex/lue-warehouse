"""Configuration for the synthetic data generator (US-2.1).

Everything the generator may vary lives here, so no number is hidden inside generation code:
portfolio size, the date window, volume targets, defect rates and the default seed.
Two profiles exist (plan E2): `small` for fast development and `full` for the real load.

The volume targets are what the later stories (US-2.2 to US-2.6) must hit. US-2.1 only carries them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

DEFAULT_SEED = 3004  # the course code; any non-negative integer works
DEFAULT_PROFILE = "small"

# The business window of the whole project (plan US-2.1). The small profile uses its last months.
WINDOW_START = date(2023, 7, 1)
WINDOW_END = date(2026, 6, 30)

# Defect rates (plan US-2.6: about 1 to 3 percent). Share of the affected rows that get the defect.
# Keys are the defect types written to the answer key.
DEFECT_RATES = {
    "exact_duplicate": 0.01,
    "conflicting_duplicate": 0.01,
    "null_required_value": 0.02,
    "inconsistent_text": 0.03,
    "wrong_data_type": 0.01,
    "out_of_range_date": 0.01,
    "orphan_reference": 0.015,
    "late_arriving_payment": 0.02,
    "late_arriving_tenant_reference": 0.01,
    "duplicate_settlement_line": 0.01,
    "tenant_attribute_change": 0.02,
    "mid_lease_rent_change": 0.02,
}
MAX_DEFECT_RATE = 0.10  # a safety limit: above this the data stops being "mostly clean"


@dataclass(frozen=True)
class Profile:
    """One size of portfolio. Frozen so a run cannot change its own configuration."""

    name: str
    cities: int
    buildings: int
    units: int
    window_start: date
    window_end: date
    target_active_leases: int  # at any one time
    target_invoice_lines: int
    target_payments: int
    target_tickets: int
    defect_rates: dict[str, float] = field(default_factory=lambda: dict(DEFECT_RATES))

    @property
    def months(self) -> int:
        return (
            (self.window_end.year - self.window_start.year) * 12
            + self.window_end.month
            - self.window_start.month
            + 1
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["window_start"] = self.window_start.isoformat()
        d["window_end"] = self.window_end.isoformat()
        d["months"] = self.months
        return d


PROFILES = {
    # 2 buildings, 3 months (plan E2). Targets are the full ratios scaled to this portfolio.
    "small": Profile(
        name="small",
        cities=2,
        buildings=2,
        units=90,
        window_start=date(2026, 4, 1),
        window_end=WINDOW_END,
        target_active_leases=75,
        target_invoice_lines=650,
        target_payments=250,
        target_tickets=40,
    ),
    # About 40 buildings, 1,800 units, 36 months (plan E2, US-2.3 to US-2.5).
    "full": Profile(
        name="full",
        cities=4,
        buildings=40,
        units=1800,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        target_active_leases=1500,
        target_invoice_lines=130_000,
        target_payments=60_000,
        target_tickets=6000,
    ),
}


def validate(profile: Profile) -> list[str]:
    """Return every problem found in a profile (an empty list means it is usable)."""
    problems = []
    if profile.window_start > profile.window_end:
        problems.append("window_start is after window_end")
    if profile.window_start < WINDOW_START or profile.window_end > WINDOW_END:
        problems.append(f"the window must lie inside {WINDOW_START} to {WINDOW_END}")
    for name in ("cities", "buildings", "units"):
        if getattr(profile, name) < 1:
            problems.append(f"{name} must be at least 1")
    if profile.units < profile.buildings:
        problems.append("units must be at least the number of buildings")
    if profile.buildings < profile.cities:
        problems.append("buildings must be at least the number of cities")
    if profile.target_active_leases > profile.units:
        problems.append("target_active_leases cannot exceed units (one lease per unit at a time)")
    for name in ("target_invoice_lines", "target_payments", "target_tickets"):
        if getattr(profile, name) < 1:
            problems.append(f"{name} must be at least 1")
    for defect, rate in profile.defect_rates.items():
        if not 0 <= rate <= MAX_DEFECT_RATE:
            problems.append(f"defect rate {defect}={rate} is outside 0 to {MAX_DEFECT_RATE}")
    return problems


def get_profile(name: str) -> Profile:
    """Look up a profile by name and refuse an unusable one."""
    if name not in PROFILES:
        raise ValueError(f"unknown profile {name!r}; choose one of {', '.join(sorted(PROFILES))}")
    profile = PROFILES[name]
    problems = validate(profile)
    if problems:
        raise ValueError(f"profile {name!r} is invalid: " + "; ".join(problems))
    return profile
