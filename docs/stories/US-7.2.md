# US-7.2 Load fact_rent_invoice_line and fact_payment

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar (carried out by Hanan) |
| Done on | 2026-11-21 |
| Branch and pull request | `e7-facts` (one pull request for US-7.1 to US-7.6, one commit per story, pushed one by one) |
| Evidence | [`../evidence/us-7.2/`](../evidence/us-7.2/) |

## Story

As a finance analyst, I want invoices and payments in separate facts at their own grains, so that collection analysis
is correct for partial and split payments.

## What was done

1. **`fact_rent_invoice_line`** (plan step 1): one row per charge line of one invoice, from `stg_invoice_line` and
   its invoice header: billed, tax, discount and net amount; invoice number and line number as degenerate
   dimensions; the invoice and due date keys; the lease, and the lease's unit and tenant in the version valid on the
   invoice date; the unit's owner on the invoice date; the charge type. It goes through the US-7.1 loader like every
   fact, on its grain, which is also the frozen DDL's unique key `uq_invoice_line`; `ck_net_amount` holds on every
   row.
2. **`fact_payment`** (step 2) is the US-7.1 fact: one row per payment amount allocated to one invoice line, so a
   split payment is several rows and a partly paid line has fewer paid than billed. Reversals stay negative amounts
   (`is_reversal`), so they reduce collected totals; the payment reference is a degenerate dimension and the payment
   method a key.
3. **Late payments** (step 3): staging already resolved each payment to its invoice lines (US-5.2, oldest due first
   after the payment's own invoice); a payment whose line is missing was quarantined in E4, so every allocation finds
   its line.
4. **Monthly reconciliation** (step 4): each fact declares, in `etl/facts/spec.py`, its amount by month in the fact
   (through `dim_date`) and in staging. After loading, in the same transaction, the step writes one row per month to
   `lue_audit.reconciliation` (staging value, fact value, difference, passed): net billed by invoice month, paid by
   paid month. A month that differs makes the step a Warning and is named in the run log; `etl/facts/run.py` shows
   the months that agree per fact.
5. Load order: the invoice fact, then the payment fact.

## Files added or changed

- `etl/facts/spec.py` (the invoice fact; `monthly` on both money facts), `etl/facts/load.py` (`monthly_sql`,
  `monthly`), `etl/facts/run.py` (reconciliation rows and the "months ok" column)
- `scripts/test_fact_load_contract.py` (12 checks), `scripts/test_fact_load.py` (20 checks)
- `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **Months by the fact's own date**: invoices by invoice date, payments by paid date (cash received). The cohort
  collection rate of D17 (paid against lines due in a month) is a mart measure (E10); it reads the same two facts.
- **The tenant of an invoice line is the lease's tenant** at the invoice date; for payments it is the payer at the
  paid date. In this data the payer is always the lease's tenant (0 differ), so the two facts agree per lease.
- This story reconciles the facts to staging. Source against warehouse, with quarantined rows as the reconciling item,
  is US-8.2 (DQ-07).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Zero grain duplicates | Pass: 129,885 invoice lines and 127,210 payment allocations, as many distinct grains | `01_` (query 3), `02_` |
| Monthly totals match staging exactly | Pass: 36 months each of net billed and paid; 72 reconciliation rows, all passed, total difference 0.00 | `01_` (query 6), `02_` |
| Reversals reduce collected totals | Pass: 5,391,828,597.00 received, 934 reversals of -44,538,888.00, collected 5,347,289,709.00 PKR | `01_` (query 5) |
| Evidence: grain check output and the monthly reconciliation | Pass | `01_` |

## How to re-check it

    python scripts/test_fact_load_contract.py   # no database: expect 12/12
    python etl/facts/run.py                     # twice: the second run changes nothing; months ok 36/36 for both
    python scripts/test_fact_load.py            # expect 20/20 (about two minutes)
