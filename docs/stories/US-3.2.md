# US-3.2 Ingest S1 from the source database

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-16 |
| Branch and pull request | `e3-ingestion` |
| Evidence | [`../evidence/us-3.2/`](../evidence/us-3.2/) |

## Story

As a data engineer, I want S1 extracted incrementally, so that reruns only move new or changed rows.

## What was done

`etl/ingest/s1_pms.py`, step `ingest_s1_pms`. For each of nine `src_pms` tables a server-side cursor on `lue_source`
streams the rows (every value cast to text) in chunks of 10,000 into `COPY` on `lue_warehouse` (two connections).
Each row's MD5 (`row_hash`) is compared with the hashes bronze already has; only new or changed rows land, as a new
version. Bronze tables: `brz_building`, `brz_unit`, `brz_tenant`, `brz_lease`, `brz_lease_event`, `brz_invoice`,
`brz_invoice_line`, `brz_payment`, `brz_payment_allocation`. After each table, a reconciliation row: every row the
source has now is in bronze.

## Decisions and deviations

- **Change detection by row hash, not by `updated_at` alone.** Only `units` and `tenants` have `updated_at`, so a
  watermark cannot see changes to leases, invoices or payments. And a change can carry an `updated_at` older than the
  newest one loaded (the US-2.6 tenant changes in `s1/changes/` are dated inside the window), which a watermark would
  miss. The test proves both. The source is read in full each run (392,000 rows on the full profile: about 4 s).
- **The watermark is still kept** (`lue_audit.etl_watermark`, decision O5) for `units` and `tenants`: the newest
  `updated_at` loaded, only moved forward, only after a successful load. A failed run moves nothing.
- **`brz_building` added** (the plan's list has no buildings, but `dim_unit` needs the city and class).
  `charge_types` and `payment_methods` are not extracted: their dimensions come from `etl/reference_data.py` (US-1.4).
- **Deleted source rows stay in bronze** (append-only); S1 never deletes.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| The first run loads everything | Pass: 391,870 rows, each table equal to its source, value for value | `01_s1_tests.txt`, `02_run_counts.txt` |
| An immediate second run loads zero rows | Pass: 391,870 read, 0 landed | `01_`, `02_` |
| Updating one source row lands exactly one row on the next run | Pass: 1 row, the new version; putting it back lands 0 | `01_`, `02_` |

## How to re-check it

    python scripts/db_load_source.py
    python etl/ingest/run.py --only S1   # twice: the second lands 0
