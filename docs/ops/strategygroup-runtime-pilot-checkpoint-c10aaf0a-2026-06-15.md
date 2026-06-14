# StrategyGroup Runtime Pilot Checkpoint - c10aaf0a

Date: 2026-06-15
Status: CURRENT_CHECKPOINT

## Scope

This checkpoint records the current StrategyGroup Runtime Pilot state after
selective watcher-branch carryover and Tokyo deployment.

Workspace and branch:

- Workspace: `/Users/jiangwei/Documents/final`
- Branch: `codex/strategygroup-runtime-pilot`
- Local head: `c10aaf0a03344e8981d18c840988d16d1a6abd3e`

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

## Tokyo Deployment

Current Tokyo deployment:

- Release path:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c10aaf0a-20260615-owner-readable-watcher-recovery`
- Deployed head:
  `c10aaf0a03344e8981d18c840988d16d1a6abd3e`
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
- `postdeploy_summary.current_head=c10aaf0a03344e8981d18c840988d16d1a6abd3e`
- top-level postdeploy packet may still show historical pre-live rehearsal
  blockers; those are not current deploy acceptance preconditions.

## Watcher State

Tokyo watcher service uses the StrategyGroup Runtime Pilot scoped runtime set:

- `strategy-runtime-3a25a46a535f`
- `strategy-runtime-579e407cc03a`
- `strategy-runtime-93353f4cf30e`

The systemd service includes `--allow-prepare-records`, but the current market
state has no fresh ready signal.

Latest verified watcher status:

- `status=watching_no_signal`
- `post_signal_auto_resume.status=waiting_for_market`
- `post_signal_auto_resume.allow_prepare_records=true`
- `post_signal_auto_resume.can_continue_without_owner_chat=true`
- `post_signal_auto_resume.blocked_reason=no_fresh_strategy_signal`
- `notification.required=false`
- `notification.reason=waiting_for_market_no_owner_attention_needed`
- `notification.sent=false`

Latest verified Console readmodel state:

- `runtime_signal_watcher_status.data.owner_state.blocked_at=watcher_signal`
- `runtime_signal_watcher_status.data.owner_state.blocked_reason=no_fresh_strategy_signal`
- `runtime_signal_watcher_status.data.owner_state.next_recover_condition=runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope`
- `runtime_signal_watcher_status.data.owner_state.automatic_recovery_action=continue_watcher_observation`
- `runtime_signal_watcher_status.data.owner_state.downgrade_mode=observe_only`
- `strategygroup_runtime_pilot_status.data.why_not_executable=[no_fresh_strategy_signal, candidate_specific_protection_budget_next_gate_pending_until_fresh_signal]`

Forbidden effects remain absent:

- `creates_shadow_candidate=false`
- `creates_execution_intent=false`
- `places_order=false`
- `calls_order_lifecycle=false`
- `exchange_write_called=false`
- `runtime_budget_mutated=false`
- `withdrawal_or_transfer_requested=false`

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
