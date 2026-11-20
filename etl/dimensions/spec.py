"""E6: the dimensions as data, in load order. One loader (etl/dimensions/load.py) reads this.

Per dimension: its table in lue_dw, surrogate key, natural key, the SQL that gives one row per
natural key with its current values from the staging contract (docs/contracts/staging.md), and
each column with its SCD type from the Phase 1 data dictionary (docs/phase1, model.py):
  0  identity: written when the member is created, never changed
  1  overwrite in place, on every version of the member (corrections, current value only)
  2  history: a change closes the current version and opens a new one (US-6.2, US-6.3)
An SCD2 dimension also has a history query: every known state of each member with the date it
took effect, oldest first. Its versions are rebuilt from that history (US-6.2).

Load order (plan US-6.1 step 3):
  static   dim_date, dim_payment_method, dim_charge_type, dim_lease_event_type, dim_request_flags
           (US-1.4, sql/30_dimensions/01_reference_dimensions.sql; checked, not reloaded); the
           calendar's holiday flags are set from the S2 register first (US-6.4)
  then     independent dimensions: owner, vendor, maintenance category, incentive, weather
  then     unit, tenant and lease (the members facts point at most)
Facts (E7) load only after every dimension.

Conventions: unit_nk = building_code || '-' || unit_no ('GLB01-A-101'); a member's first version is
valid from 1900-01-01; effective_to is exclusive (the next version's effective_from), 9999-12-31
while current; a NOT NULL column with no value gets the special-member text ('Unknown', '?' for a
one-letter code, 0 for a count). Inferred members (is_inferred) exist for tenants only: the frozen
DDL gives the flag to dim_tenant alone; a fact whose vendor is missing points at -1 (Unknown).
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass, field

from etl.staging import spec as staging

# static dimension -> its rows besides the special members -1 and -2 (US-1.4)
STATIC = {"dim_date": 1461, "dim_payment_method": 6, "dim_charge_type": 6, "dim_lease_event_type": 4,
          "dim_request_flags": 8}  # fmt: skip
STATIC_KEY = {"dim_date": "date_key", "dim_payment_method": "payment_method_key",
              "dim_charge_type": "charge_type_key", "dim_lease_event_type": "lease_event_type_key",
              "dim_request_flags": "request_flags_key"}  # fmt: skip
FIRST_DAY = "1900-01-01"  # effective_from of a member's first version: valid for any fact date
OPEN_END = "9999-12-31"  # effective_to of the current version (exclusive end)
RECENT_YEAR = "extract(year FROM current_date)::int"  # building age is as of today (Type 1)


@dataclass
class Dim:
    name: str
    key: str  # surrogate key column (identity)
    nk: list[str]  # natural key columns
    source: str  # SQL: one row per natural key, every column of cols, and source_system
    cols: dict[str, int]  # column -> SCD type (0, 1, 2), excluding key, nk and technical columns
    story: str  # the story that loads it
    staging: list[str] = field(default_factory=list)  # staging tables read (lineage)
    scd2: bool = False  # has effective_from, effective_to, is_current
    inferred: bool = False  # has is_inferred (US-6.5)
    history: str = ""  # SCD2: SQL giving nk, the type 2 columns, change_date, seq (oldest first)
    references: str = ""  # SQL giving natural keys referenced by staging (inferred members)
    depends: list[str] = field(default_factory=list)  # dimensions that must be loaded first

    @property
    def type1(self) -> list[str]:
        return [c for c, t in self.cols.items() if t == 1]

    @property
    def type2(self) -> list[str]:
        return [c for c, t in self.cols.items() if t == 2]


def validated(bronze: str, alias: str = "b") -> str:
    """Bronze rows staging may use: from validated batches, not rejected by E4 (as US-5.1)."""
    return (f"{alias}.batch_id IN (SELECT batch_id FROM lue_audit.dq_batch) AND NOT EXISTS (SELECT 1 "
            f"FROM lue_audit.dq_result r WHERE r.source_table = '{bronze}' AND r.row_id = "
            f"{alias}.row_id AND r.severity = 'reject')")  # fmt: skip


def expr(stg_table: str, column: str) -> str:
    """The staging cleaning expression of a column, over bronze alias b (one rule, two uses)."""
    return next(c.expr for c in staging.BY_NAME[stg_table].cols if c.name == column)


def age_band(year: str) -> str:
    return (f"CASE WHEN {year} IS NULL THEN 'Unknown' WHEN {RECENT_YEAR} - {year} <= 5 THEN '0–5 yrs' "
            f"WHEN {RECENT_YEAR} - {year} <= 15 THEN '6–15 yrs' ELSE '16+ yrs' END")  # fmt: skip


TENANT_HISTORY = f"""
    SELECT {expr('stg_tenant', 'tenant_code')} AS tenant_code,
           coalesce({expr('stg_tenant', 'tenant_type')}, 'Unknown') AS tenant_type,
           {expr('stg_tenant', 'employer_sector')} AS employer_sector,
           ({staging.BY_NAME['stg_tenant'].updated})::date AS change_date,
           row_number() OVER (ORDER BY {staging.BY_NAME['stg_tenant'].updated}, b.loaded_at, b.row_id) AS seq
    FROM lue_staging.brz_tenant b WHERE {validated('brz_tenant')}"""
UNIT_NK = f"{expr('stg_unit', 'building_code')} || '-' || {expr('stg_unit', 'unit_no')}"
UNIT_HISTORY = f"""
    SELECT {UNIT_NK} AS unit_nk,
           coalesce({expr('stg_unit', 'unit_type')}, 'Unknown') AS unit_type,
           coalesce({expr('stg_unit', 'furnished')}, FALSE) AS furnished_flag,
           ({staging.BY_NAME['stg_unit'].updated})::date AS change_date,
           row_number() OVER (ORDER BY {staging.BY_NAME['stg_unit'].updated}, b.loaded_at, b.row_id) AS seq
    FROM lue_staging.brz_unit b WHERE {validated('brz_unit')}"""

DIMS = [
    Dim("dim_owner", "owner_key", ["owner_code"], story="US-6.4", staging=["stg_owner", "stg_ownership"],
        source="""
        SELECT o.owner_code, coalesce(o.owner_name, 'Unknown') AS owner_name,
               coalesce(o.owner_type, 'Unknown') AS owner_type,
               CASE count(s.unit_no) WHEN 0 THEN 'None' WHEN 1 THEN '1 unit'
                    ELSE CASE WHEN count(s.unit_no) <= 5 THEN '2–5 units' ELSE '6+ units' END END AS portfolio_size_band,
               o.source_system
        FROM lue_staging.stg_owner o
        LEFT JOIN lue_staging.stg_ownership s ON s.owner_code = o.owner_code
             AND s.valid_from <= current_date AND (s.valid_to IS NULL OR s.valid_to >= current_date)
        GROUP BY o.owner_code, o.owner_name, o.owner_type, o.source_system""",
        cols={"owner_name": 1, "owner_type": 1, "portfolio_size_band": 1}),
    Dim("dim_vendor", "vendor_key", ["vendor_code"], story="US-6.3", scd2=True,
        staging=["stg_vendor"],
        source="""
        SELECT v.vendor_code, coalesce(v.vendor_name, 'Unknown') AS vendor_name,
               coalesce(v.trade, 'Unknown') AS trade, coalesce(v.rating, '?') AS rating_band,
               coalesce(v.phone, 'Unknown') AS phone, v.source_system
        FROM lue_staging.stg_vendor v""",
        history="""
        SELECT v.vendor_code, coalesce(v.previous_rating, v.rating, '?') AS rating_band,
               DATE '1900-01-01' AS change_date, 1 AS seq
        FROM lue_staging.stg_vendor v
        UNION ALL
        SELECT v.vendor_code, coalesce(v.rating, '?'), v.rating_changed_on, 2
        FROM lue_staging.stg_vendor v WHERE v.rating_changed_on IS NOT NULL""",
        cols={"vendor_name": 1, "trade": 1, "rating_band": 2, "phone": 1}),
    Dim("dim_maintenance_category", "maint_category_key", ["subcategory_code"], story="US-6.3", scd2=True,
        staging=["stg_maintenance_category"],
        source="""
        SELECT DISTINCT ON (c.subcategory_code) c.subcategory_code,
               coalesce(c.subcategory_name, 'Unknown') AS subcategory_name,
               coalesce(c.category_name, 'Unknown') AS category_name,
               coalesce(c.default_sla_hours, 0) AS default_sla_hours, c.source_system
        FROM lue_staging.stg_maintenance_category c
        ORDER BY c.subcategory_code, c.valid_from DESC""",
        history="""
        SELECT c.subcategory_code, coalesce(c.default_sla_hours, 0) AS default_sla_hours,
               c.valid_from AS change_date, row_number() OVER (ORDER BY c.valid_from) AS seq
        FROM lue_staging.stg_maintenance_category c""",
        cols={"subcategory_name": 1, "category_name": 1, "default_sla_hours": 2}),
    Dim("dim_incentive", "incentive_key", ["incentive_code"], story="US-6.4", staging=["stg_incentive_offer"],
        source="""
        SELECT i.offer_code AS incentive_code, coalesce(i.offer_type, 'Unknown') AS incentive_type,
               coalesce(i.description, 'Unknown') AS incentive_description,
               coalesce(i.discount_pct, 0) AS discount_pct, coalesce(i.rent_free_days, 0) AS rent_free_days,
               i.source_system
        FROM lue_staging.stg_incentive_offer i""",
        cols={"incentive_type": 1, "incentive_description": 1, "discount_pct": 1, "rent_free_days": 1}),
    Dim("dim_weather", "weather_key", ["city", "weather_date"], story="US-6.4", staging=["stg_weather"],
        source="""
        SELECT w.city, w.weather_date, coalesce(w.rainfall_mm, 0) AS rainfall_mm,
               CASE WHEN w.rainfall_mm IS NULL THEN 'Unknown' WHEN w.rainfall_mm < 1 THEN 'None'
                    WHEN w.rainfall_mm <= 10 THEN 'Light' ELSE 'Heavy' END AS rain_band,
               coalesce(w.max_temp_c, 0) AS max_temp_c,
               CASE WHEN w.max_temp_c IS NULL THEN 'Unknown' WHEN w.max_temp_c < 35 THEN 'Mild'
                    WHEN w.max_temp_c <= 40 THEN 'Hot' ELSE 'Extreme' END AS heat_band,
               w.source_system
        FROM lue_staging.stg_weather w""",
        cols={"rainfall_mm": 1, "rain_band": 1, "max_temp_c": 1, "heat_band": 1}),
    Dim("dim_unit", "unit_key", ["unit_nk"], story="US-6.3", scd2=True, staging=["stg_unit", "stg_building"],
        source=f"""
        SELECT u.building_code || '-' || u.unit_no AS unit_nk, u.building_code, u.unit_no,
               coalesce(u.unit_type, 'Unknown') AS unit_type, coalesce(u.bedrooms, 0) AS bedrooms,
               coalesce(u.area_sqft, 0) AS area_sqft, coalesce(u.furnished, FALSE) AS furnished_flag,
               coalesce(u.floor_no, 0) AS floor_no, coalesce(b.building_name, 'Unknown') AS building_name,
               coalesce(b.building_class, '?') AS building_class, {age_band('b.year_built')} AS building_age_band,
               coalesce(b.locality, 'Unknown') AS locality, coalesce(b.city, 'Unknown') AS city,
               coalesce(b.region, 'Unknown') AS region, u.source_system
        FROM lue_staging.stg_unit u LEFT JOIN lue_staging.stg_building b USING (building_code)""",
        history=UNIT_HISTORY,
        cols={"building_code": 0, "unit_no": 0, "unit_type": 2, "bedrooms": 1, "area_sqft": 1,
              "furnished_flag": 2, "floor_no": 0, "building_name": 1, "building_class": 1,
              "building_age_band": 1, "locality": 1, "city": 1, "region": 1}),
    Dim("dim_tenant", "tenant_key", ["tenant_code"], story="US-6.1", scd2=True, inferred=True,
        staging=["stg_tenant"],
        source="""
        SELECT t.tenant_code,
               coalesce(t.tenant_name, 'Unknown') AS tenant_name,
               coalesce(t.tenant_type, 'Unknown') AS tenant_type,
               coalesce(t.employer_sector, 'Unknown') AS employer_sector,
               coalesce(t.contact_channel, 'Unknown') AS contact_channel,
               t.source_system
        FROM lue_staging.stg_tenant t""",
        history=TENANT_HISTORY,
        references="""
        SELECT tenant_code FROM lue_staging.stg_lease WHERE tenant_code IS NOT NULL
        UNION SELECT tenant_code FROM lue_staging.stg_payment WHERE tenant_code IS NOT NULL""",
        cols={"tenant_name": 1, "tenant_type": 2, "employer_sector": 2, "contact_channel": 1}),
    Dim("dim_lease", "lease_key", ["lease_number"], story="US-6.4", staging=["stg_lease"],
        depends=["dim_unit", "dim_tenant"],
        source="""
        SELECT l.lease_number, coalesce(l.lease_type, 'Unknown') AS lease_type, l.start_date, l.end_date,
               coalesce(l.term_months, 0) AS term_months, coalesce(l.monthly_rent, 0) AS original_monthly_rent,
               coalesce(l.rent_review_type, 'Unknown') AS rent_review_type, l.previous_lease_number,
               l.source_system
        FROM lue_staging.stg_lease l""",
        cols={"lease_type": 0, "start_date": 0, "end_date": 0, "term_months": 0, "original_monthly_rent": 0,
              "rent_review_type": 0, "previous_lease_number": 0}),
]  # fmt: skip
BY_NAME = {d.name: d for d in DIMS}

# The calendar's holiday flags from the S2 register (US-6.4): every date of dim_date, the register
# is a full snapshot (a date it no longer lists goes back to FALSE / NULL).
HOLIDAYS = """
    UPDATE lue_dw.dim_date d
    SET is_public_holiday = coalesce(h.is_public_holiday, FALSE), holiday_name = h.holiday_name,
        is_ramadan = coalesce(h.is_ramadan, FALSE)
    FROM lue_dw.dim_date x LEFT JOIN lue_staging.stg_holiday h ON h.holiday_date = x.full_date
    WHERE d.date_key = x.date_key AND x.date_key > 0
      AND (d.is_public_holiday, d.holiday_name, d.is_ramadan) IS DISTINCT FROM
          (coalesce(h.is_public_holiday, FALSE), h.holiday_name, coalesce(h.is_ramadan, FALSE))"""
