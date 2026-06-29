# Batch 1064 Evidence - Machine-Readable Staging Rebuild Plan

## Batch Acceptance

| Field | Value |
| --- | --- |
| batch_id | `BATCH_1064` |
| closed_engineering_problem | Batch 1063 produced staging bucket counts, but future staging still lacked a machine-readable path list and explicit non-executed rebuild sequence. |
| capability_unlocked | Future Owner-authorized staging rebuild can use `STAGING_REBUILD_PLAN.json` / `STAGING_REBUILD_PLAN.md` as the audited input instead of the unsafe pre-existing index. |
| next_engineering_bottleneck | Owner validation / explicit staging rebuild authorization remains the bottleneck; no staging action was performed. |
| files_changed | `BATCH_1064_EVIDENCE.md`; `STAGING_REBUILD_PLAN.json`; `STAGING_REBUILD_PLAN.md`; `STAGING_COMMIT_MANIFEST.md`; latest pointer/queue/final evidence/merge readiness/Owner validation metadata. |
| tests_run | read-only tracked/cached/untracked inventory; generated staging rebuild plan validation; `python3 -m json.tool` for the plan; `git diff --check`; `python3 -m compileall src scripts tests migrations -q`; upstream/index shortstat check. |
| why_this_batch_enables_deeper_refactor | It makes the final integration path precise enough to avoid reintroducing old packet/bridge/verdict authority or committing broad evidence/runtime output while preserving the architecture-slimming work. |

## Added

- `STAGING_REBUILD_PLAN.json` with bucketed include/review/exclude path lists.
- `STAGING_REBUILD_PLAN.md` with the dry-run summary and non-executed rebuild sequence.
- Selected evidence now includes the staging rebuild plan files and Batch 1064 evidence.

## Retained

- Current index remains unchanged and classified as `not_commit_safe_as_is`.
- No direct merge into `/Users/jiangwei/Documents/final`.
- No staging, unstaging, reset, commit, push, deploy, real order, withdrawal, transfer, secret mutation, live profile expansion, order-sizing default expansion, destructive migration, or cleanup of untracked runtime evidence.
- Signal Observation grade, Tradeability Decision, Runtime Safety State, Strategy Asset State, Review Outcome State, Execution Attempt, FinalGate, Operation Layer, RequiredFacts, exchange safety, protection, reconciliation, and settlement remain unchanged.

## Deleted This Batch

- No production code deleted.
- No generated/runtime evidence was destructively cleaned.
- No staged entry was removed.

## Planned Deletion Or Downgrade

- Do not commit the current index as-is.
- After Owner validation, rebuild staging from `STAGING_REBUILD_PLAN.json` in a clean accepted-worktree flow.
- Keep broad historical token-burn evidence and transient runtime output out of default staging unless explicitly accepted as provenance.

## Legacy Fallback Exit Condition

- Future staging rebuild must use the generated include/review/exclude lists, not the pre-existing partial index.
- Future staging must preserve old packet/bridge/verdict deletions and avoid reintroducing active old-name compatibility entrypoints.
- Strict long-goal completion remains unproven under the objective file, so status remains `in_progress`.

## Revalidation

| Check | Result |
| --- | --- |
| include candidates | `704` |
| review candidates | `121` |
| exclude candidates | `1137` |
| include candidate secret-path scan | `0` |
| selected closeout evidence missing | `0` |
| current index safety | `not_commit_safe_as_is` |
| latest full unit | Batch 1062 `3123 passed, 1 skipped, 1 warning in 48.49s` |

## Safety Boundary

No reset, unstaging, staging, commit, push, deploy, real order, withdrawal,
transfer, secret mutation, live profile expansion, sizing default expansion,
destructive migration, or direct mutation of `/Users/jiangwei/Documents/final`
was performed.
