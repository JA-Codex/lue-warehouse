# Evidence: US-15.3 — Rubric Sweep and Submission Packaging

## Summary

Every Appendix B deliverable was walked against the repository at commit `cc000ae` (branch `user-story-13-15`).  17/17 items are accounted for.  `scripts/package_submission.py` runs offline and verifies all code deliverables are present.

## Key checks

| Check | Result |
|---|---|
| Phase 2 deliverables: 9 items | 9/9 ✓ |
| Phase 3 deliverables: 8 items | 8/8 ✓ (2 manual: PBIX, PPT) |
| `python scripts/package_submission.py` exits 0 | All code deliverables present |
| `make package` exits 0 | Pass |
| `python -m ruff check scripts/package_submission.py` | 0 errors |
| Git tag `phase3-submission` exists | ✓ |

## Files

- `docs/evidence/us-15.3/01_appendix_b_checklist.md` — full per-item checklist
- `docs/evidence/us-15.3/02_submission_confirmation.md` — submission record (fill LMS link after upload)

## Re-check command

```
python scripts/package_submission.py
make package
python -m ruff check scripts/package_submission.py
git tag --list "phase3-submission"
```
