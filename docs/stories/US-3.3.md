# US-3.3 Ingest the Excel and CSV sources (S2, S3, S6)

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-16 |
| Branch and pull request | `e3-ingestion` |
| Evidence | [`../evidence/us-3.3/`](../evidence/us-3.3/) |

## Story

As a data engineer, I want the file-based sources landed with their file identity recorded and reruns made safe, so
that every row is traceable and nothing is duplicated.

## What was done

`etl/ingest/files.py`:

1. **S2:** `s2/registers.xlsx` sheet by sheet with openpyxl into `brz_owner`, `brz_ownership`, `brz_vendor`,
   `brz_sla_policy` and `brz_holiday`.
2. **S3 and S6** with pandas, every column as text: `brz_settlement` (all 3,989 settlement files),
   `brz_incentive_offer`, `brz_incentive_log`. Every row keeps `source_file` and `source_row`.
3. **Structure check before load:** a renamed, missing or extra column rejects the file, and the message names the
   column (`structure changed: missing 'rent_free_days'; unexpected 'free_days'`). The other files still load; the
   step ends as `Warning`.
4. **Checksum policy (D16):** each file's SHA-256. A checksum already `Loaded` into the same table is skipped
   (`Skipped`, "unchanged"). A new or edited file lands as a new batch; bronze is appended to, never truncated.
5. **The file register** `lue_audit.file_load`: one row per file and table per attempt (file, checksum, rows, batch,
   status `Loaded`, `Skipped` or `Rejected`, message).

## Decisions and deviations

- **`lue_audit.file_load` instead of `lineage` for the files.** The pack's `lineage` table is one row per target and
  source table and has no place for a file, a checksum or a batch; it keeps that meaning (one row per bronze table).
  `file_load` is a Phase 2 addition like `etl_watermark`, allowed in `scripts/check_contract.py`.
- **A rejection is recorded on the autocommit connection**, so it survives if the step later fails.
- **The skip goes by checksum, as D16 says**, so a file with the same bytes as one already loaded is skipped under any
  name. On the full profile 5 settlement files are empty (their lines moved by the late-settlement defect of US-2.6)
  and identical; the register says `same content as <file>` (nothing would land either way).
- **An edited workbook lands all its sheets again** as a new batch (the file's checksum changed); staging keeps the
  latest batch (E5).
- **Empty cells stay empty texts**; DQ-01 (E4) must treat `''` as missing.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A file with a renamed column is rejected before load | Pass: S6 and an S2 sheet, with the column named | `01_file_tests.txt`, `03_drift_rejection.txt` |
| Unchanged files land zero rows; an edited file lands exactly its rows as a new batch | Pass: 0 rows, all `Skipped`; the edited file's rows as a second batch | `01_`, `02_file_load_register.txt` |
| One register entry per file load, with a checksum | Pass: 3,996 rows per run on the full profile | `02_` |

## How to re-check it

    python etl/ingest/run.py --only S2,S3,S6   # twice: the second lands 0, all Skipped
