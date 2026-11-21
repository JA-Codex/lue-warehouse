#!/usr/bin/env python3
"""Acceptance tests for E7: the facts. Needs the database, with staging and the dimensions loaded.

    python etl/staging/run.py
    python etl/dimensions/run.py
    python scripts/test_fact_load.py

  US-7.1  every staged allocation is one fact_payment row, amounts equal staging; every tenant and
          unit key is the version valid on the paid date, every owner the register's owner that
          day; the key-mapping chain of one payment; a payment before and after a tenant's change
          maps to the old and the new version; a rerun inserts, updates and deletes nothing; a
          changed or removed source row is updated or deleted, not duplicated; a grain twice is
          refused
  US-7.2  every staged invoice line is one fact_rent_invoice_line row with the same amounts, keys at
          the invoice date; zero grain duplicates in both facts; net billed and paid equal staging in
          every month (an independent query and the run's lue_audit.reconciliation rows); reversals
          are negative and reduce collected; a fact amount off by PKR 1 fails its month
  US-7.3  one occupancy row per unit per day of the fixed window, load duration in the run log,
          unit-days reconciled by month; vacant days -2 and 0; lease, rent, tenant and owner of
          the day; arrears against a direct computation; a rerun rewrites the last 35 days with
          identical values; a late payment in those days corrects the arrears
  US-7.4  one maintenance row per ticket; milestones -2 until reached; durations, SLA (category
          version on the raised date), vendor, tenant, flags and weather; a rerun changes nothing;
          a ticket progressing from assigned to verified updates its row, never duplicates it
At the end the facts hold staging again and staging is as it was.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.facts import keys, load, spec  # noqa: E402
from etl.facts import run as facts  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402

results: list[bool] = []
MONEY = ["fact_rent_invoice_line", "fact_payment"]  # US-7.1 and US-7.2 load these only (the snapshot is slow)


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def payment_tests(cur) -> None:
    print("US-7.1 fact_payment: point-in-time keys")
    cur.execute("TRUNCATE lue_dw.fact_payment RESTART IDENTITY")
    _r, res, loads = facts.load_all(only=["fact_payment"])
    x = loads["fact_payment"]
    staged, total = (cur.execute("SELECT count(*), sum(allocated_amount) FROM lue_staging.stg_payment_allocation") or cur.fetchone())
    loaded, fact_total = (cur.execute("SELECT count(*), sum(payment_amount) FROM lue_dw.fact_payment") or cur.fetchone())
    status = {r.step: r.status for r in res}["fact_payment"]
    check(status == "Success" and loaded == staged == x.inserted + x.rejected and fact_total == total,
          f"one row per staged allocation ({loaded:,} of {staged:,}), the same amount ({fact_total:,.2f} PKR)")
    check(x.unknown == 0, f"no key left unresolved (-1): {x.unknown_keys or 'none'}")
    wrong = scalar(cur, """
        SELECT count(*) FROM lue_dw.fact_payment f JOIN lue_dw.dim_date d ON d.date_key = f.paid_date_key
        JOIN lue_dw.dim_tenant t ON t.tenant_key = f.tenant_key JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
        WHERE NOT (d.full_date >= t.effective_from AND d.full_date < t.effective_to)
           OR NOT (d.full_date >= u.effective_from AND d.full_date < u.effective_to)""")
    check(wrong == 0, "every tenant and unit key is the version valid on the paid date")
    wrong = scalar(cur, """
        SELECT count(*) FROM lue_dw.fact_payment f JOIN lue_dw.dim_date d ON d.date_key = f.paid_date_key
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_owner o ON o.owner_key = f.owner_key
        WHERE NOT EXISTS (SELECT 1 FROM lue_staging.stg_ownership r WHERE r.building_code = u.building_code AND r.unit_no = u.unit_no
                          AND r.owner_code = o.owner_code AND r.valid_from <= d.full_date AND (r.valid_to IS NULL OR d.full_date < r.valid_to))""")
    check(wrong == 0, "every owner key is the owner of the unit on the paid date (ownership register)")
    wrong = scalar(cur, """
        SELECT count(*) FROM lue_dw.fact_payment f JOIN lue_staging.stg_payment_allocation a
          ON a.payment_reference = f.payment_reference AND a.invoice_number = f.invoice_number AND a.line_no = f.invoice_line_no
        JOIN lue_dw.dim_date dp ON dp.date_key = f.paid_date_key JOIN lue_dw.dim_date dd ON dd.date_key = f.due_date_key
        WHERE dp.full_date <> a.paid_at::date OR dd.full_date <> a.due_date OR f.days_past_due <> a.days_past_due OR f.is_reversal <> a.is_reversal""")
    check(wrong == 0, "paid and due date keys, days past due and the reversal flag equal staging's (role-playing dates via dim_date)")

    print("US-7.1 The key-mapping chain of one payment (the brief's evidence)")
    cur.execute("""
        SELECT t.tenant_code FROM lue_dw.fact_payment f JOIN lue_dw.dim_tenant t USING (tenant_key)
        WHERE t.tenant_code IN (SELECT tenant_code FROM lue_dw.dim_tenant GROUP BY 1 HAVING count(*) > 1)
        GROUP BY 1 HAVING count(DISTINCT f.tenant_key) > 1 ORDER BY 1 LIMIT 1""")
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT tenant_code FROM lue_staging.stg_payment ORDER BY payment_reference LIMIT 1")
        row = cur.fetchone()
        print("    (no tenant in this data changed a Type 2 attribute between two of its payments; the chain of one payment)")
    code = row[0]
    cur.execute("""
        SELECT p.payment_reference, p.tenant_code, p.paid_at::date, t.tenant_key, t.employer_sector, t.effective_from, t.effective_to,
               f.invoice_number, f.invoice_line_no, f.payment_amount, f.paid_date_key
        FROM lue_staging.stg_payment p JOIN lue_dw.fact_payment f USING (payment_reference)
        JOIN lue_dw.dim_tenant t ON t.tenant_key = f.tenant_key
        WHERE p.tenant_code = %s ORDER BY p.paid_at""", (code,))
    chain = cur.fetchall()
    shown = []  # the first and last payment line under each version: either side of the change
    for v in dict.fromkeys(r[3] for r in chain):
        rows = [r for r in chain if r[3] == v]
        shown += [rows[0]] + ([rows[-1]] if len(rows) > 1 else [])
    print(f"    {'payment':12} {'tenant':7} {'paid on':10} -> {'tenant_key':>10} {'sector (version)':32} -> fact row")
    for ref, tc, paid, tk, sector, frm, to, inv, ln, amt, pdk in shown:
        print(f"    {ref:12} {tc:7} {paid!s:10} -> {tk:>10} {sector[:16]:16} {frm!s:>10}..{to!s:10} -> {inv}/{ln} {amt:,.2f} paid_date_key {pdk}")
    versions = {r[3] for r in chain}
    ok = all(r[5] <= r[2] < r[6] for r in chain)
    check(bool(chain) and ok, f"tenant {code}: each of its {len(chain)} payment lines maps to the version valid on its paid date ({len(versions)} version(s) used)")

    print("US-7.1 Reruns and changes")
    _r, res, loads = facts.load_all(only=["fact_payment"])
    x = loads["fact_payment"]
    check(x.inserted == x.updated == x.deleted == 0, "a rerun inserts, updates and deletes nothing")
    cur.execute("SELECT payment_reference, invoice_number, line_no, allocated_amount, allocation_source, paid_at, due_date, days_past_due, is_reversal FROM lue_staging.stg_payment_allocation ORDER BY 1, 2, 3 LIMIT 2")
    (r1, i1, l1, a1, *_), keep2 = cur.fetchall()
    cur.execute("UPDATE lue_staging.stg_payment_allocation SET allocated_amount = allocated_amount + 1 WHERE payment_reference = %s AND invoice_number = %s AND line_no = %s", (r1, i1, l1))
    cur.execute("DELETE FROM lue_staging.stg_payment_allocation WHERE payment_reference = %s AND invoice_number = %s AND line_no = %s", keep2[:3])
    try:
        _r, res, loads = facts.load_all(only=["fact_payment"])
        x = loads["fact_payment"]
        amount = scalar(cur, "SELECT payment_amount FROM lue_dw.fact_payment WHERE payment_reference = %s AND invoice_number = %s AND invoice_line_no = %s", (r1, i1, l1))
        gone = scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment WHERE payment_reference = %s AND invoice_number = %s AND invoice_line_no = %s", keep2[:3])
        check(x.updated == 1 and x.deleted == 1 and x.inserted == 0 and amount == a1 + 1 and gone == 0,
              "a changed source row is updated in place and a removed one deleted: 1 updated, 1 deleted, nothing duplicated")
    finally:
        cur.execute("UPDATE lue_staging.stg_payment_allocation SET allocated_amount = %s WHERE payment_reference = %s AND invoice_number = %s AND line_no = %s", (a1, r1, i1, l1))
        cur.execute("INSERT INTO lue_staging.stg_payment_allocation (payment_reference, invoice_number, line_no, allocated_amount, allocation_source, paid_at, due_date, days_past_due, is_reversal) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", keep2)
    _r, res, loads = facts.load_all(only=["fact_payment"])
    x = loads["fact_payment"]
    check(x.updated == 1 and x.inserted == 1, "with staging restored, the next run puts both back (1 updated, 1 inserted)")

    f = spec.BY_NAME["fact_payment"]
    twice = spec.Fact(f.name, f.grain, f.source + " UNION ALL (" + f.source + " LIMIT 1)", f.cols, "test")
    before = scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment")
    conn = connect("lue_warehouse")
    try:
        with conn.cursor() as c:
            try:
                load.load_fact(c, twice, 0, datetime.now())
                refused = ""
            except load.FactError as exc:
                refused = str(exc)
        conn.rollback()
    finally:
        conn.close()
    check("appear twice" in refused and scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment") == before,
          "a source with a grain twice is refused and nothing changes")


def invoice_tests(cur) -> None:
    print("US-7.2 fact_rent_invoice_line")
    cur.execute("TRUNCATE lue_dw.fact_rent_invoice_line RESTART IDENTITY")
    run_id, res, loads = facts.load_all(only=MONEY)
    x = loads["fact_rent_invoice_line"]
    status = {r.step: r.status for r in res}
    cur.execute("SELECT count(*), sum(billed_amount), sum(tax_amount), sum(discount_amount), sum(net_amount) FROM lue_staging.stg_invoice_line")
    staged = cur.fetchone()
    cur.execute("SELECT count(*), sum(billed_amount), sum(tax_amount), sum(discount_amount), sum(net_amount) FROM lue_dw.fact_rent_invoice_line")
    loaded = cur.fetchone()
    check(status["fact_rent_invoice_line"] == "Success" and loaded == staged and x.inserted == staged[0] and x.unknown == 0,
          f"one row per staged invoice line ({loaded[0]:,}), billed, tax, discount and net equal staging (net {loaded[4]:,.2f} PKR); no -1 key")
    for fact, grain in (("fact_rent_invoice_line", "invoice_number, invoice_line_no"),
                        ("fact_payment", "payment_reference, invoice_number, invoice_line_no")):
        dup = scalar(cur, f"SELECT count(*) - count(DISTINCT ({grain})) FROM lue_dw.{fact}")
        check(dup == 0, f"{fact}: zero grain duplicates ({grain})")
    wrong = scalar(cur, """
        SELECT count(*) FROM lue_dw.fact_rent_invoice_line f
        JOIN lue_staging.stg_invoice i USING (invoice_number) JOIN lue_staging.stg_lease l USING (lease_number)
        JOIN lue_dw.dim_date d ON d.date_key = f.invoice_date_key JOIN lue_dw.dim_tenant t ON t.tenant_key = f.tenant_key
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_lease dl ON dl.lease_key = f.lease_key
        WHERE d.full_date <> i.invoice_date OR t.tenant_code <> l.tenant_code OR dl.lease_number <> i.lease_number
           OR NOT (i.invoice_date >= t.effective_from AND i.invoice_date < t.effective_to)
           OR NOT (i.invoice_date >= u.effective_from AND i.invoice_date < u.effective_to)""")
    check(wrong == 0, "invoice date, lease, and the lease's tenant and unit in the version valid on the invoice date")
    wrong = scalar(cur, """
        SELECT count(*) FROM lue_dw.fact_rent_invoice_line f JOIN lue_dw.dim_date d ON d.date_key = f.invoice_date_key
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_owner o ON o.owner_key = f.owner_key
        WHERE NOT EXISTS (SELECT 1 FROM lue_staging.stg_ownership r WHERE r.building_code = u.building_code AND r.unit_no = u.unit_no
                          AND r.owner_code = o.owner_code AND r.valid_from <= d.full_date AND (r.valid_to IS NULL OR d.full_date < r.valid_to))""")
    check(wrong == 0, "every owner key is the unit's owner on the invoice date")

    print("US-7.2 Monthly reconciliation to staging")
    # An independent query (not the loader's): staging and the fact by month, side by side.
    cur.execute("""
        WITH s AS (SELECT to_char(i.invoice_date, 'YYYY-MM') m, sum(il.net_amount) net FROM lue_staging.stg_invoice_line il
                   JOIN lue_staging.stg_invoice i USING (invoice_number) GROUP BY 1),
             w AS (SELECT left(f.invoice_date_key::text, 4) || '-' || substr(f.invoice_date_key::text, 5, 2) m, sum(net_amount) net
                   FROM lue_dw.fact_rent_invoice_line f GROUP BY 1),
             sp AS (SELECT to_char(paid_at, 'YYYY-MM') m, sum(allocated_amount) paid FROM lue_staging.stg_payment_allocation GROUP BY 1),
             wp AS (SELECT left(paid_date_key::text, 4) || '-' || substr(paid_date_key::text, 5, 2) m, sum(payment_amount) paid
                    FROM lue_dw.fact_payment GROUP BY 1)
        SELECT coalesce(s.m, w.m, sp.m, wp.m), s.net, w.net, sp.paid, wp.paid FROM s FULL JOIN w ON w.m = s.m
        FULL JOIN sp ON sp.m = coalesce(s.m, w.m) FULL JOIN wp ON wp.m = coalesce(s.m, w.m, sp.m) ORDER BY 1""")
    months = cur.fetchall()
    off = [r[0] for r in months if r[1] != r[2] or r[3] != r[4]]
    print(f"    {'month':8} {'net billed: staging':>20} {'fact':>16}   {'paid: staging':>16} {'fact':>16}")
    for m, sn, wn, sp_, wp_ in months[:3] + [("...", None, None, None, None)] + months[-3:]:
        print(f"    {m:8} {sn or 0:>20,.2f} {wn or 0:>16,.2f}   {sp_ or 0:>16,.2f} {wp_ or 0:>16,.2f}" if m != "..." else "    ...")
    check(months and not off, f"net billed and paid equal staging in every one of {len(months)} months" + (f": off in {off[:5]}" if off else ""))
    cur.execute("SELECT check_name, passed FROM lue_audit.reconciliation WHERE run_id = %s AND check_name LIKE 'fact\\_%%'", (run_id,))
    logged = cur.fetchall()
    per_fact = {f: sum(1 for n, _ in logged if n.startswith(f + " ")) for f in ("fact_rent_invoice_line", "fact_payment")}
    check(logged and all(p for _, p in logged) and per_fact["fact_rent_invoice_line"] == per_fact["fact_payment"] == len(months),
          f"the run wrote one passing reconciliation row per month and fact to lue_audit.reconciliation ({per_fact})")
    gross, rev, net = (cur.execute("SELECT sum(payment_amount) FILTER (WHERE NOT is_reversal), sum(payment_amount) FILTER (WHERE is_reversal), sum(payment_amount) FROM lue_dw.fact_payment") or cur.fetchone())
    neg = scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment WHERE is_reversal AND payment_amount >= 0")
    check(rev is not None and rev < 0 and neg == 0 and net == gross + rev and net < gross,
          f"reversals are negative amounts and reduce collected: {gross:,.2f} received {rev:,.2f} reversed = {net:,.2f} PKR"
          if rev is not None else "reversals reduce collected (no reversal in this data)")

    f = spec.BY_NAME["fact_rent_invoice_line"]
    conn = connect("lue_warehouse")
    try:
        with conn.cursor() as c:
            c.execute("UPDATE lue_dw.fact_rent_invoice_line SET billed_amount = billed_amount + 1, net_amount = net_amount + 1 "
                      "WHERE invoice_line_sk = (SELECT min(invoice_line_sk) FROM lue_dw.fact_rent_invoice_line)")
            broken = [m for m, s, w in load.monthly(c, f) if s != w]
        conn.rollback()
    finally:
        conn.close()
    check(len(broken) == 1, f"a fact amount changed by PKR 1 makes exactly its month fail the reconciliation ({broken})")
    _r, res, loads = facts.load_all(only=MONEY)
    check(all(x.inserted == x.updated == x.deleted == 0 and not x.months_off for x in loads.values()),
          "a rerun of both money facts inserts, updates and deletes nothing, and every month still reconciles")


MR = "fact_maintenance_request"
MR_STAGE = """SELECT f.request_sk, f.request_number, f.request_status, f.raised_date_key, f.assigned_date_key, f.resolved_date_key,
                      f.verified_date_key, f.vendor_key, f.days_to_assign, f.days_to_resolve, f.days_to_verify, f.actual_cost, f.sla_breached_flag
               FROM lue_dw.fact_maintenance_request f WHERE f.request_number = %s"""


def maintenance_tests(cur) -> None:
    print("US-7.4 fact_maintenance_request: the accumulating snapshot")
    cur.execute(f"TRUNCATE lue_dw.{MR} RESTART IDENTITY")
    _r, res, loads = facts.load_all(only=[MR])
    x = loads[MR]
    tickets = scalar(cur, "SELECT count(*) FROM lue_staging.stg_ticket")
    rows, distinct = (cur.execute(f"SELECT count(*), count(DISTINCT request_number) FROM lue_dw.{MR}") or cur.fetchone())
    check({r.step: r.status for r in res}[MR] == "Success" and rows == distinct == tickets == x.inserted and not x.months_off,
          f"one row per request: {rows:,} rows, {distinct:,} request numbers, {tickets:,} staged tickets; tickets by raised month reconcile")
    check(x.unknown == 0, f"no key left unresolved (-1): {x.unknown_keys or 'none'}")
    wrong = scalar(cur, f"""
        SELECT count(*) FROM lue_dw.{MR} f JOIN lue_staging.stg_ticket t ON t.ticket_id = f.request_number
        LEFT JOIN lue_dw.dim_date da ON da.date_key = f.assigned_date_key LEFT JOIN lue_dw.dim_date dr ON dr.date_key = f.resolved_date_key
        LEFT JOIN lue_dw.dim_date dv ON dv.date_key = f.verified_date_key JOIN lue_dw.dim_date dd ON dd.date_key = f.raised_date_key
        WHERE dd.full_date <> t.raised_at::date OR f.request_status <> t.status
           OR (t.assigned_at IS NULL) <> (f.assigned_date_key = -2) OR (t.assigned_at IS NOT NULL AND da.full_date <> t.assigned_at::date)
           OR (t.resolved_at IS NULL) <> (f.resolved_date_key = -2) OR (t.resolved_at IS NOT NULL AND dr.full_date <> t.resolved_at::date)
           OR (t.verified_at IS NULL) <> (f.verified_date_key = -2) OR (t.verified_at IS NOT NULL AND dv.full_date <> t.verified_at::date)""")
    cur.execute(f"SELECT request_status, count(*), count(*) FILTER (WHERE assigned_date_key = -2), count(*) FILTER (WHERE resolved_date_key = -2), count(*) FILTER (WHERE verified_date_key = -2) FROM lue_dw.{MR} GROUP BY 1 ORDER BY 1")
    stages = ", ".join(f"{s} {n:,} (-2: {a}/{r}/{v})" for s, n, a, r, v in cur.fetchall())
    check(wrong == 0, f"milestone date keys are the staged dates, -2 until reached (assigned/resolved/verified): {stages}")
    wrong = scalar(cur, f"""
        SELECT count(*) FROM lue_dw.{MR} f JOIN lue_staging.stg_ticket t ON t.ticket_id = f.request_number
        WHERE f.days_to_assign IS DISTINCT FROM round((extract(epoch FROM t.assigned_at - t.raised_at) / 86400)::numeric, 2)
           OR f.days_to_resolve IS DISTINCT FROM round((extract(epoch FROM t.resolved_at - t.raised_at) / 86400)::numeric, 2)
           OR f.days_to_verify IS DISTINCT FROM round((extract(epoch FROM t.verified_at - t.resolved_at) / 86400)::numeric, 2)
           OR f.estimated_cost IS DISTINCT FROM t.estimated_cost OR f.actual_cost IS DISTINCT FROM t.actual_cost""")
    check(wrong == 0, "days to assign, resolve (from raised) and verify (from resolved), recomputed from the timestamps; costs as staged; NULL until reached")
    cur.execute(f"""
        SELECT count(*) FILTER (WHERE f.sla_breached_flag IS DISTINCT FROM CASE WHEN t.resolved_at IS NULL THEN NULL
                   WHEN extract(epoch FROM t.resolved_at - t.raised_at) / 3600 > c.default_sla_hours THEN 1 ELSE 0 END),
               count(*) FILTER (WHERE NOT (t.raised_at::date >= c.effective_from AND t.raised_at::date < c.effective_to) OR c.subcategory_code <> t.subcategory_code),
               count(*) FILTER (WHERE f.sla_breached_flag = 1), count(*) FILTER (WHERE f.sla_breached_flag IS NOT NULL),
               count(*) FILTER (WHERE (f.sla_breached_flag = 1) IS DISTINCT FROM t.sla_breached)
        FROM lue_dw.{MR} f JOIN lue_staging.stg_ticket t ON t.ticket_id = f.request_number
        JOIN lue_dw.dim_maintenance_category c ON c.maint_category_key = f.maint_category_key""")
    sla_wrong, cat_wrong, breached, resolved, vs_staging = cur.fetchone()
    check(sla_wrong == cat_wrong == vs_staging == 0,
          f"SLA breach: hours to resolve > the SLA hours of the category version valid on the raised date ({breached:,} of {resolved:,} resolved breached; NULL while open)")
    wrong = scalar(cur, f"""
        SELECT count(*) FROM lue_dw.{MR} f JOIN lue_staging.stg_ticket t ON t.ticket_id = f.request_number
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
        LEFT JOIN lue_dw.dim_vendor v ON v.vendor_key = f.vendor_key LEFT JOIN lue_dw.dim_tenant tn ON tn.tenant_key = f.tenant_key
        JOIN lue_dw.dim_request_flags rf ON rf.request_flags_key = f.request_flags_key JOIN lue_dw.dim_weather w ON w.weather_key = f.weather_key
        LEFT JOIN lue_staging.stg_unit su ON su.building_code = t.building_code AND su.unit_no = t.unit_no
        LEFT JOIN lue_staging.stg_lease l ON l.unit_id = su.unit_id AND t.raised_at::date BETWEEN l.start_date AND l.end_date
        WHERE u.unit_nk <> t.building_code || '-' || t.unit_no OR NOT (t.raised_at::date >= u.effective_from AND t.raised_at::date < u.effective_to)
           OR (t.assigned_at IS NULL) <> (f.vendor_key = -2)
           OR (t.assigned_at IS NOT NULL AND (v.vendor_code <> t.vendor_code OR NOT (t.assigned_at::date >= v.effective_from AND t.assigned_at::date < v.effective_to)))
           OR (l.lease_number IS NULL) <> (f.tenant_key = -2)
           OR (l.lease_number IS NOT NULL AND (tn.tenant_code <> l.tenant_code OR NOT (t.raised_at::date >= tn.effective_from AND t.raised_at::date < tn.effective_to)))
           OR (rf.is_emergency, rf.is_recurring, rf.is_tenant_caused) IS DISTINCT FROM (t.is_emergency, t.is_recurring, t.is_tenant_caused)
           OR w.city <> u.city OR w.weather_date <> t.raised_at::date""")
    staff = scalar(cur, f"SELECT count(*) FROM lue_dw.{MR} WHERE tenant_key = -2")
    check(wrong == 0, f"unit at the raised date; vendor at the assigned date (-2 until assigned); tenant of the lease active that day (-2 for {staff:,} raised on a vacant unit); flags; the city's weather that day")
    wrong = scalar(cur, f"""
        SELECT count(*) FROM lue_dw.{MR} f JOIN lue_dw.dim_date d ON d.date_key = f.raised_date_key
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_owner o ON o.owner_key = f.owner_key
        WHERE NOT EXISTS (SELECT 1 FROM lue_staging.stg_ownership r WHERE r.building_code = u.building_code AND r.unit_no = u.unit_no
                          AND r.owner_code = o.owner_code AND r.valid_from <= d.full_date AND (r.valid_to IS NULL OR d.full_date < r.valid_to))""")
    check(wrong == 0, "every owner key is the unit's owner on the raised date (who pays the cost)")

    print("US-7.4 A ticket progressing between two runs")
    before = scalar(cur, f"SELECT md5(string_agg(concat_ws('|', request_sk, raised_date_key, assigned_date_key, resolved_date_key, verified_date_key, unit_key, tenant_key, owner_key, maint_category_key, vendor_key, request_flags_key, weather_key, request_number, request_status, days_to_assign, days_to_resolve, days_to_verify, estimated_cost, actual_cost, sla_breached_flag), ',' ORDER BY request_sk)) FROM lue_dw.{MR}")
    _r, res, loads = facts.load_all(only=[MR])
    x = loads[MR]
    again = scalar(cur, f"SELECT md5(string_agg(concat_ws('|', request_sk, raised_date_key, assigned_date_key, resolved_date_key, verified_date_key, unit_key, tenant_key, owner_key, maint_category_key, vendor_key, request_flags_key, weather_key, request_number, request_status, days_to_assign, days_to_resolve, days_to_verify, estimated_cost, actual_cost, sla_breached_flag), ',' ORDER BY request_sk)) FROM lue_dw.{MR}")
    check(x.inserted == x.updated == x.deleted == 0 and again == before, "a rerun neither duplicates nor changes any row, completed ones included (same content hash)")
    ticket = scalar(cur, "SELECT ticket_id FROM lue_staging.stg_ticket WHERE status = 'Verified' ORDER BY raised_at DESC, ticket_id LIMIT 1")
    cur.execute("DROP TABLE IF EXISTS _ticket_keep")
    cur.execute("CREATE TEMP TABLE _ticket_keep AS SELECT * FROM lue_staging.stg_ticket WHERE ticket_id = %s", (ticket,))
    # The ticket as an earlier extract had it: assigned to a vendor, not resolved yet
    cur.execute("""UPDATE lue_staging.stg_ticket SET status = 'Assigned', resolved_at = NULL, verified_at = NULL, actual_cost = NULL,
                   days_to_resolve = NULL, days_to_verify = NULL, hours_to_resolve = NULL, sla_breached = NULL WHERE ticket_id = %s""", (ticket,))
    try:
        _r, res, loads = facts.load_all(only=[MR])
        first = (cur.execute(MR_STAGE, (ticket,)) or cur.fetchall())
        n1 = loads[MR]
    finally:
        cur.execute("""UPDATE lue_staging.stg_ticket t SET status = k.status, resolved_at = k.resolved_at, verified_at = k.verified_at,
                       actual_cost = k.actual_cost, days_to_resolve = k.days_to_resolve, days_to_verify = k.days_to_verify,
                       hours_to_resolve = k.hours_to_resolve, sla_breached = k.sla_breached FROM _ticket_keep k WHERE t.ticket_id = k.ticket_id""")
    _r, res, loads = facts.load_all(only=[MR])
    second = (cur.execute(MR_STAGE, (ticket,)) or cur.fetchall())
    n2 = loads[MR]
    head = ["request_sk", "request_number", "status", "raised", "assigned", "resolved", "verified", "vendor", "d_assign", "d_resolve", "d_verify", "actual_cost", "sla_breached"]
    print("    " + " | ".join(head))
    for label, rows_ in (("run 1, assigned", first), ("run 2, verified", second)):
        for r in rows_:
            print(f"    {label}: " + " | ".join("" if v is None else str(v) for v in r))
    final = scalar(cur, f"SELECT md5(string_agg(concat_ws('|', request_sk, raised_date_key, assigned_date_key, resolved_date_key, verified_date_key, unit_key, tenant_key, owner_key, maint_category_key, vendor_key, request_flags_key, weather_key, request_number, request_status, days_to_assign, days_to_resolve, days_to_verify, estimated_cost, actual_cost, sla_breached_flag), ',' ORDER BY request_sk)) FROM lue_dw.{MR}")
    ok = (len(first) == len(second) == 1 and first[0][0] == second[0][0] and first[0][2] == "Assigned" and first[0][5] == first[0][6] == -2
          and first[0][12] is None and second[0][2] == "Verified" and second[0][5] > 0 and second[0][6] > 0 and second[0][12] is not None
          and n1.updated == n2.updated == 1 and n1.inserted == n2.inserted == n1.deleted == n2.deleted == 0)
    check(ok, f"ticket {ticket}: at the Assigned stage resolved and verified are -2; when it is verified the same row (request_sk {second[0][0] if second else '?'}) is updated, not duplicated")
    check(final == before, "with staging back as it was, the snapshot is exactly as before (same content hash)")


OCC = "fact_unit_occupancy_daily"
# A content fingerprint of the snapshot without the technical columns (D14: values, not load times)
OCC_HASH = ("SELECT count(*), sum(hashtextextended(concat_ws('|', snapshot_date_key, unit_key, tenant_key, lease_key, owner_key, "
            "is_occupied, contract_rent, current_lease_arrears, source_system), 0)) FROM lue_dw.fact_unit_occupancy_daily")


def occupancy_tests(cur) -> None:
    print("US-7.3 fact_unit_occupancy_daily: the full load")
    cur.execute(f"TRUNCATE lue_dw.{OCC}")
    run_id, res, loads = facts.load_all(only=[OCC])
    x = loads[OCC]
    seconds = scalar(cur, "SELECT round(extract(epoch FROM ended_at - started_at)) FROM lue_audit.etl_run_log WHERE run_id = %s AND step = %s", (run_id, OCC))
    first, last = keys.DATA_WINDOW
    units = scalar(cur, "SELECT count(*) FROM lue_staging.stg_unit")
    days = scalar(cur, f"SELECT DATE '{last}' - DATE '{first}' + 1")
    rows = scalar(cur, f"SELECT count(*) FROM lue_dw.{OCC}")
    check({r.step: r.status for r in res}[OCC] == "Success" and rows == units * days == x.inserted and x.unknown == 0,
          f"one row per unit per day of the fixed window {first} to {last} (never today): {units:,} units x {days:,} days = {rows:,}; no -1 key")
    check(seconds is not None and seconds < 600, f"full load duration recorded in the run log: {seconds} s (under 10 minutes on a laptop)")
    check(len(x.months) == 36 and not x.months_off, f"unit-days reconcile in every month ({len(x.months) - len(x.months_off)}/{len(x.months)})")
    dup = scalar(cur, f"SELECT count(*) - count(DISTINCT (f.snapshot_date_key, u.unit_nk)) FROM lue_dw.{OCC} f JOIN lue_dw.dim_unit u USING (unit_key)")
    stray = scalar(cur, "SELECT (SELECT count(*) FROM lue_dw.fact_unit_occupancy_daily_default) + "
                        "(SELECT count(*) FROM lue_dw.fact_unit_occupancy_daily WHERE snapshot_date_key > %s)", (int(last.replace('-', '')),))
    check(dup == 0 and stray == 0, "zero grain duplicates (snapshot day, unit); nothing in the default partition or after the window")
    cur.execute(f"""SELECT count(*) FILTER (WHERE is_occupied = 0 AND (tenant_key <> -2 OR lease_key <> -2 OR contract_rent <> 0 OR current_lease_arrears <> 0)),
                           count(*) FILTER (WHERE is_occupied = 1 AND (tenant_key < 0 OR lease_key < 0)), sum(is_occupied),
                           count(*) FILTER (WHERE current_lease_arrears < 0) FROM lue_dw.{OCC}""")
    bad_vacant, bad_occupied, occupied, negative = cur.fetchone()
    lease_days = scalar(cur, f"SELECT coalesce(sum(greatest(0, least(end_date, DATE '{last}') - greatest(start_date, DATE '{first}') + 1)), 0) FROM lue_staging.stg_lease")
    check(bad_vacant == bad_occupied == negative == 0 and occupied == lease_days,
          f"a vacant day has tenant and lease -2, rent and arrears 0; occupied days = the leases' days in the window ({occupied:,}); no negative arrears")
    wrong = scalar(cur, f"""
        SELECT count(*) FROM lue_dw.{OCC} f JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key
        LEFT JOIN lue_dw.dim_lease dl ON dl.lease_key = f.lease_key AND f.is_occupied = 1
        LEFT JOIN lue_staging.stg_lease l ON l.lease_number = dl.lease_number
        LEFT JOIN lue_dw.dim_tenant t ON t.tenant_key = f.tenant_key AND f.is_occupied = 1
        WHERE NOT (d.full_date >= u.effective_from AND d.full_date < u.effective_to)
           OR (f.is_occupied = 1 AND (l.lease_number IS NULL OR NOT d.full_date BETWEEN l.start_date AND l.end_date
               OR t.tenant_code IS DISTINCT FROM l.tenant_code OR f.contract_rent <> l.monthly_rent
               OR NOT (d.full_date >= t.effective_from AND d.full_date < t.effective_to)))""")
    check(wrong == 0, "unit version valid that day; the active lease, its rent, and its tenant in the version valid that day")
    wrong = scalar(cur, f"""
        SELECT count(*) FROM lue_dw.{OCC} f JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key
        JOIN lue_dw.dim_unit u ON u.unit_key = f.unit_key JOIN lue_dw.dim_owner o ON o.owner_key = f.owner_key
        WHERE NOT EXISTS (SELECT 1 FROM lue_staging.stg_ownership r WHERE r.building_code = u.building_code AND r.unit_no = u.unit_no
                          AND r.owner_code = o.owner_code AND r.valid_from <= d.full_date AND (r.valid_to IS NULL OR d.full_date < r.valid_to))""")
    check(wrong == 0, "every owner key is the unit's owner that day (ownership register)")
    # Arrears against a direct per-row computation (correlated, slow, obviously right) on a sample
    cur.execute(f"""
        WITH s AS (SELECT d.full_date, dl.lease_number, f.current_lease_arrears FROM lue_dw.{OCC} f TABLESAMPLE SYSTEM (2) REPEATABLE (3004)
                   JOIN lue_dw.dim_date d ON d.date_key = f.snapshot_date_key JOIN lue_dw.dim_lease dl ON dl.lease_key = f.lease_key
                   WHERE f.is_occupied = 1 LIMIT 3000)
        SELECT count(*), count(*) FILTER (WHERE s.current_lease_arrears <> e.v), count(*) FILTER (WHERE e.v > 0) FROM s CROSS JOIN LATERAL (
          SELECT coalesce((SELECT sum(il.net_amount) FROM lue_staging.stg_invoice_line il JOIN lue_staging.stg_invoice i USING (invoice_number)
                           WHERE i.lease_number = s.lease_number AND il.due_date < s.full_date), 0)
               - coalesce((SELECT sum(a.allocated_amount) FROM lue_staging.stg_payment_allocation a
                           JOIN lue_staging.stg_invoice_line il ON il.invoice_number = a.invoice_number AND il.line_no = a.line_no
                           JOIN lue_staging.stg_invoice i ON i.invoice_number = a.invoice_number
                           WHERE i.lease_number = s.lease_number AND il.due_date < s.full_date AND a.paid_at::date <= s.full_date), 0) AS v) e""")
    sampled, wrong, owing = cur.fetchone()
    check(sampled > 0 and wrong == 0,
          f"arrears = net of the lease's lines past due minus what was paid on them by that day: {sampled:,} sampled days agree with a direct computation ({owing:,} owing)")

    print("US-7.3 The 35-day refresh (NFR-08, D14)")
    before = (cur.execute(OCC_HASH) or cur.fetchone())
    _r, res, loads = facts.load_all(only=[OCC])
    x = loads[OCC]
    after = (cur.execute(OCC_HASH) or cur.fetchone())
    check(x.inserted == x.updated == x.deleted == 0 and x.refreshed == units * 35 and after == before,
          f"a rerun with no changes: 0 inserted, updated, deleted; the refresh rewrote {x.refreshed:,} rows (units x 35 days) and the values hash identically")
    # A late payment, dated inside the last 35 days, against a line already past due and still open
    end = date.fromisoformat(last)
    paid = end - timedelta(days=10)
    cur.execute("""
        SELECT il.invoice_number, il.line_no, i.lease_number, il.net_amount - coalesce(sum(a.allocated_amount), 0) AS open
        FROM lue_staging.stg_invoice_line il JOIN lue_staging.stg_invoice i USING (invoice_number)
        JOIN lue_staging.stg_lease l ON l.lease_number = i.lease_number AND %(paid)s BETWEEN l.start_date AND l.end_date
        LEFT JOIN lue_staging.stg_payment_allocation a ON a.invoice_number = il.invoice_number AND a.line_no = il.line_no
        WHERE il.due_date < %(paid)s GROUP BY 1, 2, 3, il.net_amount HAVING il.net_amount - coalesce(sum(a.allocated_amount), 0) > 0
        ORDER BY 4 DESC, 1, 2 LIMIT 1""", {"paid": paid})
    line = cur.fetchone()
    if line is None:
        check(True, "late payment: no lease in this data owes on a past-due line in the last 35 days (nothing to correct)")
        return
    inv, ln, lease, open_ = line
    amount = min(open_, 10000)
    cur.execute("SELECT f.unit_key FROM lue_dw.fact_unit_occupancy_daily f JOIN lue_dw.dim_lease dl USING (lease_key) WHERE dl.lease_number = %s AND f.snapshot_date_key = %s",
                (lease, int(paid.strftime("%Y%m%d"))))
    unit_key = cur.fetchone()[0]
    window = [paid - timedelta(days=2), paid - timedelta(days=1), paid, paid + timedelta(days=1), end]
    show = [int(d.strftime("%Y%m%d")) for d in window]

    def arrears() -> dict:
        cur.execute(f"SELECT snapshot_date_key, current_lease_arrears FROM lue_dw.{OCC} WHERE unit_key = %s AND snapshot_date_key = ANY(%s)", (unit_key, show))
        return dict(cur.fetchall())

    was = arrears()
    ref = "PAY-TEST-LATE"
    cur.execute("INSERT INTO lue_staging.stg_payment (payment_reference, tenant_code, paid_at, method_code, amount, status, is_reversal, source_system) "
                "SELECT %s, l.tenant_code, %s, 'CASH', %s, 'Cleared', FALSE, 'S1' FROM lue_staging.stg_lease l WHERE l.lease_number = %s", (ref, paid, amount, lease))
    cur.execute("INSERT INTO lue_staging.stg_payment_allocation (payment_reference, invoice_number, line_no, allocated_amount, allocation_source, paid_at, due_date, days_past_due, is_reversal) "
                "SELECT %s, invoice_number, line_no, %s, 'test', %s, due_date, %s - due_date, FALSE FROM lue_staging.stg_invoice_line WHERE invoice_number = %s AND line_no = %s",
                (ref, amount, paid, paid, inv, ln))
    try:
        _r, res, loads = facts.load_all(only=[OCC])
        now = arrears()
        print(f"    late payment {ref}: PKR {amount:,.2f} on {paid} against {inv}/{ln} (lease {lease}, unit_key {unit_key})")
        print(f"    {'day':10} {'arrears before':>16} {'after refresh':>16}")
        for k in show:
            print(f"    {k:<10} {was[k]:>16,.2f} {now[k]:>16,.2f}")
        moved = all(now[k] == was[k] - amount for k in show if k >= show[2]) and all(now[k] == was[k] for k in show if k < show[2])
        check(moved and loads[OCC].updated == (end - paid).days + 1,
              f"a late payment dated {paid} (inside the last 35 days) lowers that lease's arrears from that day by PKR {amount:,.2f}, earlier days unchanged")
    finally:
        cur.execute("DELETE FROM lue_staging.stg_payment_allocation WHERE payment_reference = %s", (ref,))
        cur.execute("DELETE FROM lue_staging.stg_payment WHERE payment_reference = %s", (ref,))
    _r, res, loads = facts.load_all(only=[OCC])
    check((cur.execute(OCC_HASH) or cur.fetchone()) == before, "with the payment removed from staging the next run restores the snapshot exactly (same hash)")


def main() -> int:
    print("=" * 70)
    print(" E7 acceptance tests: the facts (database)")
    print("=" * 70)
    try:
        wh = connect("lue_warehouse")
    except IngestError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    wh.autocommit = True
    try:
        with wh.cursor() as cur:
            try:
                facts.check_ready(cur)
            except facts.NotReady as exc:
                print(f"  [FAIL] {exc}")
                return 1
            payment_tests(cur)
            invoice_tests(cur)
            maintenance_tests(cur)
            occupancy_tests(cur)
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
