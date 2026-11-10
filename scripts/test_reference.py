#!/usr/bin/env python3
"""Acceptance tests for US-1.4 (date dimension and static reference dimensions).

    python scripts/test_reference.py            run every check
    python scripts/test_reference.py --no-rerun skip the "load again, nothing changes" check

Run scripts/db_deploy.py and scripts/db_load_reference.py first. Runs as lue_etl and changes
nothing, except that the re-run check loads the reference data a second time (which must change
nothing). Every check prints PASS or FAIL; the exit code is 0 only if all pass.
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from db_setup import ETL_ROLE, load_settings  # noqa: E402
from test_dimensions import check, connect, results  # noqa: E402

from etl import reference_data as ref  # noqa: E402

START, END = dt.date(2023, 7, 1), dt.date(2027, 6, 30)


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def state(cur) -> list:
    """Content and next key number of every reference table; equal before and after = no change."""
    out = []
    for t in ("dim_date", "dim_payment_method", "dim_charge_type", "dim_lease_event_type"):
        cur.execute(f"SELECT md5(string_agg(x::text, '|' ORDER BY x::text)) FROM lue_dw.{t} x")
        out.append((t, cur.fetchone()[0]))
    cur.execute(
        "SELECT md5(string_agg(x::text, '|' ORDER BY x::text)) FROM lue_dw.dim_request_flags x"
    )
    out.append(("dim_request_flags", cur.fetchone()[0]))
    for t, k in (
        ("dim_payment_method", "payment_method_key"),
        ("dim_charge_type", "charge_type_key"),
        ("dim_lease_event_type", "lease_event_type_key"),
        ("dim_request_flags", "request_flags_key"),
    ):
        out.append(
            (
                t + " next key",
                scalar(
                    cur,
                    f"SELECT pg_sequence_last_value(pg_get_serial_sequence('lue_dw.{t}', '{k}'))",
                ),
            )
        )
    return out


def test_date(cur) -> None:
    print("dim_date")
    days = (END - START).days + 1
    n = scalar(cur, "SELECT count(*) FROM lue_dw.dim_date WHERE date_key > 0")
    check(days == 1461 and n == 1461, f"1,461 calendar days loaded (found {n})")
    check(
        scalar(cur, "SELECT count(*) FROM lue_dw.dim_date WHERE date_key < 0") == 2,
        "plus the 2 special members (-1 Unknown, -2 Not applicable)",
    )
    lo, hi = (
        scalar(cur, "SELECT min(full_date) FROM lue_dw.dim_date WHERE date_key > 0"),
        scalar(cur, "SELECT max(full_date) FROM lue_dw.dim_date WHERE date_key > 0"),
    )
    check((lo, hi) == (START, END), f"runs from {START} to {END}")
    gaps = scalar(
        cur,
        "SELECT (max(full_date) - min(full_date) + 1) - count(DISTINCT full_date) "
        "FROM lue_dw.dim_date WHERE date_key > 0",
    )
    check(gaps == 0, "no gaps: every day between the first and the last date is present")
    check(
        scalar(
            cur,
            "SELECT count(*) FROM lue_dw.dim_date WHERE date_key > 0 "
            "AND date_key <> to_char(full_date, 'YYYYMMDD')::int",
        )
        == 0,
        "date_key is YYYYMMDD of full_date for every row",
    )
    check(
        scalar(cur, "SELECT count(*) FROM lue_dw.dim_date WHERE full_date = '2024-02-29'") == 1,
        "the leap day 2024-02-29 exists",
    )

    # Compare every row with Python's own calendar.
    cur.execute(
        "SELECT full_date, day_of_month, day_name, is_weekend, week_of_year, month_no, month_name, "
        "quarter_no, year_no, fiscal_month_no, fiscal_quarter_no, fiscal_year_label "
        "FROM lue_dw.dim_date WHERE date_key > 0"
    )
    bad = 0
    for d, dom, dname, wk, woy, mno, mname, q, y, fm, fq, fy in cur.fetchall():
        start_year = d.year if d.month >= 7 else d.year - 1
        fiscal_month = (d.month - 7) % 12 + 1
        want = (
            d.day,
            d.strftime("%A"),
            d.weekday() >= 5,
            d.isocalendar()[1],
            d.month,
            d.strftime("%B"),
            (d.month - 1) // 3 + 1,
            d.year,
            fiscal_month,
            (fiscal_month - 1) // 3 + 1,
            f"FY{start_year}-{(start_year + 1) % 100:02d}",
        )
        if (dom, dname, wk, woy, mno, mname, q, y, fm, fq, fy) != want:
            bad += 1
    check(
        bad == 0,
        f"all attributes match Python's calendar (weekday, ISO week, quarter, fiscal): {bad} wrong",
    )

    cur.execute(
        "SELECT full_date, fiscal_year_label, fiscal_month_no, fiscal_quarter_no "
        "FROM lue_dw.dim_date WHERE full_date IN ('2026-06-30', '2026-07-01') ORDER BY 1"
    )
    (d1, f1, m1, q1), (d2, f2, m2, q2) = cur.fetchall()
    check(
        (f1, m1, q1, f2, m2, q2) == ("FY2025-26", 12, 4, "FY2026-27", 1, 1),
        f"fiscal year changes at 1 July: {d1} is {f1} (month {m1}), {d2} is {f2} (month {m2})",
    )
    cur.execute("SELECT count(DISTINCT fiscal_year_label) FROM lue_dw.dim_date WHERE date_key > 0")
    check(cur.fetchone()[0] == 4, "four fiscal years: FY2023-24 to FY2026-27")
    check(
        scalar(
            cur,
            "SELECT count(*) FROM lue_dw.dim_date WHERE date_key > 0 "
            "AND (is_public_holiday OR is_ramadan OR holiday_name IS NOT NULL)",
        )
        == 0,
        "holiday and Ramadan flags start FALSE (US-6.4 fills them)",
    )


def test_static(cur) -> None:
    print("Static reference dimensions (members from etl/reference_data.py)")
    cur.execute(
        "SELECT method_code, method_name, channel_group, typical_settlement_days, "
        "payment_method_key FROM lue_dw.dim_payment_method WHERE payment_method_key > 0 "
        "ORDER BY payment_method_key"
    )
    rows = cur.fetchall()
    check(
        [r[:4] for r in rows] == ref.PAYMENT_METHODS,
        "dim_payment_method has exactly the 6 agreed methods",
    )
    check(
        [r[4] for r in rows] == [1, 2, 3, 4, 5, 6],
        "payment method keys are 1 to 6, in the agreed order",
    )
    check(
        len({r[2] for r in rows}) == 5,
        "5 channel groups: Cash, Cheque, Bank, Instant payment, Mobile wallet",
    )

    cur.execute(
        "SELECT charge_code, charge_type_name, charge_category, charge_type_key "
        "FROM lue_dw.dim_charge_type WHERE charge_type_key > 0 ORDER BY charge_type_key"
    )
    rows = cur.fetchall()
    check(
        [r[:3] for r in rows] == ref.CHARGE_TYPES,
        "dim_charge_type has exactly the 6 agreed charge types",
    )
    check([r[3] for r in rows] == [1, 2, 3, 4, 5, 6], "charge type keys are 1 to 6; RENT is key 1")
    check(
        {r[2] for r in rows} == {"Rent", "Ancillary", "Penalty", "Credit"},
        "4 charge categories: Rent, Ancillary, Penalty, Credit",
    )

    cur.execute(
        "SELECT event_code, event_name, is_exit_event, lease_event_type_key "
        "FROM lue_dw.dim_lease_event_type WHERE lease_event_type_key > 0 "
        "ORDER BY lease_event_type_key"
    )
    rows = cur.fetchall()
    check(
        [r[:3] for r in rows] == ref.LEASE_EVENT_TYPES,
        "dim_lease_event_type has exactly the 4 agreed events",
    )
    check([r[3] for r in rows] == [1, 2, 3, 4], "lease event keys are 1 to 4")
    check(
        {r[0] for r in rows if r[2]} == {"NOTICE", "TERM"},
        "exit events are Notice given and Terminated only",
    )

    cur.execute(
        "SELECT is_emergency, is_recurring, is_tenant_caused, flags_label, request_flags_key "
        "FROM lue_dw.dim_request_flags ORDER BY request_flags_key"
    )
    rows = cur.fetchall()
    check(
        len(rows) == 8 and len({r[:3] for r in rows}) == 8,
        "dim_request_flags has all 8 flag combinations, once each",
    )
    check(
        [r[:3] for r in rows] == ref.REQUEST_FLAG_COMBINATIONS,
        "flag combinations are in key order 1 to 8",
    )
    check(
        [r[3] for r in rows] == [ref.flags_label(*r[:3]) for r in rows],
        "every flags_label is the readable text of its three flags",
    )
    check(
        all(r[4] > 0 for r in rows),
        "dim_request_flags has no special members (as in the Phase 1 pack)",
    )

    print("Special members and lineage")
    for t, k in (
        ("dim_payment_method", "payment_method_key"),
        ("dim_charge_type", "charge_type_key"),
        ("dim_lease_event_type", "lease_event_type_key"),
    ):
        cur.execute(f"SELECT array_agg({k} ORDER BY {k}) FROM lue_dw.{t} WHERE {k} < 0")
        check(cur.fetchone()[0] == [-2, -1], f"{t}: special members -2 and -1 are still there")
        cur.execute(
            f"SELECT count(*) FROM lue_dw.{t} WHERE {k} > 0 "
            "AND (source_system <> 'SEED' OR batch_id <> 0 OR loaded_at IS NULL)"
        )
        check(cur.fetchone()[0] == 0, f"{t}: lineage columns are filled (source SEED, batch 0)")


def test_facts_can_resolve(cur) -> None:
    print("Facts can resolve their keys")
    # A fact needs a real date and real code keys. Look each one up the way the fact loaders will.
    cur.execute(
        "SELECT (SELECT date_key FROM lue_dw.dim_date WHERE full_date = '2025-03-14'), "
        "(SELECT payment_method_key FROM lue_dw.dim_payment_method WHERE method_code = 'JAZZ'), "
        "(SELECT charge_type_key FROM lue_dw.dim_charge_type WHERE charge_code = 'RENT'), "
        "(SELECT lease_event_type_key FROM lue_dw.dim_lease_event_type WHERE event_code = 'RENEW')"
    )
    check(
        cur.fetchone() == (20250314, 5, 1, 2),
        "date 2025-03-14 = 20250314; JAZZ = 5; RENT = 1; RENEW = 2",
    )


def main() -> int:
    import psycopg2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--no-rerun", action="store_true")
    args = ap.parse_args()
    s = load_settings()

    print("=" * 70)
    print(" US-1.4 acceptance tests: date dimension and static reference dimensions")
    print("=" * 70)
    try:
        conn = connect(s, ETL_ROLE, s.get("LUE_ETL_PASSWORD", ""))
    except psycopg2.OperationalError as exc:
        print(f"  [FAIL] cannot connect as {ETL_ROLE}: {exc}".rstrip())
        print(
            " RESULT: FAILED (is PostgreSQL running? have db_setup.py and db_deploy.py been run?)"
        )
        return 1
    conn.autocommit = True
    cur = conn.cursor()
    try:
        test_date(cur)
        test_static(cur)
        test_facts_can_resolve(cur)
        if not args.no_rerun:
            print("Re-run")
            before = state(cur)
            run = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("db_load_reference.py"))],
                capture_output=True,
                text=True,
            )
            check(run.returncode == 0, "running db_load_reference.py a second time succeeds")
            check(
                state(cur) == before, "the second run changes no row and uses no extra key number"
            )
    except psycopg2.Error as exc:
        check(False, f"a query failed: {exc}".strip())
        print("       Has python scripts/db_load_reference.py been run?")
    finally:
        conn.close()

    print("=" * 70)
    passed = sum(results)
    print(
        f" RESULT: {passed}/{len(results)} checks passed"
        + ("" if results and all(results) else " - FAILED")
    )
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
