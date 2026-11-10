# US-1.4 Load the date dimension and static reference dimensions

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha |
| Done on | 2026-11-10 |
| Branch and pull request | `e1-1.4-reference-dims` |
| Evidence | [`../evidence/us-1.4/`](../evidence/us-1.4/) |

## Story

As an analyst, I want a complete calendar and the small static dimensions loaded up front, so that every fact can
resolve its date and code keys.

## What was done

1. `sql/30_dimensions/01_reference_dimensions.sql` loads, in one run:
   - `dim_date`: 1,461 days, 2023-07-01 to 2027-06-30, with `generate_series`. `date_key` is YYYYMMDD. Day and month
     names come from arrays, so the result does not depend on the server's language. Fiscal year runs July to June
     (`FY2025-26`). Holiday and Ramadan flags start FALSE (filled in US-6.4).
   - `dim_payment_method` (6), `dim_charge_type` (6), `dim_lease_event_type` (4) and `dim_request_flags` (8, every
     combination of the three flags).
2. `scripts/db_load_reference.py` runs that file as `lue_etl` in one transaction (same pattern as `db_deploy.py`).
3. `etl/reference_data.py` holds the same static members for the data generator (S1 must use the same codes).
4. `scripts/test_reference.py`: 32 acceptance checks, including a comparison with `etl/reference_data.py`.
5. `scripts/test_dimensions.py` changed: its "all identity sequences are unused" check assumed every dimension was
   empty. It now checks the still-empty ones, and checks that the loaded ones started at key 1.
6. `Makefile` target `db-load-ref`; `make db-test` also runs `test_reference.py`. README section "Reference data".

## Files added or changed

- Added: `sql/30_dimensions/01_reference_dimensions.sql`, `scripts/db_load_reference.py`,
  `scripts/test_reference.py`, `etl/reference_data.py`, `etl/__init__.py`
- Changed: `scripts/test_dimensions.py`, `Makefile`, `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **Six charge types, not four.** The plan lists rent, service charge, late fee and utility. The frozen Phase 1 pack
  (dictionary and `tools/model.py`) has 6 rows and the invoice grain mentions credit notes, so `Credit note` and
  `Deposit adjustment` are added. The pack wins (plan A1: "do not redesign").
- **Channel groups follow the pack:** Cash, Cheque, Bank, Instant payment, Mobile wallet (5 groups).
- **Typical settlement days are our assumption** (the pack only gives JazzCash = 1): cash 0, cheque 3, bank transfer 1,
  Raast 0, JazzCash 1, Easypaisa 1. US-2.4 generates settlement lags around these values.
- **Codes** (`CASH`, `CHEQUE`, `BANK`, `RAAST`, `JAZZ`, `EASY`; `RENT`, `SERVICE`, `LATEFEE`, `UTILITY`, `CREDIT`,
  `DEPADJ`; `SIGN`, `RENEW`, `NOTICE`, `TERM`) are the business keys; S1 must use them too.
- **`dim_request_flags` has no Unknown member**, as already recorded in US-1.2 (plan US-1.4 says "plus the Unknown
  member"; it cannot fit three NOT NULL flags).
- **The load lives in `sql/30_dimensions/`, not `sql/10_ddl/`,** because `scripts/check_contract.py` compares
  `10_ddl` row for row with the pack and `db_deploy.py` runs everything in it.
- Static rows use source system `SEED`, batch 0.
- Re-run: existing static members are corrected in place (Type 1), missing ones are added, and no key numbers are
  burned, so a second run changes nothing. Existing `dim_date` rows are never overwritten, so the US-6.4 holiday flags
  survive a re-run.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| `dim_date` has 1,461 date rows plus special members; no gaps | Pass | `03_acceptance_tests.txt`, "dim_date" |
| Fiscal periods correct at the July boundary (30 June 2026 and 1 July 2026 in different fiscal years) | Pass | `03_acceptance_tests.txt`, "fiscal year changes at 1 July" |
| Static dimensions contain exactly the agreed members | Pass | `03_acceptance_tests.txt`, "Static reference dimensions" |

## How to re-check it

    python scripts/db_deploy.py
    python scripts/db_load_reference.py
    python scripts/test_reference.py   # expect "RESULT: 32/32 checks passed"

## Open items and follow-ups

- US-6.4 fills `dim_date.is_public_holiday`, `holiday_name` and `is_ramadan` from the S2 holiday register.
- Settlement days above are an assumption; change `etl/reference_data.py` and the SQL together if the team decides
  otherwise (`test_reference.py` catches a mismatch).
