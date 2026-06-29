# Batch 1070 Evidence - Subfamily Focused-Test Gate Rehearsal

## Batch Acceptance

| Field | Value |
| --- | --- |
| batch_id | `BATCH_1070` |
| closed_engineering_problem | Batch 1069 split the largest replacement families into lifecycle subfamilies, but the largest subfamilies still needed focused-test gates before any authorized staging rebuild. |
| capability_unlocked | Future staging can pair large lifecycle subfamilies with focused tests instead of relying only on line-count rehearsal. |
| next_engineering_bottleneck | Owner validation / explicit staging rebuild authorization remains the bottleneck; smaller subfamilies still need focused-test execution if they become staging commits. |
| files_changed | `BATCH_1070_EVIDENCE.md`; `STAGING_REBUILD_PLAN.json`; `STAGING_REBUILD_PLAN.md`; latest pointer/queue/final evidence/merge readiness/Owner validation metadata. |
| tests_run | `strategygroup_asset_review` focused tests; `observation_shadow_projection` focused tests; `python3 -m json.tool`; `git diff --check`; `python3 -m compileall src scripts tests migrations -q`; upstream sync check; true-index shortstat check. |
| why_this_batch_enables_deeper_refactor | It turns the largest staging risks from passive line-count warnings into executable verification gates tied to Strategy Asset and observation/shadow lifecycle semantics. |

## Added

- `subfamily_focused_test_gate` in `STAGING_REBUILD_PLAN.json`.
- Focused-test gate table in `STAGING_REBUILD_PLAN.md`.
- Actual focused-test proof for the two largest subfamilies.

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

- Do not stage a large lifecycle subfamily unless its focused-test gate is run in the same staging preparation pass.
- Do not use generated artifacts, packet/bridge/report/monitor outputs, or evidence scripts as judgment authority.
- Keep the first real staging split as tracked-core net negative before any replacement subfamily staging.

## Legacy Fallback Exit Condition

- Future staging rebuild must run the focused command for any subfamily selected for staging.
- `strategygroup_asset_review` and `observation_shadow_projection` now have passing focused-test evidence.
- Strict long-goal completion remains unproven under the objective file, so status remains `in_progress`.

## Focused-Test Gate Results

| Subfamily | Status | Command | Result |
| --- | --- | --- | --- |
| `strategygroup_asset_review` | `executed` | `python3 -m pytest tests/unit/test_strategy_group_handoff_intake_artifact.py tests/unit/test_strategy_group_live_facts_readiness_artifact.py tests/unit/test_strategygroup_btpc_l2_keep_revise_fact_source_review.py tests/unit/test_strategygroup_capital_trial_envelope_projection.py tests/unit/test_strategygroup_opportunity_review_work_loop.py -q` | `31 passed in 0.15s` |
| `observation_shadow_projection` | `executed` | `python3 -m pytest tests/unit/test_runtime_controlled_tiny_live_readiness_projection.py tests/unit/test_runtime_controlled_tiny_live_readiness_to_local_cycle_proof.py tests/unit/test_runtime_controlled_tiny_live_readiness_to_preflight_proof.py tests/unit/test_runtime_live_attempt_readiness_artifact.py tests/unit/test_runtime_live_continuation_selector_projection.py tests/unit/test_runtime_live_signal_shadow_planning_projection.py tests/unit/test_runtime_no_signal_diagnostic_evidence.py tests/unit/test_runtime_observation_operator_evidence.py tests/unit/test_runtime_observation_wakeup_evidence.py tests/unit/test_runtime_persisted_draft_source_readiness_adapter.py tests/unit/test_strategygroup_non_executing_projection.py -q` | `73 passed in 1.39s` |
| `signal_readiness_state` | `required_before_staging` | `python3 -m pytest tests/unit/test_p0_fresh_signal_cutover_hardening_artifact.py tests/unit/test_required_facts_readiness.py tests/unit/test_runtime_fresh_attempt_readiness_projection.py tests/unit/test_runtime_fresh_signal_readiness_evidence.py tests/unit/test_runtime_readiness_state.py tests/unit/test_runtime_strategy_required_facts_readiness_artifact.py tests/unit/test_runtime_strategy_signal_input_artifact_script.py tests/unit/test_runtime_strategy_signal_watch_evidence.py -q` | `not_run_this_batch` |
| `post_submit_review_lifecycle` | `required_before_staging` | `python3 -m pytest tests/unit/test_runtime_closed_trade_review_facts_artifact_script.py tests/unit/test_runtime_coverage_review_evidence.py tests/unit/test_runtime_post_close_followup_artifact_script.py tests/unit/test_runtime_live_closure_evidence_artifact.py tests/unit/test_runtime_position_lifecycle_exit_readiness_artifact.py tests/unit/test_brc_review_storage_compatibility_repository.py tests/unit/test_runtime_semantic_review_artifact.py -q` | `not_run_this_batch` |
| `first_submit_authorization` | `required_before_staging` | `python3 -m pytest tests/unit/test_runtime_first_real_submit_action_authorization_evidence.py tests/unit/test_runtime_first_real_submit_exchange_arm_authorization_evidence.py tests/unit/test_runtime_first_real_submit_final_review_artifact.py tests/unit/test_runtime_first_real_submit_local_registration_authorization_evidence.py tests/unit/test_runtime_first_real_submit_owner_evidence.py tests/unit/test_runtime_official_submit_action_time_evidence_verifier.py tests/unit/test_runtime_next_attempt_submit_preparation_evidence_verifier.py tests/unit/test_runtime_submit_rehearsal_pre_live_evidence.py tests/unit/test_runtime_next_attempt_gate_evidence.py -q` | `not_run_this_batch` |
| `refresh_artifact_generators` | `required_before_staging` | `python3 -m pytest tests/unit/test_refresh_runtime_live_closure_evidence_artifacts.py -q` | `not_run_this_batch` |
| `deploy_policy_artifacts` | `required_before_staging` | `python3 -m pytest tests/unit/test_tokyo_runtime_governance_owner_deploy_policy_artifact.py tests/unit/test_tokyo_runtime_governance_postdeploy_acceptance_evidence.py -q` | `not_run_this_batch` |

## Revalidation

| Check | Result |
| --- | --- |
| largest subfamilies with executed focused tests | `2` |
| executed focused-test total | `104 passed` |
| `STAGING_REBUILD_PLAN.json` count consistency | include `710/710`; lean `678/678`; optional `32/32`; selected evidence summary `49` |
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
