# StrategyGroup Runtime Pilot Checkpoint - bbdbb61a

Date: 2026-06-15
Status: CURRENT_CHECKPOINT

## Scope

This checkpoint records the current StrategyGroup Runtime Pilot state after:

- selective watcher-branch carryover review;
- action-time resume contract implementation;
- watcher resume state normalization;
- Trading Console readmodel consumption of `action_time_resume`;
- standing-authorization Tokyo deploy apply;
- postdeploy watcher and live-fact verification.

Workspace and branch:

- Workspace: `/Users/jiangwei/Documents/final`
- Branch: `codex/strategygroup-runtime-pilot`
- Runtime code head: `bbdbb61ad4b7bab77c99cc5163a6ae80963abd8d`

## Watch Branch Carryover

Do not merge `codex/runtime-signal-watcher-feishu` wholesale into the pilot
branch. Its broad docs archive/delete reset remains a separate docs-governance
integration item.

Useful P0 watcher/runtime content is already present in this pilot branch:

- Feishu watcher notification and readiness packets;
- deployment readiness and standing-authorized deploy apply;
- watcher auto-resume metadata;
- StrategyGroup Pilot control board;
- prepared signal evidence surfacing;
- action-time resume contract.

Current additional commit:

- `bbdbb61a` - normalize watcher resume state so no-signal packets surface as
  `waiting_for_market` instead of `operator_packet_needs_review`, and expose
  `action_time_resume` directly through the Trading Console readmodel.

## Tokyo Deployment

Current Tokyo deployment:

- Release path:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bbdbb61a-20260615-normalized-watcher-resume`
- Deployed head:
  `bbdbb61ad4b7bab77c99cc5163a6ae80963abd8d`
- Previous deployed head:
  `6614ea3841b85bd0a1c530d8f908798d56ca2913`
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

Deployment apply report:

- Path:
  `output/strategygroup-runtime-pilot/deploy-bbdbb61a/deploy-apply-report.json`
- `status=applied`
- `blockers=[]`
- `commands_executed=16`
- `remote_mutation_authorized_by=owner-standing-authorization:strategygroup-runtime-pilot:2026-06-14`

Deployment effects:

- `database_backup_created=true`
- `migrations_run=true`
- `services_restarted=true`
- `exchange_called=false`
- `execution_intent_created=false`
- `order_created=false`
- `order_lifecycle_called=false`
- `secrets_read_by_codex=false`

Postdeploy acceptance:

- Path:
  `output/strategygroup-runtime-pilot/deploy-bbdbb61a/postdeploy-acceptance-packet.json`
- `status=postdeploy_acceptance_ready`
- `blockers=[]`
- warning:
  `release_identity_from_manifest_without_git_status`

## Live Facts

Postdeploy signed GET-only facts:

- Facts:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategy-group-live-facts-readonly-bbdbb61a.json`
- Readiness:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategy-group-live-facts-readiness-bbdbb61a.json`
- Pilot status:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategygroup-runtime-pilot-status-bbdbb61a.json`

Read-only account facts:

- `facts_status=ready`
- `account.status=fresh`
- `account.can_trade=true`
- `active_position.status=no_active_position`
- `active_position.active_count=0`
- `open_orders.status=no_open_orders`
- `open_orders.open_order_count=0`
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

Candidate-specific `protection`, `budget`, and `next_attempt_gate` are still
pending until a fresh signal creates a candidate context.

## Watcher State

Watcher runtime scope:

- `strategy-runtime-3a25a46a535f`
- `strategy-runtime-579e407cc03a`
- `strategy-runtime-93353f4cf30e`

Latest postdeploy watcher tick:

- service exit: `status=0/SUCCESS`
- `runtime_ready_signal_count=0`
- `strategy_group_would_enter_signal_count=0`
- `signal_input_json=null`
- `shadow_candidate_id=null`
- `prepared_authorization_id=null`

Latest resume pack:

- Path:
  `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json`
- `status=waiting_for_market`
- `can_continue_steps_5_8=false`
- `owner_state.status=waiting_for_market`
- `owner_state.blocker_class=waiting_for_market`
- `owner_state.blocked_at=watcher_signal`
- `owner_state.blocked_reason=no_fresh_strategy_signal`
- `owner_state.next_recover_condition=runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope`
- `owner_state.automatic_recovery_action=continue_watcher_observation`
- `owner_state.downgrade_mode=observe_only`

This replaces the previous no-signal presentation where the raw wakeup status
could still show `operator_packet_needs_review`.

## Action-Time Resume

Current `action_time_resume`:

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

Forbidden before action-time `FinalGate` passes:

- `official_operation_layer_submit`
- `exchange_order`
- `order_lifecycle_submit`
- `runtime_budget_mutation`

## Trading Console Readmodel

Verified from deployed code through `src.interfaces.api_trading_console._service`
with read-only dependencies:

Watcher readmodel:

- `read_model=runtime_signal_watcher_status`
- `freshness=fresh`
- `blockers=[]`
- `owner_state.status=waiting_for_market`
- `owner_state.blocked_reason=no_fresh_strategy_signal`
- `post_signal_resume.status=waiting_for_market`
- `post_signal_resume.raw_resume_pack_status=waiting_for_market`
- `action_time_resume.status=waiting_for_market`
- `why_not_executable=[no_fresh_strategy_signal]`
- `next_safe_checkpoint=continue_watcher_observation`

Pilot readmodel:

- `read_model=strategygroup_runtime_pilot_status`
- `owner_state.status=waiting_for_market`
- `candidate_row.candidate_state=not_prepared`
- `candidate_row.final_gate_status=not_reached`
- `candidate_row.operation_layer_status=not_reached`
- `candidate_row.action_time_resume_status=waiting_for_market`
- `candidate_row.action_time_next_step=continue_watcher_observation`
- `why_not_executable=[no_fresh_strategy_signal, candidate_specific_protection_budget_next_gate_pending_until_fresh_signal]`

The HTTP endpoints are protected by auth and returned `401 Unauthorized` to a
bare local GET. This is expected and was not bypassed.

## Resume Chain

The pilot continues automatically only when the watcher observes a fresh signal
for the selected StrategyGroup runtime scope.

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

- `/opt/homebrew/bin/python3 -m py_compile scripts/build_runtime_signal_watcher_readiness_pack.py src/application/readmodels/trading_console.py`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_signal_watcher_readiness_pack.py tests/unit/test_trading_console_readmodels.py tests/unit/test_strategygroup_runtime_pilot_status.py tests/unit/test_runtime_signal_watcher_tick.py tests/unit/test_runtime_active_observation_status.py -q`
  -> `85 passed`
- `git diff --check`
  -> passed

Tokyo verification:

- deploy plan:
  `output/strategygroup-runtime-pilot/deploy-bbdbb61a/git-deploy-plan.json`
- owner deploy packet:
  `output/strategygroup-runtime-pilot/deploy-bbdbb61a/owner-git-deploy-packet.json`
- deploy apply:
  `output/strategygroup-runtime-pilot/deploy-bbdbb61a/deploy-apply-report.json`
- postdeploy acceptance:
  `output/strategygroup-runtime-pilot/deploy-bbdbb61a/postdeploy-acceptance-packet.json`
- watcher resume pack:
  `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json`
- pilot status:
  `/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot/strategygroup-runtime-pilot-status-bbdbb61a.json`

## Current Outcome

Current outcome is not a live trade. The system is deployed, observing, and
waiting for market.

Material state:

- selected pilot StrategyGroup: `MPG-001`
- selected universe: `COINUSDT`, `MSTRUSDT`, `INTCUSDT`
- risk profile: `tiny`
- leverage: `1x`
- max active position: `1`
- current blocker: `no_fresh_strategy_signal`
- automatic recovery action: `continue_watcher_observation`
- current permitted automatic action: `continue_watcher_observation`
- next non-observation action after a fresh signal:
  `run_official_action_time_final_gate_preflight`
