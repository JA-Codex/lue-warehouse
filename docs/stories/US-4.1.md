# US-4.1 Define the rule catalogue and engine

| | |
|---|---|
| Status | Done |
| Owner (plan) | Junaid (carried out by Hanan) |
| Done on | 2026-11-17 |
| Branch and pull request | `e4-quality` (one pull request for US-4.1 to US-4.4, one commit per story) |
| Evidence | [`../evidence/us-4.1/`](../evidence/us-4.1/) |

## Story

As a data engineer, I want validation rules defined as data and run by one engine, so that adding or changing a rule
never means rewriting pipeline code.

## What was done

1. **The catalogue** `etl/quality/rules.toml` (TOML, read with Python's own `tomllib`): rule id, check (DQ-01 to
   DQ-06), bronze table, type, columns and parameters, severity (`reject` or `warn`) and message. The field list and
   the 13 rule types are documented at the top of the file. 109 rules.
2. **The engine** `etl/quality/engine.py`: for each rule, in the order DQ-01 to DQ-06 and then file order, one
   `INSERT INTO lue_audit.dq_result ... SELECT ...` for the failing rows that no earlier rule rejected. So a row is
   rejected by its **first** failing rule only; warnings are counted separately and do not stop later rules. At the
   end every rejected row goes to the pack's `lue_audit.quarantine` (the row as JSON, the check, the reason).
3. **Idempotent:** before validating, the findings and quarantine rows of the batches in scope are deleted. The
   validation is one step of the US-3.1 framework (`validate_dq` in `etl_run_log`), one transaction.
4. **The runner** `etl/quality/run.py` (`make validate`); `--compare` is US-4.4.
5. DDL `sql/10_ddl/05_quality.sql`: `lue_audit.dq_result` and the safe casts `try_numeric`, `try_date`,
   `try_timestamp`. `sql/20_staging/02_bronze_row_id.sql`: a `row_id` on every bronze row.
6. **Interface for US-4.2 and US-4.3:** a rule is a `[[rule]]` block; nothing else to touch.

## Decisions and deviations

- **TOML, not YAML:** no new dependency (YAML needs PyYAML); same readability.
- **A rule's SQL is built from its fields.** Table and column names are checked against bronze first, and `;` is
  refused, so a rule cannot run a second statement. `condition` rules carry a SQL expression (business rules).
- **`lue_audit.dq_result`** (not in the pack, like `etl_watermark` and `file_load`) holds rejections and warnings by
  bronze `row_id`; the pack's quarantine keeps its meaning (rejected rows only). `check_contract.py` allows it;
  `test_smoke.py` now counts 7 audit tables.
- **`row_id` added to bronze** (an identity column, filled for rows already there): a finding names one row.
- **Each validation covers every batch in bronze** (scope can be limited to batches, which the tests use).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Adding a rule changes behaviour with no code edit | Pass: a rule added to a copy of the catalogue finds 250 shops and changes nothing else | `01_engine_tests.txt` |
| Validating twice yields identical quarantine counts | Pass: 5,636 rejected and 1,339 warnings both times; each rejection once in quarantine | `01_`, `02_two_runs.txt` |
| Evidence: the catalogue and two identical run summaries | Pass | `etl/quality/rules.toml`, `02_` |

## How to re-check it

    python scripts/test_quality_contract.py   # no database: expect 20/20
    python etl/quality/run.py                 # twice: the same counts
