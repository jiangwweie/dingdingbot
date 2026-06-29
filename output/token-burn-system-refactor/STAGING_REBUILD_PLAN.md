# Staging Rebuild Plan - Dry Run

## Status

| Field | Value |
| --- | --- |
| batch | `BATCH_1086` |
| status | `merge_ready_commit_series_clean_verified` |
| include_candidate_count | `727` |
| lean_default_include_count | `695` |
| optional_evidence_count | `32` |
| review_candidate_count | `121` |
| exclude_candidate_count | `1137` |
| include_candidate_secret_path_hits | `0` |
| lean_default_secret_path_hits | `0` |
| selected_evidence_missing | `0` |
| current_index_safety | `rebuilt_from_lean_default_after_owner_validation`; post-Batch-1085 selected evidence added without optional evidence |


## Batch 1083 Owner-Accepted Staging Rebuild

| Field | Value |
| --- | --- |
| owner_validation | `directionally_accepted` |
| staging_source | `lean_default_include_paths` |
| staged_paths | `693/693` |
| optional_evidence_staged | `0` |
| cached_shortstat | `613 files changed, 68569 insertions(+), 29187 deletions(-)` |
| cached_diff_check | passed |
| worktree_diff_check | passed |
| compileall | passed |
| full_unit | `3123 passed, 1 skipped, 1 warning in 52.24s` |
| upstream_sync | `0 0` |
| current_boundary_scans | frontend/static `0`; packet/bridge/verdict top-level scripts `0`; broad residual `19` retained/protected |

## Sequential Commit Delta Rehearsal

| Commit | Delta Shortstat |
| --- | --- |
| `commit1_tracked_core_delta` | `561 files changed, 32709 insertions(+), 63363 deletions(-)` |
| `commit2_untracked_code_replacements_delta` | `112 files changed, 42682 insertions(+)` |
| `commit3_generated_current_artifacts_delta` | `88 files changed, 12710 insertions(+), 4991 deletions(-)` |
| `commit4_minimal_evidence_delta` | `12 files changed, 7143 insertions(+)` |
| `commit5_optional_evidence_delta` | `32 files changed, 60183 insertions(+)` |

Finding: commit2 untracked replacement additions are large and require dedicated review/splitting rather than automatic inclusion after core slimming

## Replacement Feature-Family Delta Rehearsal

Path source: untracked paths in `lean_default_include_paths`, excluding
`output/token-burn-system-refactor` closeout evidence.

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

Finding: replacement additions now have feature-family split evidence. The
largest families, especially `runtime_artifact_evidence_scripts` and
`tests_artifact_evidence_projection`, must be reviewed or split further before
any authorized staging rebuild.

## Large Replacement Subfamily Delta Rehearsal

Path source: the two largest Batch 1068 replacement families,
`runtime_artifact_evidence_scripts` and `tests_artifact_evidence_projection`.

| Subfamily | Paths | Delta Shortstat |
| --- | ---: | --- |
| `deploy_policy_artifacts` | `5` | `5 files changed, 1789 insertions(+)` |
| `first_submit_authorization` | `18` | `18 files changed, 3858 insertions(+)` |
| `observation_shadow_projection` | `22` | `22 files changed, 6419 insertions(+)` |
| `post_submit_review_lifecycle` | `14` | `14 files changed, 3999 insertions(+)` |
| `refresh_artifact_generators` | `3` | `3 files changed, 1862 insertions(+)` |
| `signal_readiness_state` | `14` | `14 files changed, 4595 insertions(+)` |
| `strategygroup_asset_review` | `10` | `10 files changed, 6941 insertions(+)` |

Finding: the `86` paths from the two largest families now have lifecycle
subfamily split evidence. `strategygroup_asset_review` and
`observation_shadow_projection` remain the largest staging risks and must be
staged with focused tests or split again.

## Subfamily Focused-Test Gate

| Subfamily | Status | Result |
| --- | --- | --- |
| `strategygroup_asset_review` | `executed` | `31 passed in 0.15s` |
| `observation_shadow_projection` | `executed` | `73 passed in 1.39s` |
| `signal_readiness_state` | `executed` | `56 passed in 0.54s` |
| `post_submit_review_lifecycle` | `executed` | `40 passed in 0.87s` |
| `first_submit_authorization` | `executed` | `47 passed in 1.88s` |
| `refresh_artifact_generators` | `executed` | `8 passed in 0.30s` |
| `deploy_policy_artifacts` | `executed` | `10 passed in 0.40s` |

Finding: all lifecycle subfamilies now have passing focused-test evidence.
Rerun a subfamily command from `STAGING_REBUILD_PLAN.json` if that subfamily's
path set changes before staging.

## Batch 1074 Commit-Series Subfamily Rehearsal

This rehearsal used a temporary index initialized with `git read-tree HEAD`.
It did not mutate the real index.

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

| Bucket | Count |
| --- | ---: |
| real untracked replacement paths | `112` |
| lifecycle subfamily paths mapped for rehearsal | `83` |
| foundation / small replacement paths | `29` |
| runtime-monitor review bucket paths | `121` |

Finding: future authorized staging should rebuild the commit series from the
full worktree. The current real index stayed unchanged at
`112 files changed, 5228 insertions(+), 3549 deletions(-)` and remains
not commit-safe as-is.

## Batch 1075 Owner Acceptance Entry Refresh

| Field | Value |
| --- | --- |
| selected evidence include count | `53` |
| evidence added | `BATCH_1075_EVIDENCE.md` |
| purpose | Refresh Owner acceptance checklist, dry run, handoff index, long-goal completion audit, and merge-management entry points to the Batch 1074/1075 current state. |
| real index mutation | none |

## Batch 1076 Closeout Metadata Consistency Sweep

| Field | Value |
| --- | --- |
| selected evidence include count | `54` |
| evidence added | `BATCH_1076_EVIDENCE.md` |
| purpose | Clarify current-validation evidence versus historical transcript evidence in Owner-validation metadata. |
| real index mutation | none |

## Batch 1077 Owner Acceptance Command Replay

| Field | Value |
| --- | --- |
| selected evidence include count | `55` |
| evidence added | `BATCH_1077_EVIDENCE.md` |
| purpose | Replay Owner acceptance commands and refresh full-unit baseline. |
| full unit | `3123 passed, 1 skipped, 1 warning in 47.90s` |
| real index mutation | none |

## Batch 1078 Owner Acceptance Baseline Clarity

| Field | Value |
| --- | --- |
| selected evidence include count | `56` |
| evidence added | `BATCH_1078_EVIDENCE.md` |
| purpose | Clarify that Batch 1077 is the latest executed full-unit authority and Batch 1078 is metadata-only closeout evidence. |
| full unit | not rerun; latest remains Batch 1077 `3123 passed, 1 skipped, 1 warning in 47.90s` |
| real index mutation | none |

## Batch 1079 Current Full Unit Refresh

| Field | Value |
| --- | --- |
| selected evidence include count | `57` |
| evidence added | `BATCH_1079_EVIDENCE.md` |
| purpose | Refresh full-unit authority after Batch 1078 metadata repair. |
| full unit | `3123 passed, 1 skipped, 1 warning in 47.82s` |
| real index mutation | none |

## Batch 1080 Upstream Sync And Current-Boundary Rescan

| Field | Value |
| --- | --- |
| selected evidence include count | `58` |
| evidence added | `BATCH_1080_EVIDENCE.md` |
| purpose | Verify fetched upstream still matches local HEAD and current-boundary scans remain clean/protected after Batch 1079. |
| upstream sync | `0 0` |
| full unit | not rerun; latest remains Batch 1079 `3123 passed, 1 skipped, 1 warning in 47.82s` |
| real index mutation | none |

## Batch 1081 Queue Completion Gate Consistency

| Field | Value |
| --- | --- |
| selected evidence include count | `59` |
| evidence added | `BATCH_1081_EVIDENCE.md` |
| purpose | Align completion-gate queue/map artifacts with current validation and current-boundary Operation Layer closure. |
| full unit | not rerun; latest remains Batch 1079 `3123 passed, 1 skipped, 1 warning in 47.82s` |
| real index mutation | none |

## Batch 1082 Current Scope Coverage Map Refresh

| Field | Value |
| --- | --- |
| selected evidence include count | `62` |
| evidence added | `BATCH_1082_EVIDENCE.md`; `CURRENT_SCOPE_COVERAGE_AUDIT.md`; `CURRENT_SCOPE_FILE_CLASSIFICATION.json` |
| purpose | Add current file-level scope classification for objective-root files and downgrade stale Cycle 1 maps to historical/thematic coverage. |
| current non-pyc files | `1012` |
| unknown requires followup | `0` |
| full unit | not rerun; latest remains Batch 1079 `3123 passed, 1 skipped, 1 warning in 47.82s` |
| real index mutation | none |

## Commit Split Gate Not Executed

| Commit | Temporary Shortstat | Sequential Delta | Gate |
| --- | --- | --- | --- |
| `commit_1_tracked_core_slimming` | `561 files changed, 32709 insertions(+), 63363 deletions(-)` | `` | must stay net negative to visibly prove core slimming |
| `commit_2_required_new_code_and_tests` | `581 files changed, 55219 insertions(+), 29187 deletions(-)` | `112 files changed, 42682 insertions(+)` | must be split/reviewed by feature family; do not bulk-stage all untracked replacements after core slimming |
| `commit_3_generated_current_artifacts_optional` | `88 files changed, 12710 insertions(+), 4991 deletions(-)` | `88 files changed, 12710 insertions(+), 4991 deletions(-)` | stage only if generated latest-* artifacts are accepted as current artifacts |
| `commit_4_closeout_evidence_minimal` | `12 files changed, 7092 insertions(+)` | `12 files changed, 7143 insertions(+)` | stage only closeout evidence needed for review; keep broad evidence optional |
| `commit_5_optional_evidence` | `32 files changed, 60133 insertions(+)` | `32 files changed, 60183 insertions(+)` | do not stage by default; Owner-accepted provenance only |

## Rebuild Sequence Not Executed

- Create or use a clean integration worktree from origin/codex/owner-runtime-console-v1 after Owner acceptance.
- Do not reuse the current partial index.
- First rehearse git add -u -- src scripts tests docs/current migrations deploy AGENTS.md and require net-negative staged shortstat.
- Split untracked code/test/doc replacements by feature family; do not bulk-stage all 112 replacement additions at once.
- Split large replacement families again when a family is still evidence-heavy or test-heavy; runtime artifact/evidence scripts and artifact/evidence projection tests are not safe as one bulk replacement commit.
- Use lifecycle subfamily splits for the largest replacement families; do not stage observation/shadow projection or StrategyGroup asset review blobs without focused test pairing.
- Run the focused-test gate for any lifecycle subfamily selected for staging; strategygroup_asset_review and observation_shadow_projection already have Batch 1070 passing evidence.
- Batch 1071 has executed focused-test gates for all lifecycle subfamilies; rerun a subfamily command if its path set changes before staging.
- Batch 1074 rehearses the full temporary-index commit series from tracked core slimming through foundation replacements, lifecycle subfamilies, generated runtime-monitor review artifacts, and minimal closeout evidence; the real index remains unchanged and not commit-safe as-is.
- For each replacement-family commit, run focused tests and staged shortstat review.
- Review generated_current_artifact_review separately; stage only accepted current artifacts.
- Stage minimal closeout evidence only after code/test/doc commit shape is accepted.
- Keep optional_evidence_paths and exclude_paths out of default staging unless Owner explicitly accepts them as provenance.
- Run git diff --cached --shortstat at each commit split and require the core-code reduction to remain visible in the series.
- Run git diff --cached --check, compileall, residual scans, and full unit before commit.

Full path lists are in `STAGING_REBUILD_PLAN.json`.

## Batch 1083 Commit Series Result

- `e29ffcaa refactor: compress strategygroup lifecycle authority`
- `137e1bb8 refactor: add lifecycle state boundaries`
- `f616ed7a refactor: replace lifecycle packet scripts with projections`
- `3a64b80e test: cover lifecycle authority migration`
- `89be59eb docs: record system refactor merge evidence`

```text
expected_lean 693 committed_path_aware 693 missing 0 extra 0 optional_committed 0
613 files changed, 68606 insertions(+), 29187 deletions(-)
```

## Final Clean Verification

```text
clean worktree status -> clean
committed path-aware changes -> 820
optional historical evidence committed -> 0
committed shortstat -> 720 files changed, 78235 insertions(+), 38489 deletions(-)
ahead/behind -> 6 0
git diff --check -> passed
compileall -> passed
top-level packet/bridge/verdict scripts -> 0
broad residual -> 19 retained/protected
full unit -> 3123 passed, 1 skipped, 1 warning
```

## Batch 1086 Post-Commit Metadata Refresh

| Field | Value |
| --- | --- |
| then-current head | `e75d0196` |
| then-current upstream ahead/behind | `8 0` |
| evidence added since Batch 1083 plan | `BATCH_1084_EVIDENCE.md`; `BATCH_1085_EVIDENCE.md`; `BATCH_1086_EVIDENCE.md` |
| include candidates | `727` |
| lean default include paths | `695` |
| optional evidence | `32`, still not default-staged |
| latest full unit | Batch 1088 closeout `3124 passed, 1 skipped, 1 warning in 56.13s` |
| current total branch diff | `722 files changed, 78503 insertions(+), 38518 deletions(-)`; evidence/generated-artifact heavy |
| core slimming gate | tracked-core rehearsal remains `561 files changed, 32709 insertions(+), 63363 deletions(-)` |

## Batch 1088 Final Pointer Repair

| Field | Value |
| --- | --- |
| current head | current local `HEAD`; verify with `git rev-parse --short HEAD` |
| upstream ahead/behind | no behind commits; verify exact count with `git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1` |
| evidence added since Batch 1086 plan refresh | `BATCH_1087_EVIDENCE.md`; `BATCH_1088_EVIDENCE.md` |
| staging policy | Keep using lean default plus selected evidence; optional evidence remains excluded by default. |
| list regeneration status | Path lists were not regenerated in this metadata-only repair; Batch 1086 remains the latest generated path-list authority. |
| latest full unit | Batch 1086 post-staging `3124 passed, 1 skipped, 1 warning in 72.38s` |
| current validation requirement | Re-run diff check, compileall, JSON validation, current-boundary scans, and full unit during final Owner validation if a fresh full-unit proof is required. |

## Batch 1093 Directional Acceptance Guardrail

| Field | Value |
| --- | --- |
| owner_validation | `directionally_accepted` |
| current head | current local `HEAD`; verify with `git rev-parse --short HEAD` |
| upstream ahead/behind | `15 0` after latest fetch |
| staging policy | Continue using `STAGING_REBUILD_PLAN`: lean default plus selected evidence; optional evidence excluded by default. |
| real index policy | Do not reuse an old real index as a commit source. Current source branch is already a local commit series with a clean index. |
| forbidden-action audit | `BATCH_1093_EVIDENCE.md` found no secret literals, no Tokyo apply/probe/snapshot output inclusion, no production true authorization flags, and no direct final-worktree mutation. |
| next validation | If staging/merge is rebuilt in a clean integration worktree, rerun diff check, compileall, current-boundary scans, focused tests as needed, and full unit before final acceptance. |

## Batch 1094 Clean Integration Validation

| Field | Value |
| --- | --- |
| source_head | `eb72fa9a` |
| upstream_head | `7c84b272` |
| merge_rehearsal | automatic merge succeeded in detached clean worktree |
| unmerged_paths | `0` |
| cached_shortstat | `734 files changed, 79681 insertions(+), 38518 deletions(-)` |
| validation | diff check, cached diff check, compileall, staging JSON parse, strict conflict-marker scan, current-boundary scans, and full unit passed |
| full_unit | `3124 passed, 1 skipped, 1 warning in 60.50s` |
| policy | If upstream moves, repeat this clean integration validation before any merge/push decision. |
