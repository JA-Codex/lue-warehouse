# US-4.4 Validate the checks against the answer key

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e4-quality` |
| Evidence | [`../evidence/us-4.4/`](../evidence/us-4.4/) |

## Story

As a tester, I want proof that the checks catch what we planted and reject nothing else, so that the quality claims are
defensible.

## What was done

1. `etl/quality/answer_key.py` (`python etl/quality/run.py --compare`): traces every answer key row to its bronze
   row(s) and compares by source, table, defect type and rule, using the key's expected handling. Detected = a finding
   of the expected check with the expected handling. Every other finding is a false positive, including any rejection
   of a row the key gives to a later stage (US-5.1, US-5.2, US-6.2). Writes `data/dq_validation.csv`.
2. **Clean control batch:** `scripts/test_quality.py` generates a clean batch (`--clean`, every defect rate 0) of the
   same profile, loads it into `src_pms` and bronze, validates it, then restores your data.
3. `scripts/test_quality.py` (25 checks, the database, all of E4; `make quality-test`) and
   `scripts/test_quality_contract.py` (20 checks, no database, in `make gen-test`: CI).

## Results (full profile, seed 3004)

| | |
|---|---|
| Planted defects in E4's scope (19 groups) | 6,915 |
| Detected by the expected check and handling | 6,915 (100%) |
| Rejected / warned | 5,636 / 1,339 (equal to the key's rejectable and warn rows) |
| False positives | 0 |
| Control batch (clean): rejections / warnings | 0 / 0 (466,057 rows, 109 rules) |

## Deviations explained (README of the plan's acceptance)

- **Seven defect groups are not E4's** and pass through it untouched, as the answer key says: inconsistent text in
  buildings, units, tickets and the incentive log (cleaned in US-5.1), late and unmatched settlement lines (US-5.2),
  tenant attribute changes (US-6.2). The comparison would list any rejection of them as a false positive: there is none.
- **A conflicting duplicate is counted once per ticket** (the key's record), though both copies carry the warning.
- **How a key row is found** when its defect changed the record's own key (an orphan allocation, an emptied offer code,
  a moved start date) is documented in `etl/quality/answer_key.py`.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Detection is 100 percent for rejectable defect types | Pass: 5,636 of 5,636 | `01_dq_validation.csv`, `02_quality_tests.txt` |
| Warn-only types are reported as warnings | Pass: 4 groups, 1,279 rows | `01_` |
| False positives are zero on the control batch | Pass: 0 rejections, 0 warnings | `02_` |
| Every deviation is explained | Pass: above | this file |
| Tests can fail | Pass: 12 deliberate breakages caught (after two test additions) | `03_tests_catch_broken_code.txt` |

## How to re-check it

    python etl/generate_data.py --profile full
    python scripts/db_load_source.py
    python etl/ingest/run.py
    python etl/quality/run.py --compare      # 6,915 of 6,915, 0 false positives
    python scripts/test_quality.py           # expect 25/25 (small: seconds; full: about 6 minutes)
