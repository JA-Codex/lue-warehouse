"""US-5.4 (and the US-5.1 evidence): cleaning evidence, saved as the pipeline runs.

lue_audit.cleaning_evidence gets, per run, staging table, issue and column, the number of rows and
a before (bronze, as the source wrote it) and after (staging) sample:

  per column, of the rows this run inserted or changed (compared with their bronze row):
    whitespace          trimmed or inner spaces collapsed            ' apartment ' -> 'Apartment'
    case_or_spelling    a vocabulary value or code in one spelling   'LAHORE' -> 'Lahore'
    empty_to_null       an empty or blank text became NULL
    null_default        a missing value got its documented default  '' -> 'Unknown'
    not_in_vocabulary   a value the vocabulary does not know (NULL; a finding to look at)
    date_day_first      a DD/MM/YYYY date read day first             '08/12/2024' -> 2024-12-08
    repaired            rows of the column with any of the repairs above (a row with two counts once)
    type_conversion     values typed (number, date, timestamp, boolean)
    named_sample        the plan's ' lahore ' -> 'Lahore' sample, by name (stg_building.city)
  per table (column '*'), the run's count bridge from lue_audit.stg_load:
    rows_read = rejected_by_dq + key_not_usable + superseded + inserted + updated + unchanged,
    and within them duplicates_removed (exact duplicates E4 rejected, DQ-03),
    conflicts_resolved (superseded copies that differed from the survivor, D15),
    rows_repaired (rows with at least one repair above)
  and after US-5.2 (business): derived_allocation, unmatched_settlement, unsettled_payment.

The CSV files (one per source, plus the cumulative count bridge and the distinct values before
and after) are written by write_files().
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

import csv
import re
from pathlib import Path

from etl.staging import spec

DAY_FIRST = r"^\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}\s*$"
EVIDENCE_COLUMNS = ["run_id", "source_system", "stg_table", "issue", "column_name",
                    "rows_affected", "sample_before", "sample_after"]  # fmt: skip
BRIDGE_COLUMNS = ["stg_table", "source_system", "bronze_rows", "rejected_by_dq", "key_not_usable",
                  "deduplicated", "expected_rows", "staged_rows", "derived_rows", "difference",
                  "explained"]  # fmt: skip


PATTERNS = [  # (kind, the whole expression) as spec.py's helpers write them
    ("default", r"coalesce\((.*)\)"),
    ("vocab", r"lue_staging\.std\('(?P<domain>\w+)', b\.\w+\)"),
    ("code", r"upper\(lue_staging\.clean_text\(b\.\w+\)\)"),
    ("text", r"lue_staging\.clean_text\(b\.\w+\)"),
    ("date", r"lue_audit\.try_date\(b\.\w+\)"),
    ("typed", r"lue_audit\.try_(numeric|timestamp)\(b\.\w+\)(::[\w(), ]+)?"),
    ("typed", r"lower\(lue_staging\.clean_text\(b\.\w+\)\)::boolean"),
]


def kind_of(c: spec.Col) -> tuple[str, str | None, str | None]:
    """(kind, raw bronze column, vocabulary domain) of a loaded column; kind '' = not a cleaning
    (a lookup such as region, a constant, or a flag computed from another column)."""
    raws = set(re.findall(r"\bb\.(\w+)", c.expr))
    if len(raws) != 1:
        return "", None, None
    raw = raws.pop()
    for kind, pattern in PATTERNS:
        if re.fullmatch(pattern, c.expr):
            domain = re.search(r"lue_staging\.std\('(\w+)'", c.expr)
            return kind, raw, domain.group(1) if domain else None
    return "", None, None


def conditions(c: spec.Col) -> dict[str, str]:
    """issue -> SQL condition over b (bronze) and s (staging) for one column."""
    kind, raw, domain = kind_of(c)
    if not kind:
        return {}
    r, v = f"b.{raw}", f"s.{c.name}"
    clean = f"lue_staging.clean_text({r})"
    out = {}
    if kind in ("text", "code", "vocab", "default"):
        out["whitespace"] = f"({clean} IS NOT NULL AND {clean} <> {r})"
    out["empty_to_null"] = f"({r} IS NOT NULL AND {clean} IS NULL AND {v} IS NULL)"
    if kind == "code":
        out["case_or_spelling"] = f"({clean} IS NOT NULL AND {v} <> {clean})"
    if kind == "vocab" or (kind == "default" and domain):
        out["case_or_spelling"] = (f"({clean} IS NOT NULL AND lue_staging.std('{domain}', {r}) "
                                   f"<> {clean})")  # fmt: skip
        out["not_in_vocabulary"] = (f"({clean} IS NOT NULL AND lue_staging.std('{domain}', {r}) "
                                    f"IS NULL)")  # fmt: skip
    if kind == "default":
        inner = f"lue_audit.try_numeric({r})" if "try_numeric" in c.expr else clean
        out["null_default"] = f"({inner} IS NULL AND {v} IS NOT NULL)"
    if kind == "date":
        out["date_day_first"] = f"({r} ~ '{DAY_FIRST}' AND {v} IS NOT NULL)"
    if kind in ("date", "typed") or (kind == "default" and "try_numeric" in c.expr):
        out["type_conversion"] = f"({v} IS NOT NULL)"
    return out


REPAIRS = ("whitespace", "case_or_spelling", "empty_to_null", "null_default", "date_day_first")


def column_evidence(cur, t: spec.Table, run_id: int) -> list[tuple]:
    """(issue, column, rows, before, after) for the rows of t this run inserted or changed."""
    aggs, labels, repaired = [], [], []
    for c in t.loaded:
        kind, raw, _domain = kind_of(c)
        issues = conditions(c)
        fixes = [cond for issue, cond in issues.items() if issue in REPAIRS]
        if fixes:
            issues["repaired"] = "(" + " OR ".join(fixes) + ")"
            repaired.append(issues["repaired"])
        for issue, cond in issues.items():
            labels.append((issue, c.name))
            aggs.append(f"count(*) FILTER (WHERE {cond}), "
                        f"(array_agg(b.{raw} ORDER BY s.src_row_id) FILTER (WHERE {cond}))[1], "
                        f"(array_agg(s.{c.name}::text ORDER BY s.src_row_id) FILTER (WHERE "
                        f"{cond}))[1]")  # fmt: skip
    if not aggs:
        return []
    aggs.append(f"count(*) FILTER (WHERE {' OR '.join(repaired) or 'false'})")
    cur.execute(f"SELECT {', '.join(aggs)} FROM lue_staging.{t.name} s JOIN lue_staging.{t.bronze} "
                f"b ON b.row_id = s.src_row_id WHERE s.run_id = {int(run_id)}")  # fmt: skip
    row = cur.fetchone()
    out = []
    for i, (issue, col) in enumerate(labels):
        n, before, after = row[3 * i: 3 * i + 3]
        if n:
            out.append((issue, col, n, before, after))
    out.append(("rows_repaired", "*", row[-1], None, None))
    if t.name == "stg_building":
        # The plan names this sample: ' lahore ' -> 'Lahore', with how many cities it repaired.
        cur.execute(
            "SELECT lue_staging.std('city', ' lahore '), count(*) FILTER (WHERE s.city = 'Lahore' "
            f"AND b.city <> 'Lahore') FROM lue_staging.stg_building s JOIN lue_staging.brz_building "
            f"b ON b.row_id = s.src_row_id WHERE s.run_id = {int(run_id)}"
        )
        after, n = cur.fetchone()
        out.append(("named_sample", "city", n, " lahore ", after))
    return out


def record(cur, run_id: int, source_system: str, table: str, rows: list[tuple]) -> None:
    for issue, col, n, before, after in rows:
        cur.execute(
            "INSERT INTO lue_audit.cleaning_evidence (run_id, source_system, stg_table, issue, "
            "column_name, rows_affected, sample_before, sample_after) VALUES (%s, %s, %s, %s, %s, "
            "%s, %s, %s) ON CONFLICT (run_id, stg_table, issue, column_name) DO UPDATE SET "
            "rows_affected = EXCLUDED.rows_affected, sample_before = EXCLUDED.sample_before, "
            "sample_after = EXCLUDED.sample_after",
            (run_id, source_system, table, issue[:40], col[:40], int(n),
             None if before is None else str(before)[:200],
             None if after is None else str(after)[:200]),
        )  # fmt: skip


def load_rows(load) -> list[tuple]:
    """The run's count bridge of one table (column '*')."""
    return [("rows_read", "*", load.read, None, None),
            ("rejected_by_dq", "*", load.rejected, None, None),
            ("duplicates_removed", "*", load.duplicates, None, None),
            ("key_not_usable", "*", load.unusable, None, None),
            ("superseded", "*", load.superseded, None, None),
            ("conflicts_resolved", "*", load.conflicts, load.conflict_sample, None),
            ("inserted", "*", load.inserted, None, None),
            ("updated", "*", load.updated, None, None),
            ("unchanged", "*", load.unchanged, None, None),
            ("deleted", "*", load.deleted, None, None)]  # fmt: skip


def business_rows(cur, business) -> dict[str, list[tuple]]:
    """US-5.2 results as evidence: derived allocations, unmatched and unsettled (state)."""
    cur.execute("SELECT count(*), count(DISTINCT payment_reference), sum(allocated_amount) FROM "
                "lue_staging.stg_payment_allocation WHERE allocation_source = 'derived'")  # fmt: skip
    n, pays, total = cur.fetchone()
    cur.execute("SELECT count(*) FILTER (WHERE NOT is_matched), (array_agg(payment_reference ORDER "
                "BY channel, settlement_id) FILTER (WHERE NOT is_matched))[1] FROM "
                "lue_staging.stg_settlement")  # fmt: skip
    unmatched, sample_u = cur.fetchone()
    cur.execute("SELECT count(*) FILTER (WHERE is_unsettled), (array_agg(payment_reference ORDER "
                "BY payment_reference) FILTER (WHERE is_unsettled))[1] FROM "
                "lue_staging.stg_payment")  # fmt: skip
    unsettled, sample_p = cur.fetchone()
    return {
        "stg_payment_allocation": [
            ("derived_allocation", "allocated_amount", n, f"{pays} payments",
             f"{total or 0} PKR allocated by staging")],
        "stg_settlement": [("unmatched_settlement", "payment_reference", unmatched, sample_u,
                            "is_matched = false")],
        "stg_payment": [("unsettled_payment", "settlement_id", unsettled, sample_p,
                         "is_unsettled = true")],
    }  # fmt: skip


# ----------------------------------------------------------------------------- cumulative bridge
def bridge(cur) -> list[list]:
    """Per table over all validated bronze: bronze rows - rejected - unusable - deduplicated =
    the rows staging must hold; compared with what it holds (US-5.1)."""
    from etl.staging import load

    out = []
    for t in spec.TABLES:
        if t.name == "stg_ticket_status":
            scope = ("(b.loaded_at, b.source_file, b.source_row) IN (SELECT k.loaded_at, k.src_file, "
                     "k.src_row FROM lue_staging.stg_ticket k)")  # fmt: skip
            cur.execute(
                f"SELECT count(*), count(*) FILTER (WHERE {load._rejected('b', t.bronze)}), "
                f"count(*) FILTER (WHERE {scope}) - count(*) FILTER (WHERE {scope} AND "
                f"{load._rejected('b', t.bronze)}) FROM lue_staging.{t.bronze} b WHERE b.batch_id "
                "IN (SELECT batch_id FROM lue_audit.dq_batch)"
            )
            total, rejected, expected = cur.fetchone()
            unusable, dedup = 0, total - rejected - expected
            note = "deduplicated = entries of the ticket copies that did not survive"
        else:
            excluded = load._rejected("b", t.bronze)
            if t.where:
                excluded = f"({excluded} OR NOT ({t.where}))"
            keys = ", ".join(f"{c.expr} AS {c.name}" for c in t.cols if c.name in t.key)
            cur.execute(
                f"WITH w AS (SELECT b.row_id, {excluded} AS x FROM lue_staging.{t.bronze} b WHERE "
                f"b.batch_id IN (SELECT batch_id FROM lue_audit.dq_batch)), "
                f"k AS (SELECT {keys} FROM lue_staging.{t.bronze} b JOIN w USING (row_id) WHERE "
                f"NOT w.x) SELECT (SELECT count(*) FROM w), (SELECT count(*) FROM w WHERE x), "
                f"(SELECT count(*) FROM k WHERE NOT ({' AND '.join(f'{k} IS NOT NULL' for k in t.key)})), "
                f"(SELECT count(*) FROM (SELECT DISTINCT {', '.join(t.key)} FROM k WHERE "
                f"{' AND '.join(f'{k} IS NOT NULL' for k in t.key)}) d)"
            )
            total, rejected, unusable, expected = cur.fetchone()
            dedup = total - rejected - unusable - expected
            note = "deduplicated = older versions and conflicting copies (D15)"
        derived = 0
        where = ""
        if t.name == "stg_payment_allocation":
            where = " WHERE allocation_source = 'S1'"
            cur.execute("SELECT count(*) FROM lue_staging.stg_payment_allocation WHERE "
                        "allocation_source = 'derived'")  # fmt: skip
            derived = cur.fetchone()[0]
            note += "; derived_rows = allocations staging made (US-5.2), not from bronze"
        cur.execute(f"SELECT count(*) FROM lue_staging.{t.name}{where}")
        staged = cur.fetchone()[0]
        if staged != expected:
            note += "; DIFFERENCE: rerun staging with --full (E4 rules or results changed)"
        out.append([t.name, t.source_system, total, rejected, unusable, dedup, expected, staged,
                    derived, staged - expected, note])  # fmt: skip
    return out


def distinct_values(cur) -> list[list]:
    """Distinct values before (bronze) and after (staging) of every vocabulary column and the
    payment method (US-5.1: one spelling each)."""
    out = []
    targets = [(t, c) for t in spec.TABLES for c in t.loaded
               if kind_of(c)[0] in ("vocab", "default") and kind_of(c)[2]]  # fmt: skip
    payment = spec.BY_NAME["stg_payment"]
    targets.append((payment, next(c for c in payment.cols if c.name == "method_code")))
    for t, c in targets:
        raw = kind_of(c)[1]
        cur.execute(f"SELECT b.{raw}, count(*) FROM lue_staging.{t.bronze} b WHERE b.batch_id IN "
                    f"(SELECT batch_id FROM lue_audit.dq_batch) GROUP BY 1 ORDER BY 1")  # fmt: skip
        for value, n in cur.fetchall():
            out.append([t.name, c.name, "before", value, n])
        cur.execute(f"SELECT {c.name}::text, count(*) FROM lue_staging.{t.name} GROUP BY 1 ORDER BY 1")
        for value, n in cur.fetchall():
            out.append([t.name, c.name, "after", value, n])
    return out


def _write(path: Path, header: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def write_files(cur, run_id: int, folder: Path) -> list[Path]:
    """cleaning_evidence_S1.csv .. S6 (this run), count_bridge.csv, distinct_values.csv."""
    written = []
    sources = sorted({t.source_system for t in spec.TABLES})
    for s in sources:
        cur.execute(f"SELECT {', '.join(EVIDENCE_COLUMNS)} FROM lue_audit.cleaning_evidence WHERE "
                    "run_id = %s AND source_system = %s ORDER BY stg_table, column_name = '*' "
                    "DESC, issue, column_name", (run_id, s))  # fmt: skip
        path = folder / f"cleaning_evidence_{s}.csv"
        _write(path, EVIDENCE_COLUMNS, cur.fetchall())
        written.append(path)
    path = folder / "count_bridge.csv"
    _write(path, BRIDGE_COLUMNS, bridge(cur))
    written.append(path)
    path = folder / "distinct_values.csv"
    _write(path, ["stg_table", "column_name", "stage", "value", "rows"], distinct_values(cur))
    written.append(path)
    return written
