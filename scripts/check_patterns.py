#!/usr/bin/env python3
"""Measure the six planted business patterns with pandas (US-2.6, plan step 4).

    python etl/generate_data.py --profile full --clean --out data_full
    python scripts/check_patterns.py --data data_full

Reads only the generated files (S1 CSV, S2 workbook, S4 JSON, S6 CSV), the committed weather cache
and answer_key/planted_patterns.json (which building, vendor and city were chosen). Prints one row
per pattern: what was measured, the expected effect from etl/patterns.py, PASS or FAIL.

Exit code 1 if a pattern misses its expected effect on the full profile. The small profile (2
buildings, 3 months) is too small for most effects: it is measured and printed but never fails.
Use a clean control batch (--clean): the planted defects (duplicates, orphans) blur the numbers a
little (cleaning them is the pipeline's job, not this check's); unreadable values are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl import patterns as pat  # noqa: E402
from etl import refresh_weather as rw  # noqa: E402


@dataclass
class Result:
    number: int
    pattern: str
    where: str
    measured: str
    expected: str
    value: float  # the measured ratio (NaN when it cannot be measured)
    ok: bool


def _pd():
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pandas is missing: pip install -r requirements.txt") from None
    return pd


def load(data: Path) -> dict:
    """The generated tables as pandas DataFrames (all text, parsed where needed)."""
    pd = _pd()

    def csv(name: str):
        return pd.read_csv(data / name, dtype=str, keep_default_na=False)

    s1 = {t: csv(f"s1/{t}.csv") for t in (
        "buildings", "units", "leases", "invoices", "invoice_lines", "payment_allocations",
    )}  # fmt: skip
    registers = pd.read_excel(data / "s2" / "registers.xlsx", sheet_name=None, dtype=str)
    export = json.loads((data / "s4" / "tickets.json").read_text(encoding="utf-8"))
    tickets = pd.DataFrame(
        [
            {
                "ticket_id": t["ticket_id"],
                "building_code": t["building_code"],
                "unit_no": t["unit_no"],
                "subcategory_code": t["subcategory_code"],
                "vendor_code": t["vendor_code"],
                "raised": next(h["at"] for h in t["status_history"] if h["status"] == "Raised"),
                "resolved": next(
                    (h["at"] for h in t["status_history"] if h["status"] == "Resolved"), None
                ),
            }
            for t in export["tickets"]
        ]
    )
    manifest = json.loads((data / "run_manifest.json").read_text(encoding="utf-8"))
    chosen = json.loads((data / "answer_key" / "planted_patterns.json").read_text("utf-8"))
    return {
        **s1,
        "vendors": registers["vendors"],
        "sla": registers["sla_policy"],
        "tickets": tickets,
        "log": csv("s6/incentive_log.csv"),
        "profile": manifest["profile"],
        "chosen": chosen,
    }


def units_with_city(d: dict):
    return d["units"].merge(d["buildings"][["building_code", "city"]], on="building_code")


def arrears(d: dict) -> tuple[float, str]:
    """1: share of the billed amount still unpaid, invoices due 30+ days before the window ends."""
    pd = _pd()
    code = d["chosen"]["high_arrears_building"]["building_code"]
    end = pd.Timestamp(d["profile"]["window_end"])
    inv = d["invoices"].merge(d["leases"][["lease_number", "unit_id"]], on="lease_number")
    inv = inv.merge(d["units"][["unit_id", "building_code"]], on="unit_id")
    inv = inv[pd.to_datetime(inv["due_date"]) <= end - pd.Timedelta(days=30)]
    lines = d["invoice_lines"].assign(net=lambda x: pd.to_numeric(x["net_amount"]))
    billed = lines.groupby("invoice_number")["net"].sum()
    alloc = d["payment_allocations"].assign(
        paid=lambda x: pd.to_numeric(x["allocated_amount"], errors="coerce")
    )
    paid = alloc.groupby("invoice_number")["paid"].sum()
    inv = inv.assign(
        billed=inv["invoice_number"].map(billed).fillna(0),
        paid=inv["invoice_number"].map(paid).fillna(0),
    )
    inside = inv["building_code"] == code

    def unpaid(part) -> float:
        return float(1 - part["paid"].sum() / part["billed"].sum()) if len(part) else float("nan")

    a, b = unpaid(inv[inside]), unpaid(inv[~inside])
    return a / b if b else float("nan"), f"unpaid {a:.1%} in {code} vs {b:.1%} elsewhere"


def slow_vendor(d: dict) -> tuple[float, str]:
    """2: median resolve time as a share of the SLA in force, the vendor vs its trade's others."""
    pd = _pd()
    code = d["chosen"]["slow_vendor"]["vendor_code"]
    trade = d["chosen"]["slow_vendor"]["trade"]
    peers = set(d["vendors"].loc[d["vendors"]["trade"] == trade, "vendor_code"])
    t = d["tickets"].dropna(subset=["resolved"])
    t = t[t["vendor_code"].isin(peers)].copy()
    t["raised"] = pd.to_datetime(t["raised"], errors="coerce")
    t["hours"] = (pd.to_datetime(t["resolved"]) - t["raised"]).dt.total_seconds() / 3600
    sla = d["sla"].assign(
        valid_from=lambda x: pd.to_datetime(x["valid_from"]),
        hours=lambda x: pd.to_numeric(x["default_sla_hours"]),
    ).sort_values("valid_from")
    t = pd.merge_asof(
        t.sort_values("raised"),
        sla[["subcategory_code", "valid_from", "hours"]].rename(columns={"hours": "sla"}),
        left_on="raised",
        right_on="valid_from",
        by="subcategory_code",
    )
    t["ratio"] = t["hours"] / t["sla"]
    mine, rest = t[t["vendor_code"] == code], t[t["vendor_code"] != code]
    if mine.empty or rest.empty:
        return float("nan"), f"{code}: no resolved job to compare"
    a, b = mine["ratio"].median(), rest["ratio"].median()
    over_a, over_b = (mine["ratio"] > 1).mean(), (rest["ratio"] > 1).mean()
    return a / b, (
        f"{code} {a:.2f} of SLA ({len(mine)} jobs, {over_a:.0%} late) vs {b:.2f} ({over_b:.0%})"
    )


def season(d: dict) -> tuple[float, str]:
    """3: new-tenant move-ins per month, peak months vs the other months (per month occurring)."""
    pd = _pd()
    first = pd.Timestamp(d["profile"]["window_start"])
    last = pd.Timestamp(d["profile"]["window_end"])
    new = d["leases"][d["leases"]["previous_lease_number"] == ""]
    starts = pd.to_datetime(new["start_date"])
    starts = starts[(starts >= first) & (starts <= last)]
    months = pd.period_range(first, last, freq="M")
    per_month = starts.dt.to_period("M").value_counts().reindex(months, fill_value=0)
    peak = per_month[[m.month in pat.PEAK_MONTHS for m in months]]
    other = per_month[[m.month not in pat.PEAK_MONTHS for m in months]]
    if peak.empty or other.empty or other.mean() == 0:
        return float("nan"), "the window has no peak month or no other month"
    return peak.mean() / other.mean(), (
        f"{peak.mean():.1f} move-ins a peak month vs {other.mean():.1f} other months"
    )


def vacancy(d: dict) -> tuple[float, str]:
    """4: days vacant between a tenant leaving and the next moving in, with or without an offer."""
    pd = _pd()
    leases = d["leases"].assign(
        start=lambda x: pd.to_datetime(x["start_date"]),
        end=lambda x: pd.to_datetime(x["end_date"]),
        unit_id=lambda x: x["unit_id"].astype(int),
    ).sort_values(["unit_id", "start"])
    leases["next_start"] = leases.groupby("unit_id")["start"].shift(-1)
    gaps = leases[(leases["status"] == "Terminated") & leases["next_start"].notna()].copy()
    gaps["days"] = (gaps["next_start"] - gaps["end"]).dt.days - 1
    units = d["units"].assign(unit_id=lambda x: x["unit_id"].astype(int))
    log = d["log"].merge(units[["unit_id", "building_code", "unit_no"]],
                         on=["building_code", "unit_no"])  # fmt: skip
    log["offer_start"] = pd.to_datetime(log["start_date"], errors="coerce", format="%Y-%m-%d")
    both = gaps.merge(log[["unit_id", "offer_start"]], on="unit_id", how="left")
    after, before = both["offer_start"] > both["end"], both["offer_start"] < both["next_start"]
    both["inside"] = after & before
    offered = both.groupby(["unit_id", "end"])["inside"].any()
    gaps = gaps.set_index(["unit_id", "end"]).assign(offer=offered)
    a, b = gaps.loc[gaps["offer"], "days"], gaps.loc[~gaps["offer"], "days"]
    if a.empty or b.empty:
        return float("nan"), f"{len(a)} vacancies with an offer, {len(b)} without"
    return a.mean() / b.mean(), (
        f"{a.mean():.0f} days with an offer ({len(a)}) vs {b.mean():.0f} without ({len(b)})"
    )


def rain(d: dict) -> tuple[float, str]:
    """5: leak tickets per 1,000 unit-days, on a rainy day or the day after vs other days."""
    pd = _pd()
    first = pd.Timestamp(d["profile"]["window_start"])
    last = pd.Timestamp(d["profile"]["window_end"])
    weather = pd.DataFrame(rw.load_cache(), columns=["city", "day", "rain", "temp"])
    weather["day"] = pd.to_datetime(weather["day"])
    weather = weather[(weather["day"] >= first) & (weather["day"] <= last)].sort_values("day")
    weather["wet"] = weather["rain"].fillna(0) >= pat.RAIN_THRESHOLD_MM
    weather["rainy"] = weather["wet"] | weather.groupby("city")["wet"].shift(1, fill_value=False)
    units = units_with_city(d)
    n_units = units.groupby("city").size().rename("units")
    weather = weather.merge(n_units, left_on="city", right_index=True)
    leaks = d["tickets"][d["tickets"]["subcategory_code"].isin(pat.RAIN_LEAK_CODES)]
    leaks = leaks.merge(units[["building_code", "unit_no", "city"]],
                        on=["building_code", "unit_no"])  # fmt: skip
    leaks = leaks.assign(day=pd.to_datetime(leaks["raised"], errors="coerce").dt.normalize())
    count = leaks.groupby(["city", "day"]).size().rename("leaks")
    weather = weather.merge(count, left_on=["city", "day"], right_index=True, how="left")
    weather["leaks"] = weather["leaks"].fillna(0)

    def rate(part) -> float:
        return 1000 * part["leaks"].sum() / part["units"].sum() if len(part) else float("nan")

    a, b = rate(weather[weather["rainy"]]), rate(weather[~weather["rainy"]])
    days = int(weather["rainy"].sum())
    return a / b if b else float("nan"), (
        f"{a:.2f} per 1,000 unit-days on {days} rainy city-days vs {b:.2f} on the others"
    )


def churn(d: dict) -> tuple[float, str]:
    """6: renewals as a share of resolved leases, the churn city vs the other cities."""
    city = d["chosen"]["renewal_churn_city"]["city"]
    units = units_with_city(d)
    leases = d["leases"].merge(units[["unit_id", "city"]], on="unit_id")
    done = leases[leases["status"].isin(["Renewed", "Terminated"])]
    inside = done["city"] == city
    if not inside.any() or inside.all():
        return float("nan"), f"no resolved lease in {city}, or only there"
    a = (done[inside]["status"] == "Renewed").mean()
    b = (done[~inside]["status"] == "Renewed").mean()
    return a / b, f"{a:.0%} renew in {city} vs {b:.0%} elsewhere"


def measure(data: Path) -> list[Result]:
    d = load(data)
    c = d["chosen"]
    full = d["profile"]["name"] == "full"
    checks = [
        (1, "High-arrears building", c["high_arrears_building"]["building_code"], arrears,
         lambda v: v >= pat.ARREARS_EFFECT, c["high_arrears_building"]["expected"]),
        (2, "Slow vendor", c["slow_vendor"]["vendor_code"], slow_vendor,
         lambda v: v >= pat.SLOW_VENDOR_EFFECT, c["slow_vendor"]["expected"]),
        (3, "Seasonal move-ins", "June to August", season,
         lambda v: v >= pat.SEASON_EFFECT, c["seasonal_move_ins"]["expected"]),
        (4, "Incentive shortens vacancy", "s6 offers", vacancy,
         lambda v: v <= pat.VACANCY_EFFECT, c["incentive_shortens_vacancy"]["expected"]),
        (5, "Rain-driven leak tickets", "4 cities", rain,
         lambda v: v >= pat.RAIN_EFFECT, c["rain_driven_leaks"]["expected"]),
        (6, "Renewal churn", c["renewal_churn_city"]["city"], churn,
         lambda v: v <= pat.CHURN_EFFECT, c["renewal_churn_city"]["expected"]),
    ]  # fmt: skip
    out = []
    for number, name, where, fn, good, expected in checks:
        value, text = fn(d)
        measured = value == value  # not NaN
        ok = bool(measured and good(value)) if full else True
        out.append(Result(number, name, str(where), text, expected, value, ok))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="the generated folder")
    args = ap.parse_args(argv)
    if not (args.data / "answer_key" / "planted_patterns.json").is_file():
        print(f"{args.data}: no answer_key/planted_patterns.json; run etl/generate_data.py first")
        return 2
    results = measure(args.data)
    profile = json.loads((args.data / "run_manifest.json").read_text("utf-8"))["profile"]["name"]
    print("=" * 78)
    print(f" US-2.6 planted patterns, measured with pandas ({profile} profile)")
    print("=" * 78)
    for r in results:
        ratio = f"{r.value:.2f}" if r.value == r.value else "n/a"
        status = ("PASS" if r.ok else "FAIL") if profile == "full" else "INFO"
        print(f"  [{status}] {r.number} {r.pattern} ({r.where}): ratio {ratio}")
        print(f"         measured: {r.measured}")
        print(f"         expected: {r.expected}")
    if profile != "full":
        print(" The small profile is too small to measure these effects; nothing fails here.")
    passed = sum(r.ok for r in results)
    print("=" * 78)
    print(f" RESULT: {passed}/{len(results)} patterns show their expected effect")
    print("=" * 78)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
