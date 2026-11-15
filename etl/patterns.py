"""US-2.6: the six business patterns planted in the synthetic data, in one place.

The patterns are part of the CLEAN data (they are how this portfolio behaves, not defects), so they
are there whatever the defect rates are, also in a clean control batch. Each generator stage that
plants one imports its constants and its choice function from here:

  pattern                       planted in            what changes
  1 high-arrears building       gen_payments          tenants of one building pay late or stop
  2 slow vendor                 gen_tickets           one vendor takes about twice as long
  3 seasonal move-in peak       gen_leases (US-2.3)   new tenants move in mostly June to August
  4 incentive shortens vacancy  gen_leases            an offer on a vacant unit brings the next
                                                      tenant sooner (the S6 log lists the offers)
  5 rain-driven leak tickets    gen_tickets           leak tickets jump on and after a rainy day
  6 renewal churn in one city   gen_leases            tenants in one city renew less often

The choices (which building, vendor and city) are fixed rules on the master data, so every run with
the same profile and seed picks the same ones. The answer key records them with the expected effect
(answer_key/planted_patterns.json and .md, written by etl/gen_defects.py); scripts/check_patterns.py
measures each effect from the generated files with pandas.

Nothing here draws random numbers. The weather is real data read from the committed cache
(data/weather_cache.json, decision D12), so the generator still needs no network.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEATHER_CACHE = ROOT / "data" / "weather_cache.json"

# 1 High-arrears building. Its tenants draw their payment behaviour from these weights instead of
# the usual ones (order of gen_payments.BEHAVIOURS: on_time, occasionally_late, chronically_late,
# partial_payer, defaulter). The rest of the portfolio is unchanged.
ARREARS_WEIGHTS = (0.15, 0.20, 0.25, 0.15, 0.25)
ARREARS_EFFECT = 2.0  # expected: at least this many times the portfolio's overdue share

# 2 Slow vendor: resolve times are this many times longer than the vendor's rating suggests.
SLOW_VENDOR_TRADE = "Plumbing"
SLOW_VENDOR_FACTOR = 2.2
SLOW_VENDOR_EFFECT = 1.6  # expected: median resolve-to-SLA ratio at least this times its peers'

# 3 Seasonal move-ins: planted by US-2.3 (gen_leases.MOVE_IN_SEASON); only checked here.
PEAK_MONTHS = (6, 7, 8)
SEASON_EFFECT = 1.3  # expected (the US-2.3 test): a peak month has this many times the move-ins

# 4 Incentive on a vacant unit. When a tenant leaves (or for a unit already vacant when the window
# opens), LUE posts an offer on the unit with this probability (a marketing decision, independent
# of the unit, so a plain comparison shows the effect). The offer is posted in the first days of
# the vacancy, the vacancy is shortened and the new tenant does not wait for a better month.
P_OFFER_ON_VACANCY = 0.25
OFFER_POST_DAYS = (0, 7)  # days after move-out the offer is posted
OFFER_GAP_FACTOR = 0.6  # the vacancy (before rounding to a move-in month) is this share as long
VACANCY_EFFECT = 0.75  # expected: mean vacancy with an offer at most this share of one without

# 5 Rain-driven leaks. On a city-day with at least RAIN_THRESHOLD_MM of rain, extra leak tickets
# are raised in that city: Poisson with mean RAIN_LEAK_RATE per 100 units, times the rain in
# multiples of the threshold (capped). Most come the same day, the rest the next day.
RAIN_THRESHOLD_MM = 10.0
RAIN_LEAK_RATE = 0.15
RAIN_INTENSITY_CAP = 3.0
RAIN_NEXT_DAY_SHARE = 0.30
RAIN_LEAK_CODES = ("PLB-LEAK", "CIV-SEEP", "CIV-ROOF")
RAIN_LEAK_WEIGHTS = (0.40, 0.40, 0.20)
RAIN_EFFECT = 3.0  # expected: leak tickets per unit-day at least this times higher after rain

# 6 Renewal churn: tenants in this city renew this much less often (an absolute drop in the
# renewal probability of gen_leases.renewal_probability).
CHURN_CITY = "Karachi"
CHURN_RENEWAL_DROP = 0.20
CHURN_EFFECT = 0.75  # expected: the city's renewal rate at most this share of the other cities'


def arrears_building(master: dict) -> str | None:
    """The residential building with the most units outside the churn city (ties: lowest code).

    Kept out of the churn city so the two effects are not mixed. Falls back to any building.
    """
    count: dict[str, int] = {}
    for u in master["units"]:
        count[u["building_code"]] = count.get(u["building_code"], 0) + 1
    buildings = master["buildings"]
    for pool in (
        [b for b in buildings if b.use == "residential" and b.city != CHURN_CITY],
        [b for b in buildings if b.city != CHURN_CITY],
        list(buildings),
    ):
        if pool:
            return min(pool, key=lambda b: (-count.get(b.code, 0), b.code)).code
    return None


def slow_vendor(master: dict) -> str | None:
    """The vendor of SLOW_VENDOR_TRADE with the lowest code (exists in every profile)."""
    codes = sorted(v["vendor_code"] for v in master["vendors"] if v["trade"] == SLOW_VENDOR_TRADE)
    return codes[0] if codes else None


def rain_days(window_start: date, window_end: date, cache: Path | None = None) -> list:
    """(city, day, rainfall_mm) for every city-day of the window with at least the threshold.

    Reads the committed S5 cache. A missing cache is a clear error: the planted leaks need it.
    """
    from etl import refresh_weather as rw  # standard library only; no network is used here

    cache = WEATHER_CACHE if cache is None else cache
    if not cache.is_file():
        raise FileNotFoundError(
            f"{cache} is missing; it is committed with the repository (US-2.5). Restore it with "
            "git checkout data/weather_cache.json (or download it once: make weather)"
        )
    out = []
    for city, day, rain, _temp in rw.load_cache(cache):
        d = date.fromisoformat(day)
        if window_start <= d <= window_end and rain is not None and rain >= RAIN_THRESHOLD_MM:
            out.append((city, d, float(rain)))
    out.sort()
    return out


def describe(master: dict) -> dict:
    """The planted choices and their expected effects, for the answer key."""
    return {
        "high_arrears_building": {
            "building_code": arrears_building(master),
            "behaviour_weights": dict(
                zip(
                    (
                        "on_time",
                        "occasionally_late",
                        "chronically_late",
                        "partial_payer",
                        "defaulter",
                    ),
                    [f"{w:.2f}" for w in ARREARS_WEIGHTS],
                    strict=True,
                )
            ),
            "expected": f"overdue share of billed rent at least {ARREARS_EFFECT:.1f} times the "
            "rest of the portfolio's",
        },
        "slow_vendor": {
            "vendor_code": slow_vendor(master),
            "trade": SLOW_VENDOR_TRADE,
            "factor": f"{SLOW_VENDOR_FACTOR:.1f}",
            "expected": f"median resolve time over SLA at least {SLOW_VENDOR_EFFECT:.1f} times "
            "that of the other vendors of the trade",
        },
        "seasonal_move_ins": {
            "peak_months": list(PEAK_MONTHS),
            "expected": f"a peak month has at least {SEASON_EFFECT:.1f} times the new-tenant "
            "move-ins of an average other month",
        },
        "incentive_shortens_vacancy": {
            "offer_probability": f"{P_OFFER_ON_VACANCY:.2f}",
            "gap_factor": f"{OFFER_GAP_FACTOR:.2f}",
            "expected": f"mean vacancy with an offer at most {VACANCY_EFFECT:.2f} of the mean "
            "vacancy without one",
        },
        "rain_driven_leaks": {
            "threshold_mm": f"{RAIN_THRESHOLD_MM:.1f}",
            "codes": list(RAIN_LEAK_CODES),
            "expected": f"leak tickets per unit-day at least {RAIN_EFFECT:.1f} times higher on a "
            "rainy day or the day after than on other days",
        },
        "renewal_churn_city": {
            "city": CHURN_CITY,
            "renewal_drop": f"{CHURN_RENEWAL_DROP:.2f}",
            "expected": f"renewal rate at most {CHURN_EFFECT:.2f} of the other cities' rate",
        },
    }
