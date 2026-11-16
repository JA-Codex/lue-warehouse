# US-5.2 Apply business transformations

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e5-staging` (one pull request for US-5.1 to US-5.4, one commit per story) |
| Evidence | [`../evidence/us-5.2/`](../evidence/us-5.2/) |

## Story

As an analyst, I want derived business fields computed once in staging, so that every downstream query agrees on their
meaning.

## What was done

`etl/staging/business.py` runs as the last step of every staging run (`stage_business`). Each derived column of the
spec (28 in 6 tables, marked "derived" in the contract) is set by one `UPDATE` that changes a row only when a value
differs, so an unchanged rerun changes nothing (US-5.3).

1. **Allocation where the source did not** (plan step 1). A cleared payment whose staged S1 allocations add up to less
   than its amount (E4 rejected 4,440 allocation rows: empty amounts and unknown invoices) gets derived allocations
   for the rest (`allocation_source = 'derived'`, no bronze lineage):
   - first the open lines of the invoice the payment already pays (the source pays one invoice per payment, in line
     order: US-2.4), then the tenant's other open lines, oldest due date first;
   - only invoices issued on or before the paid date; never more than the payment's rest or a line's balance;
   - a reversal (bounced cheque) that lost an allocation reverses the rest on the original payment's lines, so a line
     does not look paid twice when the tenant pays again;
   - payments and reversals in paid order, so a reversal reopens its lines before the tenant's next payment.
2. **`days_past_due`** = paid date - due date (negative = early) on every allocation, reversals too (step 2);
   `stg_invoice_line` gets its due date, allocated amount and open balance.
3. **Settlement match** on the payment reference (step 3): `stg_settlement.is_matched` and lag;
   `stg_payment.settlement_id`, `settlement_date`, `settlement_lag_days` (earliest line) and `is_unsettled`
   (electronic, cleared, no line). A line reported in a later file (the 721 planted late lines) still matches.
4. **Lease term in months, ticket lifecycle and flags** (step 4): `term_months`; raised, assigned, resolved and
   verified times, the days and hours between them, the SLA in force on the raised date
   (`stg_maintenance_category`) and `sla_breached`; `is_emergency` (priority Emergency) and `is_recurring`.
5. **The answer key check** (`etl/staging/answer_key.py`, `make stage` runs `--compare`): `answer_key_check.csv`.

## Decisions and deviations

- **Own invoice first, then oldest due.** The plan says "oldest due line first". Applied blindly, a payment that lost
  one allocation row would pay a tenant's oldest unpaid invoice (some are over two years old) instead of the invoice
  it was for, and distort days past due and arrears (planted pattern 1). The payment's own invoice therefore comes
  first; oldest due first applies to the rest and to payments with no S1 allocation left.
- **Reversals are mirrored**, not allocated oldest due first: a reversal undoes its original.
- **`is_recurring` uses the data dictionary's 30 days**; the tenant app's own 90-day flag is kept as
  `source_is_recurring`. **`is_reversal` = status Bounced** (data dictionary).
- Derived values are recomputed for every row on each run (they depend on other tables), but only differing rows
  are written.

## Results (full profile, seed 3004)

| | |
|---|---|
| Derived allocations | 4,798 rows for 4,319 payments (all of them payments whose S1 allocation E4 rejected) |
| Cleared payments fully allocated | 59,256 of 59,256; reversals 423 of 423 |
| Payments or lines allocated beyond their amount | 0 |
| Unmatched settlement lines | 541 (answer key 541) |
| Unsettled electronic payments | 722 (answer key 722) |
| Late settlement lines still matched | 721 of 721 |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Sum of allocations = payment amount for every fully allocated payment | Pass: every cleared payment and every reversal; none over-allocated, no line over its net amount | `02_allocation_reconciliation.txt` |
| Unmatched settlement count matches the answer key | Pass: 541 = 541 (and 722 unsettled = 722) | `01_answer_key_check.csv` |
| Evidence: allocation reconciliation; unmatched count versus the key | Pass | `01_`, `02_` |

## How to re-check it

    python etl/staging/run.py --compare    # the answer key lines: all PASS
    python scripts/test_staging.py         # the US-5.2 block: 9 checks
