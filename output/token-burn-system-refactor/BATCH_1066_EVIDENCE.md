# Batch 1066 Evidence - Commit Split Line-Size Gate

## Batch Acceptance

| Field | Value |
| --- | --- |
| batch_id | `BATCH_1066` |
| closed_engineering_problem | Batch 1065 found positive staged-diff risk, but the staging plan still needed a concrete commit split gate that preserves visible core-code slimming before adding replacements, generated artifacts, or evidence. |
| capability_unlocked | Future staging can start with a net-negative tracked core commit, then add necessary replacements and evidence under explicit staged shortstat gates. |
| next_engineering_bottleneck | Owner validation / explicit staging rebuild authorization remains the bottleneck; no real staging action was performed. |
| files_changed | `BATCH_1066_EVIDENCE.md`; `STAGING_REBUILD_PLAN.json`; `STAGING_REBUILD_PLAN.md`; `STAGING_COMMIT_MANIFEST.md`; latest pointer/queue/final evidence/merge readiness/Owner validation metadata. |
| tests_run | temporary Git index rehearsals for tracked core, core without evidence, full include, lean default, generated artifacts, minimal evidence, optional evidence; `python3 -m json.tool`; `git diff --check`; true-index shortstat check. |
| why_this_batch_enables_deeper_refactor | It turns the Owner's code-size requirement into an enforceable staging gate: the first integration commit must visibly preserve core slimming before optional evidence can enter. |

## Added

- Commit split gate in `STAGING_REBUILD_PLAN.json` / `.md`.
- Temporary-index proof that tracked core-only staging is net negative.
- Explicit separation between core slimming, necessary replacements, generated artifacts, minimal closeout evidence, and optional evidence.

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

- Future authorized staging should not stage broad evidence first.
- Future authorized staging should start with tracked core slimming and require net-negative staged shortstat.
- Optional evidence remains out of default staging unless Owner explicitly accepts provenance bulk.

## Legacy Fallback Exit Condition

- Future staging rebuild must use the commit split gate in `STAGING_REBUILD_PLAN.json`.
- The accepted default commit series must keep core-code reduction visible before evidence/provenance additions.
- Strict long-goal completion remains unproven under the objective file, so status remains `in_progress`.

## Revalidation

| Check | Result |
| --- | --- |
| tracked core-only temporary index | `561 files changed, 32709 insertions(+), 63363 deletions(-)` |
| core no-evidence temporary index | `581 files changed, 55219 insertions(+), 29187 deletions(-)` |
| full include temporary index | `624 files changed, 121581 insertions(+), 29187 deletions(-)` |
| lean default temporary index | `592 files changed, 61499 insertions(+), 29187 deletions(-)` |
| generated current artifacts temporary index | `88 files changed, 12710 insertions(+), 4991 deletions(-)` |
| minimal evidence temporary index | `12 files changed, 7092 insertions(+)` |
| optional evidence temporary index | `32 files changed, 60133 insertions(+)` |
| `STAGING_REBUILD_PLAN.json` validation | passed |
| real current index diff | `112 files changed, 5228 insertions(+), 3549 deletions(-)` |
| real index safety | `not_commit_safe_as_is` |
| upstream sync | `0 0` |
| latest full unit | Batch 1062 `3123 passed, 1 skipped, 1 warning in 48.49s` |

## Safety Boundary

No reset, unstaging, staging, commit, push, deploy, real order, withdrawal,
transfer, secret mutation, live profile expansion, sizing default expansion,
destructive migration, or direct mutation of `/Users/jiangwei/Documents/final`
was performed.
