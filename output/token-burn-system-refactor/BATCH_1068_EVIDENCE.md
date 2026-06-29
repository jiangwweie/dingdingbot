# Batch 1068 Evidence - Replacement Feature-Family Split Rehearsal

## Batch Acceptance

| Field | Value |
| --- | --- |
| batch_id | `BATCH_1068` |
| closed_engineering_problem | Batch 1067 proved the untracked replacement delta was too large for bulk staging, but it did not classify the `112` replacement additions into reviewable feature-family splits. |
| capability_unlocked | Future staging can review replacement additions by capability family, keeping the core slimming commit visible while preventing artifact/test replacement bulk from hiding the architecture reduction. |
| next_engineering_bottleneck | The largest replacement families still need split-by-family review or explicit staging rebuild authorization; no real staging action was performed. |
| files_changed | `BATCH_1068_EVIDENCE.md`; `STAGING_REBUILD_PLAN.json`; `STAGING_REBUILD_PLAN.md`; latest pointer/queue/final evidence/merge readiness/Owner validation metadata. |
| tests_run | temporary Git index replacement-family rehearsal; `python3 -m json.tool`; `git diff --check`; `python3 -m compileall src scripts tests migrations -q`; upstream sync check; true-index shortstat check. |
| why_this_batch_enables_deeper_refactor | It converts the remaining positive replacement-addition blob into bounded review units, so future commits can preserve the already achieved code slimming instead of adding another opaque compatibility layer or evidence-heavy staging blob. |

## Added

- `replacement_feature_family_delta_rehearsal` in `STAGING_REBUILD_PLAN.json`.
- Feature-family split table in `STAGING_REBUILD_PLAN.md`.
- Gate requiring the largest replacement families to be split/reviewed separately before any authorized staging rebuild.

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

- Do not bulk-stage the `runtime_artifact_evidence_scripts` family.
- Do not bulk-stage the `tests_artifact_evidence_projection` family.
- Keep optional evidence out of default staging unless Owner explicitly accepts provenance bulk.
- Keep old packet/bridge/report/monitor outputs as lifecycle projections or evidence only; they must not regain judgment authority during staging.

## Legacy Fallback Exit Condition

- Future staging rebuild must use the feature-family split in `STAGING_REBUILD_PLAN.json`.
- Commit 1 must remain tracked-core net negative.
- Large replacement families must be reviewed as code/test capability groups, not hidden inside one positive replacement commit.
- Strict long-goal completion remains unproven under the objective file, so status remains `in_progress`.

## Replacement Feature-Family Rehearsal

| Family | Paths | Delta Shortstat |
| --- | ---: | --- |
| `application_artifact_projection_helpers` | `1` | `1 file changed, 136 insertions(+)` |
| `application_readmodel_helpers` | `2` | `2 files changed, 190 insertions(+)` |
| `docs_current_contracts` | `1` | `1 file changed, 250 insertions(+)` |
| `domain_state_models` | `4` | `4 files changed, 1318 insertions(+)` |
| `execution_boundary` | `2` | `2 files changed, 1332 insertions(+)` |
| `interfaces_review_projection` | `1` | `1 file changed, 19 insertions(+)` |
| `migration_schema` | `1` | `1 file changed, 109 insertions(+)` |
| `runtime_artifact_evidence_scripts` | `43` | `43 files changed, 17706 insertions(+)` |
| `runtime_ops_support_scripts` | `2` | `2 files changed, 933 insertions(+)` |
| `scripts_other` | `2` | `2 files changed, 704 insertions(+)` |
| `strategygroup_core_state_builders` | `3` | `3 files changed, 3880 insertions(+)` |
| `tests_artifact_evidence_projection` | `43` | `43 files changed, 11757 insertions(+)` |
| `tests_core_state` | `3` | `3 files changed, 3879 insertions(+)` |
| `tests_other` | `3` | `3 files changed, 381 insertions(+)` |
| `tests_support_regression` | `1` | `1 file changed, 88 insertions(+)` |

## Revalidation

| Check | Result |
| --- | --- |
| replacement path count after excluding `output/token-burn-system-refactor/` | `112` |
| replacement family insertion total | `42682` |
| commit2 sequential delta cross-check | `112 files changed, 42682 insertions(+)` |
| `STAGING_REBUILD_PLAN.json` count consistency | include `708/708`; lean `676/676`; optional `32/32`; review `121/121`; exclude `1137/1137`; selected evidence summary `47` |
| `python3 -m json.tool output/token-burn-system-refactor/STAGING_REBUILD_PLAN.json` | passed |
| `git diff --check` | passed |
| `python3 -m compileall src scripts tests migrations -q` | passed |
| upstream sync | `0 0` |
| real current index diff before validation | `112 files changed, 5228 insertions(+), 3549 deletions(-)` |
| real index safety | `not_commit_safe_as_is` |
| latest full unit | Batch 1062 `3123 passed, 1 skipped, 1 warning in 48.49s` |

## Safety Boundary

No reset, unstaging, staging, commit, push, deploy, real order, withdrawal,
transfer, secret mutation, live profile expansion, sizing default expansion,
destructive migration, or direct mutation of `/Users/jiangwei/Documents/final`
was performed.
