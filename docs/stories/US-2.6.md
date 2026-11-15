# US-2.6 Inject defects, plant business patterns and write the answer key

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-16 |
| Branch and pull request | `e2-2.6-defects-patterns` |
| Evidence | [`../evidence/us-2.6/`](../evidence/us-2.6/) |

## Story

As a tester, I want controlled defects and known business patterns recorded in an answer key, so that quality
checks and later insights can be proven correct.

## What was done

1. **Defects:** `etl/gen_defects.py`, stage `defects_answer_key`, the last stage. It reads back the clean files the
   earlier stages wrote, plants the 12 defect types of `DEFECT_RATES` (1 to 3 percent) and rewrites the files it
   changed. Table below.
2. **Answer key** in `answer_key/`: `defects_answer_key.csv` (one row per defect: source, table, record id, column,
   defect type, expected handling, expected rule, detail), `summary.csv` (count per type, source and table),
   `totals.csv` (count per type), `expectations.json` (the numbers later stories compare with) and the planted
   patterns (`planted_patterns.json` and `.md`).
3. **Patterns:** `etl/patterns.py` holds the six patterns' numbers and choices; `gen_leases`, `gen_payments` and
   `gen_tickets` plant them. Table below.
4. **Pattern check with pandas:** `scripts/check_patterns.py` (`make patterns`) measures each effect from the files.
5. **Clean control batch:** `python etl/generate_data.py --clean` (`make generate CLEAN=1`) sets every rate to 0: no
   defect, empty answer key (US-4.4 needs it for the false-positive test). The patterns are still there.
6. **Tests:** `scripts/test_defects.py` (71 checks, in `make gen-test`, so CI runs it). The four earlier generator
   suites now run on the clean control batch, which is what they always checked.

## The defects (full profile, seed 3004)

| Defect type | Where | Count | Handling | Rule |
|---|---|---|---|---|
| exact_duplicate | S4 tickets (exported twice), S6 incentive log | 60 + 6 | reject | DQ-03 |
| conflicting_duplicate | S4 tickets: an older copy with an earlier status | 60 | warn | DQ-03 (keep the latest) |
| null_required_value | S1 lease_events.event_date, payment_allocations.allocated_amount; S4 unit_no; S6 offer_code | 184 + 2,537 + 120 + 13 | reject | DQ-01 |
| inconsistent_text | S1 buildings.city, units.unit_type; S4 priority, category; S6 start date day first | 1 + 54 + 180 + 19 | repair | US-5.1 |
| wrong_data_type | S4 estimate as text (`Rs. 4,500`); S6 end date `TBD` or day 32 | 60 + 6 | reject | DQ-02 |
| out_of_range_date | S1 event dates 8 years off; S4 raised at 1970-01-01; S6 dates 10 years early | 92 + 60 + 6 | reject | DQ-06 |
| orphan_reference | S1 events to a lease and allocations to an invoice that do not exist; S4 unknown unit | 138 + 1,903 + 90 | reject | DQ-05 |
| orphan_reference | S3 settlement lines for payments S1 never recorded | 541 | warn | US-5.2 (unmatched) |
| late_arriving_tenant_reference | 38 tenants held back from S1: their 62 leases and 570 payments | 632 | warn | DQ-05 (inferred member) |
| late_arriving_payment | S3 lines reported 5 to 20 days after the payment | 721 | warn | US-5.2 |
| duplicate_settlement_line | S3 line repeated in its file | 361 | reject | DQ-03 |
| tenant_attribute_change | S1 tenants: employer sector or contact channel changes inside the window | 76 | accept | US-6.2 (SCD2) |
| mid_lease_rent_change | S1 rent lines billed above the lease rent from a month inside the lease | 587 lines | warn | DQ-04 |

8,507 defects, 5,636 of them to reject (`totals.csv`). The small profile has 43, every type at least once.

## The planted patterns (full profile, clean control batch)

| # | Pattern | Planted in | Measured | Expected |
|---|---|---|---|---|
| 1 | High-arrears building `GLB03` | `gen_payments`: its tenants draw risky payment behaviours | unpaid 21.5% vs 4.7% elsewhere (4.5x) | at least 2x |
| 2 | Slow vendor `V-001` (Plumbing) | `gen_tickets`: resolve time x2.2 | 1.35 of SLA vs 0.67 (2.0x); 84% late vs 26% | at least 1.6x |
| 3 | Seasonal move-ins | `gen_leases` (US-2.3) | 86 a month in June to August vs 60 (1.43x) | at least 1.3x |
| 4 | Incentive shortens vacancy | `gen_leases`: an offer on a vacant unit brings the next tenant sooner | 58 days vs 135 (0.43) | at most 0.75 |
| 5 | Rain-driven leak tickets | `gen_tickets`, from the real S5 rain | 2.18 vs 0.34 per 1,000 unit-days (6.3x) | at least 3x |
| 6 | Renewal churn in Karachi | `gen_leases`: renewal chance 0.20 lower | 27% renew vs 51% (0.54) | at most 0.75 |

## Files added or changed

- `etl/gen_defects.py`, `etl/patterns.py`, `scripts/test_defects.py`, `scripts/check_patterns.py` (new)
- `etl/gen_leases.py`: renewal churn, offers on vacancies, mid-lease rent changes; `etl/gen_payments.py`: arrears
  building; `etl/gen_tickets.py`: slow vendor, rain leaks, incentive log from the offers
- `etl/generate_data.py`: version 2.6, the stage, `--clean`, the weather cache hash in the manifest;
  `etl/generator_config.py`: `clean_profile`, offer targets; `etl/reference_data.py`: the offer catalogue (moved)
- `scripts/test_master_data.py`, `test_leases.py`, `test_payments.py`, `test_tickets.py`: run on the clean batch;
  `test_tickets.py`: offer count is approximate, offers lie in vacancies; `test_source_load.py`: asks for the clean
  batch
- `Makefile`, `requirements-ci.txt` (pandas), `README.md`, `docs/stories/README.md`, this file,
  `docs/evidence/us-2.6/`

## Decisions and deviations

- **Defects only where the answer key stays exact.** One defect per record; defects only on records nothing else
  points to (lease events, allocations, settlement lines, tickets, incentive rows) or on descriptive text. So a
  rejected record never orphans another (no cascade) and every rejected record fails exactly one check. Invoices,
  leases, payments and units keep their values (late tenants aside, which are flagged, not rejected).
- **S1 still loads into `src_pms`.** Its columns are typed with primary keys, so S1 has no wrong data types and no
  exact duplicates (they could not exist in the source database). Those defects are in the file sources (S3, S4,
  S6), where they really happen. Checked: every S1 value fits the frozen ERD, and the full defective load works.
- **Expected handling has a fourth value, `accept`**, for the tenant attribute changes: valid changes that must
  become a new SCD2 version, not a finding. The plan lists reject, warn and repair.
- **Late-arriving tenants** are held back from `s1/tenants.csv` and written to `s1/late_arriving/tenants.csv` (the
  next extract). **Tenant changes** are in `s1/changes/tenants.csv` (the changed rows, `updated_at` = the change).
  `db_load_source.py` loads neither; the incremental stories (US-5.3, US-6.2, US-6.5) apply them as a second extract.
- **Unmatched settlements** (US-5.2): S3 lines for payments S1 never recorded (541) are counted in
  `expectations.json`, beside the electronic payments with no settlement (722, planted by US-2.4).
- **Mid-lease rent changes are planted inside the lease simulation**, before the payments, so tenants pay what is
  billed. The lease record keeps the signed rent.
- **S2 is not damaged.** Its SCD2 test data (vendor ratings, SLA changes) is US-2.2's. A defect there would need the
  workbook rebuilt; left out on purpose.
- **Incentive offers are now posted on vacant units** (US-2.5 placed them on random units). That makes pattern 4
  real: a quarter of vacancies get an offer, those end sooner, and the offers are written to S6. The count follows
  the simulation (649 on full, 5 on small), so `target_incentive_offers` became "about" (650 and 5).
- **The generator reads the committed weather cache** (rain-driven leaks). Still no network; the manifest records
  the cache's SHA-256 under `inputs`. A missing cache is a clear error.
- **Renewal rates:** Karachi 0.20 lower; the other cities 0.04 higher, so the portfolio rate stays where US-2.3 had
  it (46%).
- **Seasonal move-ins expected 1.3x, not more.** Tenants who take an offer move in at once instead of waiting for the
  summer, which flattens the peak a little (1.43x; it was the US-2.3 test's 1.3x threshold).
- **Volumes changed** because of the patterns (full): leases 5,883 (was 5,770), invoice lines 129,885 (126,596). The
  US-2.3 to US-2.5 tests pass unchanged except the offer count.
- **The DB test of US-2.2 to US-2.4** (`test_source_load.py`) checks the clean contract, so it now asks for a clean
  control batch: `python etl/generate_data.py --clean`, then `python scripts/db_load_source.py`.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Defects at configurable rates (about 1 to 3 percent) | Pass: every count is round(rate x rows); doubling one rate doubles it and changes no other count | `02_defect_tests.txt` |
| Answer key lists every defect with source, table, record id, type, handling, plus totals per type | Pass: every difference between the files before and after injection is a key row, and the reverse | `01_`, `02_` |
| Answer key totals are reproducible with the same seed | Pass: byte-identical | `02_`, `04_reproducibility.txt` |
| Each planted pattern shows its intended effect size | Pass: 6 of 6 on the full profile | `03_pattern_check.txt` |
| Patterns documented in `planted_patterns.md` | Pass: written with the answer key | `05_samples.txt` |
| Tests can fail | Pass: see `06_tests_catch_broken_code.txt` | `06_` |

## How to re-check it

    python scripts/test_defects.py                                       # expect 71/71
    python etl/generate_data.py --profile full --clean --out data_full
    python scripts/check_patterns.py --data data_full                    # expect 6/6
    python etl/generate_data.py --profile full                           # with defects; see data/answer_key/

## Open items and follow-ups

- US-4.4 compares the quarantine with `defects_answer_key.csv` by source, table, defect type and `expected_rule`;
  `expectations.json` has the counts per check.
- US-5.3, US-6.2, US-6.5: load `s1/changes/tenants.csv` and `s1/late_arriving/tenants.csv` as the next extract.
- Content hashes depend on the NumPy version (US-2.1). Recorded with NumPy 2.4.6.
- Found while testing, not caused by this story: the small profile stops with "not enough tenants" for 9 of the
  seeds 0 to 100 (7, 49, 50, 55, 78, 84, 87, 89, 91), exactly as on `main` before US-2.6. The default seed and the
  full profile work. Worth a look in the US-2.3 tenant assignment (`gen_leases.assign_tenants`) if anyone needs
  other small seeds; simply adding tenants does not fix it.
