# US-0.3 Create the repository, branching and quality gates

| | |
|---|---|
| Status | In progress |
| Owner (plan) | Junaid |
| Repository | https://github.com/JA-Codex/lue-warehouse (public) |
| Done on | |
| Evidence | [`../evidence/us-0.3/`](../evidence/us-0.3/) |

## Story

As developers, we want a structured repository with branch protection and automatic checks, so that broken code never
reaches `main`.

## What was done

1. Created the repository `lue-warehouse`. It was made **public**: GitHub Free does not enforce rulesets on a private
   repository (the settings page says so), and enforcement is what the acceptance test needs.
2. Pushed the frozen Phase 1 pack first (US-0.2), then turned on the ruleset, so the freeze commit did not need a pull request.
3. Created the ruleset `main` (Active, empty bypass list, so it applies to administrators too):
   - restrict deletions, block force pushes;
   - require a pull request before merging, dismiss stale approvals when new commits are pushed;
   - require the status check `ci` (source: GitHub Actions).
4. Added the scaffold through the pull request `e0-0.3-scaffold`:
   - the folder layout from the plan (A5), with `.gitkeep` in empty folders;
   - `.gitignore`: virtual environments, credentials, generated data except `data/weather_cache.json` (decision D12);
   - `Makefile` with `setup`, `rebuild`, `test`, `reports` and `db-reset` (stubs except `test`), plus `help`, `lint`,
     `sqlcheck` and `manifest`;
   - `.github/workflows/ci.yml`: one job named `ci`, running `make test` on every push and pull request;
   - `.github/pull_request_template.md` with the Definition of Done from the plan (A10);
   - `scripts/ci_checks.py`, `ruff.toml`, `requirements-ci.txt`, the root `README.md`.
5. `make test` runs three checks: ruff on `etl/` and `scripts/` (the frozen pack in `docs/` is never linted), a `pglast`
   parse of every `.sql` file under `sql/` and `docs/phase1/sql/` (psql meta-commands such as `\c` are skipped), and a check
   that `docs/phase1/` still matches `MANIFEST.sha256`, with no extra or changed files.
6. Observed the ruleset rejecting a direct push to `main` (GH013, "Changes must be made through a pull request").

## Decisions and deviations

- **Public repository.** Chosen because the free plan cannot enforce rules on a private one. Never commit credentials;
  `.env` is ignored and only `.env.example` is committed.
- **Reviews are optional (team decision, 2026-11-07).** The plan said one review required; the ruleset requires the pull
  request and a passing `ci`, but no approval. The plan, README and pull request template were reworded to match. The
  optional rotation is still written down.
- **Added a CI check beyond the plan:** the frozen-pack manifest check, which makes the US-0.2 freeze enforceable.
- **Layout additions:** `scripts/` (CI checks) and `docs/evidence/`, `docs/stories/`, `docs/plan/`, recorded in the README.
- `make` is not installed on Windows by default; the README gives the direct commands.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A test pull request is blocked until `ci` passes (originally "until reviewed"; see decisions) | Pending | `03_pr_blocked_until_ci_passes.png` |
| The workflow passes on `main` | Pending: confirm after the scaffold pull request merges | `01_actions_green_on_main.png` |
| The pull request template appears | Pending: appears on pull requests opened after the scaffold merged | `04_pr_template.png` |
| Branch protection settings captured | Pending | `02_ruleset_settings.png` |

## How to re-check it

Open a pull request: the merge button is blocked until `ci` is green, and a direct `git push origin main` is rejected.
Locally: `make test` (or `ruff check etl scripts` and `python scripts/ci_checks.py`).

## Open items and follow-ups

- Run the throwaway test pull request (`e0-0.3-test-gate`) and save the four screenshots in `docs/evidence/us-0.3/`.
- The `pglast` step first ran in CI; if it ever fails on `docs/phase1/sql/physical_model.sql`, record the error here.
- Fill the plan's "GitHub repository link" deliverable row with the repository URL.
- When done: set the status here and in `README.md` of this folder to Done, with the date.
