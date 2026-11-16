#!/usr/bin/env python3
"""E5 checks that need no database (run by CI in make gen-test).

    python scripts/test_staging_contract.py

The staging spec (etl/staging/spec.py) against the bronze DDL and itself: the generated DDL and
contract are current (ddl.py --check), every expression names real bronze columns, keys and
types are sound, the vocabularies are consistent and cover the generator's values; all the SQL
the loader, the business step and the evidence build parses (pglast); the allocation rules
(US-5.2) on small cases: never more than a payment or a line, own invoice first, then oldest due,
reversals mirror the original.
"""

import re
import sys
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl import gen_master  # noqa: E402
from etl import reference_data as ref  # noqa: E402
from etl.staging import answer_key, business, ddl, evidence, load, spec  # noqa: E402

results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def bronze_ddl() -> dict[str, list[str]]:
    from pglast import ast, parse_sql

    text = (ROOT / "sql" / "20_staging" / "01_bronze.sql").read_text(encoding="utf-8")
    out = {}
    for raw in parse_sql(text):
        if isinstance(raw.stmt, ast.CreateStmt):
            out[raw.stmt.relation.relname] = [
                e.colname for e in raw.stmt.tableElts if isinstance(e, ast.ColumnDef)
            ] + ["row_id"]  # added by 02_bronze_row_id.sql
    return out


def parses(sql: str) -> str:
    """'' if the statement parses, else the error (psycopg2 parameters filled in first)."""
    from pglast import parse_sql

    sql = re.sub(r"%\((\w+)\)s", "NULL", sql).replace("%s", "NULL").replace("%%", "%")
    try:
        parse_sql(sql)
        return ""
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def spec_tests() -> None:
    print("US-5.1 The spec, the generated files and the bronze contract")
    check(ddl.main(["--check"]) == 0,
          "the staging functions, tables and contract (docs/contracts/staging.md) are what "
          "etl/staging/spec.py gives (ddl.py --check)")  # fmt: skip
    bronze = bronze_ddl()
    names = [t.name for t in spec.TABLES]
    check(len(names) == 20 and len(set(names)) == 20 and all(n.startswith("stg_") for n in names),
          f"20 staging tables, unique names: {len(names)}")  # fmt: skip
    plan = {"stg_unit", "stg_tenant", "stg_lease", "stg_lease_event", "stg_invoice_line",
            "stg_payment", "stg_payment_allocation", "stg_settlement", "stg_ticket",
            "stg_ticket_status", "stg_incentive_offer", "stg_incentive_log", "stg_weather",
            "stg_owner", "stg_vendor", "stg_maintenance_category"}  # fmt: skip
    check(plan <= set(names), "every table the plan names (US-5.1 step 5) exists in the spec")
    check(all(t.bronze in bronze for t in spec.TABLES),
          "every table reads a bronze table of sql/20_staging/01_bronze.sql")  # fmt: skip
    unknown = []
    for t in spec.TABLES:
        exprs = [c.expr for c in t.cols + t.extra_lineage] + [t.updated, t.where]
        for e in exprs:
            for col in re.findall(r"\bb\.(\w+)", e):
                if col not in bronze.get(t.bronze, []):
                    unknown.append(f"{t.name}: b.{col}")
    check(not unknown, "every b.column in the spec exists in its bronze table"
          + (f": {unknown[:5]}" if unknown else ""))  # fmt: skip
    bad_keys = [t.name for t in spec.TABLES
                if not t.key or not set(t.key) <= {c.name for c in t.loaded}]  # fmt: skip
    check(not bad_keys, "every key column is a loaded (not derived) column" +
          (f": {bad_keys}" if bad_keys else ""))  # fmt: skip
    dup_cols = [t.name for t in spec.TABLES
                if len({c.name for c in t.cols + spec.LINEAGE + t.extra_lineage})
                != len(t.cols + spec.LINEAGE + t.extra_lineage)]  # fmt: skip
    check(not dup_cols, "no column name twice in a table (lineage included)")
    percent = [t.name for t in spec.TABLES
               if "%" in " ".join([c.expr for c in t.cols] + [t.updated, t.where])]  # fmt: skip
    check(not percent, "no % in any spec expression (psycopg2 would read it as a parameter)")
    order = [t.name for t in spec.TABLES]
    check(all(order.index(t.after) < order.index(t.name) for t in spec.TABLES if t.after),
          "a table that depends on another comes after it (stg_ticket_status after stg_ticket)")
    check(all(b in bronze for b in spec.BY_BRONZE) and len(spec.BY_BRONZE) == 20,
          "one staging table per bronze table (20 of 20)")  # fmt: skip
    contract = ddl.contract_md()
    check(all(f"## {t.name}" in contract for t in spec.TABLES) and "' lahore '" in
          ddl.functions_sql(), "the contract documents every table; the functions file shows "
          "the ' lahore ' example")  # fmt: skip


def vocabulary_tests() -> None:
    print("US-5.1 Vocabularies: one spelling per value")
    keys = {}
    clash = []
    for d, values in spec.VOCABULARY.items():
        for v in values:
            k = (d, ddl.key_of(v))
            if k in keys and keys[k] != v:
                clash.append(k)
            keys[k] = v
    for (d, v), c in spec.VARIANTS.items():
        if c not in spec.VOCABULARY.get(d, []):
            clash.append((d, v, c))
        k = (d, ddl.key_of(v))
        if k in keys and keys[k] != c:
            clash.append(k)
    check(not clash, "no two canonical values share a match key; every variant maps to a "
          "canonical value of its domain" + (f": {clash}" if clash else ""))  # fmt: skip
    sql = ddl.functions_sql()
    seeded = re.findall(r"\('(\w+)', '((?:[^']|'')*)', '((?:[^']|'')*)'\)", sql)
    pairs = [(d, k) for d, k, _c in seeded if d in spec.VOCABULARY]
    check(len(pairs) == len(set(pairs)),
          f"the vocabulary seed has each (domain, key) once ({len(pairs)} rows): one INSERT can "
          "load it")  # fmt: skip
    cities = [c[0] for c in gen_master.CITIES]
    check(set(cities) == set(spec.VOCABULARY["city"]) == set(spec.REGION) == set(spec.CITY_CODE),
          f"cities: the generator's {sorted(cities)} = vocabulary = regions = codes")
    check(set(gen_master.EMPLOYER_SECTORS) == set(spec.VOCABULARY["employer_sector"]),
          "employer sectors: the generator's 15 = the vocabulary")
    unit_types = {u for offer in ref.INCENTIVE_OFFERS for u in offer[5]}
    offer_types = {offer[1] for offer in ref.INCENTIVE_OFFERS}
    check(unit_types == set(spec.VOCABULARY["unit_type"])
          and offer_types == set(spec.VOCABULARY["offer_type"]),
          "unit types and offer types: those of etl/reference_data.py = the vocabulary")
    check(set(spec.PAYMENT_METHODS) == {m[0] for m in ref.PAYMENT_METHODS} and
          {k for k, v in spec.PAYMENT_METHODS.items() if v[2]} == {"BANK", "RAAST", "JAZZ", "EASY"},
          "payment methods: the six of etl/reference_data.py; electronic = BANK, RAAST, JAZZ, "
          "EASY (as the generator's settlements)")  # fmt: skip
    check(ddl.key_of("  LaHoRe  ") == "lahore" and ddl.key_of("IT   and Software") ==
          "it and software", "match key: case and spaces ignored, as clean_text and lower in SQL")


def sql_tests() -> None:
    print("US-5.1 to US-5.4 Every statement staging builds parses")
    errors = []
    for name, text in ddl.outputs().items():
        if name.suffix == ".sql" and (e := parses(text)):
            errors.append(f"{name.name}: {e}")
    for t in spec.TABLES:
        sql, _ = load._window(t, load.EPOCH, 0, 1)
        statements = [sql, "CREATE TEMP TABLE _src AS " + load._source_select(t), load.merge_sql(t)]
        for s in statements:
            if e := parses(s):
                errors.append(f"{t.name}: {e}")
        for col in t.loaded:
            for issue, cond in evidence.conditions(col).items():
                if e := parses(f"SELECT {cond} FROM lue_staging.{t.name} s, "
                               f"lue_staging.{t.bronze} b"):  # fmt: skip
                    errors.append(f"{t.name} {issue}: {e}")
    for table in business.ORDER:
        if e := parses(business.update_sql(table)):
            errors.append(f"business {table}: {e}")
    check(not errors, "DDL, window, source, merge, evidence and business SQL parse (pglast)"
          + (f": {errors[:3]}" if errors else ""))  # fmt: skip
    derived = {t.name: [c.name for c in t.derived] for t in spec.TABLES if t.derived}
    missing = [f"{t}.{c}" for t, cols in derived.items() for c in cols
               if not re.search(rf"\b{c}\b", business.DERIVED.get(t, ""))
               or f"{c} = d.{c}" not in business.update_sql(t)]  # fmt: skip
    n = sum(map(len, derived.values()))
    check(set(derived) == set(business.DERIVED) == set(business.ORDER) and not missing,
          f"every derived column ({n} in {len(derived)} tables) is computed and set by "
          "business.py" + (f": {missing}" if missing else ""))  # fmt: skip
    kinds = {(t.name, c.name): evidence.kind_of(c)[0] for t in spec.TABLES for c in t.loaded}
    check(kinds[("stg_building", "city")] == "vocab" and kinds[("stg_ticket", "is_emergency")] == ""
          and kinds[("stg_incentive_log", "start_date")] == "date"
          and kinds[("stg_tenant", "employer_sector")] == "default"
          and kinds[("stg_unit", "furnished")] == "typed"
          and kinds[("stg_settlement", "channel")] == "",
          "evidence classifies columns by their whole expression (a flag computed from priority "
          "is not a priority repair)")  # fmt: skip
    m = load.merge_sql(spec.BY_NAME["stg_unit"])
    check("IS DISTINCT FROM" in m and ">=" in m and "src_row_id IS NULL" in m
          and "RETURNING (xmax = 0)" in m,
          "the merge updates only a changed value, never with an older version, lets a derived "
          "row give way to the source, and tells inserts from updates")  # fmt: skip
    m = load.merge_sql(spec.BY_NAME["stg_ticket_status"])
    check(">=" not in m, "stg_ticket_status follows the surviving ticket copy (no version test)")
    w, _ = load._window(spec.BY_NAME["stg_unit"], load.EPOCH, 0, 1)
    check("b.loaded_at > %(wm)s OR (b.loaded_at = %(wm)s AND b.batch_id > %(wm_batch)s)" in w and
          "lue_audit.dq_batch" in w and "'reject'" in w,
          "the window: after the watermark (same second: a later batch), validated batches "
          "only, E4 rejections excluded")  # fmt: skip


def allocation_tests() -> None:
    print("US-5.2 Allocation where the source did not (pure rules)")
    d = date

    def lines():
        return {"T1": [[d(2024, 1, 10), d(2024, 1, 1), "INV-A", 1, D("100")],
                       [d(2024, 2, 10), d(2024, 2, 1), "INV-B", 1, D("60")],
                       [d(2024, 2, 10), d(2024, 2, 1), "INV-B", 2, D("40")],
                       [d(2024, 3, 10), d(2024, 3, 1), "INV-C", 1, D("80")]]}  # fmt: skip

    def pay(ref, day, rest, invoices=(), tenant="T1"):
        return (ref, tenant, datetime(2024, day[0], day[1], 12), D(rest), set(invoices))

    def plan(pos, rev=(), ls=None, pairs=(), s1_of=None):
        return business.plan(list(pos), list(rev), ls if ls is not None else lines(), set(pairs),
                             s1_of or {})  # fmt: skip

    got = plan([pay("P1", (2, 15), "130")])
    check(got == {("P1", "INV-A", 1): D("100"), ("P1", "INV-B", 1): D("30")},
          "oldest due line first, never more than a line's balance or the payment's rest")
    got = plan([pay("P1", (2, 15), "50", {"INV-B"})], pairs={("P1", "INV-B", 1)})
    check(got == {("P1", "INV-B", 2): D("40"), ("P1", "INV-A", 1): D("10")},
          "the payment's own invoice first (US-2.4: one invoice per payment), a line it already "
          "has is skipped, then the oldest due")  # fmt: skip
    got = plan([pay("P1", (1, 5), "500")])
    check(sum(got.values()) == D("100") and all(k[1] == "INV-A" for k in got),
          "never on an invoice issued after the payment; the rest stays unallocated")
    ls = lines()
    got = plan([pay("P2", (3, 16), "150"), pay("P1", (3, 15), "150")], ls=ls)
    per_line = {}
    for (_p, inv, ln), a in got.items():
        per_line[(inv, ln)] = per_line.get((inv, ln), 0) + a
    check(sum(got.values()) == D("280") and per_line[("INV-A", 1)] == D("100")
          and got[("P1", "INV-A", 1)] == D("100") and all(x[4] >= 0 for x in ls["T1"]),
          "payments in paid order share the balances: 280 of 300 allocated, the earlier "
          "payment first, no line over its balance")  # fmt: skip
    check(plan([pay("P1", (3, 15), "50", tenant="T9")]) == {},
          "a tenant with no open line: nothing derived")
    orig = {"P1": [("INV-A", 1, D("100")), ("INV-B", 1, D("30"))]}
    rev = [("R1", "P1", datetime(2024, 2, 20), D("-130"))]
    got = plan([], rev, s1_of=orig)
    check(got == {("R1", "INV-A", 1): D("-100"), ("R1", "INV-B", 1): D("-30")},
          "a reversal mirrors the original's allocations, negative, line by line")
    got = plan([], [("R1", "P1", datetime(2024, 2, 20), D("-30"))], pairs={("R1", "INV-A", 1)},
               s1_of=orig)  # fmt: skip
    check(got == {("R1", "INV-B", 1): D("-30")},
          "a reversal skips a line it already reverses in S1 and never reverses more than its rest")
    got = plan([], [("R1", "P1", datetime(2024, 2, 20), D("-500"))], s1_of=orig)
    check(sum(got.values()) == D("-130"),
          "never more than the original allocated (rest -500, original 130)")
    # A bounced cheque, then the tenant pays again: the reversal (earlier) reopens INV-A line 1,
    # so the new payment (later, E4 rejected its allocation) can take it.
    ls = lines()
    ls["T1"][0][4] = D("0")  # INV-A line 1 paid by P1 in S1
    got = plan([pay("P3", (2, 25), "100")], [("R1", "P1", datetime(2024, 2, 20), D("-100"))],
               ls=ls, s1_of={"P1": [("INV-A", 1, D("100"))]})  # fmt: skip
    check(got.get(("R1", "INV-A", 1)) == D("-100") and got.get(("P3", "INV-A", 1)) == D("100"),
          "payments and reversals in paid order: a reversal reopens its line for the tenant's "
          "next payment")  # fmt: skip
    got = plan([pay("P1", (2, 15), "100")], [("R1", "P1", datetime(2024, 2, 20), D("-100"))])
    check(got.get(("R1", "INV-A", 1)) == D("-100"),
          "a reversal of a payment staging allocated itself mirrors those derived allocations")


def answer_key_tests() -> None:
    print("US-5.1 The answer key's repairs are read")
    check(answer_key.canonical("'Lahore' written as 'lahore'") == "Lahore"
          and answer_key.canonical("'Apartment' written as ' apartment '") == "Apartment"
          and answer_key.canonical("2024-12-08 written as 08/12/2024 (day first)") == "2024-12-08"
          and answer_key.canonical("something else") is None,
          "canonical values come from the key's detail (quoted spelling, day-first date)")
    check(set(answer_key.TABLES) == {"buildings", "units", "tickets", "incentive_log"},
          "every table with a US-5.1 repair in the answer key is mapped to its staging table")


def main() -> int:
    print("=" * 70)
    print(" E5 contract tests: staging spec, SQL and allocation rules (no database)")
    print("=" * 70)
    spec_tests()
    vocabulary_tests()
    sql_tests()
    allocation_tests()
    answer_key_tests()
    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
