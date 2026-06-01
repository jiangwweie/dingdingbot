# BRC Pre-Live Release Baseline - 2026-06-01

## Baseline

- Current branch: `codex/brc-owner-console-v0`
- Baseline target tag: `brc-bnb-prelive-20260601`
- Tag type: local annotated tag, not pushed
- Tag target: final release-governance report commit on this branch
- Migration head: `030`

## Included Milestones

- BNB protected testnet rehearsal completed.
- Strategy Trial architecture governance completed.
- Owner Console main flow completed.
- Owner risk acknowledgement / authorization draft is PG-backed.
- Environment contract simplified.
- Live remains blocked until explicit Owner live authorization.

## Commits Included

- `6556cd25` - `feat(brc): persist owner trial flow and simplify environment contract`
- `b55f2e47` - `feat(console): implement owner trial decision flow`
- This report commit - release baseline governance report.

## Dirty File Classification Before Commit

| Classification | Files |
| --- | --- |
| `current_baseline_should_commit` | `.env.local.example`, `.env.tiny-live.example`, `.env.local.testnet.example`, `.env.production.example`, `.env.tokyo.prelive.example`, `docs/ops/environment-contract.md`, `migrations/versions/2026-06-01-030_create_owner_trial_flow_metadata.py`, `src/application/owner_trial_flow.py`, `src/infrastructure/owner_trial_flow_repository.py`, `src/infrastructure/pg_models.py`, `src/interfaces/api_brc_console.py`, `src/application/runtime_config.py`, `src/infrastructure/database.py`, `src/application/strategy_trial_architecture_governance.py`, `tests/unit/test_environment_contract.py`, `tests/unit/test_execution_permission.py`, `tests/unit/test_strategy_trial_bnb_profile_seed.py`, `tests/unit/test_owner_trial_flow.py`, `gemimi-web-front/src/pages/brc/OwnerConsoleV2.tsx`, `gemimi-web-front/src/pages/brc/OwnerConsoleV2.test.tsx`, `gemimi-web-front/src/services/api.ts` |
| `unrelated_preexisting_dirty` | none found |
| `generated_report_or_screenshot` | this report |
| `local_secret_or_env_never_commit` | none found |
| `build_artifact_never_commit` | none found |
| `uncertain_needs_review` | none found |

## Branch Inventory

- Current work branch: `codex/brc-owner-console-v0`
- Integration branch: `dev`
- Stable/legacy branch: `main`
- `master`: no local or remote branch found
- `origin/HEAD`: points to `origin/main`
- Current branch has no upstream configured.
- `dev` is an ancestor of current branch.
- `origin/dev` is an ancestor of current branch.
- `main` is an ancestor of current branch.

## Remote / Upstream Facts

- Remote: `origin` = `https://github.com/jiangwweie/dingdingbot.git`
- Local `dev`: `2592c2f8fb18a301fdb9d89e0fcb31db559e0951`
- Remote `origin/dev`: `a1c3dca245540cdafa120f283b965a38d28a5088`
- Local `main`: `41f271f66507c9d6b1d573990041b7849eea7fc4`
- Remote `origin/main`: `28b7254ee7854f90b9cc436af606c973b7fd1e83`
- No merge into `main`/`dev` was performed.
- No push was performed.

## Backend Status

- Owner trial flow metadata is persisted through PG-backed repository.
- Mainline SQLite/local metadata storage is not used for Owner trial flow.
- Migration `030` adds:
  - `brc_owner_risk_acknowledgements`
  - `brc_bounded_live_trial_authorization_drafts`
- Authorization drafts remain non-executable:
  - `live_ready=false`
  - `order_permission_granted=false`
  - `execution_permission_granted=false`
  - `execution_intent_created=false`
  - `order_created=false`

## Frontend Status

- Owner Console shows backend-recorded risk acknowledgement.
- Owner Console can request non-executable authorization draft metadata.
- UI still disables live authorization.
- UI states that authorization draft is not an order and does not create live ExecutionIntent.

## Environment Contract Status

- Production/prelive templates are globally read-only.
- `RUNTIME_PROFILE` is documented and guarded as dev/testnet-only.
- Core mainline storage backends are fixed to `postgres`.
- `BRC_EXECUTION_PERMISSION_MAX` is a global cap, not live authorization.
- Runtime control and test signal injection are disabled in production/prelive templates.
- Canonical exchange credential names are `EXCHANGE_API_KEY` and `EXCHANGE_API_SECRET`.

## Validation

- `python3 -m compileall -q src scripts` passed.
- `python3 -m pytest -q tests/unit/test_environment_contract.py tests/unit/test_brc_console_api_surface.py tests/unit/test_mi001_sol_trial_start_checklist.py tests/unit/test_execution_permission.py tests/unit/test_owner_trial_flow.py tests/unit/test_strategy_trial_bnb_profile_seed.py` passed: `71 passed`.
- `cd gemimi-web-front && npm run lint` passed.
- `cd gemimi-web-front && npx vitest run` passed: `7 files / 14 tests`.
- `cd gemimi-web-front && npm run build` passed.
- `git diff --check` passed before commits.
- `git diff --cached --check` passed before commits.
- `python3 -m alembic heads` reported `030 (head)`.

## Known Deployment Blockers

- No explicit Owner live authorization has been granted.
- No live runtime should be started from this baseline.
- Production/live runtime scope must resolve from PG-backed Owner authorization; `RUNTIME_PROFILE` is not a live selector.
- Remote branch / release policy remains local-only until Owner explicitly authorizes push or merge.

## Safety Boundary

- No live order placed.
- No testnet order placed.
- No runtime started.
- No exchange API called.
- No credential values changed.
- No secrets printed.
- No push performed.
- No destructive git operation performed.
