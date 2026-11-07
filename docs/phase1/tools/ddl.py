"""Generate the PostgreSQL physical model (DDL) from model.py."""
import re
from model import DIMENSIONS, FACTS, AUDIT, PROJECT, VERSION, SCHEMA_DW, SCHEMA_AUDIT

SPECIAL = {-1: "Unknown", -2: "Not applicable"}
NO_SPECIAL = {"dim_request_flags"}


def special_value(c, member, tname):
    t = c["type"].upper()
    name = c["name"]
    if c["key"] == "PK":
        return str(member)
    if name == "effective_from":
        return "'1900-01-01'"
    if name == "effective_to":
        return "'9999-12-31'"
    if name == "is_current":
        return "TRUE"
    if name in ("source_system",):
        return "'ETL'"
    if name == "batch_id":
        return "0"
    if name == "loaded_at":
        return "'1900-01-01 00:00:00'"
    if name in ("full_date", "weather_date"):
        return "'1900-01-01'" if member == -1 else "'1900-01-02'"
    if t.startswith("DATE"):
        return "'1900-01-01'"
    if t.startswith("BOOLEAN"):
        return "FALSE"
    if t.startswith(("INT", "SMALLINT", "BIGINT", "NUMERIC")):
        return "0"
    if t.startswith("CHAR"):
        return "'?'"
    m = re.search(r"\((\d+)\)", t)
    n = int(m.group(1)) if m else 20
    word = SPECIAL[member] if n >= len(SPECIAL[member]) else ("UNK" if member == -1 else "N/A")
    return "'" + word[:n] + "'"


def nk_columns(t):
    nk = t["nk"]
    if t["name"] == "dim_unit":
        return ["unit_nk"]
    if t["name"] == "dim_weather":
        return ["city", "weather_date"]
    if t["name"] == "dim_request_flags":
        return ["is_emergency", "is_recurring", "is_tenant_caused"]
    return [nk.split()[0]]


def table_ddl(t, schema=SCHEMA_DW, is_fact=False):
    lines = []
    pk_cols = [c["name"] for c in t["cols"] if "PK" in c["key"]]
    for c in t["cols"]:
        null = "" if c["null"] else " NOT NULL"
        lines.append(f"    {c['name']:<26} {c['type']}{null}")
    lines.append(f"    , CONSTRAINT pk_{t['name']} PRIMARY KEY ({', '.join(pk_cols)})")
    for c in t["cols"]:
        if c["ref"] and c["ref"].startswith("dim_"):
            target = [x for x in DIMENSIONS if x["name"] == c["ref"]][0]
            tpk = [x["name"] for x in target["cols"] if x["key"] == "PK"][0]
            lines.append(f"    , CONSTRAINT fk_{t['name'][:20]}_{c['name'][:-4]} FOREIGN KEY ({c['name']}) "
                         f"REFERENCES {schema}.{c['ref']} ({tpk})")
    if not is_fact:
        scd2 = any(c["name"] == "effective_from" for c in t["cols"])
        nks = nk_columns(t)
        if scd2:
            lines.append(f"    , CONSTRAINT uq_{t['name']}_version UNIQUE ({', '.join(nks)}, effective_from)")
        else:
            lines.append(f"    , CONSTRAINT uq_{t['name']}_nk UNIQUE ({', '.join(nks)})")
    if t["name"] == "fact_rent_invoice_line":
        lines.append("    , CONSTRAINT uq_invoice_line UNIQUE (invoice_number, invoice_line_no)")
        lines.append("    , CONSTRAINT ck_net_amount CHECK (net_amount = billed_amount + tax_amount - discount_amount)")
    if t["name"] == "dim_lease":
        lines.append("    , CONSTRAINT ck_lease_dates CHECK (key_is_special(lease_key) OR end_date > start_date)")
    if t["name"] == "fact_lease_event":
        lines.append("    , CONSTRAINT ck_event_count CHECK (event_count = 1)")
    body = ",\n".join(l.replace("    , ", "    ", 1) if l.startswith("    , ") else l for l in lines)
    part = ""
    if t["name"] == "fact_unit_occupancy_daily":
        part = " PARTITION BY RANGE (snapshot_date_key)"
    return f"CREATE TABLE {schema}.{t['name']} (\n{body}\n){part};"


def build():
    out = [f"-- {PROJECT} · physical model (PostgreSQL 16+)",
           f"-- {VERSION}. Generated from the same model as the data dictionary and diagrams.",
           "-- Run in psql: \\i physical_model.sql",
           "",
           f"DROP SCHEMA IF EXISTS {SCHEMA_DW} CASCADE;",
           f"DROP SCHEMA IF EXISTS {SCHEMA_AUDIT} CASCADE;",
           f"CREATE SCHEMA {SCHEMA_DW};",
           f"CREATE SCHEMA {SCHEMA_AUDIT};",
           "",
           "-- helper used by a CHECK constraint so special members (-1, -2) pass",
           "CREATE OR REPLACE FUNCTION key_is_special(k INT) RETURNS BOOLEAN",
           "LANGUAGE sql IMMUTABLE AS $$ SELECT k < 0 $$;",
           "",
           "-- ============================== DIMENSIONS =============================="]
    for d in DIMENSIONS:
        out += ["", f"-- {d['name']}: {d['grain']}", table_ddl(d)]
        if d["name"] not in NO_SPECIAL:
            for m in (-1, -2):
                cols = [c["name"] for c in d["cols"]]
                vals = [special_value(c, m, d["name"]) for c in d["cols"]]
                out.append(f"INSERT INTO {SCHEMA_DW}.{d['name']} ({', '.join(cols)})\n  VALUES ({', '.join(vals)});")
    out += ["", "-- ================================ FACTS ================================="]
    for f in FACTS:
        out += ["", f"-- {f['name']} ({f['type']}): {f['grain']}", table_ddl(f, is_fact=True)]
        if f["name"] == "fact_unit_occupancy_daily":
            out.append("-- one partition per month, Jul 2023 – Jun 2027")
            y, m = 2023, 7
            while (y, m) < (2027, 7):
                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                out.append(f"CREATE TABLE {SCHEMA_DW}.fact_unit_occupancy_daily_{y}_{m:02d} PARTITION OF {SCHEMA_DW}.fact_unit_occupancy_daily "
                           f"FOR VALUES FROM ({y}{m:02d}01) TO ({ny}{nm:02d}01);")
                y, m = ny, nm
        for c in f["cols"]:
            if c["ref"] and c["ref"].startswith("dim_") and "PK" not in c["key"]:
                out.append(f"CREATE INDEX ix_{f['name'][:22]}_{c['name'][:-4]} ON {SCHEMA_DW}.{f['name']} ({c['name']});")
        if f["name"] == "fact_unit_occupancy_daily":
            out.append(f"CREATE INDEX ix_occupancy_unit_date ON {SCHEMA_DW}.fact_unit_occupancy_daily (unit_key, snapshot_date_key);")
        if f["name"] == "fact_maintenance_request":
            out.append(f"CREATE INDEX ix_maint_open ON {SCHEMA_DW}.fact_maintenance_request (raised_date_key) "
                       "WHERE resolved_date_key = -2;")
    out += ["", "-- ================================ AUDIT ================================="]
    for a in AUDIT:
        sch, name = a["name"].split(".")
        lines = []
        pk_cols = [c["name"] for c in a["cols"] if "PK" in c["key"]]
        for c in a["cols"]:
            lines.append(f"    {c['name']:<20} {c['type']}{'' if c['null'] else ' NOT NULL'}")
        lines.append(f"    CONSTRAINT pk_{name} PRIMARY KEY ({', '.join(pk_cols)})")
        out += ["", f"-- {a['name']}: {a['grain']}",
                f"CREATE TABLE {a['name']} (\n" + ",\n".join(lines) + "\n);"]
    out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    open(sys.argv[1], "w").write(build())
