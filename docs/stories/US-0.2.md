# US-0.2 Complete and freeze the Phase 1 baseline

| | |
|---|---|
| Status | Done |
| Owner (plan) | Whole team |
| Done on | 2026-11-07 |
| Tag | `phase1-v2.1-final`, on commit `8b266bf` ("user story 0.1+0.2") |
| Evidence | [`../evidence/us-0.2/`](../evidence/us-0.2/) |

## Story

As the team, we want the Phase 1 pack finalized with real author details and frozen, so that the submitted design is the
exact design we build.

## What was done

1. Collected the four names and roll numbers (open item O2, now closed) and set `AUTHORS` in `tools/model.py`:
   Junaid Minhas (23L-2559), Ahmad Waqar (23L-2634), Hanan Tiwana (23L-2536), Eesha Khurram (23L-2641).
2. Regenerated the five PDFs, the schema diagrams PDF and the dictionary. The author line appears on every cover, in each
   PDF's Author property and on the dictionary's README sheet.
3. Fixed `tools/build_schema_pdf.py`: the final PDF assembly was dropping the Author property, so the schema diagrams PDF
   had none. It now writes Title and Author.
4. Added a "Frozen baseline" section and a change-control section (rules and a change log) to the Phase 1 README, and removed
   the "replace the placeholder" checklist item.
5. Updated the development plan: the title-page placeholder replaced by the real names, O2 marked closed, risk 14
   marked resolved, and the spelling changed from "Esha" to "Eesha" throughout (61 places).
6. Built `MANIFEST.sha256` (SHA-256 of all 54 pack files) so that the repository copy can be proven identical.
7. Pushed the pack to `docs/phase1/` and tagged it `phase1-v2.1-final`.
8. Added `.gitattributes` with `docs/phase1/** -text` so Windows line-ending conversion cannot change the pack's bytes.
   A stray `docs/phase1/.gitattributes` was removed (a file inside the pack would not be in the manifest).

## Decisions and deviations

- Authors are printed in full (name and roll number) on every cover.
- The pack's change control: after the freeze, a design change needs a dated change-log row, a regeneration, a new
  manifest and a new tag.
- The `main` ruleset rejected a direct push of the `.gitattributes` commit ("Changes must be made through a pull
  request"). It went in through the branch `e0-0.2-gitattributes` instead. This was also the first proof the rules are enforced.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| No placeholder text remains in any PDF or in the plan | Pass: zero hits in all PDFs (text and file properties), the dictionary, the README, `model.py` and the plan | `1_placeholder_search.txt` |
| The tag exists | Pass: `phase1-v2.1-final` is on GitHub | `3_freeze_commands.txt` |
| `docs/phase1/` matches the submitted files | Pass: 55 files (54 pack files and the manifest) are on `main`. CI verifies them against the manifest on every run | `docs/phase1/MANIFEST.sha256`, CI job `ci` |

## How to re-check it

```
python scripts/ci_checks.py --manifest
git rev-parse "phase1-v2.1-final^{commit}"
```

On Windows without `sha256sum`, use PowerShell's `Get-FileHash` against `MANIFEST.sha256`, or run the Python check above.

## Open items and follow-ups

- The US-0.1 old-name search still returns 0 on the frozen pack (`2_US-0.1_regression_search.txt`).
