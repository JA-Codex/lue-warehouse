"""US-7.1: business keys to surrogate keys, the same way for every fact.

Each helper returns a SQL fragment for a fact's source query:
  date_key(expr)          a date (or timestamp) -> its dim_date key; the calendar's own keys are
                          YYYYMMDD, so the key is computed, and a date outside the calendar or NULL
                          gives -1 (Unknown), or the given key for "not yet" (-2, Not applicable)
  scd2(dim, alias, nk, on_date)
                          a LEFT JOIN to the version valid on that day:
                          nk = business key AND on_date >= effective_from AND on_date < effective_to
  plain(dim, alias, nk)   a LEFT JOIN on the natural key (Type 1 and static dimensions)
  owner(alias, building, unit, on_date)
                          the owner of the unit on that day from the ownership register
                          (valid_from <= day < valid_to; an open period has no valid_to), then dim_owner
  key(alias, column)      coalesce(alias.key, -1): a key that cannot be resolved is -1 (Unknown),
                          never a dropped row; the loader counts the -1 keys of every fact
The unit's natural key is building_code || '-' || unit_no (dim_unit.unit_nk, US-6.3).
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

# The calendar is fixed by US-1.4 (dim_date): 2023-07-01 to 2027-06-30. The loader checks the
# dimension holds exactly these days before any fact is loaded (etl/facts/run.py), so a computed
# key always exists in dim_date.
CALENDAR = ("2023-07-01", "2027-06-30")
UNKNOWN, NOT_APPLICABLE = -1, -2

# The data window of the sources (etl/generator_config.py WINDOW_START, WINDOW_END; CI checks they
# agree). A periodic snapshot covers exactly these days, never up to today (US-7.3).
DATA_WINDOW = ("2023-07-01", "2026-06-30")


def date_key(expr: str, missing: int = UNKNOWN) -> str:
    d = f"({expr})::date"
    return (f"CASE WHEN {expr} IS NULL THEN {missing} WHEN {d} BETWEEN DATE '{CALENDAR[0]}' AND "
            f"DATE '{CALENDAR[1]}' THEN to_char({d}, 'YYYYMMDD')::int ELSE {UNKNOWN} END")  # fmt: skip


def scd2(dim: str, alias: str, nk: str, on_date: str) -> str:
    natural = {"dim_tenant": "tenant_code", "dim_unit": "unit_nk", "dim_vendor": "vendor_code",
               "dim_maintenance_category": "subcategory_code"}[dim]  # fmt: skip
    return (f"LEFT JOIN lue_dw.{dim} {alias} ON {alias}.{natural} = {nk} AND ({on_date})::date >= "
            f"{alias}.effective_from AND ({on_date})::date < {alias}.effective_to")  # fmt: skip


def plain(dim: str, alias: str, nk: str) -> str:
    natural = {"dim_lease": "lease_number", "dim_owner": "owner_code", "dim_incentive": "incentive_code",
               "dim_payment_method": "method_code", "dim_charge_type": "charge_code",
               "dim_lease_event_type": "event_code"}[dim]  # fmt: skip
    return f"LEFT JOIN lue_dw.{dim} {alias} ON {alias}.{natural} = {nk}"


def owner(alias: str, building: str, unit: str, on_date: str) -> str:
    return (f"LEFT JOIN lue_staging.stg_ownership {alias}_r ON {alias}_r.building_code = {building} "
            f"AND {alias}_r.unit_no = {unit} AND {alias}_r.valid_from <= ({on_date})::date AND "
            f"({alias}_r.valid_to IS NULL OR ({on_date})::date < {alias}_r.valid_to) "
            f"LEFT JOIN lue_dw.dim_owner {alias} ON {alias}.owner_code = {alias}_r.owner_code")  # fmt: skip


def key(alias: str, column: str) -> str:
    return f"coalesce({alias}.{column}, {UNKNOWN})"
