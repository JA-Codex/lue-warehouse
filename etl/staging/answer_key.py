"""US-5.1 and US-5.2 against the US-2.6 answer key (what the generator planted for staging).

  repairs (expected_rule US-5.1): every planted spelling, case, whitespace or day-first date is
      found in staging with the canonical value. A record that is not staged (E4 rejected it, or
      a ticket copy without an accepted Raised entry) is counted as such, not as repaired.
  matching (expected_rule US-5.2): every planted orphan settlement line is unmatched, every
      settlement reported late is still matched, and the totals equal the generator's
      expectations (answer_key/expectations.json: unmatched_settlements,
      unsettled_electronic_payments).
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

COLUMNS = ["check", "table", "column", "expected", "found", "not_staged", "wrong", "ok", "note"]
# answer key table -> (staging table, key columns in record_id order)
TABLES = {
    "buildings": ("stg_building", ["building_code"]),
    "units": ("stg_unit", ["unit_id"]),
    "tickets": ("stg_ticket", ["ticket_id"]),
    "incentive_log": ("stg_incentive_log",
                      ["building_code", "unit_no", "offer_code", "start_date"]),  # fmt: skip
}
QUOTED = re.compile(r"'(?P<good>.*)' written as '(?P<bad>.*)'$")
DAY_FIRST = re.compile(r"(?P<good>\d{4}-\d{2}-\d{2}) written as (?P<bad>\S+) \(day first\)$")


@dataclass
class Comparison:
    rows: list[list] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.rows) and all(r[7] for r in self.rows)


def canonical(detail: str) -> str | None:
    m = QUOTED.match(detail) or DAY_FIRST.match(detail)
    return m.group("good") if m else None


def _staged(cur, table: str, keys: list[str], column: str) -> dict[tuple, str | None]:
    cur.execute(f"SELECT {', '.join(k + '::text' for k in keys)}, {column}::text FROM "
                f"lue_staging.{table}")  # fmt: skip
    return {tuple(r[:-1]): r[-1] for r in cur.fetchall()}


def compare(cur, data: Path) -> Comparison:
    key_file = data / "answer_key" / "defects_answer_key.csv"
    with key_file.open(encoding="utf-8", newline="") as f:
        key = list(csv.DictReader(f))
    out = Comparison()
    groups: dict[tuple[str, str], list[dict]] = {}
    for k in key:
        if k["expected_rule"] == "US-5.1":
            groups.setdefault((k["table"], k["column"]), []).append(k)
    for (table, column), rows in sorted(groups.items()):
        target, keys = TABLES[table]
        staged = _staged(cur, target, keys, column)
        found = missing = wrong = 0
        example = ""
        for k in rows:
            want = canonical(k["detail"])
            record = tuple(k["record_id"].split("|"))
            if record not in staged:
                missing += 1
            elif want is not None and staged[record] == want:
                found += 1
            else:
                wrong += 1
                example = example or f"{k['record_id']}: {staged[record]!r}, expected {want!r}"
        out.rows.append(["repair", target, column, len(rows), found, missing, wrong,
                         found + missing == len(rows) and wrong == 0,
                         example or "repaired to the canonical value"])  # fmt: skip

    def settlement_flags() -> dict[str, bool]:
        cur.execute("SELECT channel || ':' || settlement_id, is_matched FROM "
                    "lue_staging.stg_settlement")  # fmt: skip
        return dict(cur.fetchall())

    flags = settlement_flags()
    planted = (("orphan_reference", False, "unmatched"),
               ("late_arriving_payment", True, "matched (reported late)"))  # fmt: skip
    for defect, want, text in planted:
        rows = [k for k in key if k["defect_type"] == defect and k["expected_rule"] == "US-5.2"]
        found = sum(flags.get(k["record_id"]) is want for k in rows)
        missing = sum(k["record_id"] not in flags for k in rows)
        wrong = len(rows) - found - missing
        out.rows.append(["match", "stg_settlement", "is_matched", len(rows), found, missing, wrong,
                         found == len(rows), f"each planted line is {text}"])  # fmt: skip
    expect = json.loads((data / "answer_key" / "expectations.json").read_text(encoding="utf-8"))
    matching = expect.get("matching_us_5_2", {})
    cur.execute("SELECT count(*) FILTER (WHERE NOT is_matched) FROM lue_staging.stg_settlement")
    unmatched = cur.fetchone()[0]
    cur.execute("SELECT count(*) FILTER (WHERE is_unsettled) FROM lue_staging.stg_payment")
    unsettled = cur.fetchone()[0]
    for name, got, col, table in (
        ("unmatched_settlements", unmatched, "is_matched", "stg_settlement"),
        ("unsettled_electronic_payments", unsettled, "is_unsettled", "stg_payment"),
    ):
        want = matching.get(name)
        out.rows.append(["total", table, col, want, got, "", "", want is not None and got == want,
                         f"{name} in expectations.json"])  # fmt: skip
    return out


def write(result: Comparison, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(result.rows)
