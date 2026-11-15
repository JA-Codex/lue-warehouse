# US-2.3 Generate leases, lease events and invoices

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar |
| Done on | 2026-11-15 |
| Branch and pull request | `e2-2.3-leases-invoices` |
| Evidence | [`../evidence/us-2.3/`](../evidence/us-2.3/) |

## Story

As a data engineer, I want a realistic lease lifecycle with monthly invoicing, so that occupancy, invoicing and lease
event facts have consistent history.

## What was done

1. `etl/gen_leases.py`, stage `leases_invoices`. It rebuilds the master data (a pure function of the seed, as in
   US-2.2) and simulates the portfolio in four phases, each with its own seeded stream:
   unit timelines (leases, renewals, vacancy gaps), tenant assignment, lease events, invoices and lines.
2. Outputs: `s1/leases.csv`, `s1/lease_events.csv`, `s1/invoices.csv`, `s1/invoice_lines.csv`, with exactly the
   columns of the Phase 1 source ERD.
3. `sql/05_source/02_src_pms_leases.sql` creates the four `src_pms` tables (primary keys only) and
   `scripts/db_load_source.py` loads them with the master tables, still in one transaction.
4. Tests: `scripts/test_leases.py` (114 checks, no database) and 12 new checks in `scripts/test_source_load.py`
   (54 in total, database). `make gen-test` and `make db-test` run them.
5. `etl/gen_leases.build_billing(profile, master, rng_for)` returns the same data as Python objects, so US-2.4 can
   rebuild leases and invoices instead of reading the CSV files.

## What the data looks like (full profile, seed 3004)

| | |
|---|---|
| Leases | 5,770 (3,743 first leases of a chain, 2,027 renewals) |
| Active leases | 1,500 when the window opens, 1,486 on average (target 1,500) |
| Invoices / invoice lines | 53,482 / 126,596 (target about 130,000; 2.4 lines per invoice) |
| Lease events | 8,826: 2,243 SIGN, 2,027 RENEW, 2,278 NOTICE, 2,278 TERM |
| Renewal rate | 47% of resolved leases renew |
| Seasonality | June to August move-ins run at 1.6 times the other months |
| Runtime | 1.6 s (full), 0.1 s (small) |

Small profile: 86 leases, 212 invoices, 497 lines (target 530).

## Files added or changed

- Added: `etl/gen_leases.py`, `scripts/test_leases.py`, `sql/05_source/02_src_pms_leases.sql`, `docs/evidence/us-2.3/`
- Changed: `etl/generate_data.py` (imports the stage, version 2.3), `etl/generator_config.py` (small-profile
  invoice-line target), `scripts/db_load_source.py`, `scripts/test_source_load.py`, `Makefile`, `README.md`,
  `docs/stories/README.md`

## Decisions and deviations

- **Opening leases are migrated leases and start before the window.** US-2.2's note says a lease must not start
  before its tenant exists, and tenants made before the window were all created in the go-live fortnight. Taken
  literally, 1,500 opening leases would all start in the last two weeks of June 2023, end together in May 2024 and
  renew in one wave, forever. Instead each opening lease has a start date before the window (a uniform point of its
  term has passed) and the tenant record dates from the migration. What does hold, and is tested: every lease that
  starts inside the window starts on or after its tenant's record, and **no invoice and no lease event is dated
  before its tenant's record**. That is the invariant the "invoice before the tenant" defect (US-2.6) needs.
- **Rent is constant inside a lease and changes only at renewal.** Plan step 3 mentions "mid-lease rent changes" and
  US-2.6 lists the same thing as a defect (`mid_lease_rent_change`, 2%). I put them in US-2.6, where the answer key
  can record them, so the clean data satisfies the acceptance rule exactly: rent billed equals monthly rent times the
  months billed, for every lease, with no exception.
- **`rent_review_type` describes the renewal.** 'Annual escalation' is a 12-month commercial lease whose contract
  sets a 5 to 10 percent uplift at renewal; 'Fixed' is everything else (the renewal rent is negotiated).
- **A termination is a tenant who does not renew at the end of the term.** There are no early terminations, so
  `end_date` is always the real last day and occupancy (US-7.3) is simply start to end. Easy to add later.
- **Leases start on the 1st and end on a month end.** Invoices are issued on the 1st, due on the 10th, so every
  lease-month has exactly one invoice and the reconciliation is exact.
- **Resolution stops at the window end.** A lease that ends on or after 2026-06-30 is Active and has no NOTICE,
  RENEW or TERM. Otherwise the last months would show notices without the matching renewals.
- **Invoice numbers are `INV-2026-03-0831` (16 characters).** The dictionary's example `INV-2026-03-00831` has 17
  characters and does not fit its own `VARCHAR(16)`, so the lease sequence is 4 digits. The generator refuses more
  than 9,999 leases.
- **Tax:** 16 percent on commercial rent and commercial service charge, none elsewhere. It is synthetic. It gives
  `tax_amount` real values; remove it if the team prefers an all-zero column.
- **`discount_amount` is 0, `invoices.status` is `Issued`.** Incentives belong to US-2.5 and US-2.6; US-2.4 settles
  the invoices and may set Paid, Partial or Overdue. Charge types LATEFEE, CREDIT and DEPADJ are not used yet.
- **Corporate tenants can hold up to 4 leases at once** (about 12% of tenants). Individuals never overlap.
- **About 12% of tenant records never get a lease** (applicants). The small profile has more (38%) because three
  months cannot use 120 tenants.
- **Small-profile line target changed from 650 to 530.** US-2.1 flagged it as a scaled guess to revisit; the real
  ratio is 2.4 lines per lease-month.
- **New content hash:** `--profile small --seed 3004` is now `a9cac42a...ec811db`. The US-2.1 and US-2.2 files are
  byte-identical to before (`7e1030ea...ffbf7089` without this stage).
- **Stage order in the manifest can differ.** `leases_invoices` rebuilds its own master data, so it does not depend
  on `master_data` running first. If a test imports `etl.gen_master` before `etl.generate_data`, the manifest lists
  the stages in the other order; the files and hash are the same.
- **Verified on PostgreSQL 16.2 with real psycopg2** (embedded server), not a stand-in. `test_dimensions.py` and
  `test_facts.py` could not run there because that build has no libxml; they are untouched by this story.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Zero overlapping leases per unit | Pass (generator test and SQL self-join: 0 pairs) | `02_`, `04_overlap_check_and_counts.txt` |
| Invoice totals equal lease rent times months active | Pass for every lease, in Python and SQL | `02_`, `03_database_tests.txt` |
| Seasonal move-in peaks visible | Pass: June to August 1.6x | `05_monthly_lease_starts.txt` |
| About 1,500 active leases | Pass: 1,500 at open, 1,486 average | `02_`, `04_` |
| About 130,000 invoice lines | Pass: 126,596 (-2.6%) | `02_acceptance_tests.txt` |
| Deterministic | Pass: same seed identical, other seed different | `01_hash_comparison.txt` |
| Tests can fail | Pass: 11 mutations caught | `06_tests_catch_broken_data.txt` |

## How to re-check it

    python scripts/test_leases.py                               # expect 114/114
    python scripts/test_generator.py                            # expect 39/39
    python scripts/test_master_data.py                          # expect 129/129
    make generate PROFILE=full && make db-load-source
    python scripts/test_source_load.py                          # expect 54/54

## Open items and follow-ups

- **US-2.4** can call `build_billing` to get leases and lines. It needs to decide invoice status.
- **US-2.6** plants the rent changes by editing later RENT lines of a lease (the clean totals make any change
  visible). "An incentive that shortens vacancy" needs the S6 log before the lease simulation, or a re-run of it;
  `simulate_unit` takes everything from the profile and the stream, so a vacancy multiplier is a small change.
  "Higher renewal churn in one city": edit `RENEWAL_BASE` in `etl/gen_leases.py`; the cities are within 2 points
  of each other now, so a planted gap will stand out.
- Tenants: 3,800 are used at 88%. The dictionary expects about 4,500 tenant versions; raise `tenants` if wanted.
