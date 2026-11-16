#!/usr/bin/env python3
"""E3 checks that need no database (run by CI in make gen-test).

    python scripts/test_ingest_contract.py

1. The contract between the generator and the ingestion: for every source, the columns the
   generator writes (a fresh small generation in a temporary folder) are the columns the
   ingestor expects and the bronze table has (sql/20_staging/01_bronze.sql, parsed with pglast).
2. The text rules: how a value is written for COPY (missing vs empty), how a cell or JSON value
   becomes text, the row hash, and the structure-drift messages.
"""

import csv
import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402
from etl.ingest import base, files, json_weather, s1_pms  # noqa: E402

results: list[bool] = []
META = ["batch_id", "source_system", "loaded_at"]


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def bronze_tables() -> dict[str, list[str]]:
    from pglast import ast, parse_sql

    text = (ROOT / "sql" / "20_staging" / "01_bronze.sql").read_text(encoding="utf-8")
    out = {}
    for raw in parse_sql(text):
        stmt = raw.stmt
        if isinstance(stmt, ast.CreateStmt):
            assert stmt.relation.schemaname == "lue_staging"
            out[stmt.relation.relname] = [
                e.colname for e in stmt.tableElts if isinstance(e, ast.ColumnDef)
            ]
    return out


def load_model():
    import importlib.util

    spec = importlib.util.spec_from_file_location("m", ROOT / "docs/phase1/tools/model.py")
    module = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
    return module


def main() -> int:
    print("=" * 70)
    print(" E3 contract tests (no database): generator -> ingestors -> bronze DDL")
    print("=" * 70)
    brz = bronze_tables()
    erd = load_model().SOURCE_ERD
    print("Bronze DDL")
    check(len(brz) == 20 and all(n.startswith("brz_") for n in brz),
          "sql/20_staging/01_bronze.sql creates 20 lue_staging.brz_* tables")  # fmt: skip
    check(all(any(cols[i:i + 3] == META for i in range(len(cols))) for cols in brz.values()),
          "every bronze table has batch_id, source_system and loaded_at")  # fmt: skip

    print("S1: src_pms (frozen source ERD) -> bronze")
    ok = all(
        brz[t] == [c[1] for c in erd[src]] + META + ["row_hash", "row_id"]
        for src, t in s1_pms.TABLES.items()
    )
    check(ok, "the 9 S1 bronze tables have the source columns in order, then the metadata")
    check(set(erd) - set(s1_pms.TABLES) == {"charge_types", "payment_methods"},
          "only the two reference tables are not extracted (their dimensions come from US-1.4)")

    with tempfile.TemporaryDirectory(prefix="lue_contract_") as tmp:
        out = Path(tmp)
        gd.run(cfg.get_profile("small"), cfg.DEFAULT_SEED, out)
        print("Files written by the generator -> the ingestors' expected columns -> bronze")
        tail = META + ["source_file", "source_row", "row_id"]
        import openpyxl

        book = openpyxl.load_workbook(out / "s2" / "registers.xlsx", read_only=True)
        sheets_ok = all(
            sheet in book.sheetnames
            and list(next(book[sheet].iter_rows(max_row=1, values_only=True))) == cols
            and brz[target] == cols + tail
            for sheet, (target, cols) in files.S2_SHEETS.items()
        )
        book.close()
        check(sheets_ok, "S2: the 5 sheets' headers = the ingestor's columns = bronze")
        heads = {tuple(next(csv.reader(p.open(encoding="utf-8"))))
                 for p in (out / "s3").glob("settlement_*.csv")}  # fmt: skip
        check(heads == {tuple(files.S3_COLUMNS)} and brz["brz_settlement"] == files.S3_COLUMNS
              + tail, f"S3: all {len(list((out / 's3').glob('*.csv')))} settlement files have "
              "the expected header, as bronze")  # fmt: skip
        check(all(
            next(csv.reader((out / "s6" / f).open(encoding="utf-8"))) == cols
            and brz[t] == cols + tail for f, (t, cols) in files.S6_FILES.items()),
            "S6: offers.csv and incentive_log.csv headers = expected = bronze")  # fmt: skip
        export = json.loads((out / "s4" / "tickets.json").read_text(encoding="utf-8"))
        check(json_weather.ticket_structure(export) == json_weather.TICKET_KEYS
              and brz["brz_ticket"] == json_weather.TICKET_COLUMNS + tail
              and brz["brz_ticket_status"] == json_weather.STATUS_COLUMNS + tail,
              "S4: every generated ticket has the expected keys; both bronze tables match")
        cache = json.loads((ROOT / "data" / "weather_cache.json").read_text(encoding="utf-8"))
        check(all(set(json_weather.WEATHER_DAILY) <= set(c["daily"]) for c in cache["cities"])
              and brz["brz_weather"] == json_weather.WEATHER_COLUMNS + tail,
              "S5: the committed cache has the expected arrays; bronze matches")  # fmt: skip
        check(json_weather.ticket_structure({"tickets": [{"ticket_id": "x"}]})
              != json_weather.TICKET_KEYS and json_weather.ticket_structure([])
              != json_weather.TICKET_KEYS, "S4: a ticket with other keys is seen as drift")

    print("Text rules")
    check(base.copy_text(None) == "\\N" and base.copy_text("") == '""',
          "COPY: a missing value is NULL, an empty text stays an empty text")  # fmt: skip
    check(base.copy_text('say "hi", ok\nnext') == '"say ""hi"", ok\nnext"',
          "COPY: quotes, commas and line breaks survive")  # fmt: skip
    check(base.copy_text("\\N") == '"\\N"', "COPY: the text \\N itself is not mistaken for NULL")
    check([files.as_text(v) for v in (None, True, False, 0, 4850, "Rs. 8,300",
           date(2024, 1, 5), datetime(2024, 1, 5), datetime(2024, 1, 5, 9, 30))]
          == [None, "true", "false", "0", "4850", "Rs. 8,300", "2024-01-05", "2024-01-05",
              "2024-01-05 09:30:00"],
          "cells and JSON values become the text they show (dates ISO, booleans true/false)")
    check(s1_pms.row_hash(["a", None]) != s1_pms.row_hash(["a", ""])
          and s1_pms.row_hash(["ab", "c"]) != s1_pms.row_hash(["a", "bc"])
          and len(s1_pms.row_hash(["x"])) == 32,
          "row hash: NULL differs from '', value boundaries count, 32 hex characters")
    msg = files.drift(["a", "b", "c"], ["a", "B", "c"])
    check(files.drift(["a", "b"], ["a", "b"]) == ""
          and "missing 'b'" in msg and "unexpected 'B'" in msg
          and "different order" in files.drift(["a", "b"], ["b", "a"]),
          "drift: matching columns pass; a renamed column is named in the message")
    check(files.relative_name(ROOT / "data" / "s3" / "x.csv", ROOT / "data") == "s3/x.csv",
          "files are recorded by their name inside the data folder")

    print("=" * 70)
    ok = results and all(results)
    print(f" RESULT: {sum(results)}/{len(results)} checks passed" + ("" if ok else " - FAILED"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
