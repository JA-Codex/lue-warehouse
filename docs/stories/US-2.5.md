# US-2.5 Generate tickets, incentives and weather

| | |
|---|---|
| Status | Done |
| Owner (plan) | Eesha (carried out by Hanan) |
| Done on | 2026-11-16 |
| Branch and pull request | `e2-2.5-tickets-weather` |
| Evidence | [`../evidence/us-2.5/`](../evidence/us-2.5/) |

## Story

As a data engineer, I want maintenance tickets, leasing incentives and a weather history, so that the remaining
processes have data.

## What was done

1. **S5 weather, real data:** `etl/refresh_weather.py` (`make weather`) downloads daily maximum temperature and
   rainfall for the four cities, for every day of the window (2023-07-01 to 2026-06-30), from the Open-Meteo
   historical API, once, into the committed `data/weather_cache.json` (D12). `make weather-check` checks coverage
   without the network. Standard library only (no new dependency).
2. **S4 tickets and S6 incentives:** `etl/gen_tickets.py`, stage `tickets_incentives`: `s4/tickets.json` (6,000 tickets
   on the full profile, each with a nested status history), `s6/offers.csv` (the incentive catalogue) and
   `s6/incentive_log.csv` (600 offers posted on units).
3. **Tests:** `scripts/test_weather.py` (52 checks, against a local stand-in for the API, so no internet is needed and CI
   can run it) and `scripts/test_tickets.py` (67 checks). Both are in `make gen-test`, so CI runs them.
4. **Config:** `etl/generator_config.py` gained `target_incentive_offers`. `etl/reference_data.py` gained the weather
   cities and variables. `etl/generate_data.py` gained the stage-order list (the same code as the US-2.4 branch).

## Why the weather download cannot break the project

| Risk | What happens |
|---|---|
| Rate limit (HTTP 429). The free API counts a long date range as several calls; asking for three years at once can exceed 600 calls a minute | 16 small requests (4 cities x 4 periods, never more than one calendar year), 3 s apart. "Minutely" limit: wait (Retry-After, else 65 s), retry. "Hourly" or "Daily" limit: stop at once and say when to rerun |
| Network error, timeout, HTTP 5xx | Up to 6 attempts, with waits that double |
| Download stopped halfway | Each finished request is kept in `data/.weather_parts/` (not committed); the next run resumes |
| Bad answer (missing or repeated day, wrong unit or time zone, impossible value, cut-off JSON) | Rejected and retried; never written |
| Failure while writing | The cache is replaced in one atomic step, only when all 16 parts are valid |
| The network blocks the API | `--print-urls` gives the 16 links; save them from a browser; `--import-dir` builds the cache |
| Teammates and CI without internet | Nobody else calls the API: the generator, the tests and the pipeline read only the committed cache |
| Missing values (null) from the API | Kept as null and counted by `--check`; the data dictionary sends them to quarantine (DQ) |

## Files added or changed

- `etl/refresh_weather.py`, `etl/gen_tickets.py` (new); `etl/generate_data.py`, `etl/generator_config.py`,
  `etl/reference_data.py`
- `scripts/test_weather.py`, `scripts/test_tickets.py` (new)
- `scripts/test_master_data.py`, `scripts/test_source_load.py`: load the frozen `model.py` without writing
  `__pycache__` into `docs/phase1` (see below)
- `scripts/db_reset.py`: import re-wrapped by `ruff --fix` (see below)
- `data/weather_cache.json` (new, committed), `Makefile`, `README.md`, `docs/stories/README.md`, this file,
  `docs/evidence/us-2.5/`

## Decisions and deviations

- **Tickets carry no tenant.** The fact finds the tenant from the lease active on the raised date, or -2 for a vacant
  unit (dictionary). This keeps US-2.5 dependent on US-2.2 only, as the plan says, not on the unmerged US-2.3.
- **Ticket fields:** unit by business key (`building_code` + `unit_no`), subcategory, priority (Emergency, High,
  Normal), the three request flags, `reported_via`, vendor, estimate and final cost (whole rupees),
  `status_history`. `is_emergency` = priority Emergency; `is_recurring` = same unit and subcategory within the 90 days
  before. Ticket ids `MR-<year>-<5 digits>` (13 characters).
- **Seasonality, not patterns.** AC tickets peak in summer, seepage and roof work in the monsoon, geysers in winter.
  The planted patterns (a slow vendor, rain-driven leaks, an incentive that shortens vacancy) are US-2.6's.
- **Tickets do not read the weather.** Rain-driven leaks are planted in US-2.6. So the generator never needs the cache
  and its output depends only on (profile, seed).
- **Incentives:** 7 offers in the dictionary's three types; offers suit the unit type; at most one offer at a time per
  unit (keeps the coverage fact's key unique). Whether the unit was vacant on a day is the coverage fact's job (E7).
- **Weather window = the project window**, not the calendar (dim_date runs to 2027-06-30; tickets end 2026-06-30).
- **Pakistan time** (`timezone=Asia/Karachi`, D13): a day is a Pakistan calendar day.
- **Fix outside the story (1): `__pycache__` in the frozen pack.** Loading `docs/phase1/tools/model.py` from a test made
  Python write `docs/phase1/tools/__pycache__/`, and the next `make test` reported the frozen pack as changed. CI never
  saw it (it checks the pack before the tests), but every laptop did. The three loaders now switch bytecode writing off.
- **Fix outside the story (2): lint on `main`.** The current ruff reports an unsorted import in `scripts/db_reset.py`
  (US-1.5). CI installs the newest ruff, so every new pull request would fail. Re-wrapped with `ruff --fix`; no code
  change.
- **Merging with US-2.3 and US-2.4** (unmerged branches): `Makefile` and `etl/generate_data.py` conflict on 4 small
  spots; keep both sides (see `07_merge_rehearsal.txt`). Rehearsed: all six generator suites pass after the merge.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Every ticket has a valid unit, category and vendor reference (before defect injection) | Pass (small and full) | `02_ticket_tests.txt` |
| Incentive windows lie within the window and reference real units | Pass | `02_ticket_tests.txt` |
| The weather cache covers every city and every day | Pass | `03_weather_tests.txt`, `04_weather_cache_check.txt` |
| About 6,000 tickets as JSON with a nested status history | Pass: 6,000 | `02_`, `05_samples.txt` |
| Tests can fail | Pass: 13 real bugs caught; one gap found and closed | `06_tests_catch_broken_code.txt` |

## How to re-check it

    python scripts/test_tickets.py              # expect 67/67
    python scripts/test_weather.py              # expect 52/52 (needs the committed cache for the last 3)
    python etl/refresh_weather.py --check       # or: make weather-check

## Open items and follow-ups

- US-2.6: plant rain-driven leak tickets (read `data/weather_cache.json` through `refresh_weather.load_cache`), a slow
  vendor, an incentive that shortens vacancy; inject ticket defects (missing resolve times, statuses out of order) and
  S6 defects (mixed date formats, unit codes without the building prefix).
- US-3.4: ingest `s4/tickets.json` and the weather cache (`load_cache` returns one row per city and day).
- Content hashes depend on the NumPy version (US-2.1). Recorded with NumPy 2.4.6.
