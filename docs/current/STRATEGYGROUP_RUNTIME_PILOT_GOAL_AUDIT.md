# StrategyGroup Runtime Pilot Goal Audit

Last updated: 2026-06-18

## Purpose

This file is the current audit surface for the active StrategyGroup Runtime
Pilot goal:

```text
P0 real-entry fast chain
P0 exit hardening
P1 StrategyGroup tier governance
```

It separates proven engineering readiness from the remaining market-dependent
first real-order closure. It is not a frontend plan and not a historical-debt
cleanup plan.

## Current State

| Item | Current Evidence |
| --- | --- |
| Workspace | `/Users/jiangwei/Documents/final` |
| Branch | `codex/owner-runtime-console-v1` |
| Branch head | moving git ref; verify with `git log --oneline -1 --decorate` |
| Latest deployed runtime head | `ea34594badc066bc0c714d02c385341106665e07` |
| Latest Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ea34594b-watch-ready-normalization` |
| Goal progress | `P0=waiting_for_market`, `P0.5=ready` |
| Quiet monitor | `DONT_NOTIFY` |
| Runtime blockers | none |
| Product gaps | none |
| Current safe action | continue watcher observation until fresh selected StrategyGroup signal |

## Requirement Audit

### P0 Real-Entry Fast Chain

| Requirement | Current Proof | Status |
| --- | --- | --- |
| fresh signal -> candidate/auth automatic chain | `runtime-dry-run-audit-chain-current.json` has `fresh_signal_fast_auto_chain_checked=true` and `non_executing_prepare_auto_bridge_checked=true` | Proven by dry-run |
| RequiredFacts readiness | Dry-run audit has `required_facts_readiness_checked=true`; daily check has `runtime_dry_run_missing_required_checks=[]` | Proven by dry-run |
| action-time FinalGate sequence | Dry-run audit has `all_selected_strategygroups_reach_finalgate_dispatch_checked=true` and `selected_strategygroup_dispatch_guard_checked=true` | Proven by dry-run |
| official Operation Layer evidence relay | Dry-run audit has `operation_layer_evidence_relay_checked=true`, `operation_layer_authorization_chain_guard_checked=true`, and `scoped_pipeline_operation_layer_handoff_checked=true` | Proven by dry-run |
| hard submit blocker matrix | Dry-run audit has `operation_layer_hard_safety_blocker_matrix_checked=true` and `operation_layer_blocker_review_policy_checked=true` | Proven by dry-run |
| real exchange submit | Not proven because no fresh market signal currently exists; daily check reports `waiting_for_market=true` | Market-dependent |

### P0 Exit Hardening

| Requirement | Current Proof | Status |
| --- | --- | --- |
| exchange-native hard stop required after entry | `runtime_live_position_monitor` requires an exchange reduce-only stop; local-only SL still blocks with `active_position_missing_hard_stop` | Proven by unit tests |
| CCXT/Binance nested reduce-only shape | `test_exchange_native_hard_stop_accepts_reduce_only_from_info_payload` covers `info.reduceOnly=true` | Proven by unit tests |
| TP1 first-stage shape | `runtime_position_exit_plan` preserves default TP1 review shape and blocks fake TP orders when min qty / step makes partial TP infeasible | Proven by unit tests |
| runner first-stage rule | `runner_primary_exit_rule=structure_invalidation_first`, ATR trailing and time stop are review-only helpers | Proven by domain model/tests |
| standing reduce-only recovery authorization packet | `test_runtime_reduce_only_close_authorization.py` proves ready and blocked recovery-packet shapes; no per-order chat confirmation is required inside the official recovery boundary | Proven by unit tests |
| post-submit exit outcome matrix | Dry-run audit has `post_submit_exit_outcome_matrix_checked=true` | Proven by dry-run |
| protection-failure reduce-only recovery route | Dry-run audit has `reduce_only_recovery_standing_authorization_checked=true`; recovery still requires action-time FinalGate and official Operation Layer | Proven by dry-run |
| entry filled + protection failure handling | Dry-run outcome matrix includes protection-failed path and recovery/review shape | Proven by dry-run |
| real post-submit close/reconcile/settle after actual order | Not proven because no real order has been accepted yet | Market/order-dependent |

### P1 StrategyGroup Tier Governance

| Requirement | Current Proof | Status |
| --- | --- | --- |
| L0-L4 tier policy exists | `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json` consumed by dry-run audit | Proven |
| first live lane limited to MPG-001 | Dry-run audit has `only_mpg_tiny_real_order_eligible_checked=true`; L4 list is `["MPG-001"]` | Proven |
| TEQ/FBS/SOR/PMR remain non-L4 | Dry-run tier rows: `TEQ-001=L2`, `FBS-001=L3`, `SOR-001=L3`, `PMR-001=L1` | Proven |
| new BRF/BTPC/VCB/LSR/RBR default non-L4 | Dry-run audit has `new_strategygroups_default_observe_only_checked=true` and all new groups at `L1` | Proven |
| strategy handoffs cannot define custom execution pipeline | Dry-run audit has `strategy_handoff_no_execution_pipeline_fields_checked=true` and `strategygroup_adapter_boundary_checked=true` | Proven |

## Current Verification Commands

| Command | Result |
| --- | --- |
| `python3 scripts/run_strategygroup_runtime_daily_check.py --auto-cache --heartbeat --output-json output/runtime-monitor/latest-daily-check.json --output-owner-progress output/runtime-monitor/latest-owner-progress.md` | `DONT_NOTIFY`, waiting for market |
| `python3 scripts/run_strategygroup_runtime_goal_progress_audit.py --owner-progress --output-json output/runtime-monitor/latest-goal-progress.json --output-owner-progress output/runtime-monitor/latest-goal-progress.md` | `P0=waiting_for_market`, `P0.5=ready`, no blockers |
| `python3 scripts/runtime_dry_run_audit_chain.py --output-json output/strategygroup-runtime-pilot/runtime-dry-run-audit-chain-current.json` | `status=passed`, `scenario_count=14`, all required checks true |

## Completion Boundary

The goal is not complete yet. Current engineering evidence proves that the
non-executing fast chain, exit-hardening policy, and StrategyGroup tier policy
are ready. The remaining proof requires a real fresh selected StrategyGroup
signal and, only if all official gates pass, the first bounded real order
through:

```text
fresh signal
-> RequiredFacts
-> candidate/auth
-> action-time FinalGate
-> official Operation Layer
-> exchange-native hard stop
-> post-submit finalize
-> reconciliation
-> budget settlement
-> review
```

Healthy waiting for market is not a blocker. It is the expected state while no
fresh selected StrategyGroup signal exists.

## Safety Invariants

| Invariant | Current Status |
| --- | --- |
| FinalGate bypass | false |
| Operation Layer bypass | false |
| exchange write during audit | false |
| real order during audit | false |
| withdrawal or transfer | false |
| secret or credential mutation | false |
| live profile mutation | false |
| order-sizing default mutation | false |
| mock signal treated as real signal | false |
| disabled smoke treated as real execution proof | false |

## Latest Checkpoint

### 2026-06-18 Fresh Signal TTL Guard

The dry-run fast chain now makes the StrategyGroup signal freshness window
machine-checkable. Current StrategyGroup handoffs use a `120` second freshness
window, and the mock fresh-signal path records that the signal is inside this
window while a synthetic stale signal is rejected by the same TTL boundary.

| Item | Evidence |
| --- | --- |
| Pilot freshness window | `freshness_window_seconds=120` across current StrategyGroup handoffs |
| New mock-pass artifact | `fresh_signal_freshness_checks` inside `mock_fresh_signal_dry_run_pass` |
| Fast-chain checks | `fresh_signal_within_freshness_window=true` and `stale_signal_rejected_by_freshness_window=true` |
| Shared handoff guard | `uses_pilot_signal_freshness_window=true` for each current StrategyGroup handoff |
| Boundary | Freshness is a runtime readiness check, not a chat confirmation or execution authority |
| Safety | Local dry-run/test work only; no Tokyo call, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 L4 Runtime Requirement Guard

The StrategyGroup tier policy now carries a machine-readable
`l4_real_order_requirements` list. This makes `L4 tiny_real_order_eligible`
auditable as eligibility for the official runtime chain, not direct execution
authority. The dry-run audit fails if the L4 requirement list omits any
required step or drifts from the current first-live-order boundary.

| Item | Evidence |
| --- | --- |
| Policy source | `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json` includes `l4_real_order_requirements` |
| Required chain | selected scope, tiny risk, fresh signal, RequiredFacts, candidate/auth, action-time FinalGate, official Operation Layer, exchange-native protection, finalize, reconciliation, budget settlement, review |
| New dry-run check | `l4_real_order_requirements_complete=true` inside `runtime_tier_policy_validation.checks` |
| Boundary | L4 remains limited to `MPG-001`; tier policy is not execution authority, FinalGate input, Operation Layer input, or sizing default |
| Safety | Local dry-run/test work only; no Tokyo call, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Post-Submit Owner-Confirmation Regression Guard

The dry-run post-submit exit outcome matrix now explicitly proves that none of
the six covered post-submit outcomes reintroduce per-order Owner chat
confirmation as a next-step gate. Recovery after protection failure still
requires standing authorization, action-time FinalGate, and the official
Operation Layer; it does not require a new chat approval inside the selected
tiny-risk runtime boundary.

| Item | Evidence |
| --- | --- |
| Covered outcomes | `entry_filled_protection_ok`, `entry_filled_protection_failed`, `partial_fill`, `exchange_submit_failed_before_acceptance`, `active_position_remains_open`, `position_closed_by_sl_tp_or_reduce_only_recovery` |
| New dry-run check | `no_post_submit_case_requires_owner_chat_confirmation=true` |
| Boundary | Standing recovery remains bounded by FinalGate and Operation Layer, not by old per-order chat confirmation |
| Safety | Local dry-run/test work only; no Tokyo call, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Standing Recovery Proof Isolation Guard

The legacy compatibility isolation packet now explicitly checks the current
standing reduce-only recovery proof artifacts for old per-order Owner
close-confirmation terms. This prevents bridge proof fixtures from silently
regressing from the standing recovery route back to the retired
`owner_authorize_reduce_only_close` semantics.

| Item | Evidence |
| --- | --- |
| Isolation packet | `runtime_legacy_compatibility_isolation_packet.py` now reports `standing_recovery_proof_artifacts_present=true` and `standing_recovery_proofs_have_no_legacy_owner_close_terms=true` |
| Blocked regression | Unit coverage injects `monitor_position_or_owner_authorize_reduce_only_close` and requires `standing_recovery_proof_uses_legacy_owner_close_terms` |
| Local packet run | `/tmp/runtime-legacy-isolation.json`: `status=legacy_compatibility_isolated_from_runtime_mainline`, `blockers=[]` |
| Verification | `14 passed` for legacy isolation plus controlled tiny-live bridge proof tests; `py_compile` passed for the isolation packet scripts |
| Safety | This is local packet/test work only; it does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-18 Real-Order Readiness Matrix Summary

Tokyo snapshot and daily check now surface the real-order readiness matrix as a
compact count instead of hiding it inside the raw goal-status packet. This keeps
healthy waiting low-noise while still showing whether the first real-order path
is waiting on market conditions or blocked by execution readiness.

| Item | Evidence |
| --- | --- |
| Local commit | `592cd5f1 feat(runtime): summarize real order readiness matrix` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-592cd5f1-real-order-matrix-summary` |
| Deploy apply | `output/tokyo-git-deploy-apply-592cd5f1.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-592cd5f1.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]` |
| Real-order matrix | latest snapshot reports `10 pass / 4 waiting / 0 blocked`; waiting keys are `fresh_signal`, `candidate_authorization`, `action_time_finalgate`, and `official_operation_layer` |
| Verification | `85 passed` for daily check, goal progress, goal status, and Tokyo snapshot unit tests |

### 2026-06-18 Runtime Monitor Cache Head Guard

The low-noise runtime monitor now treats cache freshness as a three-part check:
schema version, generated-at age, and deployed runtime head. A fresh local cache
whose `source.runtime_head` or `source.expected_runtime_head` no longer matches
`docs/current/RUNTIME_MONITOR_BASELINE.json` is blocked or refreshed instead of
quietly reporting a stale `DONT_NOTIFY`.

| Item | Evidence |
| --- | --- |
| Local commit | `2f382cd8 feat(runtime): invalidate monitor cache on deployed head drift` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-2f382cd8-cache-head-drift` |
| Deploy apply | `output/tokyo-git-deploy-apply-2f382cd8.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-2f382cd8.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]` |
| Cache source | `output/runtime-monitor/latest-daily-check.json` records `source.expected_runtime_head` and `source.runtime_head` for cache-head validation |
| Verification | `85 passed` for daily check, goal progress, goal status, and Tokyo snapshot unit tests |

### 2026-06-18 Standing Reduce-Only Recovery Checkpoint

The active-position recovery path no longer presents the current pilot's
reduce-only recovery readiness as an old per-order Owner chat confirmation.
When an entry is filled but exchange-native protection creation fails, the
system now treats reduce-only recovery as a standing-authorized risk-reducing
path that still must pass action-time FinalGate and the official Operation
Layer before any real exchange action.

| Item | Evidence |
| --- | --- |
| Domain readiness | `RuntimeReduceOnlyCloseOwnerPacketStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION` carries `operation_layer_required=true`, `finalgate_required=true`, and no owner approval value |
| Post-close followup | `ready_for_standing_reduce_only_recovery` requires `prepare_official_operation_layer_reduce_only_recovery`, `run_action_time_finalgate_for_reduce_only_recovery`, and `execute_reduce_only_recovery_through_operation_layer` |
| Continuation selector | Active-position continuation selects `monitor_position_or_prepare_official_reduce_only_recovery` instead of the old owner-authorize close action |
| Dry-run audit | `runtime-dry-run-audit-chain-current.json`: `status=passed`, `scenario_count=14`, `reduce_only_recovery_standing_authorization_checked=true`, `exchange_write_called=false`, `order_created=false` |
| Monitor state | `run_strategygroup_runtime_daily_check.py --from-cache --require-fresh-cache --owner-progress`: `DONT_NOTIFY`, `waiting_for_market`, `L0_local_cache_read`, `remote_interaction_count=0` |
| Verification | `90 passed` for dry-run/monitor status tests; `109 passed, 1 skipped` for reduce-only recovery/domain/readmodel tests; `py_compile` passed for modified runtime files |

### 2026-06-18 Standing Reduce-Only Recovery Deploy Checkpoint

The standing reduce-only recovery checkpoint was pushed and deployed to Tokyo.
Tokyo is now on the runtime head that understands
`ready_for_standing_reduce_only_recovery`, carries the new dry-run required
check, and keeps healthy market-waiting low-noise.

| Item | Evidence |
| --- | --- |
| Local commit | `bb2b2bf0 feat(runtime): align reduce-only recovery authorization` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bb2b2bf0-standing-reduce-only-recovery` |
| Deploy apply | `output/tokyo-git-deploy-apply-bb2b2bf0.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-bb2b2bf0.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects `bb2b2bf0b1dfcb72a5616dadfa8e32f0d884d950` |
| Safety | Deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-18 Bridge Proof Standing-Recovery Fixture Checkpoint

The controlled tiny-live bridge proof fixtures now use the same standing
reduce-only recovery selector state as the runtime continuation chain. This
keeps local proof artifacts from reintroducing the old
`owner_authorize_reduce_only_close` selected action while the official route
continues to require fresh prepare, FinalGate, and controlled submit preflight.

| Item | Evidence |
| --- | --- |
| Waiting selector fixture | `runtime_controlled_tiny_live_bridge_to_preflight_proof.py` now uses `continuation_refresh_monitor_position_or_standing_recovery` and `monitor_position_or_prepare_official_reduce_only_recovery` |
| Legacy owner action scan | Targeted `rg` found no `monitor_position_or_owner_authorize_reduce_only_close` or owner-close refresh status in the bridge proof and bridge proof tests |
| Test isolation | CLI tests now monkeypatch official proof builders instead of touching login-protected runtime proof paths |
| Verification | `64 passed` for controlled bridge, continuation, dry-run closure, and daily-check tests; `py_compile` passed for the bridge proof scripts |
| Safety | This is local proof/test work only; it does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-18 Runtime Exit-Hardening Deploy Checkpoint

The current runtime exit-hardening proof set was deployed to Tokyo through the
bounded git deploy path. Tokyo now runs the head that includes the pilot
confidence floor alignment, dry-run audit chain validation, fresh-signal
freshness guard, L4 tier requirements, post-submit Owner-confirmation
regression guard, and standing recovery proof isolation guard.

| Item | Evidence |
| --- | --- |
| Deployed runtime head | `18c30ae03dc735e6f4043fbdcdeedd75cc16faba` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-18c30ae0-runtime-exit-hardening` |
| Deploy dry-run | `output/tokyo-git-deploy-dry-run-18c30ae0.json`: `status=dry_run_ready`, `blockers=[]`, `interaction.level=L1_deploy_plan_only`, `remote_interaction_count=0` |
| Deploy apply | `output/tokyo-git-deploy-apply-18c30ae0.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-18c30ae0.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, total remote interactions `8` including one L1 postdeploy daily check |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects `18c30ae03dc735e6f4043fbdcdeedd75cc16faba` |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Watcher Ready Normalization Deploy Checkpoint

The low-noise monitor reported a false hard-safety interruption after Tokyo
generated a `post-signal-resume-pack.json` with status
`ready_for_non_executing_prepare` while every runtime signal summary still
reported `waiting_for_signal`. The readiness pack builder now normalizes this
inconsistent no-signal shape back to `waiting_for_market` unless there is an
actionable runtime signal, signal input, shadow candidate, or prepared
authorization evidence.

| Item | Evidence |
| --- | --- |
| Local commit | `ea34594b fix(runtime): normalize watcher ready without actionable signal` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ea34594b-watch-ready-normalization` |
| Deploy dry-run | `output/tokyo-git-deploy-dry-run-ea34594b.json`: `status=dry_run_ready`, `blockers=[]`, `interaction.level=L1_deploy_plan_only`, `remote_interaction_count=0` |
| Deploy apply | `output/tokyo-git-deploy-apply-ea34594b.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-ea34594b.json`: `status=waiting_for_market`, `interaction.level=L1_daily_check_from_snapshot`, `remote_interaction_count=1`, `mutates_remote_files=false`, `calls_finalgate=false`, `calls_operation_layer=false`, `calls_exchange_write=false`, `places_order=false` |
| Quiet monitor | `output/runtime-monitor/latest-daily-check.json`: `decision=DONT_NOTIFY`, `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]` |
| Goal progress | `output/runtime-monitor/latest-goal-progress.json`: `status=waiting_for_market`, `P0=waiting_for_market`, `P0.5=ready`, `remote_interaction_count=0` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects `ea34594badc066bc0c714d02c385341106665e07` |
| Verification | `84 passed` for readiness pack, daily check, goal progress, goal status, and dry-run audit tests; `py_compile` passed for watcher readiness / daily check / goal status scripts |
| Safety | Fix and deploy did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |
