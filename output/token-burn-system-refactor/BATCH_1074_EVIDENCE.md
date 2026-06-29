# Batch 1074 Evidence - Temporary Index Commit-Series Rehearsal

## Summary

| Field | Value |
| --- | --- |
| batch | `BATCH_1074` |
| status | `in_progress_not_completed` |
| closed_engineering_problem | The prepared branch had focused-test gates and path-family splits, but still lacked an executable temporary-index commit-series rehearsal proving that the large architecture-slimming diff can be staged in reviewable order without reusing the unsafe real index. |
| capability_unlocked | `commit_series_rehearsal_ready`: an authorized future staging rebuild can start with visible tracked core slimming, then add foundation replacements, lifecycle subfamilies, generated runtime-monitor review artifacts, and minimal closeout evidence as separate gates. |
| next_engineering_bottleneck | Owner validation / explicit staging rebuild authorization; the real index remains partial and not commit-safe as-is. |

## Scope

| Item | Value |
| --- | --- |
| worktree | `/Users/jiangwei/Documents/final-system-refactor-20260623` |
| branch | `codex/system-refactor-20260623` |
| upstream | `origin/codex/owner-runtime-console-v1` |
| upstream sync before rehearsal | `0 0` |
| temporary index only | yes |
| real staging mutated | no |
| deploy / push / commit / real order | not performed |

## Temporary Index Path Classification

| Bucket | Count | Meaning |
| --- | ---: | --- |
| real untracked replacement paths | `112` | Replacement code/docs/tests visible from the current real index. |
| lifecycle subfamily paths | `83` | Paths mapped from focused test gates into executable lifecycle staging groups. |
| foundation / small replacement paths | `29` | Typed contracts, state builders, domain/readmodel helpers, migration, monitor/profile helpers, and support tests staged before lifecycle artifact groups. |
| runtime-monitor review bucket | `121` | Generated/provenance review paths from `STAGING_REBUILD_PLAN.json`; not default code authority. |

## Commit-Series Rehearsal

The rehearsal used `GIT_INDEX_FILE=/tmp/codex-batch1074-index.*`, initialized
with `git read-tree HEAD`. The real index remained unchanged.

| Step | Temporary Staged Shortstat |
| --- | --- |
| `baseline` | `0 files changed` |
| `tracked_core_slimming` | `561 files changed, 32709 insertions(+), 63363 deletions(-)` |
| `foundation_and_small_replacements` | `576 files changed, 40171 insertions(+), 57080 deletions(-)` |
| `strategygroup_asset_review` | `578 files changed, 42173 insertions(+), 52141 deletions(-)` |
| `observation_shadow_projection` | `581 files changed, 44441 insertions(+), 47838 deletions(-)` |
| `signal_readiness_state` | `582 files changed, 45217 insertions(+), 44517 deletions(-)` |
| `post_submit_review_lifecycle` | `585 files changed, 46128 insertions(+), 41609 deletions(-)` |
| `first_submit_authorization` | `593 files changed, 47755 insertions(+), 39378 deletions(-)` |
| `refresh_artifact_generators` | `593 files changed, 47905 insertions(+), 37666 deletions(-)` |
| `deploy_policy_artifacts` | `593 files changed, 48173 insertions(+), 36145 deletions(-)` |
| `generated_runtime_monitor_review_bucket` | `707 files changed, 64392 insertions(+), 43503 deletions(-)` |
| `minimal_closeout_evidence` | `727 files changed, 72479 insertions(+), 43503 deletions(-)` |

## Real Index Safety Check

| Check | Result |
| --- | --- |
| real index after temporary rehearsal | `112 files changed, 5228 insertions(+), 3549 deletions(-)` |
| result | unchanged |
| interpretation | Batch 1074 did not run real `git add`, `git reset`, `git commit`, or `git push`; future staging must rebuild from the full worktree using a fresh/temporary index or an explicitly authorized real staging pass. |

## Add / Retain / Delete Plan

| Field | Value |
| --- | --- |
| added | Executable temporary-index commit-series rehearsal for the current architecture-slimming branch. |
| retained | Tradeability Decision, Runtime Safety State, Strategy Asset State, Review Outcome State, Execution Attempt, FinalGate, Operation Layer, RequiredFacts, exchange safety, protection, reconciliation, settlement, live profile, sizing defaults, secrets, deploy, push, and real orders. |
| deleted | none; this is a merge/staging safety batch and does not change production code. |
| planned deletion | Legacy packet/bridge/verdict/report/monitor authority remains demoted; further physical deletion is only for concrete Owner-validation regressions or dedicated migration branches. |

## Why This Enables Deeper Refactor Closeout

This batch converts the previous family/subfamily analysis into an executable
commit-series rehearsal. It proves the branch can preserve the visible core
code reduction first, then add typed state/replacement surfaces by lifecycle
boundary. That keeps the refactor aligned with the requested main chain:

```text
Strategy Asset State
-> Tradeability Decision
-> Runtime Safety State
-> Execution Attempt
-> Review Outcome State
```

Packets, bridges, reports, and monitors remain evidence/projection buckets, not
judgment authorities.

## Tests And Checks

| Command / Check | Result |
| --- | --- |
| temporary-index commit-series rehearsal | passed |
| real-index post-check | unchanged at `112 files changed, 5228 insertions(+), 3549 deletions(-)` |
| `python3 -m json.tool output/token-burn-system-refactor/STAGING_REBUILD_PLAN.json` | passed |
| staging-plan count consistency | include `714/714`; lean `682/682`; optional `32/32`; `commit_series_subfamily_rehearsal.status=executed_temporary_index_only` |
| `git diff --check` | passed |
| `python3 -m compileall src scripts tests migrations -q` | passed |
| `git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1` | `0 0` |
| full tracked diff | `597 files changed, 36104 insertions(+), 67782 deletions(-)` |
| latest full unit baseline | Batch 1072: `3123 passed, 1 skipped, 1 warning in 54.73s` |
| latest Owner-validation rescan | Batch 1073: frontend/static `0`; active top-level packet/bridge/verdict entrypoints `0`; Owner-action legacy `0`; `real_order_authority=true` `0`; broad residual `19` retained/protected |
