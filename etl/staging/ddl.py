#!/usr/bin/env python3
"""Write the staging DDL and contract from etl/staging/spec.py (US-5.1).

    python etl/staging/ddl.py            # rewrite the three files
    python etl/staging/ddl.py --check    # exit 1 if a file is not what the spec gives (CI)

  sql/20_staging/03_staging_functions.sql   clean_text, std, the vocabularies and lookups
  sql/20_staging/04_staging_tables.sql      the stg_ tables
  docs/contracts/staging.md                 the staging contract (E6 and E7 read it)
"""

# ruff: noqa: E501  (SQL text and the contract's sentences: long lines read better)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.staging import spec  # noqa: E402

FUNCTIONS = ROOT / "sql" / "20_staging" / "03_staging_functions.sql"
TABLES = ROOT / "sql" / "20_staging" / "04_staging_tables.sql"
CONTRACT = ROOT / "docs" / "contracts" / "staging.md"


def q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def key_of(value: str) -> str:
    """The match key of a value: lower case, trimmed, inner spaces collapsed (as clean_text)."""
    return " ".join(value.split()).lower()


def functions_sql() -> str:
    rows = []
    for domain, values in spec.VOCABULARY.items():
        for v in values:
            rows.append((domain, key_of(v), v))
    for (domain, variant), canonical in spec.VARIANTS.items():
        rows.append((domain, key_of(variant), canonical))
    vocab = ",\n".join(f"    ({q(d)}, {q(k)}, {q(c)})" for d, k, c in rows)
    cities = ",\n".join(f"    ({q(c)}, {q(spec.CITY_CODE[c])}, {q(r)})" for c, r in spec.REGION.items())
    methods = ",\n".join(
        f"    ({q(code)}, {q(name)}, {q(kind)}, {'TRUE' if electronic else 'FALSE'})"
        for code, (name, kind, electronic) in spec.PAYMENT_METHODS.items()
    )
    return f"""-- US-5.1: cleaning functions and vocabularies for staging. Written by etl/staging/ddl.py from
-- etl/staging/spec.py (do not edit by hand). Run as lue_etl by scripts/db_deploy.py. Safe to re-run:
-- the seeds use ON CONFLICT DO UPDATE, so a changed spelling in the spec reaches the database.
--
-- clean_text trims, collapses inner spaces and turns an empty text into NULL. It does not change
-- case: a blind Title Case would break values such as 'IT and Software', 'WhatsApp' or 'HVAC'.
-- Case and spelling are standardised by std(domain, value) through the vocabulary, which matches
-- ignoring case and spaces: std('city', ' lahore ') = std('city', 'LAHORE') = 'Lahore'. A value
-- that is not in the vocabulary gives NULL (counted in the cleaning evidence, US-5.4).
-- Dates and numbers use the safe casts of E4: lue_audit.try_date (YYYY-MM-DD or DD/MM/YYYY),
-- try_numeric and try_timestamp.

CREATE OR REPLACE FUNCTION lue_staging.clean_text(value text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT nullif(regexp_replace(regexp_replace(value, '^\\s+|\\s+$', '', 'g'), '\\s+', ' ', 'g'), '')
$$;

CREATE TABLE IF NOT EXISTS lue_staging.vocabulary (
    domain               VARCHAR(30) NOT NULL,
    variant_key          VARCHAR(80) NOT NULL,
    canonical            VARCHAR(80) NOT NULL,
    CONSTRAINT pk_vocabulary PRIMARY KEY (domain, variant_key)
);

INSERT INTO lue_staging.vocabulary (domain, variant_key, canonical) VALUES
{vocab}
ON CONFLICT (domain, variant_key) DO UPDATE SET canonical = EXCLUDED.canonical;

CREATE OR REPLACE FUNCTION lue_staging.std(domain text, value text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT v.canonical FROM lue_staging.vocabulary v
    WHERE v.domain = std.domain AND v.variant_key = lower(lue_staging.clean_text(std.value))
$$;

CREATE TABLE IF NOT EXISTS lue_staging.city (
    city                 VARCHAR(30) NOT NULL,
    city_code            CHAR(3) NOT NULL,
    region               VARCHAR(30) NOT NULL,
    CONSTRAINT pk_city PRIMARY KEY (city)
);

INSERT INTO lue_staging.city (city, city_code, region) VALUES
{cities}
ON CONFLICT (city) DO UPDATE SET city_code = EXCLUDED.city_code, region = EXCLUDED.region;

CREATE OR REPLACE FUNCTION lue_staging.region_of(city text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT c.region FROM lue_staging.city c WHERE c.city = region_of.city
$$;

CREATE OR REPLACE FUNCTION lue_staging.city_code(city text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT c.city_code FROM lue_staging.city c WHERE c.city = city_code.city
$$;

CREATE TABLE IF NOT EXISTS lue_staging.payment_method (
    method_code          VARCHAR(10) NOT NULL,
    method_name          VARCHAR(30) NOT NULL,
    method_type          VARCHAR(20) NOT NULL,
    is_electronic        BOOLEAN NOT NULL,
    CONSTRAINT pk_payment_method PRIMARY KEY (method_code)
);

INSERT INTO lue_staging.payment_method (method_code, method_name, method_type, is_electronic) VALUES
{methods}
ON CONFLICT (method_code) DO UPDATE SET method_name = EXCLUDED.method_name,
    method_type = EXCLUDED.method_type, is_electronic = EXCLUDED.is_electronic;
"""


def tables_sql() -> str:
    out = ["""-- US-5.1: the staging tables (lue_staging.stg_*), the clean contract the dimension and fact
-- loaders read (docs/contracts/staging.md). Written by etl/staging/ddl.py from etl/staging/spec.py
-- (do not edit by hand). Run as lue_etl by scripts/db_deploy.py. Safe to re-run.
-- One row per natural key (the primary key): the surviving version (D15). Typed and cleaned.
-- Lineage columns at the end name the bronze row that survived. Columns marked "derived" are
-- computed by etl/staging/business.py (US-5.2). No secondary indexes (D20)."""]
    for t in spec.TABLES:
        lines = []
        for c in t.cols:
            null = " NOT NULL" if c.name in t.key else ""
            mark = "  -- derived (US-5.2)" if c.derived else ""
            lines.append(f"    {c.name:<24} {c.type}{null},{mark}")
        for c in [*spec.LINEAGE, *t.extra_lineage]:
            lines.append(f"    {c.name:<24} {c.type},")
        lines.append(f"    CONSTRAINT pk_{t.name} PRIMARY KEY ({', '.join(t.key)})")
        out.append(f"-- {t.doc}\nCREATE TABLE IF NOT EXISTS lue_staging.{t.name} (\n"
                   + "\n".join(lines) + "\n);")  # fmt: skip
    return "\n\n".join(out) + "\n"


def contract_md() -> str:
    lines = [
        "# Staging contract (lue_staging.stg_*)",
        "",
        "Written by `etl/staging/ddl.py` from `etl/staging/spec.py` (US-5.1): do not edit by hand.",
        "The dimension (E6) and fact (E7) loaders read only these tables.",
        "",
        "## Rules for every table",
        "",
        "- **One row per natural key** (the primary key). The surviving bronze row is the latest by",
        "  the source's `updated_at` (where the source has one), then `loaded_at`, then `batch_id`,",
        "  then the row's position (decision D15).",
        "- **Only rows E4 did not reject** take part (`lue_audit.dq_result`), and only from bronze",
        "  batches E4 has validated (`lue_audit.dq_batch`); staging refuses to run otherwise.",
        "- **Values are cleaned and typed:** text trimmed with inner spaces collapsed and empty as",
        "  NULL (`clean_text`); codes in upper case; vocabulary values in one spelling (`std`, which",
        "  ignores case and spaces); dates `YYYY-MM-DD` or day-first `DD/MM/YYYY` (repaired); numbers",
        "  and timestamps by the safe casts of E4.",
        "- **Lineage on every row:** `source_system`, `batch_id`, `loaded_at` and `src_row_id` of the",
        "  surviving bronze row, `src_updated_at`, and `run_id` and `staged_at` of the last change.",
        "- **Incremental (US-5.3):** a run reads the bronze rows landed since the table's watermark",
        "  (`lue_audit.etl_watermark`, source_system `STG`) and merges by the key, changing a row only",
        "  when a value differs and never with an older version.",
        "- **Derived columns** (marked) are computed by US-5.2 after every load.",
        "",
        "## Vocabularies",
        "",
        "| Domain | Values |",
        "|---|---|",
    ]
    for d, values in spec.VOCABULARY.items():
        lines.append(f"| {d} | {', '.join(values)} |")
    lines += ["", "Other spellings accepted: " + ", ".join(
        f"{v} -> {c}" for (d, v), c in spec.VARIANTS.items()) + "."]
    lines += ["", "Regions: " + ", ".join(f"{c} {spec.CITY_CODE[c]} ({r})"
                                          for c, r in spec.REGION.items()) + "."]
    for t in spec.TABLES:
        lines += ["", f"## {t.name}", "", f"{t.doc} From `lue_staging.{t.bronze}` ({t.source_system}). "
                  f"Key: `{', '.join(t.key)}`."
                  + (" Survivorship uses the source's `updated_at`." if t.updated else ""), "",
                  "| Column | Type | Meaning | NULL |", "|---|---|---|---|"]  # fmt: skip
        for c in t.cols:
            mark = " (derived)" if c.derived else ""
            null = "key" if c.name in t.key else c.null
            lines.append(f"| `{c.name}` | {c.type} | {c.doc}{mark} | {null} |")
        for c in t.extra_lineage:
            lines.append(f"| `{c.name}` | {c.type} | {c.doc} (lineage) | |")
    return "\n".join(lines) + "\n"


def outputs() -> dict[Path, str]:
    return {FUNCTIONS: functions_sql(), TABLES: tables_sql(), CONTRACT: contract_md()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only check that the files are current")
    args = ap.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != text:
            stale.append(path)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
    for p in stale:
        print(("STALE   " if args.check else "written ") + p.relative_to(ROOT).as_posix())
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
