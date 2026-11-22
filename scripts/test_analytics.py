#!/usr/bin/env python3
"""E11 acceptance tests: the analytical SQL pack. Needs a loaded warehouse (python etl/run_pipeline.py).

    python scripts/test_analytics.py

  US-11.6  every query of analytical.sql and olap.sql runs (read-only) on whichever profile is loaded,
           and returns rows on the full one (on the small one an empty result is reported, as 3 months
           cannot hold, say, 3 late payments in 12 months); the files also run end to end in psql when
           psql is installed
  US-11.1  Q1 agrees with mart_collections_monthly and vw_monthly_collections; Q2's arrears with the
           mart's at the window end; the ageing buckets add up to the overdue lines
  US-11.2  Q6 monthly averages reconcile with mart_occupancy_monthly; Q7 counts completed spells only
  US-11.3  Q12 counts rent only and applies the stated fee; the planted patterns show (full profile):
           GLB03's arrears, the slow vendor V-001, the June to August move-ins, incentives shortening
           vacancy, leaks after heavy rain, renewal churn in Karachi
  US-11.4  the ROLLUP and CUBE label every subtotal; the verification query reads 0 differences
  US-11.5  three results recomputed independently with pandas from the facts match to the cent:
           Q1 (every building and month), Q12 (every owner), O1 (every ROLLUP row)
Nothing is changed: every query runs in a read-only transaction.
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

import os
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_analytics as ra  # noqa: E402

from etl.ingest.base import IngestError, connect, settings  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def rows_as_dicts(q) -> list[dict]:
    return [dict(zip(q.columns, r, strict=True)) for r in q.rows]


def frame(cur, sql: str):
    import pandas as pd

    cur.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])


def main() -> int:
    print("=" * 70)
    print(" E11 acceptance tests: the analytical SQL pack (database)")
    print("=" * 70)
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    cur = wh.cursor()
    try:
        cur.execute("SELECT count(*) FROM lue_dw.fact_payment")
        if not cur.fetchone()[0]:
            print("  [FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
            return 1
        cur.execute("SELECT count(DISTINCT building_code) FROM lue_dw.dim_unit WHERE unit_key > 0")
        full = cur.fetchone()[0] >= 40  # the planted patterns are measured on the full profile only

        print("US-11.6 Every query runs")
        qs = {q.label: ra.run(cur, q) for q in ra.all_queries()}
        failed = {k: q.error for k, q in qs.items() if q.error}
        empty = [k for k, q in qs.items() if not q.error and not q.rows]
        check(not failed and (not empty or not full) and len(qs) >= 24,
              f"all {len(qs)} queries of analytical.sql and olap.sql run read-only" + (" and return rows" if full else "") + f" ({'full' if full else 'small'} profile)"
              + (f": failed {failed}" if failed else "") + (f": empty {empty}" if empty and full else ""))
        if empty and not full:
            print(f"  [note] empty on the small profile, as its 3 months allow: {', '.join(empty)} (each returns rows on the full profile)")
        psql = shutil.which("psql")
        if psql:
            s = settings()
            env = {**os.environ, "PGPASSWORD": s.get("LUE_ETL_PASSWORD", "")}
            codes = {f.name: subprocess.run([psql, "-h", s.get("PGHOST", "localhost"), "-p", s.get("PGPORT", "5432"), "-U", s.get("LUE_ETL_USER", "lue_etl"),
                                             "-d", "lue_warehouse", "-v", "ON_ERROR_STOP=1", "-q", "-o", os.devnull, "-f", str(f)],
                                            env=env, capture_output=True, text=True).returncode for f in ra.FILES}  # fmt: skip
            check(all(c == 0 for c in codes.values()), "both files run end to end in psql -v ON_ERROR_STOP=1: " + ", ".join(f"{k} exit {v}" for k, v in codes.items()))
        else:
            print("  [note] psql is not on the PATH here: the psql run is skipped (it is in the evidence)")

        print("US-11.1 Finance (Q1 to Q5)")
        q1 = {(r["building_code"], r["month"]): (r["billed"], r["collected"]) for r in rows_as_dicts(qs["Q1"])}
        cur.execute("SELECT building_code, to_char(month_start, 'YYYY-MM'), billed_due, collected_cohort FROM lue_reporting.mart_collections_monthly WHERE billed_due <> 0 OR collected_cohort <> 0")
        mart = {(b, m): (x, y) for b, m, x, y in cur.fetchall()}
        cur.execute("SELECT sum(billed_due), sum(collected_cohort) FROM lue_reporting.vw_monthly_collections")
        vb, vc = cur.fetchone()
        rates = all(r["collection_rate"] == round(r["collected"] / r["billed"], 4) for r in rows_as_dicts(qs["Q1"]) if r["billed"])
        check(q1 == mart and sum(v[0] for v in q1.values()) == vb and sum(v[1] for v in q1.values()) == vc and rates,
              f"Q1 = mart_collections_monthly in all {len(q1):,} building-months and = vw_monthly_collections in total (billed {vb:,.0f}, collected {vc:,.0f}); rate = collected / billed (D17)")
        cur.execute("SELECT building_code, arrears_month_end FROM lue_reporting.mart_collections_monthly WHERE month_key = (SELECT max(month_key) FROM lue_reporting.vw_dim_month)")
        arrears = dict(cur.fetchall())
        q2 = rows_as_dicts(qs["Q2"])
        check(all(arrears.get(r["building_code"]) == r["arrears"] for r in q2) and [r["arrears_rank"] for r in q2] == sorted(r["arrears_rank"] for r in q2),
              f"Q2's arrears = the collections mart at the window end for all {len(q2)} buildings; ranked by arrears ratio")
        q3 = rows_as_dicts(qs["Q3"])
        check([r["bucket"] for r in q3] == [b for b in ("0-30", "31-60", "61-90", "90+") if b in {r["bucket"] for r in q3}] and abs(sum(r["share_of_overdue"] for r in q3) - 1) < Decimal("0.0005"),
              "Q3: the ageing buckets in order (0-30, 31-60, 61-90, 90+), their shares add up to the overdue balance")
        check(all(r["late_payments"] >= 3 for r in rows_as_dicts(qs["Q4a"])) and {"late_share", "repeat_late_payers"} <= set(qs["Q4b"].columns),
              f"Q4: {len(qs['Q4a'].rows)} repeat late payers (3 or more payments over 15 days late in 12 months); late share by sector at payment time")
        q5 = rows_as_dicts(qs["Q5"])
        settled = [r for r in q5 if r["avg_settlement_lag_days"] is not None]
        check(settled and settled == sorted(settled, key=lambda r: r["avg_settlement_lag_days"]) and all(r["settled_allocations"] == 0 for r in q5 if r["avg_settlement_lag_days"] is None),
              "Q5: methods ranked by settlement lag, fastest first; cash and cheques have no settlement file and say so (no lag)")

        print("US-11.2 Occupancy and leasing (Q6 to Q8)")
        q6 = {(r["month"], r["city"], r["unit_type"]): r["occupancy_rate"] for r in rows_as_dicts(qs["Q6a"])}
        cur.execute("""SELECT to_char(m.month_start, 'YYYY-MM'), b.city, m.unit_type, round(sum(m.occupied_days)::numeric / sum(m.unit_days), 4)
                       FROM lue_reporting.mart_occupancy_monthly m JOIN lue_reporting.vw_dim_building b ON b.building_code = m.building_code GROUP BY 1, 2, 3""")
        mo = {(a, b, c): d for a, b, c, d in cur.fetchall()}
        check(q6 == mo, f"Q6: the monthly average of daily occupancy = mart_occupancy_monthly in all {len(q6)} month, city and unit-type rows")
        cur.execute("SELECT sum(completed_vacancy_spells) FROM lue_reporting.mart_occupancy_monthly")
        mart_spells = cur.fetchone()[0]
        q7 = sum(r["completed_spells"] for r in rows_as_dicts(qs["Q7"]))
        check(0 < q7 <= mart_spells, f"Q7: {q7:,} completed spells, the censored ones left out (the mart, which keeps spells that began before the window, has {mart_spells:,})")
        q8 = rows_as_dicts(qs["Q8"])
        check(all(r["renewed"] + r["lost_at_renewal"] == r["leases_expired"] and r["renewal_rate"] <= r["renewal_rate_lease_link"] for r in q8),
              "Q8: renewed + lost = expired for every building; the event-based rate never exceeds the lease-link rate")

        print("US-11.3 Maintenance, owners, incentives, weather (Q9 to Q14)")
        q12 = rows_as_dicts(qs["Q12"])
        cur.execute("SELECT sum(rent_collected), sum(maintenance_cost), sum(management_fee) FROM lue_reporting.mart_owner_portfolio_monthly")
        mr, mc, mf = cur.fetchone()
        fee = next(q.header["Definition"] for k, q in qs.items() if k == "Q12")
        check(all(r["noi"] == r["rent_collected"] - r["maintenance_cost"] - r["management_fee"] for r in q12)
              and sum(r["rent_collected"] for r in q12) == mr and sum(r["maintenance_cost"] for r in q12) == mc
              and "FEE ASSUMPTION" in fee and "RENT" in qs["Q12"].sql,
              "Q12: rent (charge type RENT only) - cost - fee on every owner; rent and cost = the owner mart; the fee assumption is stated")
        if full:
            q9 = [r for r in rows_as_dicts(qs["Q9a"]) if r["category_name"] == "Plumbing"]
            slow = next(r for r in q9 if r["vendor_code"] == "V-001")
            others = sorted(r["median_resolve_over_sla"] for r in q9 if r["vendor_code"] != "V-001")
            check(slow["slowest_in_category"] == 1 and slow["median_resolve_over_sla"] >= Decimal("1.6") * others[len(others) // 2],
                  f"pattern 2: V-001 is the slowest plumber, median {slow['median_resolve_over_sla']} x SLA against {others[len(others) // 2]} for the median other plumber (at least 1.6 times)")
            check(q2[0]["building_code"] == "GLB03" and q2[0]["arrears_ratio"] >= 2 * q2[1]["arrears_ratio"],
                  f"pattern 1: GLB03 has the highest arrears ratio ({q2[0]['arrears_ratio']:.1%}), at least twice the next building's ({q2[1]['arrears_ratio']:.1%})")
            q6b = {r["month_no"]: r["move_ins"] for r in rows_as_dicts(qs["Q6b"])}
            peak = sum(q6b[m] for m in (6, 7, 8)) / 3
            other = sum(v for m, v in q6b.items() if m not in (6, 7, 8)) / 9
            check(peak >= Decimal("1.3") * Decimal(other), f"pattern 3: June to August average {peak:.0f} new-tenant move-ins a month, {peak / other:.2f} times the other months (at least 1.3)")
            q13 = {r["offer_group"]: r for r in rows_as_dicts(qs["Q13"])}
            check(q13["Any offer"]["ratio_to_no_offer"] <= Decimal("0.75"), f"pattern 4: vacancy with an offer lasts {q13['Any offer']['ratio_to_no_offer']} of the vacancy without one (at most 0.75)")
            q14 = rows_as_dicts(qs["Q14"])
            check(q14[0]["ratio_to_other_days"] >= 3, f"pattern 5: leak requests per unit-day are {q14[0]['ratio_to_other_days']} times higher on heavy-rain days (10 mm or more) or the day after (at least 3)")
            k = [r for r in q8 if r["city"] == "Karachi"]
            o = [r for r in q8 if r["city"] != "Karachi"]
            kr = sum(r["renewed"] for r in k) / sum(r["leases_expired"] for r in k)
            orr = sum(r["renewed"] for r in o) / sum(r["leases_expired"] for r in o)
            lowest = sum(1 for r in q8[: len(k)] if r["city"] == "Karachi")
            check(kr <= 0.75 * orr and q8[0]["city"] == "Karachi",
                  f"pattern 6: Karachi renews {kr:.1%} of expiring leases against {orr:.1%} elsewhere (at most 0.75 of it); {lowest} of the {len(k)} lowest-ranked buildings are in Karachi")
        else:
            print("  [note] the planted patterns are measured on the full profile only (the small one is too small): skipped")

        print("US-11.4 ROLLUP and CUBE")
        o1, o2, o3 = rows_as_dicts(qs["O1"]), rows_as_dicts(qs["O2"]), rows_as_dicts(qs["O3"])
        labels = {r["row_level"] for r in o1} | {r["row_level"] for r in o2}
        nulls = [r for r in o1 + o2 if any(v is None for k, v in r.items() if k in ("region", "city", "building", "channel_group"))]
        check({"Building", "City subtotal", "Region subtotal", "Grand total"} <= labels and {"City x channel", "City total (all channels)", "Channel total (all cities)"} <= labels and not nulls,
              "every subtotal row is labelled by GROUPING() (building, city, region, grand total; city x channel and both margins); no NULL label")
        check(len(o3) == 8 and all(r["differing"] == 0 and r["max_difference"] == 0 for r in o3),
              f"the verification query: {len(o3)} checks, {sum(r['items_checked'] for r in o3)} subtotals, 0 differences")

        print("US-11.5 Cross-checks with pandas, to the cent")
        lines = frame(cur, "SELECT f.invoice_number, f.invoice_line_no, f.net_amount, u.building_code, d.full_date AS due_date FROM lue_dw.fact_rent_invoice_line f JOIN lue_dw.dim_unit u USING (unit_key) JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key WHERE f.due_date_key > 0")
        pays = frame(cur, """SELECT p.payment_amount, p.owner_key, c.charge_code, u.building_code, u.city, u.region, dd.full_date AS due_date, pd.full_date AS paid_date
                             FROM lue_dw.fact_payment p JOIN lue_dw.dim_unit u USING (unit_key) JOIN lue_dw.dim_charge_type c USING (charge_type_key)
                             JOIN lue_dw.dim_date dd ON dd.date_key = p.due_date_key JOIN lue_dw.dim_date pd ON pd.date_key = p.paid_date_key WHERE p.paid_date_key > 0""")
        cur.execute("SELECT window_start, window_end FROM lue_reporting.vw_reporting_window")
        start, end = cur.fetchone()
        import pandas as pd

        first = pd.Timestamp(start).replace(day=1)
        lines["due_date"], pays["due_date"], pays["paid_date"] = (pd.to_datetime(lines["due_date"]), pd.to_datetime(pays["due_date"]), pd.to_datetime(pays["paid_date"]))
        lw = lines[(lines.due_date >= first) & (lines.due_date <= pd.Timestamp(end))].assign(month=lambda x: x.due_date.dt.strftime("%Y-%m"))
        pw = pays[(pays.due_date >= first) & (pays.due_date <= pd.Timestamp(end)) & (pays.paid_date <= pd.Timestamp(end))].assign(month=lambda x: x.due_date.dt.strftime("%Y-%m"))
        b = lw.groupby(["building_code", "month"]).net_amount.sum()
        c = pw.groupby(["building_code", "month"]).payment_amount.sum()
        pandas_q1 = {k: (v, c.get(k, Decimal(0))) for k, v in b.items()}
        check(pandas_q1 == q1, f"Q1 recomputed in pandas: billed and collected equal in all {len(pandas_q1):,} building-months")
        rent = pays[pays.charge_code == "RENT"].groupby("owner_key").payment_amount.sum()
        cost = frame(cur, "SELECT owner_key, actual_cost FROM lue_dw.fact_maintenance_request WHERE actual_cost IS NOT NULL").groupby("owner_key").actual_cost.sum()
        owners = frame(cur, "SELECT owner_key, owner_code FROM lue_dw.dim_owner").set_index("owner_key").owner_code
        cur.execute("SELECT value FROM lue_reporting.vw_reporting_parameter WHERE parameter = 'management_fee_rate'")
        rate = cur.fetchone()[0]
        pandas_q12 = {}
        for key in set(rent.index) | set(cost.index):
            r, k = rent.get(key, Decimal(0)), cost.get(key, Decimal(0))
            pandas_q12[owners[key]] = r - k - (r * rate).quantize(Decimal("0.01"))
        sql_q12 = {r["owner_code"]: r["noi"] for r in q12 if r["rent_collected"] or r["maintenance_cost"]}
        check(pandas_q12 == sql_q12, f"Q12 recomputed in pandas: NOI equal for all {len(sql_q12)} owners with rent or cost (fee {rate:.0%})")
        po = pays[(pays.paid_date >= pd.Timestamp(start)) & (pays.paid_date <= pd.Timestamp(end))]
        roll = {("Building", r, c_, b_): v for (r, c_, b_), v in po.groupby(["region", "city", "building_code"]).payment_amount.sum().items()}
        roll |= {("City subtotal", r, c_, "All buildings"): v for (r, c_), v in po.groupby(["region", "city"]).payment_amount.sum().items()}
        roll |= {("Region subtotal", r, "All cities", "All buildings"): v for r, v in po.groupby("region").payment_amount.sum().items()}
        roll[("Grand total", "All regions", "All cities", "All buildings")] = po.payment_amount.sum()
        sql_o1 = {(r["row_level"], r["region"], r["city"], r["building"]): r["collected"] for r in o1}
        check(roll == sql_o1, f"O1 recomputed in pandas: all {len(sql_o1)} ROLLUP rows equal (buildings, city, region and grand totals)")
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
