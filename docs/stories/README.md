# Story log

One row per user story. Status values: `Not started`, `In progress`, `Done`. Newest work at the bottom of each epic.
Story definitions live in the plan: `../plan/LUE_Development_Plan_v1.1.md`.

## E0. Foundation and Phase 1 closure

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-0.1 | Align the Phase 1 pack with the briefs | Hanan | Done | 2026-11-06 | [US-0.1](US-0.1.md) | [evidence](../evidence/us-0.1/) |
| US-0.2 | Complete and freeze the Phase 1 baseline | Whole team | Done | 2026-11-07 | [US-0.2](US-0.2.md) | [evidence](../evidence/us-0.2/) |
| US-0.3 | Create the repository, branching and quality gates | Junaid | Done | 2026-11-07 | [US-0.3](US-0.3.md) | [evidence](../evidence/us-0.3/) |
| US-0.4 | Provide a reproducible local environment | Eesha | Done | 2026-11-07 | [US-0.4](US-0.4.md) | [evidence](../evidence/us-0.4/) |

## E1. Database implementation

| Story | Title | Owner (plan) | Status | Done on | Log | Evidence |
|---|---|---|---|---|---|---|
| US-1.1 | Create databases, roles and schemas | Hanan | Done | 2026-11-09 | [US-1.1](US-1.1.md) | [evidence](../evidence/us-1.1/) |
| US-1.2 | Deploy dimension DDL with keys and special members | Hanan | Done | 2026-11-09 | [US-1.2](US-1.2.md) | [evidence](../evidence/us-1.2/) |
| US-1.3 | Deploy fact DDL, foreign keys and partitions | Hanan | Done | 2026-11-10 | [US-1.3](US-1.3.md) | [evidence](../evidence/us-1.3/) |
| US-1.4 | Load the date dimension and static reference dimensions | Eesha | Done | 2026-11-10 | [US-1.4](US-1.4.md) | [evidence](../evidence/us-1.4/) |
| US-1.5 | Create audit tables, the watermark table and the reset script | Eesha | Not started | | | |

## Later epics

Add a section per epic as work starts (E2 generator, and so on), using `_TEMPLATE.md` for each story.

## Team decisions made while doing the work

| Date | Decision | Where recorded |
|---|---|---|
| 2026-11-06 | Renamed schemas (`lue_*`) are used instead of the brief's `project_*`; pending instructor confirmation (O4) | [US-0.1](US-0.1.md), `phase1/README.md` |
| 2026-11-07 | Repository is public, because GitHub Free does not enforce branch rules on private repositories | [US-0.3](US-0.3.md) |
| 2026-11-07 | A teammate review before merging is optional and not enforced; the `ci` check and the pull request are enforced | [US-0.3](US-0.3.md) |
| 2026-11-10 | The static reference dimensions have 6 charge types (not the plan's 4), following the Phase 1 pack; settlement days are our assumption | [US-1.4](US-1.4.md) |
| 2026-11-09 | `dim_request_flags` keeps no special members, as in the Phase 1 pack; plan US-1.4's "plus the Unknown member" cannot fit (three NOT NULL flags, all 8 combinations unique) | [US-1.2](US-1.2.md) |
