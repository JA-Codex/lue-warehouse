# docs/

| Folder | What it holds |
|---|---|
| `phase1/` | The frozen Phase 1 design pack (v2.1). Never edited; CI checks it against `MANIFEST.sha256`. |
| `plan/` | The development plan for Phases 2 and 3 (epics, user stories, decisions D1 onwards, risks). |
| `stories/` | **The story log.** One file per user story: what was done, why, what changed, how it was checked. Start at `stories/README.md`. |
| `evidence/` | Proof for each story (search outputs, check results, screenshots), one folder per story. |
| `contracts/` | Generated table and key contracts, refreshed weekly. |
| `reports/` | Generated PDFs: cleaning, data quality, indexing, insights. |

## Keeping the log up to date

Every story's pull request must also:

1. Create or update `stories/US-x.y.md` (copy `stories/_TEMPLATE.md`).
2. Update the status row in `stories/README.md`.
3. Put the evidence in `evidence/us-x.y/` and link it from the story file.

The pull request template has a checkbox for this.
