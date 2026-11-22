#!/usr/bin/env python3
"""E10 acceptance tests: the reporting layer. Needs a loaded warehouse (python etl/run_pipeline.py).

    python scripts/test_reporting.py

  US-10.1  every view returns rows; its totals equal queries written straight on the facts (a
           different route: day by day, not through the marts); the alias views return exactly the
           rows of their targets; lue_reader can read every vw_dim_* view
  US-10.2  the marts were refreshed by the pipeline (the refresh_marts step in the run log); each
           mart's grain is unique (a unique index, and no grain twice); every month of every measure
           equals the facts (zero variance); occupancy is unit-days, never a sum of daily counts
  US-10.3  lue_reader reads lue_reporting only: it cannot read lue_staging, lue_dw or lue_audit,
           cannot write or create anything, and cannot refresh the marts (the denials are printed)
Nothing is changed: the reader's attempts are refused, and the test reads only.
"""

# ruff: noqa: E501  (SQL text and messages: long lines read better)

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.ingest.base import IngestError, connect, settings  # noqa: E402

results: list[bool] = []
VIEWS = ["vw_monthly_collections", "vw_tenant_analysis", "vw_unit_performance"]
ALIASES = {"vw_monthly_sales": "vw_monthly_collections", "vw_customer_analysis": "vw_tenant_analysis",
           "vw_product_performance": "vw_unit_performance"}  # fmt: skip
DIMS = ["vw_dim_date", "vw_dim_month", "vw_dim_building", "vw_dim_unit", "vw_dim_tenant", "vw_dim_owner",
        "vw_dim_vendor", "vw_dim_maintenance_category", "vw_dim_payment_method"]  # fmt: skip
MARTS = {"mart_collections_monthly": ["month_key", "building_code"],
         "mart_occupancy_monthly": ["month_key", "building_code", "unit_type"],
         "mart_maintenance_monthly": ["month_key", "building_code", "unit_type", "maint_category_key", "vendor_key"],
         "mart_owner_portfolio_monthly": ["month_key", "owner_key"]}  # fmt: skip
TECHNICAL = {"source_system", "batch_id", "loaded_at"}


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def by_month(cur, sql: str) -> dict:
    cur.execute(sql)
    return {int(k): Decimal(v or 0) for k, v in cur.fetchall()}


def off(a: dict, b: dict) -> list:
    """Months where two {month: value} maps differ (a month missing on one side counts as 0)."""
    return sorted(k for k in set(a) | set(b) if a.get(k, 0) != b.get(k, 0))


# the window and its months, straight from the facts and dim_date (not from the reporting views)
WINDOW = "(SELECT min(snapshot_date_key) AS a, max(snapshot_date_key) AS b FROM lue_dw.fact_unit_occupancy_daily)"
MONTH = "(to_char({d}, 'YYYYMM') || '01')::int"
END = f"(SELECT d.full_date FROM lue_dw.dim_date d, {WINDOW} w WHERE d.date_key = w.b)"


def reader_tries(s: dict) -> dict:
    """What lue_reader may and may not do: {attempt: (allowed, message)}."""
    import psycopg2
    import psycopg2.extensions

    out = {}
    conn = psycopg2.connect(host=s.get("PGHOST", "localhost"), port=int(s.get("PGPORT", "5432")),
                            user=s.get("LUE_READER_USER", "lue_reader"), password=s.get("LUE_READER_PASSWORD", ""),
                            dbname="lue_warehouse", connect_timeout=10)  # fmt: skip
    conn.autocommit = True
    try:
        attempts = {f"read lue_reporting.{n}": f"SELECT count(*) FROM lue_reporting.{n}" for n in [*VIEWS, *ALIASES, *DIMS, *MARTS]}
        attempts |= {
            "read lue_dw.fact_payment": "SELECT count(*) FROM lue_dw.fact_payment",
            "read lue_staging.stg_tenant": "SELECT count(*) FROM lue_staging.stg_tenant",
            "read lue_audit.etl_run_log": "SELECT count(*) FROM lue_audit.etl_run_log",
            "write a mart": "DELETE FROM lue_reporting.mart_collections_monthly",
            "create a table in lue_reporting": "CREATE TABLE lue_reporting.reader_was_here (x int)",
            "write in a read-write transaction": "BEGIN READ WRITE; CREATE TABLE lue_reporting.reader_was_here (x int); COMMIT",
            "refresh the marts": "SELECT * FROM lue_reporting.refresh_marts()",
        }
        for name, sql in attempts.items():
            with conn.cursor() as cur:
                try:
                    cur.execute(sql)
                    out[name] = (True, "")
                except psycopg2.Error as exc:
                    out[name] = (False, str(exc).strip().splitlines()[0])
                    if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                        cur.execute("ROLLBACK")  # a refused statement inside BEGIN ... COMMIT leaves it open
        out["the reader's sessions start read-only"] = (scalar(conn.cursor(), "SHOW default_transaction_read_only") == "on", "")
    finally:
        conn.close()
    return out


def main() -> int:
    print("=" * 70)
    print(" E10 acceptance tests: the reporting layer (database)")
    print("=" * 70)
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    cur = wh.cursor()
    try:
        if not scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment"):
            print("  [FAIL] the warehouse has no facts: run python etl/run_pipeline.py first")
            return 1
        months = scalar(cur, "SELECT count(*) FROM lue_reporting.vw_dim_month")

        print("US-10.2 The marts")
        cur.execute("SELECT r.run_id, r.status, r.rows_read FROM lue_audit.etl_run_log r WHERE r.step = 'refresh_marts' "
                    "AND r.run_id >= (SELECT max(run_id) FROM lue_audit.etl_run_log WHERE step LIKE 'fact\\_%%') ORDER BY r.run_id DESC LIMIT 1")  # fmt: skip
        log = cur.fetchone()
        counts = {m: scalar(cur, f"SELECT count(*) FROM lue_reporting.{m}") for m in MARTS}
        check(log is not None and log[1] == "Success" and log[2] == sum(counts.values()) and all(counts.values()),
              f"refreshed by the pipeline after the facts (run {log[0] if log else '-'}, step refresh_marts, {sum(counts.values()):,} rows); no manual step")
        dup = {m: scalar(cur, f"SELECT count(*) - count(DISTINCT ({', '.join(g)})) FROM lue_reporting.{m}") for m, g in MARTS.items()}
        cur.execute("SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'lue_reporting' AND indexdef LIKE 'CREATE UNIQUE%%'")
        unique = {t: d for t, d in cur.fetchall()}
        check(all(v == 0 for v in dup.values()) and all(m in unique and all(c in unique[m] for c in g) for m, g in MARTS.items()),
              "each mart's grain is unique: a unique index on its grain (so it refreshes concurrently) and no grain twice")

        # collections, month by month, straight from the facts
        billed = by_month(cur, f"SELECT {MONTH.format(d='d.full_date')}, sum(f.net_amount) FROM lue_dw.fact_rent_invoice_line f JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key, {WINDOW} w WHERE f.due_date_key BETWEEN (w.a / 100) * 100 + 1 AND w.b GROUP BY 1")
        cohort = by_month(cur, f"SELECT {MONTH.format(d='d.full_date')}, sum(f.payment_amount) FROM lue_dw.fact_payment f JOIN lue_dw.dim_date d ON d.date_key = f.due_date_key, {WINDOW} w WHERE f.due_date_key BETWEEN (w.a / 100) * 100 + 1 AND w.b AND f.paid_date_key BETWEEN 1 AND w.b GROUP BY 1")
        cash = by_month(cur, f"SELECT {MONTH.format(d='d.full_date')}, sum(f.payment_amount) FROM lue_dw.fact_payment f JOIN lue_dw.dim_date d ON d.date_key = f.paid_date_key, {WINDOW} w WHERE f.paid_date_key BETWEEN (w.a / 100) * 100 + 1 AND w.b GROUP BY 1")
        mart = {c: by_month(cur, f"SELECT month_key, sum({c}) FROM lue_reporting.mart_collections_monthly GROUP BY 1") for c in ("billed_due", "collected_cohort", "cash_received")}
        bad = {"billed": off(billed, mart["billed_due"]), "cohort": off(cohort, mart["collected_cohort"]), "cash": off(cash, mart["cash_received"])}
        check(not any(bad.values()) and billed and set(billed) <= set(mart["billed_due"]),
              f"mart_collections_monthly = the facts in all {months} months ({len(billed)} with billing): billed by due month, collected against those lines (D17), cash by paid month" + (f": differ {bad}" if any(bad.values()) else ""))
        # arrears at each month end, day by day from the facts: lines past due minus the payments made against them by then
        cur.execute(f"""SELECT m.month_key, u.building_code,
            (SELECT coalesce(sum(l.net_amount), 0) FROM lue_dw.fact_rent_invoice_line l JOIN lue_dw.dim_date dd ON dd.date_key = l.due_date_key JOIN lue_dw.dim_unit lu ON lu.unit_key = l.unit_key
              WHERE lu.building_code = u.building_code AND dd.full_date + 1 <= m.month_end)
          - (SELECT coalesce(sum(p.payment_amount), 0) FROM lue_dw.fact_payment p JOIN lue_dw.dim_date dd ON dd.date_key = p.due_date_key JOIN lue_dw.dim_date pd ON pd.date_key = p.paid_date_key JOIN lue_dw.dim_unit pu ON pu.unit_key = p.unit_key
              WHERE pu.building_code = u.building_code AND greatest(dd.full_date + 1, pd.full_date) <= m.month_end)
          FROM (SELECT month_key, month_end FROM lue_reporting.vw_dim_month ORDER BY month_key) m
          CROSS JOIN (SELECT DISTINCT building_code FROM lue_dw.dim_unit WHERE unit_key > 0 ORDER BY 1 LIMIT 3) u
          WHERE m.month_key IN ((SELECT min(month_key) FROM lue_reporting.vw_dim_month), (SELECT max(month_key) FROM lue_reporting.vw_dim_month),
                                (SELECT month_key FROM lue_reporting.vw_dim_month ORDER BY month_key OFFSET {months // 2} LIMIT 1))""")  # fmt: skip
        direct = {(k, b): v for k, b, v in cur.fetchall()}
        cur.execute("SELECT month_key, building_code, arrears_month_end FROM lue_reporting.mart_collections_monthly")
        stored = {(k, b): v for k, b, v in cur.fetchall()}
        wrong = [k for k in direct if direct[k] != stored.get(k)]
        check(direct and not wrong, f"arrears at month end = lines past due - payments made against them by then, computed day by day ({len(direct)} building-months: first, middle, last month)" + (f": differ {wrong[:3]}" if wrong else ""))

        occ = {c: by_month(cur, f"SELECT {MONTH.format(d='d.full_date')}, {e} FROM lue_dw.fact_unit_occupancy_daily f JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key GROUP BY 1")
               for c, e in (("unit_days", "count(*)"), ("occupied_days", "sum(f.is_occupied)"))}  # fmt: skip
        eom = "(SELECT max(snapshot_date_key) FROM lue_dw.fact_unit_occupancy_daily GROUP BY snapshot_date_key / 100)"  # each month's last day
        occ["rent_roll_month_end"] = by_month(cur, f"SELECT (f.snapshot_date_key / 100) * 100 + 1, sum(f.contract_rent) FROM lue_dw.fact_unit_occupancy_daily f WHERE f.snapshot_date_key IN {eom} GROUP BY 1")
        occ["arrears_month_end"] = by_month(cur, f"SELECT (f.snapshot_date_key / 100) * 100 + 1, sum(f.current_lease_arrears) FROM lue_dw.fact_unit_occupancy_daily f WHERE f.snapshot_date_key IN {eom} GROUP BY 1")
        occ["active_leases"] = by_month(cur, "SELECT (snapshot_date_key / 100) * 100 + 1, count(DISTINCT lease_key) FROM lue_dw.fact_unit_occupancy_daily WHERE is_occupied = 1 GROUP BY 1")
        bad = {c: off(v, by_month(cur, f"SELECT month_key, sum({c}) FROM lue_reporting.mart_occupancy_monthly GROUP BY 1")) for c, v in occ.items()}
        # completed vacancy spells by another route: a vacant day followed by an occupied day of the same unit
        spells = by_month(cur, """SELECT (a.snapshot_date_key / 100) * 100 + 1, count(*) FROM lue_dw.fact_unit_occupancy_daily a
            JOIN lue_dw.dim_unit ua ON ua.unit_key = a.unit_key JOIN lue_dw.dim_date da ON da.date_key = a.snapshot_date_key
            JOIN lue_dw.dim_date db ON db.full_date = da.full_date + 1
            JOIN lue_dw.fact_unit_occupancy_daily b ON b.snapshot_date_key = db.date_key JOIN lue_dw.dim_unit ub ON ub.unit_key = b.unit_key AND ub.unit_nk = ua.unit_nk
            WHERE a.is_occupied = 0 AND b.is_occupied = 1 GROUP BY 1""")
        bad["completed_vacancy_spells"] = off(spells, by_month(cur, "SELECT month_key, sum(completed_vacancy_spells) FROM lue_reporting.mart_occupancy_monthly GROUP BY 1"))
        check(not any(bad.values()), "mart_occupancy_monthly = the facts in every month: unit-days, occupied unit-days, month-end rent roll and arrears, active leases, completed vacancy spells (a vacant day followed by a let one)" + (f": differ {bad}" if any(bad.values()) else ""))
        rate = scalar(cur, "SELECT round(sum(occupied_days)::numeric / sum(unit_days), 6) FROM lue_reporting.mart_occupancy_monthly")
        direct_rate = scalar(cur, "SELECT round(avg(occupied) / (SELECT count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE snapshot_date_key = (SELECT min(snapshot_date_key) FROM lue_dw.fact_unit_occupancy_daily)), 6) FROM (SELECT snapshot_date_key, sum(is_occupied) AS occupied FROM lue_dw.fact_unit_occupancy_daily GROUP BY 1) d")
        check(rate == direct_rate and 0 < rate < 1, f"occupancy = occupied unit-days / unit-days = the average of daily occupied units over units ({rate:.2%}), never a sum across days")

        mnt = {c: by_month(cur, f"SELECT {MONTH.format(d='d.full_date')}, {e} FROM lue_dw.fact_maintenance_request f JOIN lue_dw.dim_date d ON d.date_key = f.raised_date_key GROUP BY 1")
               for c, e in (("requests", "count(*)"), ("resolved_requests", "count(f.days_to_resolve)"), ("days_to_resolve_sum", "sum(f.days_to_resolve)"),
                            ("sla_breached", "sum(f.sla_breached_flag)"), ("actual_cost", "sum(f.actual_cost)"), ("estimated_cost", "sum(f.estimated_cost)"))}  # fmt: skip
        bad = {c: off(v, by_month(cur, f"SELECT month_key, sum({c}) FROM lue_reporting.mart_maintenance_monthly GROUP BY 1")) for c, v in mnt.items()}
        check(not any(bad.values()), "mart_maintenance_monthly = the facts in every raised month: requests, resolved, days to resolve, SLA breaches, estimated and actual cost" + (f": differ {bad}" if any(bad.values()) else ""))

        own = {"rent_collected": by_month(cur, f"SELECT {MONTH.format(d='d.full_date')}, sum(f.payment_amount) FROM lue_dw.fact_payment f JOIN lue_dw.dim_date d ON d.date_key = f.paid_date_key JOIN lue_dw.dim_charge_type c ON c.charge_type_key = f.charge_type_key WHERE c.charge_code = 'RENT' GROUP BY 1"),
               "maintenance_cost": mnt["actual_cost"], "unit_days": occ["unit_days"], "cash_received": cash}  # fmt: skip
        bad = {c: off(v, by_month(cur, f"SELECT month_key, sum({c}) FROM lue_reporting.mart_owner_portfolio_monthly GROUP BY 1")) for c, v in own.items()}
        fee = scalar(cur, "SELECT value FROM lue_reporting.vw_reporting_parameter WHERE parameter = 'management_fee_rate'")
        sums = scalar(cur, "SELECT count(*) FROM lue_reporting.mart_owner_portfolio_monthly WHERE management_fee <> round(rent_collected * management_fee_rate, 2) OR noi <> rent_collected - maintenance_cost - management_fee OR management_fee_rate <> %s", (fee,))
        check(not any(bad.values()) and sums == 0, f"mart_owner_portfolio_monthly = the facts in every month (rent collected, cash, maintenance cost, unit-days); fee = {fee:.0%} of rent collected, NOI = rent - cost - fee on every row" + (f": differ {bad}" if any(bad.values()) else ""))

        print("US-10.1 The views")
        rows = {v: scalar(cur, f"SELECT count(*) FROM lue_reporting.{v}") for v in [*VIEWS, *DIMS]}
        check(all(rows.values()), "every view returns rows: " + ", ".join(f"{v} {n:,}" for v, n in rows.items() if v in VIEWS))
        cur.execute("SELECT sum(billed_due), sum(collected_cohort), sum(cash_received), count(*) FILTER (WHERE collection_rate_cohort IS DISTINCT FROM round(collected_cohort / nullif(billed_due, 0), 4)) FROM lue_reporting.vw_monthly_collections")
        b, c, k, wrong = cur.fetchone()
        cur.execute("SELECT month_key, billed_due, cash_received, billed_growth, cash_received_growth FROM lue_reporting.vw_monthly_collections ORDER BY month_key")
        mc = cur.fetchall()
        growth = all(r[3] is None and r[4] is None for r in mc[:1]) and all(
            n[3] == round((n[1] - p[1]) / p[1], 4) and n[4] == round((n[2] - p[2]) / p[2], 4) for p, n in zip(mc, mc[1:]) if p[1] and p[2])
        check(b == sum(billed.values()) and c == sum(cohort.values()) and k == sum(cash.values()) and wrong == 0 and growth and len(mc) == months,
              f"vw_monthly_collections: one row per month ({len(mc)}); totals = the facts (billed {b:,.0f}, collected {c:,.0f}, cash {k:,.0f}); rate = collected / billed (D17); growth = LAG")
        cur.execute("SELECT sum(total_collected), sum(late_payments), sum(current_arrears), count(*) - count(DISTINCT tenant_key) FROM lue_reporting.vw_tenant_analysis")
        tc, late, arrears, twice = cur.fetchone()
        direct_late = scalar(cur, "SELECT count(DISTINCT (tenant_key, payment_reference)) FROM lue_dw.fact_payment WHERE NOT is_reversal AND days_past_due > 0")
        last = scalar(cur, "SELECT sum(arrears_month_end) FROM lue_reporting.mart_collections_monthly WHERE month_key = (SELECT max(month_key) FROM lue_reporting.vw_dim_month)")
        paid = scalar(cur, "SELECT sum(payment_amount) FROM lue_dw.fact_payment")
        segs = scalar(cur, "SELECT count(DISTINCT payer_segment) FROM lue_reporting.vw_tenant_analysis")
        check(tc == paid and late == direct_late and arrears == last and twice == 0 and segs >= 3,
              f"vw_tenant_analysis: one row per tenant version; collected = the facts ({tc:,.0f}), late payments = the facts ({late:,}), arrears = the collections mart at the window end ({arrears:,.0f}); {segs} payer segments")
        cur.execute("SELECT sum(units), sum(unit_days), sum(occupied_days), sum(maintenance_cost), sum(maintenance_requests) FROM lue_reporting.vw_unit_performance")
        units, ud, od, cost, req = cur.fetchone()
        direct_units = scalar(cur, f"SELECT count(*) FROM lue_dw.fact_unit_occupancy_daily f, {WINDOW} w WHERE f.snapshot_date_key = w.b")
        check(units == direct_units and ud == sum(occ["unit_days"].values()) and od == sum(occ["occupied_days"].values())
              and cost == sum(mnt["actual_cost"].values()) and req == sum(mnt["requests"].values()),
              f"vw_unit_performance: per building and unit type; units at the window end ({units:,}), unit-days, occupied days, maintenance cost and requests = the facts")
        same = {a: (scalar(cur, f"SELECT count(*) FROM (SELECT * FROM lue_reporting.{a} EXCEPT ALL SELECT * FROM lue_reporting.{t}) x")
                    + scalar(cur, f"SELECT count(*) FROM (SELECT * FROM lue_reporting.{t} EXCEPT ALL SELECT * FROM lue_reporting.{a}) x"),
                    rows[t]) for a, t in ALIASES.items()}  # fmt: skip
        check(all(d == 0 and n > 0 for d, n in same.values()), "the brief-named aliases return exactly their targets' rows (D18): " + ", ".join(f"{a} = {t}" for a, t in ALIASES.items()))
        cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'lue_reporting' AND table_name LIKE 'vw\\_dim\\_%%'")
        tech = [f"{t}.{c}" for t, c in cur.fetchall() if c in TECHNICAL]
        check(not tech and len(DIMS) == scalar(cur, "SELECT count(*) FROM information_schema.views WHERE table_schema = 'lue_reporting' AND table_name LIKE 'vw\\_dim\\_%%'"),
              f"{len(DIMS)} slicer views (vw_dim_*): date, month, building, unit, tenant, owner, vendor, maintenance category, payment method; no technical columns" + (f": {tech}" if tech else ""))

        print("US-10.3 Access")
        tries = reader_tries(settings())
        reads = [n for n in tries if n.startswith("read lue_reporting.")]
        check(all(tries[n][0] for n in reads), f"lue_reader reads all {len(reads)} objects of lue_reporting (views, aliases, slicers, marts)" + (f": refused {[n for n in reads if not tries[n][0]]}" if not all(tries[n][0] for n in reads) else ""))
        denied = ["read lue_dw.fact_payment", "read lue_staging.stg_tenant", "read lue_audit.etl_run_log"]
        check(not any(tries[n][0] for n in denied), "lue_reader cannot read lue_dw, lue_staging or lue_audit")
        for n in denied:
            print(f"         {n}: {tries[n][1]}")
        writes = ["write a mart", "create a table in lue_reporting", "write in a read-write transaction", "refresh the marts"]
        check(not any(tries[n][0] for n in writes) and tries["the reader's sessions start read-only"][0],
              "lue_reader cannot write, create, or refresh the marts; its sessions start read-only")
        for n in writes:
            print(f"         {n}: {tries[n][1]}")
        check(scalar(cur, "SELECT count(*) FROM pg_tables WHERE schemaname = 'lue_reporting' AND tablename = 'reader_was_here'") == 0, "nothing the reader tried was created")
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
