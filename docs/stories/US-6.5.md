# US-6.5 Handle inferred members, late arrivals and test the dimensions

| | |
|---|---|
| Status | Done |
| Owner (plan) | Hanan |
| Done on | 2026-11-21 |
| Branch and pull request | `e6-dimensions` (one pull request for US-6.1 to US-6.5, one commit per story) |
| Evidence | [`../evidence/us-6.5/`](../evidence/us-6.5/) |

## Story

As a data engineer, I want late-arriving members handled gracefully and the dimensions proven correct, so that facts
always load and keys can be trusted.

## What was done

1. **Inferred members:** a tenant that a lease or payment references before S1 sends it becomes a member with
   `is_inferred` TRUE and the Unknown member's attributes (source_system 'INFERRED'), so the facts can point at it.
   When the real record arrives it is completed in place: same key, real values, `is_inferred` FALSE, no new version.
2. **Key -1** stays for a reference with no natural key at all. The frozen DDL gives `is_inferred` to `dim_tenant`
   only; every ticket's vendor is in the register, and a missing one would map to -1.
3. **The dimension test suite** `sql/90_tests/01_dimension_tests.sql` (47 tests, each returns its violations): unique
   surrogate keys, no NULL keys, special members present, one row per natural key, and for the SCD2 dimensions one
   current version, first version from 1900-01-01, current open and others closed, no gap or overlap; an inferred
   member has one version; the unit hierarchy is complete; the calendar flags equal the register.
4. **`scripts/test_dim_load.py`** runs the whole of E6 on the data folder: first extract, the next extract, both
   loads, and the SQL tests.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| All dimension tests return zero violations | Pass: 47 of 47 | `01_inferred_and_tests.txt` |
| A late tenant is created as inferred and later completed with no extra version | Pass: the 38 tenants of `s1/late_arriving` | `01_` |
| Inferred member count versus the answer key | Pass: exactly the 38 late tenants | `02_dimension_tests.txt` |

## How to re-check E6

    python scripts/test_dim_load_contract.py   # no database: expect 19/19
    python scripts/test_dim_load.py            # expect 22/22 (full profile: about 3 minutes)
