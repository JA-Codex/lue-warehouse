# US-2.4 Generate payments and settlements

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar |
| Done on | 2026-11-15 |
| Branch and pull request | `e2-2.4-payments-settlements` |
| Evidence | [`../evidence/us-2.4/`](../evidence/us-2.4/) |

## Story

As a data engineer, I want payments that behave like real tenants (late, partial, bounced) and bank and wallet
settlement files, so that collection, ageing and settlement analytics have meaningful signal.

## What was done

1. `etl/gen_payments.py`, stage `payments`. It rebuilds the master data and the billing with the US-2.2 and US-2.3
   seeds, then simulates every tenant paying every invoice. Writes `s1/payments.csv`, `s1/payment_allocations.csv`,
   the rewritten `s1/invoices.csv` (final `status`) and `s3/settlement_<channel>_<date>.csv`.
2. Five payment behaviours, one per tenant for the whole window (table below), plus a favourite payment method.
3. Bounced cheques: a negative payment with negative allocations; four in five tenants pay again.
4. S3 settlements: one record per electronic payment, with a channel fee and a settlement lag per channel; 2% of
   electronic payments are left out on purpose (unmatched).
5. `sql/05_source/03_src_pms_payments.sql` creates `src_pms.payments` and `src_pms.payment_allocations`;
   `scripts/db_load_source.py` loads them.
6. Tests: `scripts/test_payments.py` (80 checks, no database) and 12 more checks in `scripts/test_source_load.py`
   (66 in total, database). `make gen-test` and `make db-test` run them.
7. `build_payments(profile, master, billing, rng_for)` returns the same data as Python objects, including each
   tenant's behaviour, for US-2.6's answer key.
8. `STAGE_ORDER` in `etl/generate_data.py`: an explicit run order (see Decisions).

## Behaviour profiles (full profile, seed 3004)

| Behaviour | Share of tenants | What it does | Result |
|---|---|---|---|
| on_time | 55% (corporate 72%) | pays from the 1st to the due date | 100% by the due date, median 2 days early |
| occasionally_late | 20% | late in 20% of months, 1 to 30 days | 80% on time, 90th percentile 6 days late |
| chronically_late | 10% | always late, median 12 days | 0% on time, 90th percentile 31 days |
| partial_payer | 10% | 40 to 90% first, the rest 15 to 75 days later (65% of months) | 12.7% of what they are billed stays open |
| defaulter | 5% | a few normal months, then stops; sometimes pays an old invoice 45 to 120 days late | 66% of invoices never paid |

Full table in `04_behaviour_profiles.txt`.

## What the data looks like (full profile, seed 3004)

| | |
|---|---|
| Payments | 58,672 (target about 60,000): 58,252 cleared, 420 bounced-cheque reversals |
| Allocation rows | 124,735 |
| Collection | 95.4% of billed (PKR 5.28 bn of 5.54 bn) |
| Invoice status | 49,681 Paid, 1,866 Partial, 1,935 Overdue |
| Methods | Bank 29%, Cash 22%, Cheque 17%, Raast 14%, Easypaisa 10%, JazzCash 9% |
| Settlements | 35,312 in 3,888 files; 703 electronic payments (2.0%) unmatched |
| Settlement lag | Raast 0.05 days, Bank 1.35, JazzCash 1.50, Easypaisa 1.65 |
| Runtime | under 3 s |

Small profile: 226 payments (target 230), 152 settlements in 101 files, 94.5% collected.

## S3 file format

`s3/settlement_<channel>_<yyyy-mm-dd>.csv`, channel one of `bank`, `raast`, `jazzcash`, `easypaisa`, date = the
settlement date. One file per channel per day that has at least one settlement. Columns:
`settlement_id, payment_reference, transaction_date, settlement_date, gross_amount, fee_amount, net_amount`.
`settlement_id` is `BNK`, `RST`, `JZC` or `EPY` + the date + a 4-digit number; channel + settlement_id is the
natural key. Fees: bank 25 rupees flat, Raast 0.05% (at least 5 rupees), JazzCash 1.0%, Easypaisa 1.2%.
`payment_reference` is the S1 receipt number, which E3 uses to match a settlement to a payment.

## Files added or changed

- Added: `etl/gen_payments.py`, `scripts/test_payments.py`, `sql/05_source/03_src_pms_payments.sql`,
  `docs/evidence/us-2.4/`
- Changed: `etl/generate_data.py` (imports the stage, `STAGE_ORDER`, version 2.4), `etl/generator_config.py`
  (small payment target), `etl/gen_leases.py` (docstring only), `scripts/test_leases.py` and
  `scripts/test_source_load.py` (invoice status), `scripts/db_load_source.py`, `Makefile`, `README.md`,
  `docs/stories/README.md`, `docs/stories/US-2.3.md`

## Decisions and deviations

- **Explicit stage order.** Registration order depended on how the program was started: running
  `python etl/generate_data.py` re-imports the module, and with a second dependent stage `payments` registered
  before `master_data` and its invoice rewrite was overwritten by the US-2.3 stage. `STAGE_ORDER` now fixes the
  order; each later story adds its stage name there. (Found by a test, not in production.)
- **`invoices.csv` is rewritten.** The US-2.3 stage writes status `Issued`; this stage rewrites the file with the
  same rows and the final status: Paid, Partial or Overdue as at 2026-06-30. Every due date falls inside the
  window, so `Issued` no longer occurs. The US-2.3 tests were changed from "Issued" to the new set.
- **Bounced cheque = negative payment.** The reversal is a new receipt (status Bounced, amount negative,
  `reversal_of` the original, 3 to 7 days later) with negative allocations on the same lines. The original receipt
  keeps status Cleared, as the dictionary says `is_reversal` comes from `status = 'Bounced'`. A cheque that would
  bounce after the window closes does not bounce.
- **One payment pays one invoice,** split across that invoice's lines in line order (rent first). A tenant who
  pays two months at once makes two payments. Simple to allocate and to test; say if you want multi-invoice receipts.
- **`fact_payment` will have about 125,000 rows, not 60,000.** The dictionary says about 60,000 for the fact, but
  its grain is one allocation, and 60,000 is the number of payments (the plan's figure for this story). Payments are
  on target; the allocation count follows from 2.4 lines per invoice. Worth correcting in the dictionary note or
  keeping in mind for E7 volumes.
- **Cash and cheque never settle.** Only the four electronic methods have S3 files. "Unmatched" means an
  electronic payment with no settlement (`settlement_lag_days` NULL in the fact). Settlement rows whose reference
  matches no payment are a US-2.6 defect, not here.
- **Settlements can fall up to 3 days after 2026-06-30.** The bank has them even though the portfolio window has
  closed, so late-June payments are not wrongly unmatched.
- **No payments after the window; none before the invoice date.** A late payment on an invoice from June simply
  does not exist yet, which is why the last months show more arrears.
- **Small payment target changed from 250 to 230** (the real count is 226).
- **New content hash:** `--profile small --seed 3004` is now `cbdb041c...b7872f`. Every file from US-2.1 to US-2.3
  is byte-identical to before except `s1/invoices.csv` (status).
- **Verified on PostgreSQL 16.2 with real psycopg2** (embedded server). `test_dimensions.py` and `test_facts.py`
  need libxml, which that build lacks; this story does not touch them.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Behaviour profiles show the intended late-day distributions | Pass, per profile | `04_behaviour_profiles.txt`, `02_` |
| No payment allocation exceeds the invoice line | Pass (Python and SQL) | `02_`, `03_database_tests.txt` |
| Reversals net to the original | Pass: each reversal equals its cheque, 3 to 7 days later | `02_`, `03_` |
| About 60,000 payments | Pass: 58,672 (-2.2%) | `02_acceptance_tests.txt` |
| Settlement lag differs by channel | Pass: 0.05 / 1.35 / 1.50 / 1.65 days | `04_`, `02_` |
| Small share unmatched on purpose | Pass: 2.0% | `04_`, `05_` |
| Deterministic | Pass, including all S3 files | `01_hash_comparison.txt` |
| Tests can fail | Pass: 11 mutations caught | `06_tests_catch_broken_data.txt` |

## How to re-check it

    python scripts/test_payments.py                             # expect 80/80
    python scripts/test_leases.py                               # expect 114/114
    make generate PROFILE=full && make db-load-source
    python scripts/test_source_load.py                          # expect 66/66

## Open items and follow-ups

- **US-2.5** (tickets, incentives, registers) is independent of this story.
- **US-2.6** plants duplicate payments and duplicate settlement lines, settlement references that match nothing,
  and the high-arrears building. `build_payments(...).behaviour` gives each tenant's behaviour for the answer key.
  The arrears building can be planted by lowering the behaviour mix for tenants in one building before the
  simulation, or by dropping payments afterwards; the clean totals make either visible.
- E3 (S3 ingestion) can rely on the file format above. A bounced cheque has no S3 record.
- LATEFEE and CREDIT charge types are still unused; late fees would be new invoice lines and change US-2.3 output.
