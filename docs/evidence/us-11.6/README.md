# Evidence for US-11.6: every query on the small profile, and the definition issues found

The plan's drafts in `sql/60_analytics/draft/` were not kept as a separate folder: the queries were written straight
into the final files and run on the small profile first, which is the purpose of the story (find missing columns,
ambiguous definitions and performance problems early). This folder records that run and what it found.

| File | What it shows |
|---|---|
| `01_small_profile_run.txt` | `python scripts/run_analytics.py` on the small profile (2 buildings, 3 months): all 24 queries run |
| `02_small_profile_tests.txt` | `python scripts/test_analytics.py` on the small profile: 16/16 (the planted patterns are measured on the full profile only) |

## Issues found and how each was settled

| # | Issue | Found by | Settled |
|---|---|---|---|
| 1 | W3 divided by zero: on the small profile most fiscal years have no cash (the occupancy snapshot, and so the window, always spans the full 36 months; billing exists in the last 3) | the small-profile run (psql stopped, exit 3) | `nullif`: the share is empty for a year without cash |
| 2 | Q4a returns no rows on the small profile: 3 months cannot hold 3 late payments in 12 months | the small-profile run | correct as it is; the test reports it on the small profile and requires rows on the full one |
| 3 | Q3 buckets: the plan says 0-30, 31-60, 61 and over; the pack's KPI says 0-30, 31-60, 61-90, 90+ | reading both | the pack's four buckets; the plan's "61 and over" is the last two together (stated in the header) |
| 4 | Q5 "settlement": only electronic payments have a settlement date (the S3 files); cash and cheques have none | the first run (no lag for CASH, CHEQUE) | both measures shown: settlement lag where it exists, days past due for every method; the header says why cash and cheques have no lag |
| 5 | Q6b move-ins: counting SIGN events put the peak in July (the go-live month), not June to August | comparing with `scripts/check_patterns.py` | a move-in is a new tenant's lease starting (no previous lease), the pattern's own measure |
| 6 | Q7 censoring differs from the occupancy mart's: the mart keeps a spell that began before the window and ended inside it | the plan's rule for Q7 | Q7 applies the plan's rule (both ends inside the window), stated beside the query; the mart keeps its definition, documented in `docs/reporting.md` |
| 7 | Q8: 91 RENEW events were quarantined (planted defects), so an event-based rate understates renewals | profiling `fact_lease_event` against `dim_lease` | the plan's event-based rate, with the lease-link rate beside it; the difference is the quarantine |
| 8 | Q12: the brief gives no management fee rate | the plan (US-11.3) | 8 percent of rent collected, stated beside the query and held in `lue_reporting.vw_reporting_parameter` (shared with the owner mart) |
| 9 | Q14: "heavy rain" needs a threshold and the effect shows the day after too | the planted pattern's definition | 10.0 mm or more on the day or the day before, stated beside the query |
| 10 | Performance: three first versions used a subquery per row on tables without an index (Q3 payments per line, Q8 events per lease, Q13 offers per spell) | reading the plans before the full run | rewritten as joins; the whole pack runs in about 10 seconds on the full profile |

No warehouse change was needed: every column the questions use exists.
