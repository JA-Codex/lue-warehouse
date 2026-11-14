# US-2.1 Build the generator framework, configuration and seeding

| | |
|---|---|
| Status | Done |
| Owner (plan) | Ahmad Waqar |
| Done on | 2026-11-14 |
| Branch and pull request | `e2-2.1-generator` |
| Evidence | [`../evidence/us-2.1/`](../evidence/us-2.1/) |

## Story

As a developer, I want a configurable, seeded generator skeleton, so that every run is reproducible and scalable.

## What was done

1. `etl/generator_config.py`: two profiles, `small` (2 buildings, 90 units, 3 months: 2026-04-01 to 2026-06-30) and `full`
   (4 cities, 40 buildings, 1,800 units, 36 months: 2023-07-01 to 2026-06-30). Each carries the volume targets from the
   plan (full: 1,500 active leases, 130,000 invoice lines, 60,000 payments, 6,000 tickets), 12 defect rates of 1 to 3
   percent, and the default seed (3004). `get_profile` refuses an invalid profile (reversed window, zero units, more
   leases than units, a defect rate above 10 percent).
2. `etl/generate_data.py`: the command line (`--profile small|full`, `--seed`, `--out`), the run context and a stage
   registry. A stage is one function with the `@stage` decorator; stages run in registration order.
3. Seeding: each stage calls `ctx.rng()` and gets a NumPy `Generator` derived from the run's seed and the stage name.
4. Output: creates `s1` to `s6` and `answer_key` (plus `_framework`) under `--out`, clears them first so no stale file
   survives a rerun, and writes `run_manifest.json` (seed, profile, stage list, SHA-256 of every file, one content hash).
   `run_info.json` holds the non-deterministic facts (time, Python and NumPy versions) and is kept out of the hash.
5. One stage ships with the framework, `framework_probe`: it draws numbers from its seeded stream and writes
   `_framework/rng_probe.csv`. It is the determinism evidence until US-2.2 produces real files.
6. `scripts/test_generator.py`: 39 checks, no database needed. Two deliberately broken copies of the generator were run
   against it to prove it can fail (`03_tests_catch_broken_seeding.txt`).
7. `Makefile`: `make generate` and `make gen-test`; `gen-test` is part of `make test`, so CI runs it. `numpy` was added to
   `requirements-ci.txt` for that.

## Files added or changed

- Added: `etl/generator_config.py`, `etl/generate_data.py`, `scripts/test_generator.py`, `docs/evidence/us-2.1/`
- Changed: `Makefile`, `requirements-ci.txt`, `README.md`, `docs/stories/README.md`

## Decisions and deviations

- **One seeded generator per stage, not one shared generator.** Plan step 2 says "a single seeded NumPy generator passed
  to every sub-generator". Every stream still comes from the single run seed, but is derived from the stage name. With one
  shared generator, one extra random draw in US-2.2 would silently change every number US-2.3 to US-2.6 produce, and four
  people are writing those stages in parallel. Recorded in the story index.
- **Small-profile window** is the last three months of the full window (plan only says "3 months").
- **Small-profile volume targets** are my scaling of the full ratios to 90 units; adjust them when US-2.3 to US-2.5
  show what the small profile really produces.
- **Output hash covers files only.** Folders (`answer_key` is empty until US-2.6) and `run_info.json` are not hashed.
- **NumPy version.** NumPy does not promise identical streams across versions. Teammates on different versions could get
  different hashes for the same seed. Pin a NumPy version in `requirements.txt` if the team sees this.
- **Cross-platform check done.** The evidence was first produced on Linux. On 2026-11-14 the same command on a Windows
  machine printed the same content hash (`67c361e8...fd1f68`) and `scripts/test_generator.py` passed 39/39
  (`04_windows_run.txt`).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| The small profile completes in under a minute | Pass: 0.1 s today (it generates nothing but the probe, so this is re-checked in US-2.6) | `02_acceptance_tests.txt` |
| Same seed gives identical hashes | Pass: same content hash and byte-identical files, also when rerun into the same folder | `01_hash_comparison.txt`, `02_acceptance_tests.txt` |
| A different seed gives different data | Pass | `01_hash_comparison.txt`, `02_acceptance_tests.txt` |

## How to re-check it

    python scripts/test_generator.py      # expect "RESULT: 39/39 checks passed"
    python etl/generate_data.py --seed 3004 --out data    # expect content hash 67c361e8...fd1f68 (Linux and Windows)

## Open items and follow-ups

- US-2.2 onward: add stages with `@stage`, follow the rules at the top of `etl/generate_data.py`, and re-run
  `make gen-test`; the "no unseeded randomness" check also scans any `etl/gen_*.py` file.
- The small profile's speed check should be re-run once the real stages exist.
