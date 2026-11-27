"""Read the portal's data from the warehouse, as lue_reader (live mode).

    from live_data import fetch_live; data = fetch_live()

Reads only lue_reporting: the vw_portal_* views (sql/50_reporting/02_owner_portal.sql, generated from the
analytical queries) and the marts behind the dashboard's measures (scripts/powerbi_expected.py, so the portal's
portfolio figures equal Power BI's by construction). Read-only: the role cannot write, and nothing here builds
SQL from user input. Connection settings are those of the rest of the project (.env: PGHOST, PGPORT,
LUE_READER_USER, LUE_READER_PASSWORD).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts", ROOT / "frontend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from portal_data import assemble, rows  # noqa: E402

VIEWS = {  # key used by assemble(): the view and its order
    "Q2": "vw_portal_building_arrears", "Q3": "vw_portal_ageing", "Q4a": "vw_portal_late_payers",
    "Q6b": "vw_portal_move_in_season", "Q7": "vw_portal_vacancy_by_type", "Q8": "vw_portal_renewal",
    "Q9a": "vw_portal_vendor_time", "Q10": "vw_portal_building_sla", "Q11": "vw_portal_building_cost",
    "Q12": "vw_portal_owner_noi", "Q13": "vw_portal_incentives", "Q14": "vw_portal_rain", "W2": "vw_portal_monthly_cash",
}  # fmt: skip
ORDER = {"Q12": "noi_rank, owner_code", "W2": "year_month", "Q6b": "month_no", "Q3": "bucket"}


def query(cur, sql):
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return rows(dict(zip(cols, r)) for r in cur.fetchall())


def fetch_live() -> dict:
    import powerbi_expected as pe

    conn = pe.connect_reader()
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '60s'")
            T = {k: query(cur, f"SELECT * FROM lue_reporting.{v}" + (f" ORDER BY {ORDER[k]}" if k in ORDER else ""))
                 for k, v in VIEWS.items()}
            bld = query(cur, "SELECT building_code, building_name, building_class, locality, city "
                             "FROM lue_reporting.vw_dim_building")
            holdings = query(cur, "SELECT owner_code, building_code, unit_type, units FROM lue_reporting.vw_portal_owner_holding")
            monthly = query(cur, "SELECT owner_code, year_month, rent_collected, noi FROM lue_reporting.vw_portal_owner_month "
                                 "ORDER BY owner_code, year_month")
            w = query(cur, "SELECT window_start, window_end FROM lue_reporting.vw_reporting_window")[0]
            model = pe.Model.load(cur)
    finally:
        conn.close()

    ctx = model.ctx({})  # the whole window, as the dashboard's first card
    measures = {name: [fmt, pe.raw(model.value(name, ctx))] for name, fmt in pe.numeric().items()}
    decisions = {"Window": {k: getattr(model, k.lower())(ctx)["text"] for k in ("D1", "D2", "D3")}}
    series = {}
    for r in monthly:
        s = series.setdefault(r["owner_code"], {"m": [], "rent": [], "noi": []})
        s["m"].append(r["year_month"])
        s["rent"].append(r["rent_collected"])
        s["noi"].append(r["noi"])
    data = assemble(T, bld, holdings, measures, decisions,
                    {"from": w["window_start"], "to": w["window_end"], "profile": "live", "seed": None},
                    series=series, source="live")
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return data
