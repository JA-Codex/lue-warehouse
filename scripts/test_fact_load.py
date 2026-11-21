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
At the end the facts hold staging again and staging is as it was.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.facts import load, spec  # noqa: E402
from etl.facts import run as facts  # noqa: E402
from etl.ingest.base import IngestError, connect  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def scalar(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def payment_tests(cur) -> None:
    print("US-7.1 fact_payment: point-in-time keys")
    cur.execute("TRUNCATE lue_dw.fact_payment RESTART IDENTITY")
    _r, res, loads = facts.load_all()
    x = loads["fact_payment"]
    staged, total = (cur.execute("SELECT count(*), sum(allocated_amount) FROM lue_staging.stg_payment_allocation") or cur.fetchone())
    loaded, fact_total = (cur.execute("SELECT count(*), sum(payment_amount) FROM lue_dw.fact_payment") or cur.fetchone())
    check(res[0].status in ("Success", "Warning") and loaded == staged == x.inserted + x.rejected and fact_total == total,
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
    _r, res, loads = facts.load_all()
    x = loads["fact_payment"]
    check(x.inserted == x.updated == x.deleted == 0, "a rerun inserts, updates and deletes nothing")
    cur.execute("SELECT payment_reference, invoice_number, line_no, allocated_amount, allocation_source, paid_at, due_date, days_past_due, is_reversal FROM lue_staging.stg_payment_allocation ORDER BY 1, 2, 3 LIMIT 2")
    (r1, i1, l1, a1, *_), keep2 = cur.fetchall()
    cur.execute("UPDATE lue_staging.stg_payment_allocation SET allocated_amount = allocated_amount + 1 WHERE payment_reference = %s AND invoice_number = %s AND line_no = %s", (r1, i1, l1))
    cur.execute("DELETE FROM lue_staging.stg_payment_allocation WHERE payment_reference = %s AND invoice_number = %s AND line_no = %s", keep2[:3])
    try:
        _r, res, loads = facts.load_all()
        x = loads["fact_payment"]
        amount = scalar(cur, "SELECT payment_amount FROM lue_dw.fact_payment WHERE payment_reference = %s AND invoice_number = %s AND invoice_line_no = %s", (r1, i1, l1))
        gone = scalar(cur, "SELECT count(*) FROM lue_dw.fact_payment WHERE payment_reference = %s AND invoice_number = %s AND invoice_line_no = %s", keep2[:3])
        check(x.updated == 1 and x.deleted == 1 and x.inserted == 0 and amount == a1 + 1 and gone == 0,
              "a changed source row is updated in place and a removed one deleted: 1 updated, 1 deleted, nothing duplicated")
    finally:
        cur.execute("UPDATE lue_staging.stg_payment_allocation SET allocated_amount = %s WHERE payment_reference = %s AND invoice_number = %s AND line_no = %s", (a1, r1, i1, l1))
        cur.execute("INSERT INTO lue_staging.stg_payment_allocation (payment_reference, invoice_number, line_no, allocated_amount, allocation_source, paid_at, due_date, days_past_due, is_reversal) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", keep2)
    _r, res, loads = facts.load_all()
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
    finally:
        wh.close()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
