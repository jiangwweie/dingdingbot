# Branch Merge Management Plan

## Status

| Field | Value |
| --- | --- |
| plan_status | `directionally_accepted_staging_closeout_pending` |
| source_worktree | `/Users/jiangwei/Documents/final-system-refactor-20260623` |
| source_branch | `codex/system-refactor-20260623` |
| upstream | `origin/codex/owner-runtime-console-v1` |
| source_head | current local `HEAD`; verify with `git rev-parse --short HEAD` |
| upstream_head | `7c84b272` |
| upstream_sync_after_fetch | no behind commits; verify with `git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1` |
| latest_post_fetch_verification | latest full unit authority is clean integration worktree `BATCH_1094_EVIDENCE.md`; latest current-entry pointer repair is `BATCH_1092_EVIDENCE.md`; latest forbidden-action diff audit is `BATCH_1093_EVIDENCE.md`; latest no-final merge rehearsal is `BATCH_1089_EVIDENCE.md`; latest clean integration worktree rehearsal is `BATCH_1094_EVIDENCE.md`; latest temporary-index staging rehearsal remains `BATCH_1074_EVIDENCE.md`; optional evidence remains out of default staging |
| commit_status | `local_commit_series_created_not_pushed` |
| index_status | `clean_after_selected_path_commit`; do not reuse obsolete broad partial index |
| push_status | `not_pushed` |
| deploy_status | `not_deployed` |
| final_worktree_mutation | `forbidden` |

## Current Branch Fact

`codex/system-refactor-20260623` contains the accepted local commit series on
top of the current upstream head:

```text
git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1
<local ahead count>	0

git log --oneline -1 HEAD
<current short HEAD> <latest local closeout commit>

git log --oneline -1 origin/codex/owner-runtime-console-v1
7c84b272 fix(strategygroup): harden trial-grade standby readiness
```

The system-refactor work exists as local commits on top of that upstream head:

```text
722 files changed, 78503 insertions(+), 38518 deletions(-)
core slimming gate: tracked-core rehearsal 32709 insertions / 63363 deletions
```

## Merge Principle

Do not merge by mutating `/Users/jiangwei/Documents/final` directly. That
worktree has external modified/untracked runtime and output state. Treat it as
Owner/runtime state, not as the integration scratch area.

Use a clean integration worktree after Owner validation.

## Recommended Sequence

| Step | Command / Action | Acceptance |
| --- | --- | --- |
| 1 | Review `OWNER_VALIDATION_AUDIT.md`, `FINAL_EVIDENCE_PACKET.md`, `BATCH_1085_EVIDENCE.md`, `BATCH_1086_EVIDENCE.md`, `BATCH_1093_EVIDENCE.md`, and `STAGING_REBUILD_PLAN.md`. | Branch isolation, diff shape, residual policy, main-chain invariants, selected evidence, staging policy, forbidden-action audit, and latest full-unit validation pass. |
| 2 | Optional: re-run `python3 -m pytest tests/unit -q`. | Latest recorded full unit is Batch 1094 clean integration worktree: `3124 passed, 1 skipped, 1 warning in 60.50s`. |
| 3 | Do not stage optional evidence by default. | No accidental cleanup or bulk inclusion of untracked runtime evidence. |
| 4 | Use existing local commits on `codex/system-refactor-20260623`. | Commit series already exists locally and is not pushed. |
| 5 | Create a clean integration worktree from fresh upstream. | `/Users/jiangwei/Documents/final` remains untouched. |
| 6 | Re-run no-final merge rehearsal if upstream moves. | Batch 1089 proves the current series merges cleanly against upstream `7c84b272`; any new upstream commit requires repeating this check before integration. |
| 7 | Re-run clean worktree merge rehearsal if upstream moves. | Batch 1090 proves a detached upstream worktree can merge source head `c8527a40` with unmerged paths `0`; any new upstream commit requires repeating this check before integration. |
| 8 | Re-run clean merged full unit if upstream moves. | Batch 1094 proves a detached upstream worktree can merge source head `eb72fa9a` and pass full unit; any new upstream commit requires repeating this check before integration. |
| 9 | Merge or cherry-pick the accepted commit(s) into the clean integration worktree. | Conflicts resolved without reintroducing packet/bridge/frontend authority. |
| 10 | Re-run acceptance checklist in the integration worktree. | `git diff --check`, compileall, residual policy, focused tests as needed, and full unit pass. |
| 11 | Keep no-go actions out of this branch. | No push/deploy/real-order/live-profile/sizing/secret action occurs inside this closeout branch. |

## Suggested Clean Integration Commands

These commands are intentionally not executed in this closeout pass:

```bash
cd /Users/jiangwei/Documents/final-system-refactor-20260623
git fetch origin
git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1

# after Owner accepts and commits exist:
git worktree add /Users/jiangwei/Documents/final-system-refactor-integration \
  -b codex/system-refactor-integration-YYYYMMDD \
  origin/codex/owner-runtime-console-v1

cd /Users/jiangwei/Documents/final-system-refactor-integration
git merge --no-ff codex/system-refactor-20260623
```

If the source branch remains uncommitted at validation time, do not commit the
existing index as-is. Current index state is not empty: `112 files changed,
5228 insertions(+), 3549 deletions(-)`, and Batch 1060 classifies it as a
partial pre-existing staged subset that still contains old `packet/bridge/verdict`
paths. Rebuild staging from the accepted full worktree after Owner validation.
Do not use `/Users/jiangwei/Documents/final` as the staging area.

## Architecture Preservation Checks During Merge

| Check | Required Result |
| --- | --- |
| Tradeability source | `Tradeability Decision` remains the only can-trade readmodel. |
| Runtime safety source | `Runtime Safety State` remains the live-submit readiness / safety authority. |
| Main lifecycle object | `Execution Attempt` remains the real lifecycle entry object. |
| Packet / bridge / report / monitor | Projection or evidence only; no judgment authority. |
| FinalGate / Operation Layer / RequiredFacts | Preserved; no bypass. |
| Exchange safety / protection / reconciliation / settlement | Preserved; no regression. |
| Residual scan | `19` retained/protected hits unless an explicit dedicated migration is accepted. |
| Code size | Net reduction remains visible; avoid adding compatibility layers that erase slimming gains. |
| Active packet entrypoints | Top-level packet/bridge/verdict script scan remains `0`; do not reintroduce packet-named compatibility shims. |
| Reconciliation orphan import | Do not reintroduce fake `IMPORTED_TO_DB`; orphan entry import authority requires a real repository import contract. |
| Owner validation dry-run | Batch 1058 scans remain clean: frontend/static `0`, top-level packet/bridge/verdict scripts `0`, production Owner-action legacy fields `0`, production/runtime `real_order_authority=true` `0`. |
| Closeout consistency | Batch 1061 confirms post-fetch upstream sync remains `0 0`, tracked diff remains net `-31678`, current index remains unchanged and not commit-safe as-is, and no staging/commit/push/deploy/main-worktree mutation occurred. |
| Latest full-unit validation | Batch 1072 confirms post-subfamily full unit `3123 passed, 1 skipped, 1 warning in 54.73s`, compileall passed, diff check passed, and upstream sync remains `0 0`. |
| Latest Owner-validation rescan | Batch 1073 confirms frontend/static `0`, packet/bridge/verdict entrypoints `0`, Owner-action legacy `0`, real-order authority true `0`, and broad residual `19` retained/protected. |
| Latest staging rehearsal | Batch 1074 confirms temporary-index commit-series rehearsal is executable and the real index remains unchanged / not commit-safe as-is. |
| Latest forbidden-action audit | Batch 1093 confirms secret literals `0`, Tokyo/runtime apply/probe/snapshot output paths `0`, production true authorization flags `0`, and true-flag hits are negative tests or forbidden-source evidence. |
| Latest clean integration validation | Batch 1094 confirms clean merge into upstream `7c84b272`, unmerged paths `0`, strict conflict markers `0`, compileall/current-boundary scans passed, and full unit `3124 passed, 1 skipped, 1 warning in 60.50s`. |

## No-Go

- No direct merge into `/Users/jiangwei/Documents/final`.
- No push before Owner acceptance.
- No deploy.
- No real order.
- No secret or credential mutation.
- No live profile expansion.
- No order sizing default expansion.
- No destructive migration.
- No cleanup of untracked output/runtime evidence during validation.
