# StrategyGroup Runtime Pilot Checkpoint - 6614ea38

Date: 2026-06-15
Status: CURRENT_CHECKPOINT

## Scope

This checkpoint records the current StrategyGroup Runtime Pilot state after:

- selective watcher-branch carryover review;
- action-time resume contract implementation;
- standing-authorization deploy apply;
- Tokyo postdeploy verification;
- signed GET-only live fact refresh;
- StrategyGroup Pilot Status refresh.

Workspace and branch:

- Workspace: `/Users/jiangwei/Documents/final`
- Branch: `codex/strategygroup-runtime-pilot`
- Runtime code head: `6614ea3841b85bd0a1c530d8f908798d56ca2913`

## Watcher Branch Carryover Decision

Do not merge `codex/runtime-signal-watcher-feishu` wholesale into the pilot
branch. That side branch contains a large docs archive/delete reset and must
remain a separate docs integration item.

Useful P0 watcher/runtime content is already present in this pilot branch,
primarily through earlier focused commits such as:

- `7adf19e9` - propagate watcher auto resume standing authorization;
- `71a2eab1` - add strategygroup pilot control board;
- `115232f1` - add watcher readiness resume console;
- `419f272a` - include watcher scope in resume pack;
- `594fa558` - surface prepared signal evidence in pilot status.

Current additional commit:

- `6614ea38` - add `action_time_resume` as the machine-readable resume contract
  between watcher packets, Pilot Status, action-time `FinalGate`, and the
  official `Operation Layer`.

The docs reset/compression work from the watcher branch is intentionally not
merged here.

## Tokyo Deployment

Current Tokyo deployment:

- Release path:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6614ea38-20260615-action-time-resume-contract`
- Deployed head:
  `6614ea3841b85bd0a1c530d8f908798d56ca2913`
- Previous deployed head:
  `594fa55883e85beac5b93791d8b954ac691262ac`
- Branch in release manifest:
  `codex/strategygroup-runtime-pilot`
- Migration count:
  `84`
- Latest migration:
  `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`
- Backend service:
  `active`
- Watcher timer:
  `active`

Deployment apply result:

- Report:
  `output/strategygroup-runtime-pilot/deploy-6614ea38/deploy-apply-report.json`
- `status=applied`
- `blockers=[]`
- `commands_executed=16`
- `remote_mutation_authorized_by=owner-standing-authorization:strategygroup-runtime-pilot:2026-06-14`
- `remote_mutation_confirmation_phrase_required=false`

Deployment effects were bounded:

- `database_backup_created=true`
- `migrations_run=true`
- `services_restarted=true`
- `exchange_called=false`
- `execution_intent_created=false`
- `order_created=false`
- `order_lifecycle_called=false`
- `secrets_read_by_codex=false`

Postdeploy acceptance:

- Report:
  `output/strategygroup-runtime-pilot/deploy-6614ea38/postdeploy-acceptance-packet.json`
- `status=postdeploy_acceptance_ready`
- `blockers=[]`
- warning:
  `release_identity_from_manifest_without_git_status`

## Live Fact Refresh

Postdeploy signed GET-only live facts were refreshed on Tokyo:

- Facts:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategy-group-live-facts-readonly-6614ea38.json`
- Readiness:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategy-group-live-facts-readiness-6614ea38.json`

Read-only account facts:

- `facts_status=ready`
- `account.status=fresh`
- `account.can_trade=true`
- `active_position.status=no_active_position`
- `active_position.active_count=0`
- `active_position.active_symbols=[]`
- `open_orders.status=no_open_orders`
- `open_orders.open_order_count=0`
- `open_orders.open_order_symbols=[]`
- `collector_errors={}`

Read-only safety invariants:

- `signed_get_only=true`
- `exchange_write_called=false`
- `execution_intent_created=false`
- `order_created=false`
- `order_lifecycle_called=false`
- `runtime_budget_mutated=false`
- `withdrawal_or_transfer_created=false`
- `secrets_printed=false`

Live-facts readiness:

- `status=strategy_group_observe_ready_armed_blocked`
- `observe_ready=5`
- `armed_candidate_prepare_ready=0`
- `can_continue_observation=true`
- `can_prepare_fresh_candidate=false`
- `next_gate=wait_for_or_generate_fresh_strategy_signal`
- `requires_action_time_final_gate_before_submit=true`
- `requires_official_operation_layer=true`

The armed-candidate blockers are candidate-specific `protection`, `budget`, and
`next_attempt_gate` facts. They are expected to resolve only after a fresh signal
exists and the candidate path can build candidate-specific evidence.

## Watcher State

Tokyo watcher service is scoped to the StrategyGroup Runtime Pilot runtime set:

- `strategy-runtime-3a25a46a535f`
- `strategy-runtime-579e407cc03a`
- `strategy-runtime-93353f4cf30e`

Latest manual postdeploy watcher tick:

- service status: `status=0/SUCCESS`
- `wakeup-packet.status=operator_packet_needs_review`
- `active_runtime_count=6`
- `monitored_runtime_count=3`
- `runtime_ready_signal_count=0`
- `strategy_group_would_enter_signal_count=0`
- `shadow_candidate_id=null`
- `prepared_authorization_id=null`

Latest resume pack:

- Path:
  `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json`
- `status=operator_packet_needs_review`
- blockers are only:
  `strategy_signal_not_ready_for_shadow_candidate_prepare` for the three scoped
  MPG runtimes.

## Action-Time Resume Contract

The current `action_time_resume` state is:

- `status=waiting_for_market`
- `next_step=continue_watcher_observation`
- `allowed_auto_actions=[continue_watcher_observation]`
- `signal_input_json=null`
- `shadow_candidate_id=null`
- `prepared_authorization_id=null`
- `requires_action_time_final_gate=true`
- `requires_fresh_action_time_facts=false`
- `requires_official_operation_layer=true`
- `final_gate_status=not_reached`
- `operation_layer_status=not_reached`
- `places_order=false`
- `calls_order_lifecycle=false`
- `exchange_write_called=false`
- `withdrawal_or_transfer_requested=false`

Forbidden until action-time `FinalGate` passes:

- `official_operation_layer_submit`
- `exchange_order`
- `order_lifecycle_submit`
- `runtime_budget_mutation`

When a prepared authorization exists, `action_time_resume.status` must become
`ready_for_action_time_final_gate` and the only allowed automatic action is:

- `run_official_action_time_final_gate_preflight`

## Pilot Status

Current Pilot Status:

- Path:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategygroup-runtime-pilot-status-6614ea38.json`
- `status=waiting_for_market`
- `owner_state.blocked_at=watcher_signal`
- `owner_state.blocked_reason=no_fresh_strategy_signal`
- `owner_state.next_recover_condition=runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope`
- `owner_state.automatic_recovery_action=continue_watcher_observation`
- `owner_state.downgrade_mode=observe_only`

Candidate row:

- `candidate_state=not_prepared`
- `fresh_signal_id=pending`
- `runtime_grant_status=pending`
- `authorization_evidence_status=pending`
- `final_gate_status=not_reached`
- `operation_layer_status=not_reached`
- `action_time_resume_status=waiting_for_market`
- `action_time_next_step=continue_watcher_observation`
- `signal_input_json=null`
- `shadow_candidate_id=null`
- `prepared_authorization_id=null`

Pilot Status safety invariants:

- `reads_existing_evidence_only=true`
- `pilot_status_builder_only=true`
- `creates_candidate=false`
- `authorizes_execution=false`
- `places_order=false`
- `order_created=false`
- `order_lifecycle_called=false`
- `exchange_write_called=false`
- `runtime_budget_mutated=false`
- `withdrawal_or_transfer_created=false`

## Resume Condition

The pilot can continue automatically only when the watcher observes a fresh
signal for the selected StrategyGroup runtime scope.

Resume chain:

```text
fresh strategy signal
-> RequiredFacts readiness
-> non-executing prepare records
-> shadow candidate / runtime grant / authorization evidence
-> action-time FinalGate
-> official Operation Layer action only
-> post-submit finalize / reconciliation / budget settlement
```

Standing authorization removes repeated chat confirmation for deploy apply and
in-boundary runtime advancement. It does not authorize `FinalGate` bypass,
`Operation Layer` bypass, withdrawal, transfer, credential mutation, live profile
mutation, order-sizing default expansion, runtime-boundary expansion, stale-fact
execution, duplicate submit, or conflicting position/order exposure.

## Verification

Local verification:

- `/opt/homebrew/bin/python3 -m py_compile scripts/build_runtime_signal_watcher_readiness_pack.py scripts/build_strategygroup_runtime_pilot_status.py scripts/execute_tokyo_runtime_governance_git_deploy.py scripts/plan_tokyo_runtime_governance_git_deploy.py src/domain/standing_authorization.py`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_signal_watcher_readiness_pack.py tests/unit/test_strategygroup_runtime_pilot_status.py tests/unit/test_tokyo_runtime_governance_git_deploy.py tests/unit/test_tokyo_runtime_governance_deploy_executor.py -q`
  -> `31 passed`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_signal_watcher_tick.py tests/unit/test_runtime_active_observation_status.py tests/unit/test_trading_console_readmodels.py -q`
  -> `72 passed`
- `git diff --check`
  -> passed before commit

Tokyo verification:

- deploy plan:
  `output/strategygroup-runtime-pilot/deploy-6614ea38/git-deploy-plan.json`
- owner deploy packet:
  `output/strategygroup-runtime-pilot/deploy-6614ea38/owner-git-deploy-packet.json`
- deploy apply report:
  `output/strategygroup-runtime-pilot/deploy-6614ea38/deploy-apply-report.json`
- postdeploy acceptance:
  `output/strategygroup-runtime-pilot/deploy-6614ea38/postdeploy-acceptance-packet.json`
- watcher resume pack:
  `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json`
- pilot status:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategygroup-runtime-pilot-status-6614ea38.json`
- live facts:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategy-group-live-facts-readonly-6614ea38.json`
- live-facts readiness:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategy-group-live-facts-readiness-6614ea38.json`

## Current Outcome

Current outcome is not a live trade. The system is deployed, observing, and
waiting for market.

Material state:

- selected pilot StrategyGroup: `MPG-001`
- selected universe: `COINUSDT`, `MSTRUSDT`, `INTCUSDT`
- risk profile: `tiny`
- max active position: `1`
- current blocker: `no_fresh_strategy_signal`
- automatic recovery action: `continue_watcher_observation`
- current permitted automatic action: `continue_watcher_observation`
- next non-observation action after a fresh signal:
  `run_official_action_time_final_gate_preflight`
