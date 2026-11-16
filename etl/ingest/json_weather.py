"""US-3.4: S4 tickets (JSON) and S5 weather (the committed cache) into bronze.

S4: s4/tickets.json is flattened. brz_ticket gets one row per ticket object, in file order
(source_row 1 is the first object), every scalar as text: JSON null is NULL, true/false stay
true/false, a number is its digits, and a planted text where a number belongs ("Rs. 8,300") stays
that text. brz_ticket_status gets one row per entry of the ticket's status_history, with
status_seq 1, 2, ... and the same source_row, so the two copies of a duplicated ticket keep their
own histories (the ticket id alone would mix them).

S5: data/weather_cache.json (decision D12) gives brz_weather one row per city and day.

Both follow the checksum policy of US-3.3 (an unchanged file is skipped) and the structure check (a
missing or unexpected key rejects the file before anything lands). Reconciliation rows: tickets in
the file = brz_ticket rows; status entries in the file (the sum of the array lengths) =
brz_ticket_status rows; city-days in the cache = brz_weather rows.
"""

from __future__ import annotations

import json
from pathlib import Path

from etl.ingest.base import META_COLUMNS, ROOT, Step, copy_rows, sha256_file
from etl.ingest.files import FileLoader, as_text, drift, lineage, need, relative_name

TICKET_COLUMNS = ["ticket_id", "building_code", "unit_no", "category", "subcategory_code",
                  "subcategory", "priority", "is_emergency", "is_recurring", "is_tenant_caused",
                  "reported_via", "description", "vendor_code", "estimate", "final_cost",
                  "status"]  # fmt: skip
TICKET_KEYS = [*TICKET_COLUMNS, "status_history"]
STATUS_COLUMNS = ["ticket_id", "status_seq", "status", "status_at", "vendor_code"]
STATUS_KEYS = {"status", "at", "vendor_code"}  # vendor_code only on the Assigned entry
WEATHER_COLUMNS = ["city", "weather_date", "max_temp_c", "rainfall_mm"]
WEATHER_DAILY = ["time", "temperature_2m_max", "precipitation_sum"]


def ticket_structure(export) -> list[str]:
    """The keys found, in the order expected, or a description of the first difference."""
    if not isinstance(export, dict) or not isinstance(export.get("tickets"), list):
        return ["<no 'tickets' list at the top level>"]
    for i, t in enumerate(export["tickets"], start=1):
        if not isinstance(t, dict) or list(t) != TICKET_KEYS:
            return list(t) if isinstance(t, dict) else [f"<ticket {i} is not an object>"]
        history = t["status_history"]
        if not isinstance(history, list) or not all(
            isinstance(h, dict) and {"status", "at"} <= set(h) <= STATUS_KEYS for h in history
        ):
            return [*TICKET_COLUMNS, f"<status_history of ticket {i} has other keys>"]
    return TICKET_KEYS


def ingest_s4(step: Step, data: Path) -> None:
    path = need(data / "s4" / "tickets.json")
    checksum = sha256_file(path)
    loader = FileLoader(step, data)
    try:
        export = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        export = None
        bad = [f"<not valid JSON: {exc.msg} at line {exc.lineno}>"]
    else:
        bad = ticket_structure(export)
    tickets = export["tickets"] if bad == TICKET_KEYS else []
    loader.load(path, checksum, "brz_ticket", TICKET_KEYS[:-1],
                bad[:-1] if bad == TICKET_KEYS else bad,
                lambda: [[t[c] for c in TICKET_COLUMNS] for t in tickets])  # fmt: skip
    _load_status(loader, path, checksum, tickets, bad == TICKET_KEYS, bad)
    loader.reconcile("brz_ticket", "brz_ticket rows vs tickets in the file")
    loader.reconcile("brz_ticket_status", "brz_ticket_status rows vs status entries in the file")
    lineage(step, "brz_ticket", "S4 s4/tickets.json", "S4")
    lineage(step, "brz_ticket_status", "S4 s4/tickets.json status_history", "S4")


def _load_status(loader: FileLoader, path: Path, checksum: str, tickets: list, ok: bool,
                 found: list) -> None:  # fmt: skip
    """Status entries: one row each, keyed to the ticket object they came from (source_row)."""
    step = loader.step
    name = relative_name(path, loader.data)
    target = "brz_ticket_status"
    if not ok:
        problem = drift(TICKET_KEYS, found)
        loader.register(name, checksum, target, 0, "Rejected", message=problem, audit=True)
        step.reject()
        return
    rows = [
        (t["ticket_id"], str(seq), as_text(h["status"]), as_text(h["at"]),
         as_text(h.get("vendor_code")), position)
        for position, t in enumerate(tickets, start=1)
        for seq, h in enumerate(t["status_history"], start=1)
    ]  # fmt: skip
    step.read(len(rows))
    loader.current[target].append((name, checksum, len(rows)))
    if (checksum, target) in loader.loaded:
        reason = loader.skip_reason(name, checksum, target)
        loader.register(name, checksum, target, 0, "Skipped", message=reason)
        return
    batch = step.new_batch()
    stamp = (batch, step.source_system, step.loaded_at.isoformat(sep=" "))
    n = copy_rows(
        step.cur,
        target,
        STATUS_COLUMNS + list(META_COLUMNS) + ["source_file", "source_row"],
        (r[:-1] + stamp + (name, r[-1]) for r in rows),
    )
    step.result.rows_written += n
    loader.register(name, checksum, target, n, "Loaded", batch=batch)
    loader.loaded[(checksum, target)] = name


def weather_file(data: Path) -> Path:
    """The cache next to the generated data, else the committed one."""
    local = data / "weather_cache.json"
    return local if local.is_file() else ROOT / "data" / "weather_cache.json"


def ingest_s5(step: Step, data: Path) -> None:
    path = need(weather_file(data))
    checksum = sha256_file(path)
    loader = FileLoader(step, data)
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        cities = cache["cities"]
        found = list(WEATHER_COLUMNS)
        for c in cities:
            daily = c["daily"]
            if not all(k in daily for k in WEATHER_DAILY) or len(
                {len(daily[k]) for k in WEATHER_DAILY}
            ) != 1:
                found = [*WEATHER_COLUMNS, f"<daily arrays of {c.get('city')} differ>"]
                break
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        cities, found = [], [f"<not a weather cache: {type(exc).__name__} {exc}>"]
    ok = found == WEATHER_COLUMNS
    loader.load(
        path, checksum, "brz_weather", WEATHER_COLUMNS, found,
        lambda: [
            (c["city"], day, temp, rain)
            for c in (cities if ok else [])
            for day, temp, rain in zip(
                c["daily"]["time"], c["daily"]["temperature_2m_max"],
                c["daily"]["precipitation_sum"], strict=True,
            )
        ],
    )  # fmt: skip
    loader.reconcile("brz_weather", "brz_weather rows vs city-days in the cache")
    lineage(step, "brz_weather", "S5 data/weather_cache.json", "S5")
