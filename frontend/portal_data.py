"""Shape the warehouse results into the JSON the owner portal reads (one shape for both sources).

build_data.py (snapshot: the recorded outputs) and live_data.py (live: the vw_portal_* views as lue_reader) both
call assemble(), so the page cannot tell them apart and the parity test (scripts/test_frontend.py) covers both.
"""

from datetime import date, datetime
from decimal import Decimal

LATE_PAYERS_SHOWN = 40


def plain(v):
    """A JSON-safe value: Decimal and dates from the database, numbers as they are."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and v.as_tuple().exponent >= 0 else float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def rows(cursor_rows):
    return [{k: plain(v) for k, v in r.items()} for r in cursor_rows]


def assemble(T, bld, holdings, measures, decisions, window, series=None, total_owners=None, source="snapshot"):
    """T: {'Q2': [...], 'Q3': ..., 'W2': ...} rows as dicts keyed by the view's column names.
    bld: [{'building_code','building_name','building_class','locality','city'}]; holdings: [{'owner_code',
    'building_code','unit_type','units'}]; measures: {name: [format, Window value, ...]}; decisions:
    {'Window': {'D1': text, 'D2': text, 'D3': text}}; series: {owner_code: {'m': [...], 'rent': [...], 'noi': [...]}}."""
    buildings = {}
    in_scope = {r["building_code"] for r in T["Q2"]}
    for r in bld:
        if r["building_code"] in in_scope:
            buildings[r["building_code"]] = {"code": r["building_code"], "name": r["building_name"].strip(),
                                             "city": r["city"].strip().title(), "locality": r["locality"].strip(),
                                             "cls": r["building_class"]}
    for r in T["Q2"]:
        buildings[r["building_code"]].update(billed=r["billed"], arrears=r["arrears"], arrears_ratio=r["arrears_ratio"],
                                             arrears_rank=r["arrears_rank"])
    for r in T["Q8"]:
        buildings[r["building_code"]].update(leases_expired=r["leases_expired"], renewed=r["renewed"],
                                             renewal_rate=r["renewal_rate"], lost_at_renewal=r["lost_at_renewal"])
    for r in T["Q10"]:
        buildings[r["building_code"]].update(resolved=r["resolved_requests"], sla_breaches=r["sla_breaches"],
                                             sla_rate=r["sla_breach_rate"])
    for r in T["Q11"]:
        buildings[r["building_code"]].update(maint_cost=r["actual_cost"], cost_per_unit_month=r["cost_per_unit_month"],
                                             requests=r["requests"])

    held = {}
    for h in holdings:
        held.setdefault(h["owner_code"], {}).setdefault(h["building_code"], {"Apartment": 0, "Office": 0, "Shop": 0})
        held[h["owner_code"]][h["building_code"]][h["unit_type"].strip().title()] += h["units"]

    owners = []
    for r in T["Q12"]:
        by_b = held.get(r["owner_code"], {})
        mix = {}
        for counts in by_b.values():
            for t, n in counts.items():
                if n:
                    mix[t] = mix.get(t, 0) + n
        o = {"code": r["owner_code"], "name": r["owner_name"], "type": r["owner_type"], "units": r["units_owned_at_end"],
             "rent": r["rent_collected"], "maint": r["maintenance_cost"], "fee": r["management_fee"], "noi": r["noi"],
             "margin": r["noi_margin"] or 0, "rank": r["noi_rank"], "unit_mix": mix,
             "buildings": [{"code": k, **v} for k, v in sorted(by_b.items())],
             "units_check": sum(mix.values()) == r["units_owned_at_end"]}
        if series and r["owner_code"] in series:
            o["series"] = series[r["owner_code"]]
        owners.append(o)

    return {
        "window": window, "source": source, "total_owners": total_owners or len(owners),
        "owners": owners, "buildings": buildings,
        "ageing": T["Q3"], "late_payers": T["Q4a"][:LATE_PAYERS_SHOWN], "move_in_season": T["Q6b"],
        "vacancy_by_type": T["Q7"], "vendors": T["Q9a"], "incentives": T["Q13"], "rain": T["Q14"],
        "cash_by_month": T["W2"], "measures": measures, "decisions": decisions,
    }
