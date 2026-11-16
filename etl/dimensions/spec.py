"""US-6.1: the dimensions as data, in load order. One loader (etl/dimensions/load.py) reads this.

Per dimension: its table in lue_dw, surrogate key, natural key, the SQL that gives one row per
natural key from the staging contract (docs/contracts/staging.md), and each column with its SCD
type from the Phase 1 data dictionary (docs/phase1, model.py):
  0  identity: written when the member is created, never changed
  1  overwrite in place, on every version of the member (corrections, current value only)
  2  history: a change makes a new version (US-6.2, US-6.3); until then written at creation only

Load order (plan US-6.1 step 3): independent dimensions first, then unit, tenant and lease:
  static   dim_date, dim_payment_method, dim_charge_type, dim_lease_event_type, dim_request_flags
           (US-1.4, sql/30_dimensions/01_reference_dimensions.sql; checked here, not reloaded)
  then     the dimensions of DIMS below, in list order.
Facts (E7) load only after every dimension.
"""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from dataclasses import dataclass, field

# static dimension -> its rows besides the special members -1 and -2 (US-1.4)
STATIC = {"dim_date": 1461, "dim_payment_method": 6, "dim_charge_type": 6, "dim_lease_event_type": 4,
          "dim_request_flags": 8}  # fmt: skip
STATIC_KEY = {"dim_date": "date_key", "dim_payment_method": "payment_method_key",
              "dim_charge_type": "charge_type_key", "dim_lease_event_type": "lease_event_type_key",
              "dim_request_flags": "request_flags_key"}  # fmt: skip
FIRST_DAY = "1900-01-01"  # effective_from of a member's first version: valid for any fact date
OPEN_END = "9999-12-31"  # effective_to of the current version


@dataclass
class Dim:
    name: str
    key: str  # surrogate key column (identity)
    nk: list[str]  # natural key columns
    source: str  # SQL giving one row per natural key, with every column of cols (and source_system)
    cols: dict[str, int]  # column -> SCD type (0, 1, 2), excluding key, nk and technical columns
    story: str  # the story that loads it
    staging: list[str] = field(default_factory=list)  # staging tables read (lineage)
    scd2: bool = False  # has effective_from, effective_to, is_current
    inferred: bool = False  # has is_inferred (US-6.5)
    depends: list[str] = field(default_factory=list)  # dimensions that must be loaded first

    @property
    def type1(self) -> list[str]:
        return [c for c, t in self.cols.items() if t == 1]

    @property
    def type2(self) -> list[str]:
        return [c for c, t in self.cols.items() if t == 2]


DIMS = [
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
        cols={"tenant_name": 1, "tenant_type": 2, "employer_sector": 2, "contact_channel": 1}),
]  # fmt: skip
BY_NAME = {d.name: d for d in DIMS}
