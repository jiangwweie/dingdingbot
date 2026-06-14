# StrategyGroup Runtime Pilot Checkpoint - 419f272a

Date: 2026-06-15
Status: CURRENT_CHECKPOINT

## Scope

This checkpoint records the current StrategyGroup Runtime Pilot state after
selective watcher-branch carryover, action-time handoff liveness repair, and
Tokyo deployment.

Workspace and branch:

- Workspace: `/Users/jiangwei/Documents/final`
- Branch: `codex/strategygroup-runtime-pilot`
- Runtime code head: `419f272a271cc46e6eb6fd00ee72fb48efa4837e`

## Watcher Branch Carryover Decision

Do not merge `codex/runtime-signal-watcher-feishu` wholesale into the pilot
branch. That side branch contains a large docs archive/delete reset that must
remain a separate integration item.

Useful P0 watcher/runtime content has been carried into the pilot branch by
focused commits:

- reuse deployment Feishu environment for watcher notification;
- run Tokyo watcher as the `ubuntu` service user;
- separate watcher deployment readiness from Owner attention;
- expose watcher readiness and resume pack status;
- expose watcher auto-resume decision;
- propagate standing authorization into watcher resume semantics;
- surface pilot watcher scope mismatch;
- preserve selected watcher runtime IDs;
- surface scoped watcher runtime count;
- align prepare flow with standing authorization;
- suppress no-signal watcher wakeups.
- expose watcher prepare evidence so ready-signal auto-resume can distinguish
  actual non-executing prepare record creation from decision-only metadata.
- remove the action-time chat-confirmation blocker from the fresh attempt /
  executable handoff chain; the next step is now action-time `FinalGate` plus
  official `Operation Layer`, not fresh Owner chat confirmation.
- include scoped watcher runtime summaries in the post-signal resume pack so
  the StrategyGroup Runtime Pilot status can prove the watcher is aligned with
  the selected StrategyGroup scope.

## Tokyo Deployment

Current Tokyo deployment:

- Release path:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-419f272a-20260615-watcher-scope-resume-pack`
- Deployed head:
  `419f272a271cc46e6eb6fd00ee72fb48efa4837e`
- Branch in release manifest:
  `codex/strategygroup-runtime-pilot`
- Migration count:
  `84`
- Latest migration:
  `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`
- Backend health:
  `status=ok`, `runtime_bound=true`, `live_ready=false`

Deployment apply effects were bounded:

- `database_backup_created=true`
- `migrations_run=true`
- `services_restarted=true`
- `exchange_called=false`
- `execution_intent_created=false`
- `order_created=false`
- `order_lifecycle_called=false`
- `secrets_read_by_codex=false`

Postdeploy verifier result:

- `postdeploy_summary.status=postdeploy_acceptance_passed`
- `postdeploy_acceptance_packet.status=postdeploy_acceptance_ready`
- `postdeploy_summary.current_head=419f272a271cc46e6eb6fd00ee72fb48efa4837e`
- `postdeploy_summary.health={status: ok, runtime_bound: true, live_ready: false}`
- top-level postdeploy packet may still show historical pre-live rehearsal
  blockers; those are not current deploy acceptance preconditions.

Action-time liveness verifier result:

- remote source no longer contains
  `call_official_submit_endpoint_after_action_time_confirmation`;
- remote source contains
  `call_official_submit_endpoint_after_action_time_final_gate_and_operation_layer_pass`;
- `requires_action_time_confirmation=false` in the fresh-attempt readiness,
  fresh-signal bridge, cycle-executable handoff, and full next-attempt cycle
  scripts;
- `requires_owner_chat_confirmation=false`;
- `uses_standing_runtime_authorization=true` only when the chain is ready for
  action-time gate continuation.

## Watcher State

Tokyo watcher service uses the StrategyGroup Runtime Pilot scoped runtime set:

- `strategy-runtime-3a25a46a535f`
- `strategy-runtime-579e407cc03a`
- `strategy-runtime-93353f4cf30e`

The systemd service includes `--allow-prepare-records`, but the current market
state has no fresh ready signal.

Latest verified watcher status:

- `status=watching_no_signal`
- `post_signal_resume_pack.status=operator_packet_needs_review`
- `post_signal_resume_pack.active_runtime_count=6` for the full active runtime
  set reported by the status packet.
- `post_signal_resume_pack.monitored_runtime_count=3` for the current pilot
  watcher scope.
- `post_signal_resume_pack.selected_runtime_instance_ids=[strategy-runtime-93353f4cf30e, strategy-runtime-579e407cc03a, strategy-runtime-3a25a46a535f]`
- `post_signal_resume_pack.runtime_signal_summaries_count=3`
- `watcher_tick.notification.required=false`
- `watcher_tick.notification.reason=waiting_for_market_no_owner_attention_needed`
- `post_signal_auto_resume.status=waiting_for_market`
- `post_signal_auto_resume.allow_prepare_records=true`
- `post_signal_auto_resume.can_continue_without_owner_chat=true`
- `post_signal_auto_resume.blocked_reason=no_fresh_strategy_signal`
- `notification.required=false`
- `notification.reason=waiting_for_market_no_owner_attention_needed`
- `notification.sent=false`

Scoped runtime summaries in the post-signal resume pack:

| Runtime | StrategyGroup | Symbol | Side | Signal state | Action | Reason |
|---|---|---|---|---|---|---|
| `strategy-runtime-93353f4cf30e` | `MPG-001` | `COIN/USDT:USDT` | `long` | `waiting_for_signal` | `no_action` | `mpg_no_action_momentum_persistence_not_confirmed` |
| `strategy-runtime-579e407cc03a` | `MPG-001` | `MSTR/USDT:USDT` | `long` | `waiting_for_signal` | `no_action` | `mpg_no_action_momentum_persistence_not_confirmed` |
| `strategy-runtime-3a25a46a535f` | `MPG-001` | `INTC/USDT:USDT` | `long` | `waiting_for_signal` | `no_action` | `mpg_no_action_momentum_persistence_not_confirmed` |

Latest verified Console readmodel state:

- `strategygroup_runtime_pilot_status.data.status=waiting_for_market`
- `strategygroup_runtime_pilot_status.data.pilot_selection.selected_strategy_group_id=MPG-001`
- `strategygroup_runtime_pilot_status.data.pilot_selection.selected_universe=[INTCUSDT, MSTRUSDT, COINUSDT]`
- `strategygroup_runtime_pilot_status.data.pilot_selection.risk_profile=tiny`
- `strategygroup_runtime_pilot_status.data.pilot_selection.max_notional=8`
- `runtime_signal_watcher_status.data.owner_state.blocked_at=watcher_signal`
- `runtime_signal_watcher_status.data.owner_state.blocked_reason=no_fresh_strategy_signal`
- `runtime_signal_watcher_status.data.owner_state.next_recover_condition=runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope`
- `runtime_signal_watcher_status.data.owner_state.automatic_recovery_action=continue_watcher_observation`
- `runtime_signal_watcher_status.data.owner_state.downgrade_mode=observe_only`
- `strategygroup_runtime_pilot_status.data.why_not_executable=[no_fresh_strategy_signal, candidate_specific_protection_budget_next_gate_pending_until_fresh_signal]`
- `strategygroup_runtime_pilot_status.data.watcher_scope_alignment.status=aligned`
- `strategygroup_runtime_pilot_status.data.watcher_scope_alignment.out_of_scope_count=0`
- `strategygroup_runtime_pilot_status.data.control_board.runtime_row.watcher_scope=aligned`
- `strategygroup_runtime_pilot_status.data.control_board.strategy_group_row.status=armed_observation_waiting_for_signal`
- `strategygroup_runtime_pilot_status.data.control_board.strategy_group_row.next_action=continue_watcher_observation`
- `watcher_tick.safety_invariants.prepare_records_created=false`
- `watcher_tick.safety_invariants.allowed_prepare_record_effects=[]`
- `status_packet.safety_invariants.observed_prepare_records_created=false`
- These prepare evidence fields are expected to become true only after a fresh
  signal causes non-executing prepare records to be created.

Forbidden effects remain absent:

- `creates_shadow_candidate=false`
- `creates_execution_intent=false`
- `places_order=false`
- `calls_order_lifecycle=false`
- `exchange_write_called=false`
- `runtime_budget_mutated=false`
- `withdrawal_or_transfer_requested=false`

Watcher timer state:

- `brc-runtime-signal-watcher.timer=enabled, active`
- latest manual postdeploy tick completed with `status=0/SUCCESS`
- next scheduled tick remains managed by the systemd timer

## Resume Condition

The pilot should continue automatically only when the watcher observes a fresh
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
in-boundary runtime advancement. It does not authorize FinalGate bypass,
Operation Layer bypass, withdrawal, transfer, credential mutation, live profile
mutation, order-sizing default expansion, runtime-boundary expansion, stale-fact
execution, duplicate submit, or conflicting position/order exposure.

## Verification

Local verification:

- `/opt/homebrew/bin/python3 -m py_compile scripts/runtime_full_next_attempt_submit_cycle.py scripts/runtime_cycle_executable_submit_handoff.py scripts/runtime_fresh_signal_readiness_bridge.py scripts/runtime_fresh_signal_readiness_fixture.py scripts/build_runtime_fresh_attempt_readiness_packet.py`
- `/opt/homebrew/bin/python3 -m py_compile scripts/build_runtime_signal_watcher_readiness_pack.py scripts/build_strategygroup_runtime_pilot_status.py`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_cycle_executable_submit_handoff.py tests/unit/test_runtime_fresh_signal_readiness_bridge.py tests/unit/test_runtime_fresh_signal_readiness_fixture.py tests/unit/test_runtime_fresh_attempt_readiness_packet.py -q`
  -> `26 passed`
- `/opt/homebrew/bin/pytest tests/unit/test_tokyo_runtime_governance_deploy_executor.py tests/unit/test_tokyo_runtime_governance_git_deploy.py tests/unit/test_tokyo_runtime_governance_owner_deploy_packet.py tests/unit/test_tokyo_runtime_governance_postdeploy_acceptance_packet.py -q`
  -> `28 passed`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_active_observation_status.py tests/unit/test_runtime_signal_watcher_tick.py tests/unit/test_strategygroup_runtime_pilot_status.py tests/unit/test_strategygroup_runtime_pilot_overlay_docs.py -q`
  -> `28 passed`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_signal_watcher_readiness_pack.py tests/unit/test_strategygroup_runtime_pilot_status.py -q`
  -> `10 passed`
- `/opt/homebrew/bin/pytest tests/unit/test_trading_console_readmodels.py -q`
  -> `57 passed`
- `/opt/homebrew/bin/pytest tests/unit/test_runtime_signal_watcher_tick.py tests/unit/test_runtime_active_observation_status.py -q`
  -> `15 passed`

Tokyo verification:

- owner deploy packet:
  `output/strategygroup-runtime-pilot/deploy-419f272a/owner-git-deploy-packet.json`,
  `status=ready_for_owner_git_deploy_decision`, `blockers=[]`,
  `deploy_confirmation_phrase_required=false`;
- git deploy apply report: `status=applied`, `blockers=[]`,
  `remote_mutation_authorized_by=owner-standing-authorization:strategygroup-runtime-pilot:2026-06-14`,
  `remote_mutation_confirmation_phrase_required=false`;
- postdeploy acceptance packet: `status=postdeploy_acceptance_ready`,
  `blockers=[]`;
- backend service: `active`;
- health endpoint: `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`;
- watcher service: latest manual tick `SUCCESS`, timer `enabled` and `active`;
- watcher status remains `watching_no_signal`, so no fresh-signal continuation
  has fired yet.
