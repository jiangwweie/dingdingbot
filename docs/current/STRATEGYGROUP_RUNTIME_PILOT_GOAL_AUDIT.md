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
| Latest deployed runtime head | `592cd5f1cddaca3d8fc7066a9a0f3c0b64ed4540` |
| Latest Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-592cd5f1-real-order-matrix-summary` |
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
