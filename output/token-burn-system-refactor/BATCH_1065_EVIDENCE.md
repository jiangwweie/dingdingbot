# Batch 1065 Evidence - Temporary Index Size Rehearsal

## Batch Acceptance

| Field | Value |
| --- | --- |
| batch_id | `BATCH_1065` |
| closed_engineering_problem | `STAGING_REBUILD_PLAN.json` was machine-readable, but it had not been rehearsed through a temporary Git index. The first rehearsal showed that blindly staging include paths would create a large positive staged diff, masking the architecture-slimming result. |
| capability_unlocked | Staging rebuild now has an explicit size-risk guardrail: use a lean default path set and keep large evidence files optional unless Owner explicitly accepts evidence bulk. |
| next_engineering_bottleneck | Owner validation / explicit staging rebuild authorization remains the bottleneck; future staging must preserve architecture slimming and line-size visibility. |
| files_changed | `BATCH_1065_EVIDENCE.md`; `STAGING_REBUILD_PLAN.json`; `STAGING_REBUILD_PLAN.md`; `STAGING_COMMIT_MANIFEST.md`; latest pointer/queue/final evidence/merge readiness/Owner validation metadata. |
| tests_run | temporary Git index rehearsal for full include plan; temporary Git index rehearsal for lean default plan; path-family shortstat audit; `git diff --check`; true-index shortstat check. |
| why_this_batch_enables_deeper_refactor | It prevents the final integration artifact from turning a code-slimming refactor into a bloated evidence-heavy commit and creates a concrete guardrail for preserving visible line reduction. |

## Added

- Temporary-index rehearsal result for full include plan.
- Temporary-index rehearsal result for lean default plan.
- Explicit line-size risk finding.
- Requirement that future staging keep large evidence optional and run staged shortstat before commit.

## Retained

- Current real index remains unchanged and classified as `not_commit_safe_as_is`.
- No direct merge into `/Users/jiangwei/Documents/final`.
- No staging, unstaging, reset, commit, push, deploy, real order, withdrawal, transfer, secret mutation, live profile expansion, order-sizing default expansion, destructive migration, or cleanup of untracked runtime evidence.
- Signal Observation grade, Tradeability Decision, Runtime Safety State, Strategy Asset State, Review Outcome State, Execution Attempt, FinalGate, Operation Layer, RequiredFacts, exchange safety, protection, reconciliation, and settlement remain unchanged.

## Deleted This Batch

- No production code deleted.
- No generated/runtime evidence was destructively cleaned.
- No staged entry was removed.

## Planned Deletion Or Downgrade

- Do not use the full include plan as a single default commit if it makes staged shortstat positive.
- Keep `RESUME_PACKET.md`, `PROGRESS_LEDGER.md`, and broad historical evidence optional unless explicitly accepted.
- Future authorized staging must use lean default paths first, then decide generated/current artifacts and evidence in separate reviewed commits.

## Legacy Fallback Exit Condition

- Future staging rebuild must run a temporary-index or clean-worktree staged shortstat before commit.
- The accepted default commit set should preserve visible architecture slimming; evidence/provenance bulk must not hide code reduction.
- Strict long-goal completion remains unproven under the objective file, so status remains `in_progress`.

## Revalidation

| Check | Result |
| --- | --- |
| full include temporary index | `624 files changed, 121581 insertions(+), 29187 deletions(-)` |
| lean default temporary index | `592 files changed, 61499 insertions(+), 29187 deletions(-)` |
| final plan include candidates | `705` |
| final plan lean default paths | `673` |
| final plan optional evidence paths | `32` |
| final plan review candidates | `121` |
| final plan exclude candidates | `1137` |
| final plan include secret-path scan | `0` |
| final plan selected evidence missing | `0` |
| tracked source/docs/tests shortstat | `549 files changed, 31991 insertions(+), 57505 deletions(-)` |
| tracked `output/runtime-monitor` shortstat | `47 files changed, 4110 insertions(+), 10274 deletions(-)` |
| real current index diff | `112 files changed, 5228 insertions(+), 3549 deletions(-)` |
| real index safety | `not_commit_safe_as_is` |
| upstream sync | `0 0` |
| latest full unit | Batch 1062 `3123 passed, 1 skipped, 1 warning in 48.49s` |

## Safety Boundary

No reset, unstaging, staging, commit, push, deploy, real order, withdrawal,
transfer, secret mutation, live profile expansion, sizing default expansion,
destructive migration, or direct mutation of `/Users/jiangwei/Documents/final`
was performed.
