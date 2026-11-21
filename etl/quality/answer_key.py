"""US-4.4: compare the quality engine's findings with the US-2.6 answer key.

Each answer key row in scope for E4 (expected_rule DQ-01 to DQ-06) is traced to its bronze row(s)
and counts as DETECTED when one of them has a finding of that check with that handling: reject
(quarantined) or warn. Every finding that no key row explains is a FALSE POSITIVE, and so is any
rejection of a row the key says must pass E4 untouched (expected_rule US-5.1, US-5.2, US-6.2:
those are handled later). One rejection explains one planted rejection (an exact duplicate must
lose one copy, not both); a planted warning explains the warnings on all its copies.

How a key row is found in bronze (the key names records as the source did before the defect):
  S1 lease_events       event_id
  S1 leases, payments   lease_number, payment_reference
  S1 invoice_lines      invoice_number|line_no
  S1 payment_allocations payment_reference|invoice_number|line_no; an orphan's invoice became
                        INV-2099-..., so payment and line number decide
  S3 settlements        channel:settlement_id
  S4 tickets            ticket_id, in brz_ticket and brz_ticket_status (a 1970 raise time is a
                        status row)
  S6 incentive_log      building|unit|offer|start; the defect may have emptied the offer or moved
                        the start date, so unit, then offer (or empty) and start date (as written,
                        day first, or ten years early) decide
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

COLUMNS = ["kind", "source", "table", "defect_type", "expected_handling", "expected_rule",
           "expected", "detected", "missed", "found_by", "note"]  # fmt: skip
LATER = {"US-5.1": "cleaned in staging (US-5.1)", "US-5.2": "matched in staging (US-5.2)",
         "US-6.2": "a new SCD2 version (US-6.2)"}  # fmt: skip


@dataclass
class Comparison:
    rows: list[list] = field(default_factory=list)
    detected: int = 0
    expected: int = 0
    false_positives: int = 0

    @property
    def ok(self) -> bool:
        return self.detected == self.expected and self.false_positives == 0


def _fetch(cur, sql: str) -> list[tuple]:
    cur.execute(sql)
    return cur.fetchall()


class Bronze:
    """Just the columns needed to find the key's records, loaded once."""

    def __init__(self, cur):
        self.index: dict[str, dict] = {}
        idx = defaultdict(lambda: defaultdict(list))
        for rid, event in _fetch(cur, "SELECT row_id, event_id FROM lue_staging.brz_lease_event"):
            idx["lease_events"][event].append(("brz_lease_event", rid))
        for rid, n in _fetch(cur, "SELECT row_id, lease_number FROM lue_staging.brz_lease"):
            idx["leases"][n].append(("brz_lease", rid))
        for rid, n in _fetch(cur, "SELECT row_id, payment_reference FROM lue_staging.brz_payment"):
            idx["payments"][n].append(("brz_payment", rid))
        for rid, inv, line in _fetch(cur, "SELECT row_id, invoice_number, line_no FROM "
                                          "lue_staging.brz_invoice_line"):  # fmt: skip
            idx["invoice_lines"][f"{inv}|{line}"].append(("brz_invoice_line", rid))
        for rid, pay, inv, line in _fetch(cur, "SELECT row_id, payment_reference, invoice_number, "
                                               "line_no FROM lue_staging.brz_payment_allocation"):
            idx["payment_allocations"][(pay, line)].append(("brz_payment_allocation", rid, inv))
        for rid, sid, f in _fetch(cur, "SELECT row_id, settlement_id, source_file FROM "
                                       "lue_staging.brz_settlement"):  # fmt: skip
            channel = f.rsplit("/", 1)[-1][len("settlement_"):].rsplit("_", 1)[0]
            idx["settlements"][f"{channel}:{sid}"].append(("brz_settlement", rid))
        for table in ("brz_ticket", "brz_ticket_status"):
            for rid, tid in _fetch(cur, f"SELECT row_id, ticket_id FROM lue_staging.{table}"):
                idx["tickets"][tid].append((table, rid))
        for rid, b, u, o, s in _fetch(cur, "SELECT row_id, building_code, unit_no, offer_code, "
                                           "start_date FROM lue_staging.brz_incentive_log"):
            idx["incentive_log"][(b, u)].append(("brz_incentive_log", rid, o, s))
        self.index = idx

    def find(self, source: str, table: str, record: str) -> list[tuple[str, int]]:
        idx = self.index.get(table, {})
        if table == "payment_allocations":
            pay, inv, line = record.split("|")
            moved = "INV-2099" + inv[8:]
            return [(t, r) for t, r, got in idx.get((pay, line), []) if got in (inv, moved)]
        if table == "incentive_log":
            b, u, o, s = record.split("|")
            d = date.fromisoformat(s)
            try:
                early = d.replace(year=d.year - 10).isoformat()
            except ValueError:
                early = d.replace(year=d.year - 10, day=28).isoformat()
            starts = {s, d.strftime("%d/%m/%Y"), early}
            return [(t, r) for t, r, got_o, got_s in idx.get((b, u), [])
                    if got_o in (o, "") and got_s in starts]  # fmt: skip
        return list(idx.get(record, []))


def compare(cur, key_file: Path, run_id: int | None) -> Comparison:
    """The planted defects against the findings of one validation run, or (run_id None) against
    the current findings of every batch: each batch keeps the findings of the run that last
    validated it, so all of lue_audit.dq_result is the current picture (US-9.1)."""
    with key_file.open(encoding="utf-8", newline="") as f:
        key = list(csv.DictReader(f))
    findings = defaultdict(list)  # (table, row_id) -> [(rule_id, check_name, severity, reason)]
    where = "" if run_id is None else f" WHERE run_id = {int(run_id)}"
    for table, rid, rule, check, sev, reason in _fetch(
        cur,
        f"SELECT source_table, row_id, rule_id, check_name, severity, reason FROM "
        f"lue_audit.dq_result{where}",
    ):
        findings[(table, rid)].append((rule, check, sev, reason))
    bronze = Bronze(cur)
    explained: set[tuple] = set()
    groups: dict[tuple, Counter] = defaultdict(Counter)
    found_by: dict[tuple, Counter] = defaultdict(Counter)
    notes: dict[tuple, set] = defaultdict(set)
    out = Comparison()
    for k in key:
        group = (k["source"], k["table"], k["defect_type"], k["expected_handling"],
                 k["expected_rule"])  # fmt: skip
        groups[group]["expected"] += 1
        rows = bronze.find(k["source"], k["table"], k["record_id"])
        if not k["expected_rule"].startswith("DQ-"):
            continue  # judged below: must not be rejected
        out.expected += 1
        if not rows:
            notes[group].add("record not found in bronze")
            continue
        hits = [
            (row, f)
            for row in rows
            for f in findings.get(row, [])
            if f[1].startswith(k["expected_rule"]) and f[2] == k["expected_handling"]
            and (row, f[0]) not in explained
        ]  # fmt: skip
        if not hits:
            other = {f[0] for row in rows for f in findings.get(row, [])}
            if other:
                notes[group].add("caught by another rule: " + ", ".join(sorted(other)))
            continue
        groups[group]["detected"] += 1
        out.detected += 1
        for row, f in hits[:1] if k["expected_handling"] == "reject" else hits:
            explained.add((row, f[0]))
            found_by[group][f[0]] += 1
    for group, c in sorted(groups.items()):
        source, table, defect, handling, rule = group
        later = not rule.startswith("DQ-")
        miss = 0 if later else c["expected"] - c["detected"]
        note = "; ".join(sorted(notes[group]))
        rules_used = " ".join(f"{r}:{n}" for r, n in sorted(found_by[group].items()))
        if later:
            note = LATER.get(rule, rule) + "; must pass E4 (a rejection would be a false positive)"
        out.rows.append(["planted" if not later else "later stage", source, table, defect,
                         handling, rule, c["expected"], "" if later else c["detected"],
                         "" if later else miss,
                         rules_used, note])  # fmt: skip
    fp: dict[tuple, list] = defaultdict(list)
    for row, fs in findings.items():
        for f in fs:
            if (row, f[0]) not in explained:
                fp[(row[0], f[0], f[1], f[2])].append(f[3])
    for (table, rule, check, sev), reasons in sorted(fp.items()):
        out.false_positives += len(reasons)
        out.rows.append(["false positive", "", table, "", sev, check, "", len(reasons), "", rule,
                         "e.g. " + reasons[0]])  # fmt: skip
    return out


def write(result: Comparison, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(result.rows)
        w.writerow(["total", "", "", "", "", "", result.expected, result.detected,
                    result.expected - result.detected, "",
                    f"{result.false_positives} false positives"])  # fmt: skip
