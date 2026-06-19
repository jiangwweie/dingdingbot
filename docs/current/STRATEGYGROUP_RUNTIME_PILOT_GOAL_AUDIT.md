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
| Branch head | moving git ref; verify with `git log --oneline -1 --decorate` before apply |
| Latest deployed runtime head | `e5f8c13b283d011d3c1eb8e27a0a7fe3ad873249` |
| Latest Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-e5f8c13b-cutover-ready-current` |
| Latest deploy apply | `output/tokyo-git-deploy-apply-e5f8c13b.json`: `status=applied`, `blockers=[]`, `remote_interaction_count=7`, `remote_files_modified=true`, `calls_exchange_write=false`, `places_order=false` |
| Latest postdeploy acceptance | `output/tokyo-runtime-deploy-session-e5f8c13b.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, total remote interactions `8` |
| Goal progress | `P0=waiting_for_market`, `P0.5=ready` |
| Quiet monitor | `DONT_NOTIFY` |
| Runtime blockers | none |
| Product gaps | none |
| Current safe action | continue watcher observation until fresh selected StrategyGroup signal |

## Monitor Refresh Classification Constraint

Local monitor cache freshness is an observability constraint, not a live-trading
safety blocker.

| Condition | Required classification | Constraint |
| --- | --- | --- |
| `runtime_progress_cache_missing` | `monitor_refresh_needed` | Notify automation to refresh, do not populate `checks.blockers` |
| `runtime_progress_cache_stale` | `monitor_refresh_needed` | Notify automation to refresh, do not classify as `hard_safety_stop` |
| `runtime_progress_cache_schema_stale` | `monitor_refresh_needed` | Refresh cache before trusting fields, do not mark P0 blocked |
| `runtime_progress_cache_runtime_head_stale` | `monitor_refresh_needed` | Refresh cache against current runtime head, do not treat as a trading gate failure |

When the runtime chain remains ready and the only issue is monitor freshness,
the goal-progress layer must preserve the first-order truth:

```text
P0 = waiting_for_market
P0.5 = ready
Owner intervention = false
checks.blockers = []
```

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
| TEQ/BTPC/FBS/SOR/PMR remain non-L4 | Dry-run tier rows: `TEQ-001=L2`, `BTPC-001=L2`, `FBS-001=L3`, `SOR-001=L3`, `PMR-001=L1` | Proven |
| new BRF/VCB/LSR/RBR default non-L4 | Dry-run audit has `new_strategygroups_default_observe_only_checked=true` and all default new groups at `L1` | Proven |
| strategy handoffs cannot define custom execution pipeline | Dry-run audit has `strategy_handoff_no_execution_pipeline_fields_checked=true` and `strategygroup_adapter_boundary_checked=true` | Proven |

## Current Verification Commands

| Command | Result |
| --- | --- |
| `python3 scripts/run_strategygroup_runtime_daily_check.py --auto-cache --heartbeat --output-json output/runtime-monitor/latest-daily-check.json --output-owner-progress output/runtime-monitor/latest-owner-progress.md` | `DONT_NOTIFY`, waiting for market |
| `python3 scripts/run_strategygroup_runtime_goal_progress_audit.py --owner-progress --output-json output/runtime-monitor/latest-goal-progress.json --output-owner-progress output/runtime-monitor/latest-goal-progress.md` | `P0=waiting_for_market`, `P0.5=ready`, no blockers |
| `python3 scripts/runtime_dry_run_audit_chain.py --output-json output/strategygroup-runtime-pilot/runtime-dry-run-audit-chain-current.json` | `status=passed`, `scenario_count=14`, all required checks true |
| `python3 scripts/run_strategygroup_runtime_replay_lab.py --output-json output/strategygroup-runtime-pilot/replay-lab/runtime-replay-report.json --output-owner-progress output/strategygroup-runtime-pilot/replay-lab/runtime-replay-owner-progress.md` | `status=passed`, `strategy_group_id=MPG-001`, replay-only safety flags true |
| `python3 scripts/runtime_live_cutover_readiness.py --output-json output/strategygroup-runtime-pilot/live-cutover-readiness/runtime-live-cutover-readiness.json --output-owner-progress output/strategygroup-runtime-pilot/live-cutover-readiness/runtime-live-cutover-readiness.md` | `status=live_cutover_waiting_for_fresh_signal`, `next_fresh_signal_cutover_ready=true`, `non_market_blockers=[]` |
| `python3 scripts/execute_tokyo_runtime_governance_git_deploy.py --json --apply --git-ref codex/owner-runtime-console-v1 --target-commit e5f8c13b283d011d3c1eb8e27a0a7fe3ad873249 --release-name brc-runtime-governance-e5f8c13b-cutover-ready-current --previous-release /home/ubuntu/brc-deploy/releases/brc-runtime-governance-58f0fc29-live-closure-goal-status-order --expected-deployed-head 58f0fc29452e8af1f4ab5a383e0d399c8789a57c --expected-remote-migration-count 84 --expected-remote-latest-migration 2026-06-11-084_create_runtime_post_submit_budget_settlements.py` | `status=applied`, `blockers=[]`, `remote_interaction_count=7`, `calls_exchange_write=false`, `places_order=false` |

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

### 2026-06-18 Cutover Ready Current Tokyo Deploy

The cutover source-visibility and deploy-readiness checkpoint is now deployed
to Tokyo through the bounded git deploy path. Postdeploy acceptance remains
healthy waiting-for-market with no blockers or product gaps.

| Item | Evidence |
| --- | --- |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-e5f8c13b-cutover-ready-current` |
| Deploy dry-run | `output/tokyo-git-deploy-dry-run-e5f8c13b.json`: `status=dry_run_ready`, `blockers=[]`, `apply_requested=false`, `commands_executed=0`, `remote_files_modified=false` |
| Deploy apply | `output/tokyo-git-deploy-apply-e5f8c13b.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-e5f8c13b.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, total remote interactions `8` including one L1 postdeploy daily check |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects `e5f8c13b283d011d3c1eb8e27a0a7fe3ad873249` |
| Boundary | Bounded deploy only; no FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Live Cutover Same-Tick Visibility Contract

The local live-cutover readiness packet now includes a
`same_tick_product_state_visibility_contract`. This upgrades the source-readiness
ordering fix from unit-test coverage into the same P0.5 readiness surface used
by goal-progress and Owner-readable status checks.

| Item | Evidence |
| --- | --- |
| Cutover section | `runtime_live_cutover_readiness.py` adds `same_tick_product_state_visibility` with four required checks |
| Required order | The local contract verifies `dry_run -> chain_closure -> live_closure -> goal_status -> owner-console-source-readiness API` |
| Current run | `runtime-live-cutover-readiness.json` reports `status=live_cutover_waiting_for_fresh_signal`, `next_fresh_signal_cutover_ready=true`, `non_market_blockers=[]`, and same-tick visibility `status=ready` |
| Goal progress | Latest local goal-progress reports `P0=waiting_for_market`, `P0.5=ready`, `blockers=none`, `product_gaps=none` |
| Boundary | Local readiness/audit projection only; no server file mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Same-Tick Source Readiness Visibility Fix

The watcher product-state post-step now refreshes
`strategygroup-runtime-goal-status.json` before it refreshes
`owner-console-source-readiness.json` and the other local readmodel packets.
This closes the remaining one-tick visibility gap after the live closure
evidence and goal-status refresh hook.

| Item | Evidence |
| --- | --- |
| Refresh order | `refresh_strategygroup_runtime_product_state_packets.py` runs dry-run refresh, chain-closure refresh, live-closure refresh, goal-status refresh, then readmodel/API packet refresh |
| Source-readiness impact | `owner-console-source-readiness.json` can consume the same-tick `strategygroup-runtime-goal-status.json` instead of reading the previous watcher tick |
| Test coverage | `test_refresh_packets_can_refresh_dry_run_and_goal_status` asserts the order `dry_run -> chain_closure -> live_closure -> goal_status -> owner-console-source-readiness API` |
| Boundary | Local report/readmodel refresh only; no FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Same-Tick Goal Status Visibility Fix

The watcher product-state post-step now refreshes `strategygroup-runtime-goal-status.json`
after `runtime-live-closure-evidence*.json` is generated. This prevents a
future first bounded real-order closure from being visible only one watcher
tick later.

| Item | Evidence |
| --- | --- |
| Systemd hook | `80-product-state-refresh.conf` now passes `--refresh-goal-status`, `--goal-status-output-json`, and `--release-manifest` |
| Refresh order | `refresh_strategygroup_runtime_product_state_packets.py` runs dry-run refresh, chain-closure refresh, live-closure refresh, then goal-status refresh when all optional flags are enabled |
| Test coverage | `test_refresh_packets_can_refresh_dry_run_and_goal_status` asserts the order `dry_run -> chain_closure -> live_closure -> goal_status` |
| Owner impact | When the first live closure evidence is complete, goal-status can observe it in the same watcher post-step instead of waiting for another tick |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-58f0fc29-live-closure-goal-status-order` |
| Deploy dry-run | `output/tokyo-git-deploy-dry-run-58f0fc29.json`: `status=dry_run_ready`, `blockers=[]`, `interaction.level=L1_deploy_plan_only`, `remote_interaction_count=0` |
| Deploy apply | `output/tokyo-git-deploy-apply-58f0fc29.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-58f0fc29.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, total remote interactions `8` including one L1 postdeploy daily check |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects `58f0fc29452e8af1f4ab5a383e0d399c8789a57c` |
| Boundary | Readmodel/report refresh only; no FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Live Closure Refresh Hook Tokyo Deploy

The product-state live closure refresh hook was pushed and deployed to Tokyo
as a bounded runtime-governance release. Postdeploy acceptance reports healthy
waiting-for-market with no blockers or product gaps.

| Item | Evidence |
| --- | --- |
| Local commit | `57676b72 feat(runtime): hook live closure refresh into product state` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-57676b72-live-closure-refresh-hook` |
| Deploy dry-run | `output/tokyo-git-deploy-dry-run-57676b72.json`: `status=dry_run_ready`, `blockers=[]`, `interaction.level=L1_deploy_plan_only`, `remote_interaction_count=0` |
| Deploy apply | `output/tokyo-git-deploy-apply-57676b72.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-57676b72.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, total remote interactions `8` including one L1 postdeploy daily check |
| Monitor baseline | At that checkpoint, `docs/current/RUNTIME_MONITOR_BASELINE.json` expected `57676b728e1ecc950c9b74fd14faad2c5cf093aa` |
| Safety | Bounded deploy only; no FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Live Closure Evidence Product-State Refresh Hook

The first bounded live-order closure refresher is now wired into the watcher
product-state post-step. After a future real fresh-signal execution run writes
official reports, the same post-step that refreshes product state can also
generate live closure evidence and verification before the goal-status packet
is rebuilt.

| Item | Evidence |
| --- | --- |
| Product-state integration | `refresh_strategygroup_runtime_product_state_packets.py` accepts `--refresh-live-closure-evidence` |
| Watcher hook | `80-product-state-refresh.conf` enables `--refresh-live-closure-evidence` and writes `runtime-live-closure-evidence*.json` under the watcher report directory |
| Refresh ordering | Live closure evidence refresh runs before `strategygroup-runtime-goal-status.json` refresh, so goal status can observe first-live completion in the same watcher post-step |
| Refresh summary | `product-state-refresh-packet.json` includes `live_closure_evidence_refresh` with verification status, completion booleans, and reject reasons |
| Healthy no-signal behavior | `live_closure_refresh_not_started` is not a blocker and remains Owner state `等待机会` |
| Rejected evidence behavior | `live_closure_refresh_rejected` becomes a refresh blocker instead of silently completing the goal |
| Boundary | This remains report projection only; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |
| Verification | Product-state refresh and systemd unit tests cover the new hook and safety invariants |

### 2026-06-18 Live Closure Evidence Refresh

The first bounded live-order closure path now has a local refresher that scans
a report directory and writes the canonical evidence packet plus verification
packet consumed by the low-noise monitor and goal-progress audit. This removes
the manual packet-assembly gap after a future real fresh-signal execution run.

| Item | Evidence |
| --- | --- |
| Refresh command | `scripts/refresh_runtime_live_closure_evidence_packets.py --report-dir <reports-dir>` |
| Generated evidence | Writes `runtime-live-closure-evidence.json` |
| Generated verification | Writes `runtime-live-closure-evidence-verification.json` |
| Generated refresh report | Writes `runtime-live-closure-evidence-refresh.json` |
| No-evidence behavior | Emits `live_closure_refresh_not_started` / `live_closure_not_started`, which remains Owner state `等待机会` |
| Partial-evidence behavior | Emits `live_closure_refresh_in_progress` when official live evidence has started but later closure stages are not complete |
| Complete-evidence behavior | Emits `live_closure_refresh_complete` only when all 13 first-live closure evidence keys pass verifier checks |
| Anti-false-positive guard | Skips non-live dry-run/mock/sample/controlled inputs by default and rejects any exchange-result shape that lacks positive live-exchange and real-order markers |
| Boundary | This is report projection only; it does not create evidence and does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |
| Verification | `test_refresh_runtime_live_closure_evidence_packets.py` covers complete, in-progress, no-live-evidence, and no-live-marker rejection paths |

### 2026-06-18 Live Closure Evidence Snapshot Projection

The low-noise Tokyo snapshot and daily-check path now consumes first-live
closure evidence without adding another remote interaction. The same L1
read-only snapshot reads the closure packet files when present, verifies an
evidence packet locally when a verification packet is absent, and projects the
result into daily-check fields that goal-progress already understands.

| Item | Evidence |
| --- | --- |
| Snapshot files | `probe_tokyo_runtime_snapshot.py` reads `runtime-live-closure-evidence.json` and `runtime-live-closure-evidence-verification.json` in the existing report directory |
| Snapshot projection | `first_bounded_real_order_complete`, `real_order_closure_proven`, and `runtime_live_closure_evidence_status` are exposed in snapshot checks |
| Daily-check projection | `run_strategygroup_runtime_daily_check.py` carries those fields through L1/L0 reports and marks waiting false when real closure is proven |
| Rejected evidence | Rejected live closure evidence becomes a product gap, not a completed first-live goal |
| Interaction budget | This reuses the existing L1 read-only snapshot and does not add a second Tokyo interaction |
| Safety | Read/projection/test work only; no server mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Live Closure Evidence Packet Builder

The first bounded live-order closure path now has a local packet builder that
collects official report evidence ids into the same 13-key contract consumed by
the live closure verifier. This is the handoff layer between a future real
fresh-signal execution run and the goal-progress completion boundary.

| Item | Evidence |
| --- | --- |
| Packet builder | `scripts/runtime_live_closure_evidence_packet.py` |
| Contract mapping | Maps official source reports into `live_watcher_signal_packet_id` through `submit_outcome_review_id` |
| Goal-progress integration | `run_strategygroup_runtime_goal_progress_audit.py` can auto-verify `runtime-live-closure-evidence.json` when a separate verification packet is absent |
| Anti-false-positive guard | Controlled, dry-run, rehearsal, no-live-exchange, or no-real-order evidence is emitted with reject reasons and cannot complete the first-live goal |
| Boundary | The builder only reads existing JSON reports and writes a local packet; it does not create execution evidence and does not call FinalGate or Operation Layer |
| Safety | Local packet/test work only; no Tokyo API call, server mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Live Closure Evidence Verifier

The P0 first bounded live-order goal now has a local evidence verifier for the
future real closure packet. It verifies a supplied live evidence packet against
the first-live-closure contract and can distinguish complete, in-progress, and
rejected closure evidence without calling any live execution path.

| Item | Evidence |
| --- | --- |
| Verifier | `scripts/runtime_live_closure_evidence_verifier.py` |
| Complete status | `live_closure_complete` only when all 13 contract evidence keys are present in order |
| Official source guard | Complete evidence must also carry an official live closure source marker; shape-only mock/rehearsal packets are rejected |
| In-progress status | Missing exchange-native hard stop blocks later finalize/reconciliation stages with `blocked_by_previous_stage` |
| Rejected status | Replay, synthetic signal, or disabled-smoke evidence becomes `blocked_live_closure_rejected` |
| Goal-progress integration | `run_strategygroup_runtime_goal_progress_audit.py` accepts `--live-closure-evidence-verification-json` and only marks the goal complete when verifier completion is true |
| Boundary | Verifier is local evidence classification only; it does not create evidence, does not call FinalGate, and does not call Operation Layer |
| Safety | Local packet/test work only; no Tokyo API call, server mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Chain Closure Live-Proof Contract Alignment

The runtime chain-closure status now consumes the same first-live-closure
contract used by the P0 cutover-readiness packet. This prevents the monitor
surface from reporting an older, shorter live-proof list while the cutover
contract requires the full first-order closure evidence sequence.

| Item | Evidence |
| --- | --- |
| Chain-closure source | `scripts/runtime_execution_chain_closure_status.py` imports `runtime_live_cutover_readiness.build_live_closure_cutover_contract()` |
| Real execution status | Remains `waiting_for_live_action_time_proof`; `real_order_allowed=false` after local dry-run success |
| Live stage count | `live_closure_stage_count=9` |
| Missing live evidence count | `missing_live_proofs` now contains 13 contract evidence keys from `live_watcher_signal_packet_id` through `submit_outcome_review_id` |
| Boundary | Local dry-run proof still cannot replace live same-run FinalGate, official Operation Layer, exchange acceptance, exchange-native protection, and post-submit settlement evidence |
| Safety | Local packet/test work only; no Tokyo API call, server mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 First Live Closure Cutover Contract

The P0 cutover readiness packet now includes a machine-readable first bounded
live-order closure contract. This contract defines the exact evidence sequence
that must be present after a real fresh selected StrategyGroup signal before the
first live closure can be treated as complete.

| Item | Evidence |
| --- | --- |
| Contract source | `scripts/runtime_live_cutover_readiness.py` emits `live_closure_cutover_contract` |
| Ordered stages | live fresh signal, RequiredFacts ready, candidate/auth bound, action-time FinalGate, official Operation Layer ready, real exchange acceptance, exchange-native protection, post-submit finalize, reconciliation/settlement/review |
| Required evidence keys | `live_watcher_signal_packet_id`, `required_facts_readiness_packet_id`, `candidate_id`, `runtime_grant_id`, `fresh_submit_authorization_id`, `action_time_finalgate_packet_id`, `operation_layer_submit_authorization_id`, `exchange_submit_execution_result_id`, `exchange_native_hard_stop_order_id`, `runtime_post_submit_finalize_packet_id`, `post_submit_reconciliation_evidence_id`, `post_submit_budget_settlement_id`, `submit_outcome_review_id` |
| Regression guard | Goal-progress marks stale old cutover packets without this contract as `blocked` with `live_closure_cutover_contract:missing_or_not_ready` |
| Boundary | The contract is not submit authority and does not authorize mock/replay/disabled-smoke evidence as live closure proof |
| Safety | Local packet/test work only; no Tokyo API call, server mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 P0 Live Cutover Readiness Packet

The P0 first bounded live-order goal now has a local cutover-readiness packet
that compresses the existing dry-run audit into one Owner-readable question:
are non-market blockers cleared for the next fresh selected StrategyGroup
signal?

| Item | Evidence |
| --- | --- |
| Cutover packet | `scripts/runtime_live_cutover_readiness.py` builds `runtime-live-cutover-readiness.json` and Owner-readable Markdown |
| Current cutover state | `status=live_cutover_waiting_for_fresh_signal`, `owner_state=等待机会`, `next_fresh_signal_cutover_ready=true`, `current_real_submit_allowed=false` |
| Non-market blockers | `non_market_blockers=[]`; strategy scope, entry fast chain, Operation Layer relay, hard blocker policy, exit/protection recovery, post-submit close loop, and dry-run safety sections are all `ready` |
| Legacy confirmation regression guard | Cutover packet checks `disabled_smoke_not_real_execution_proof`, `legacy_local_registration_probe_tolerated_without_blocking_cutover`, `post_submit_outcomes_do_not_require_owner_chat_confirmation`, and `standing_reduce_only_recovery_does_not_require_owner_chat_confirmation` |
| Goal progress integration | `run_strategygroup_runtime_goal_progress_audit.py` reads or locally auto-generates the packet and exposes `live_cutover_readiness_boundary.status=ready` with `product_gaps=[]` |
| Boundary | This is cutover readiness, not real submit authority. Current real submit remains blocked by absence of a live fresh selected StrategyGroup signal |
| Safety | Local packet/test work only; no Tokyo API call, server mutation, live FinalGate call, live Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Replay Corpus and Post-Submit Simulator Expansion

The P0.5 rehearsal loop now covers a broader local corpus instead of a single
sample. This checkpoint remains local-only and does not deploy to Tokyo.

| Item | Evidence |
| --- | --- |
| MPG-001 replay corpus | `docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json` covers `trend_continuation`, `false_breakout`, `fast_reversal`, `choppy_no_trade`, `stale_signal`, `missing_facts`, `active_position_conflict`, and `protection_missing` |
| Cost review skeleton | Replay events carry `fee_estimate_usdt`, `slippage_estimate_usdt`, `funding_impact_usdt`, `min_qty_step_size_impact`, `net_edge_note`, and `not_submit_authority=true` |
| Post-submit simulator | `docs/current/strategy-group-handoffs/MPG-001/replay/post-submit-simulator-matrix.json` covers accepted/protected, SL creation failed, partial fill, rejected before acceptance, closed by SL, closed by TP1, and still-open paths |
| Dry-run required checks | Runtime dry-run audit exposes `mpg001_replay_corpus_checked`, `post_submit_simulator_matrix_checked`, and `cost_review_skeleton_checked` |
| Quiet monitor retune | `tokyo-runtime-quiet-monitor` heartbeat changed from 30 minutes to 2 hours; baseline records `healthy_waiting_for_market_interval_minutes=120` |
| Safety | Local test/replay/simulator/automation-frequency work only; no Tokyo deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Runtime Replay Lab Checkpoint

The P0.5 Runtime Replay Lab now has a local MPG-001 contract, a tracked
historical-style replay sample, a tracked synthetic signal fixture set, and a
unified dry-run audit integration. This checkpoint is local-only and does not
deploy to Tokyo.

| Item | Evidence |
| --- | --- |
| Replay contract | `src/domain/strategygroup_runtime_replay.py` defines replay events, report packets, review recommendations, safety invariants, and external sidecar policy |
| MPG-001 sample | `docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-sample.json` |
| Synthetic fixtures | `docs/current/strategy-group-handoffs/MPG-001/replay/synthetic-signal-fixtures.json` covers no-signal, fresh-pass, stale, missing-fact, conflict, protection-missing, and profile-boundary branches |
| Local runner | `scripts/run_strategygroup_runtime_replay_lab.py` emits a replay report and Owner-readable local progress note |
| Dry-run audit | `runtime-dry-run-audit-chain` includes `runtime_replay_lab_checked`, `mpg001_replay_sample_checked`, `synthetic_signal_fixture_set_checked`, and `external_replay_adapter_sidecar_only_checked` |
| External framework policy | Freqtrade or similar tools are future sidecar research adapters only, not FinalGate, Operation Layer, Owner state, live signal identity, or real-submit authority |
| Safety | Local test/replay work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

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
`l4_real_order_requirements` list. The legacy label
`L4 tiny_real_order_eligible` means allocated-subaccount bounded-aggressive
real-order eligibility for the official runtime chain, not a request to lower
leverage, shrink notional, or avoid eligible live actions. The dry-run audit
fails if the L4 requirement list omits any required step or drifts from the
current first-live-order boundary.

| Item | Evidence |
| --- | --- |
| Policy source | `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json` includes `l4_real_order_requirements` |
| Required chain | selected scope, Owner-allocated subaccount/profile boundary, fresh signal, RequiredFacts, candidate/auth, action-time FinalGate, official Operation Layer, exchange-native protection, finalize, reconciliation, budget settlement, review |
| New dry-run check | `l4_real_order_requirements_complete=true` inside `runtime_tier_policy_validation.checks` |
| Boundary | L4 remains limited to `MPG-001`; tier policy is not execution authority, FinalGate input, Operation Layer input, or sizing default |
| Safety | Local dry-run/test work only; no Tokyo call, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Post-Submit Owner-Confirmation Regression Guard

The dry-run post-submit exit outcome matrix now explicitly proves that none of
the six covered post-submit outcomes reintroduce per-order Owner chat
confirmation as a next-step gate. Recovery after protection failure still
requires standing authorization, action-time FinalGate, and the official
Operation Layer; it does not require a new chat approval inside the selected
Owner-allocated subaccount/profile boundary.

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
| Monitor baseline | At that checkpoint, `docs/current/RUNTIME_MONITOR_BASELINE.json` expected `18c30ae03dc735e6f4043fbdcdeedd75cc16faba` |
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
| Monitor baseline | At that checkpoint, `docs/current/RUNTIME_MONITOR_BASELINE.json` expected `ea34594badc066bc0c714d02c385341106665e07` |
| Verification | `84 passed` for readiness pack, daily check, goal progress, goal status, and dry-run audit tests; `py_compile` passed for watcher readiness / daily check / goal status scripts |
| Safety | Fix and deploy did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Cutover Target Mode Audit Checkpoint

The active target mode is **P0 First Bounded Live Order Closure Cutover**. The
goal is not complete until a real fresh selected StrategyGroup signal produces
the first bounded live order closure with exchange acceptance, exchange-native
protection, post-submit finalize, reconciliation, budget settlement, and review
evidence. This checkpoint confirms the non-market cutover chain remains ready
and the remaining blockers are market-dependent.

| Item | Evidence |
| --- | --- |
| Active goal | `P0 First Bounded Live Order Closure Cutover` |
| Current state | `waiting_for_market`; next fresh signal cutover ready; current real submit not allowed without a real fresh signal |
| Dispatcher audit | `runtime_signal_watcher_resume_dispatcher.py` keeps the path as fresh signal -> candidate/auth -> action-time FinalGate -> Operation Layer evidence -> official Operation Layer submit -> post-submit finalize |
| Legacy confirmation posture | Non-executing prepare, fresh authorization binding, real submit, and reduce-only recovery use standing authorization inside the selected boundary; no per-order chat confirmation is reintroduced |
| Local cutover readiness | `runtime_live_cutover_readiness.py`: `status=live_cutover_waiting_for_fresh_signal`; all cutover sections ready |
| Replay lab | `run_strategygroup_runtime_replay_lab.py`: `P0.5 replay_ready`, 8 replay samples, 7 post-submit simulator cases, and synthetic fixtures for no signal, stale signal, missing facts, active position, open order, protection missing, boundary mismatch, and fresh-signal pass |
| Low-noise monitor | `run_strategygroup_runtime_daily_check.py --from-cache --require-fresh-cache --owner-progress`: `DONT_NOTIFY`, `healthy_waiting_for_market`, `L0_local_cache_read`, `remote_interaction_count=0`, `10 pass / 4 waiting / 0 blocked` |
| Goal progress | `run_strategygroup_runtime_goal_progress_audit.py --owner-progress`: `not_complete_waiting_for_market`, P0.5 ready, non-market blockers none |
| Verification | `94 passed` for dispatcher, systemd unit, live closure evidence, execution-chain closure, and StrategyGroup goal-status tests |
| Safety | This checkpoint did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-19 BTPC L2 Replay-to-Review Expansion

The P0.5 replay lane now covers `BTPC-001` as an L2 shadow-candidate
observation StrategyGroup. This expands no-action / would-enter diagnostics
without changing the P0 L4 real-order lane.

| Item | Evidence |
| --- | --- |
| BTPC L2 corpus | `docs/current/strategy-group-handoffs/BTPC-001/replay/btpc-001-l2-replay-corpus.json` covers `bear_pullback_would_enter`, `no_signal_bear_trend_not_ready`, `strong_uptrend_conflict`, `missing_derivatives_context`, and `stale_signal` |
| Replay contract | `src/domain/strategygroup_runtime_replay.py` validates `BTPC-001` L2 replay events and keeps them non-executing |
| Local runner | `scripts/run_strategygroup_runtime_replay_lab.py` now reports `L2 shadow replay samples: 5` |
| Dry-run audit | `runtime-dry-run-audit-chain` exposes `btpc001_l2_shadow_replay_checked=true` |
| L4 boundary | `MPG-001` remains the only L4 real-order eligible StrategyGroup; `BTPC-001` remains L2 shadow-candidate observation only |
| Verification | `python3 -m py_compile src/domain/strategygroup_runtime_replay.py scripts/run_strategygroup_runtime_replay_lab.py scripts/runtime_dry_run_audit_chain.py`; `/opt/homebrew/bin/pytest tests/unit/test_strategygroup_runtime_replay_lab.py tests/unit/test_runtime_dry_run_audit_chain.py -q`; replay report and dry-run audit both `status=passed` |
| Safety | Local replay/test work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 VCB L1 Observe Replay-to-Review Expansion

The P0.5 replay lane now covers `VCB-001` as an L1 observe-only StrategyGroup.
This expands volatility-compression breakout visibility without promoting VCB
to L2 shadow-candidate or L4 real-order scope.

| Item | Evidence |
| --- | --- |
| VCB L1 corpus | `docs/current/strategy-group-handoffs/VCB-001/replay/vcb-001-l1-observe-replay-corpus.json` covers `compression_breakout_would_enter`, `no_signal_no_compression`, `false_breakout_disable_needed`, `missing_compression_context`, and `stale_signal` |
| Replay contract | `src/domain/strategygroup_runtime_replay.py` validates `VCB-001` L1 observe replay events and keeps them non-executing |
| Local runner | `scripts/run_strategygroup_runtime_replay_lab.py` now reports `L1 observe replay samples: 5` |
| Dry-run audit | `runtime-dry-run-audit-chain` exposes `vcb001_l1_observe_replay_checked=true` |
| L4 boundary | `MPG-001` remains the only L4 real-order eligible StrategyGroup; `VCB-001` remains L1 observe-only |
| Safety | Local replay/test work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 LSR L1 Observe Replay-to-Review Expansion

The P0.5 replay lane now covers `LSR-001` as an L1 observe-only StrategyGroup.
This keeps liquidity-sweep observations and the short-revival rewrite gap
visible without promoting LSR to L2 shadow-candidate or L4 real-order scope.

| Item | Evidence |
| --- | --- |
| LSR L1 corpus | `docs/current/strategy-group-handoffs/LSR-001/replay/lsr-001-l1-observe-replay-corpus.json` covers `liquidity_sweep_long_would_enter_current_v0`, `short_revival_rewrite_needed`, `no_signal_no_sweep_reclaim`, `missing_range_context`, and `stale_signal` |
| Replay contract | `src/domain/strategygroup_runtime_replay.py` validates `LSR-001` L1 observe replay events and keeps them non-executing |
| Local runner | `scripts/run_strategygroup_runtime_replay_lab.py` reports L1 observe replay samples covering both `VCB-001` and `LSR-001` |
| Dry-run audit | `runtime-dry-run-audit-chain` exposes `lsr001_l1_observe_replay_checked=true` |
| L4 boundary | `MPG-001` remains the only L4 real-order eligible StrategyGroup; `LSR-001` remains L1 observe-only |
| Safety | Local replay/test work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 BRF L1 Observe Replay-to-Review Expansion

The P0.5 replay lane now covers `BRF-001` as an L1 observe-only StrategyGroup.
This expands bear-rally-failure short visibility and short-squeeze-risk review
without promoting BRF to L2 shadow-candidate or L4 real-order scope.

| Item | Evidence |
| --- | --- |
| BRF L1 corpus | `docs/current/strategy-group-handoffs/BRF-001/replay/brf-001-l1-observe-replay-corpus.json` covers `bear_rally_failure_short_would_enter`, `no_signal_rally_not_failed`, `short_squeeze_risk_revision_needed`, `missing_rally_context`, and `stale_signal` |
| Replay contract | `src/domain/strategygroup_runtime_replay.py` validates `BRF-001` L1 observe replay events and keeps them non-executing |
| Local runner | `scripts/run_strategygroup_runtime_replay_lab.py` reports L1 observe replay samples covering `BRF-001`, `VCB-001`, and `LSR-001` |
| Dry-run audit | `runtime-dry-run-audit-chain` exposes `brf001_l1_observe_replay_checked=true` |
| L4 boundary | `MPG-001` remains the only L4 real-order eligible StrategyGroup; `BRF-001` remains L1 observe-only |
| Safety | Local replay/test work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Replay-to-Review Owner Summary Checkpoint

The P0.5 replay Owner progress report now includes a StrategyGroup-level review
table. This makes broader market observation legible while P0 waits for a real
fresh selected StrategyGroup signal.

| Item | Evidence |
| --- | --- |
| Owner table | `scripts/run_strategygroup_runtime_replay_lab.py` emits `StrategyGroup Replay Review` with per-group layer, sample count, review-signal count, quiet/no-action count, revise count, and execution boundary |
| Covered groups | Current table covers `MPG-001`, `BTPC-001`, `BRF-001`, `VCB-001`, and `LSR-001` |
| Verification | `tests/unit/test_strategygroup_runtime_replay_lab.py` asserts the Owner progress rows for `BTPC-001`, `BRF-001`, `VCB-001`, and `LSR-001` |
| Safety | Reporting work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Signal Coverage Owner Opportunity Table Checkpoint

The P0.5 signal coverage expansion review now makes broader observe-only
would-enter rows directly reviewable. Each Owner progress table row includes
the StrategyGroup tier, suggested next tier, suggested action, confidence, and
execution boundary.

| Item | Evidence |
| --- | --- |
| Owner opportunity table | `scripts/build_strategygroup_signal_coverage_expansion_review.py` emits `StrategyGroup`, `Symbol`, `Side`, `Confidence`, `Tier`, `Next tier`, `Action`, and `Boundary` columns |
| Review use | Broader would-enter rows can now be triaged as observe-only, L2 shadow review, L3 armed-observation review, L4 official-chain-only, or unclassified handoff work |
| L4 boundary | The table still reports `real_order_scope_change_recommended=false`, `l4_promotion_recommended=false`, and `may_place_real_order_after_this_review=false` |
| Verification | `tests/unit/test_strategygroup_signal_coverage_expansion_review.py` asserts the owner table header and row boundary text |
| Safety | Reporting work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 L2 Opportunity Triage Explanation Checkpoint

The P0.5 L2 readiness and intake dry-run Owner reports now explain why broader
would-enter observations do or do not become new L2 intake candidates. This
keeps market-opportunity review moving while P0 waits for a real fresh selected
StrategyGroup signal.

| Item | Evidence |
| --- | --- |
| L2 readiness table | `scripts/build_strategygroup_l2_readiness_review.py` emits StrategyGroup, symbol, side, current tier, priority, L2 readiness, recommended action, and blocking gaps |
| Intake no-candidate explanation | `scripts/run_strategygroup_l2_intake_dry_run.py` reports source readiness rows, enabled L2 count, blocked row count, and `no_conditional_l2_review_candidates` when no new intake row exists |
| Current interpretation | `BTPC-001` can continue L2 shadow-candidate observation; `LSR-001`, `RBR-001`, and `VCB-001` remain blocked by explicit L2 gaps |
| L4 boundary | The reports still keep `tier_policy_change=false`, `l4_scope_change=false`, `shadow_candidate_now=false`, `FinalGate=false`, `Operation Layer=false`, and `real_order=false` |
| Verification | `tests/unit/test_strategygroup_l2_readiness_review.py` and `tests/unit/test_strategygroup_l2_intake_dry_run.py` assert the richer Owner rows, source states, and no-candidate reason |
| Safety | Reporting work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Opportunity Decision Loop Checkpoint

The P0.5 path now has a repeatable local decision loop instead of another
report-only layer. The loop joins observed would-enter rows, replay coverage,
blocking gaps, and L2 tier state into per-StrategyGroup decisions.

| Item | Evidence |
| --- | --- |
| Decision loop script | `scripts/build_strategygroup_opportunity_decision_loop.py` consumes signal coverage expansion, L2 readiness, L2 intake, and replay lab artifacts |
| Machine output | `latest-opportunity-decision-loop.json` emits per-StrategyGroup `observed_signal`, `replay_verification`, `blocking_gaps_before_l2`, `gap_work_items`, `decision_action`, and `next_checkpoint` |
| Current decisions | Current local run maps `BTPC-001` to `continue_l2_shadow_quality_review`, `LSR-001` and `VCB-001` to `repair_blocking_gaps_with_replay_or_facts`, and `RBR-001` to `park_or_vocabulary_only` |
| L4 boundary | The loop keeps `real_order_authorized_count=0`, `l4_scope_change_recommended_count=0`, `places_order=false`, `calls_finalgate=false`, `calls_operation_layer=false`, and `calls_exchange_write=false` |
| Verification | `tests/unit/test_strategygroup_opportunity_decision_loop.py` covers L2-enabled continuation, L1 replay-plus-gap repair, missing-replay-before-L2, forbidden source effects, and CLI output |
| Safety | Local decision-loop work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Opportunity Work Queue Checkpoint

The local decision loop now emits an actionable P0.5 work queue so broader
would-enter observations do not stop at markdown/report review. The queue turns
each blocking gap into work type, priority, scheduled status, validation command,
and completion signal.

| Item | Evidence |
| --- | --- |
| Work queue output | `latest-opportunity-decision-loop.json` now includes `work_queue.status`, `next_local_checkpoint`, `by_work_type`, `by_owner_priority`, and per-item `queue_id`, `actionable_task`, `validation_command`, and `completion_signal` |
| Current queue | Current local run reports `work_queue_item_count=19`, `scheduled_work_queue_item_count=15`, and next checkpoint `repair_classifier_or_disable_state_gaps_for_lsr_vcb` |
| Current grouping | Current work types are classifier/rule work, economic replay work, required fact or market-data work, strategy quality review, and strategy review work |
| Scheduling rule | `LSR-001` and `VCB-001` classifier/economic gaps are scheduled for P0.5 repair; `BTPC-001` continues L2 shadow-quality/fact review; `RBR-001` stays unscheduled/parked unless new evidence appears |
| L4 boundary | The queue keeps `real_order_authorized=0`, `l4_scope_change_recommended=0`, `places_order=false`, `calls_finalgate=false`, `calls_operation_layer=false`, and `calls_exchange_write=false` |
| Verification | `tests/unit/test_strategygroup_opportunity_decision_loop.py` asserts work-queue counts, priority/type grouping, parked-item scheduling behavior, missing-replay queue behavior, CLI output, and safety invariants |
| Safety | Local work-queue generation only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 LSR/VCB Classifier Repair Spec Checkpoint

The highest-priority P0.5 work queue items for `LSR-001` and `VCB-001` now have
machine-readable classifier repair specs tied to replay acceptance cases. This
turns the classifier/disable-state gaps into a local closure contract instead
of another report-only note.

| Item | Evidence |
| --- | --- |
| Policy input | `main-control-signal-coverage-expansion-policy.json` defines `classifier_repair_spec` for `LSR-001` and `VCB-001` |
| LSR target | `LSR-001` repair target is `side_specific_short_revival_classifier`, covering the lookahead rewrite and missing disable-state gaps |
| VCB target | `VCB-001` repair target is `true_breakout_pre_entry_classifier`, covering the pre-entry classifier and false-breakout disable-state gaps |
| Replay coverage | `latest-opportunity-decision-loop.json` reports `replay_case_coverage.covered=true` for all four LSR/VCB classifier work-queue items |
| L2 boundary | The specs keep both groups at L1 observe-only; they are not L2 promotion authority, L4 scope expansion, FinalGate input, Operation Layer input, or real-order authority |
| Verification | `tests/unit/test_strategygroup_l2_readiness_review.py` and `tests/unit/test_strategygroup_opportunity_decision_loop.py` assert repair specs, replay-case coverage, no real-order authority, and no L4 scope change |
| Safety | Local policy/specification and replay-coverage projection only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 LSR/VCB Economic Replay Spec Checkpoint

The P0.5 work queue now also carries economic replay specs for `LSR-001` and
`VCB-001`. The replay contract exposes cost, slippage, funding, min-qty/step,
fill-slot, leverage-survival, net-edge, and no-submit-authority fields without
reducing Owner-selected leverage or creating execution authority.

| Item | Evidence |
| --- | --- |
| Replay cost contract | `StrategyGroupReplayCostReview` now includes `fill_slot_assumption`, `leverage_survival_note`, and `does_not_lower_owner_selected_leverage` |
| Policy input | `main-control-signal-coverage-expansion-policy.json` defines `economic_replay_spec` for `LSR-001` and `VCB-001` |
| Static corpus | LSR/VCB tracked replay corpus samples used by the economic specs carry fill-slot and leverage-survival fields |
| Work queue coverage | Current `latest-opportunity-decision-loop.json` reports `economic_case_coverage.covered=true`, `missing_cases=[]`, and `uncovered_cases=[]` for all three LSR/VCB economic replay queue items |
| L2 boundary | The specs are local replay review only; they are not L2 promotion authority, L4 scope expansion, FinalGate input, Operation Layer input, or real-order authority |
| Verification | `tests/unit/test_strategygroup_runtime_replay_lab.py`, `tests/unit/test_strategygroup_l2_readiness_review.py`, and `tests/unit/test_strategygroup_opportunity_decision_loop.py` assert replay cost fields, economic specs, economic-case coverage, no real-order authority, and no L4 scope change |
| Safety | Local replay/specification and coverage projection only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Opportunity Work Queue Coverage State Checkpoint

The P0.5 opportunity work queue now distinguishes items whose local replay/spec
coverage is ready from items still waiting on fact sources, strategy review,
strategy-quality decisions, or parked evidence. This keeps the local loop from
turning into more report text while also preventing covered LSR/VCB replay work
from being misread as L2 promotion, L4 scope expansion, or real-order authority.

| Item | Evidence |
| --- | --- |
| Queue fields | `latest-opportunity-decision-loop.json` work items now include `coverage_status`, `coverage_ready`, and `next_stage_decision` |
| Current local run | `observed_opportunity_count=4`, `replay_covered_count=3`, `work_queue_item_count=19`, `scheduled_work_queue_item_count=15`, `coverage_ready_item_count=7`, `coverage_pending_item_count=4`, and `strategy_decision_pending_count=1` |
| Coverage grouping | `by_coverage_status` reports `local_replay_coverage_ready=7`, `fact_source_pending=4`, `strategy_decision_pending=1`, `strategy_review_pending=3`, and `parked=4` |
| Next stage | Covered LSR/VCB classifier/economic items emit `strategy_quality_review_before_l2_no_promotion`; BTPC missing fact items emit `attach_fact_source_before_l2_review`; RBR remains `parked` |
| L4 boundary | Coverage-ready is not candidate authority, FinalGate authority, Operation Layer authority, L2 promotion authority, L4 scope expansion, or real-order authority |
| Verification | `tests/unit/test_strategygroup_opportunity_decision_loop.py` asserts LSR/VCB coverage-ready states, BTPC fact-source pending state, RBR parked state, no real-order authority, and no L4 scope change |
| Safety | Local decision-loop work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Strategy Quality Decision Rollup Checkpoint

The P0.5 decision loop now rolls coverage-ready queue items into a
StrategyGroup-level quality decision. This moves the local loop from "coverage
exists" to "what should the project do with the covered evidence" without
promoting any group, widening L4 scope, or creating real-order authority.

| Item | Evidence |
| --- | --- |
| Quality rollup | `latest-opportunity-decision-loop.json` now includes `strategy_quality_decisions.status=ready`, `rows`, `by_decision`, and safety invariants |
| Current local decisions | Current local run reports `revise_before_l2=2`, `keep_observing=1`, `park=1`, `needs_replay=0`, `real_order_authorized=0`, and `l4_scope_change_recommended=0` |
| LSR/VCB outcome | `LSR-001` and `VCB-001` roll up to `revise_before_l2` with next stage `record_revise_decision_and_keep_l1_until_review_passes` |
| BTPC/RBR outcome | `BTPC-001` remains `keep_observing_l2_shadow_with_fact_review`; `RBR-001` remains `park_until_new_edge` |
| Next checkpoint | `decision.default_next_step=record_lsr001_vcb001_strategy_quality_revise_before_l2`; `work_queue.next_local_checkpoint=record_strategy_quality_decisions_for_coverage_ready_items` |
| Boundary | Strategy-quality decisions are not L2 promotion authority, L4 scope change, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_strategygroup_opportunity_decision_loop.py` asserts the rollup counts, LSR/VCB revise decisions, BTPC keep-observing-with-fact-review, RBR parked state, Owner progress table, and no live-authority expansion |
| Safety | Local decision-loop work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Strategy Quality Revision Task Checkpoint

The P0.5 decision loop now turns `revise_before_l2` into concrete revision
tasks. This prevents the LSR/VCB quality decision from becoming another
summary-only state and gives the next local checkpoint a classifier/economic
repair surface to execute and verify.

| Item | Evidence |
| --- | --- |
| Revision task output | `strategy_quality_decisions.rows[].revision_tasks` now carries queue id, work type, gap, actionable task, validation command, completion signal, revision stage, and no-authority flags |
| Current local run | `revision_task=7`, `classifier_revision_task=4`, `economic_revision_task=3`, `revise_before_l2=2`, `real_order_authorized=0`, and `l4_scope_change_recommended=0` |
| LSR tasks | `LSR-001` emits classifier revisions for `lookahead_failed_proxy_requires_rewrite` and `lsr_disable_classifier_state_missing_from_runtime`, plus economic survival review for `cost_fill_slot_m2m_and_leverage_boundary_missing` |
| VCB tasks | `VCB-001` emits classifier revisions for `false_breakout_disable_state_missing_from_runtime` and `pre_entry_classifier_does_not_reproduce_post_entry_edge`, plus economic survival review for `slot_m2m_equity_and_leverage_ruin_state_missing` and `volume_compression_cost_m2m_full_sequence_negative` |
| Owner progress | The local Owner markdown `Strategy Quality Decisions` table includes `Revision Tasks` so the revise decision exposes work count without reading raw packets |
| Boundary | Revision tasks are not strategy-parameter changes, tier-policy changes, L2 promotion authority, L4 scope expansion, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_strategygroup_opportunity_decision_loop.py` asserts revision-task counts, task stages, validation commands, completion signals, Owner progress table, and no live-authority expansion |
| Safety | Local decision-loop work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 Strategy Quality Revision Completion State Checkpoint

The P0.5 decision loop now distinguishes revision tasks that merely exist from
revision tasks that are locally ready to execute and verify. This moves the
loop from "write down the LSR/VCB repair work" to "prove the repair work has
the replay/spec/cost acceptance surface needed for the next local revision
checkpoint."

| Item | Evidence |
| --- | --- |
| Revision readiness fields | `strategy_quality_decisions.rows[].revision_tasks[]` now emits `revision_status`, `revision_ready`, `acceptance_case_coverage_ready`, required entry/disable/cost-field counts, and `completion_blocker` |
| Completion rollup | `strategy_quality_decisions.revision_completion.status=local_revision_completion_ready` when all revision tasks have coverage, required states/fields, and no-authority boundaries |
| Current local run | `revision_task=7`, `revision_ready=7`, `classifier_revision_ready=4`, `economic_revision_ready=3`, `remaining_revision_blocker=0`, `real_order_authorized=0`, and `l4_scope_change_recommended=0` |
| Next checkpoint | `decision.default_next_step=execute_lsr001_vcb001_local_revision_tasks_before_l2` |
| Owner progress | The local Owner markdown adds `Revision Ready` beside `Revision Tasks` so readiness is visible without reading raw packets |
| Boundary | Revision-ready is not strategy-parameter mutation, tier-policy mutation, L2 promotion authority, L4 scope expansion, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_strategygroup_opportunity_decision_loop.py` asserts revision readiness counts, status rollups, acceptance-case coverage, entry/disable/cost-field counts, completion blockers, Owner markdown, and no live-authority expansion |
| Safety | Local decision-loop work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 LSR/VCB Local Revision Execution Checkpoint

The P0.5 loop now executes the ready LSR/VCB local revision tasks in the local
classifier and replay-review surfaces. This is still pre-L2 review work: it
does not promote either StrategyGroup, expand L4 scope, or create real-order
authority.

| Item | Evidence |
| --- | --- |
| LSR classifier execution | `LSR001PriceActionEvaluator` now uses `lsr-001-price-action-v1`, emits `side_specific_short_revival_classifier`, disables the old long-preview conflict, and exposes entry/disable-state evidence |
| VCB classifier execution | `VCB001PriceActionEvaluator` now uses `vcb-001-price-action-v1`, requires compression breakout plus volume expansion, disables wick-only false breakout, and exposes entry/disable-state evidence |
| Policy execution evidence | `main-control-signal-coverage-expansion-policy.json` records `revision_execution.status=local_classifier_revision_executed` and `replay_execution.status=local_economic_replay_executed` for LSR/VCB |
| Readiness rollup | `latest-l2-readiness-review.json` reports `classifier_revision_executed_count=2`, `economic_replay_executed_count=2`, `tier_policy_change_recommended=false`, `l4_scope_change_recommended=false`, and `shadow_candidate_creation_recommended_now=false` |
| Decision-loop rollup | `latest-opportunity-decision-loop.json` reports `revision_executed=7`, `classifier_revision_executed=4`, `economic_revision_executed=3`, `remaining_revision_execution=0`, and `revision_execution.status=local_revision_execution_complete` |
| Next checkpoint | `decision.default_next_step=run_lsr001_vcb001_post_revision_replay_review_before_l2` |
| Boundary | Revision execution is not strategy-tier mutation, L2 promotion authority, L4 scope expansion, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_reference_price_action_evaluators.py`, `tests/unit/test_strategygroup_l2_readiness_review.py`, and `tests/unit/test_strategygroup_opportunity_decision_loop.py` assert classifier execution behavior, execution rollups, Owner markdown, and no live-authority expansion |
| Safety | Local domain/review work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 LSR/VCB Post-Revision Replay Review Checkpoint

The P0.5 loop now verifies the revised LSR/VCB classifiers with deterministic
post-revision replay cases before any L2 promotion review. This closes the
local loop from "revision executed" to "revision behavior replay-checked" while
keeping the real P0 live path waiting for a real selected StrategyGroup fresh
signal.

| Item | Evidence |
| --- | --- |
| Review artifact | `latest-post-revision-replay-review.json` reports `status=passed`, `review_case_count=5`, `passed_case_count=5`, `failed_case_count=0`, `would_enter_case_count=2`, and `disable_or_no_action_case_count=3` |
| LSR coverage | `short_revival_short_would_enter` returns `would_enter/short`; `old_long_preview_disabled` returns `no_action/none` |
| VCB coverage | `true_breakout_with_volume_would_enter` returns `would_enter/long`; `false_breakout_reversal_disabled` and `volume_expansion_missing_disabled` return `no_action/none` |
| Decision-loop handoff | When LSR/VCB revision rows are active, the decision loop can consume the passed review and advance to `record_lsr001_vcb001_post_revision_quality_before_l2`; the latest local queue has shifted to `continue_btpc_l2_shadow_fact_quality_review` because the current observed set is BTPC/RBR |
| Local monitor sequence | `run_strategygroup_runtime_local_monitor_sequence.py` now includes `post_revision_replay_review` after L2 tier-policy review and keeps passed review cases non-blocking |
| Boundary | Post-revision replay review is not L2 promotion authority, L4 scope expansion, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_strategygroup_post_revision_replay_review.py`, `tests/unit/test_strategygroup_opportunity_decision_loop.py`, and `tests/unit/test_strategygroup_runtime_local_monitor_sequence.py` assert review cases, next-step handoff, local monitor integration, and no live-authority expansion |
| Safety | Local replay/review work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 BTPC L2 Shadow Fact Quality Review Checkpoint

The P0.5 loop now classifies the active BTPC-001 L2 shadow observation fact
gaps instead of leaving them as a flat pending list. This keeps the opportunity
discovery lane useful during no-signal periods while preserving the real-order
boundary: BTPC remains L2 shadow observation only and does not become L4 or
real-order eligible.

| Item | Evidence |
| --- | --- |
| Review artifact | `latest-btpc-l2-shadow-fact-quality-review.json` reports `status=btpc_l2_shadow_fact_quality_review_ready`, `fact_gap_count=5`, `classified_fact_gap_count=5`, `fact_source_pending_count=4`, `strategy_review_pending_count=1`, and `forbidden_effect_count=0` |
| L2 observation | `btpc_state.l2_shadow_observation_enabled=true`, `btpc_state.replay_covered=true`, and `decision.l2_shadow_observation_can_continue=true` |
| Replay support | BTPC replay summary carries five fixtures, including `missing_derivatives_context`, with `would_enter_replay_count=2` |
| Fact classification | Historical OI, global long/short ratio, and top-trader ratio gaps block promotion beyond L2 review; the exchange margin/liquidation model blocks any BTPC real-order eligibility; short-squeeze review remains strategy-review pending and not a runtime submit blocker |
| Next checkpoint | `decision.default_next_step=attach_btpc_derivatives_fact_sources_and_margin_model_for_l2_quality_review` |
| Local monitor sequence | `run_strategygroup_runtime_local_monitor_sequence.py` now runs `opportunity_decision_loop` and `btpc_l2_shadow_fact_quality_review` after post-revision replay review |
| Boundary | BTPC fact-quality review is not tier-policy mutation, L2 promotion authority, L4 scope expansion, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_strategygroup_btpc_l2_shadow_fact_quality_review.py` and `tests/unit/test_strategygroup_runtime_local_monitor_sequence.py` assert fact-gap classification, next-step handoff, monitor integration, and no live-authority expansion |
| Safety | Local review work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-19 BTPC Local Fact Proxy Review Checkpoint

The P0.5 loop now attaches review-only local proxy coverage for the BTPC-001
derivatives and margin/liquidation gaps. This gives replay and L2 shadow quality
review a usable local model while keeping the live-order boundary explicit:
proxy facts do not satisfy live RequiredFacts and cannot feed FinalGate,
Operation Layer, exchange write, or real order.

| Item | Evidence |
| --- | --- |
| Review artifact | `latest-btpc-local-fact-proxy-review.json` reports `status=btpc_local_fact_proxy_review_ready`, `expected_proxy_fact_count=5`, `proxy_attached_count=5`, `l2_quality_proxy_ready_count=5`, and `live_required_fact_satisfied_count=0` |
| Proxy coverage | Historical OI, global long/short ratio, top-trader ratio, margin/liquidation shape, and short-squeeze review rule are attached as local P0.5 review proxies only |
| Margin model | The review model carries research leverage cases from the BTPC handoff and marks `not_exchange_truth=true`, `live_exchange_maintenance_margin_required=true`, and `does_not_lower_owner_selected_leverage=true` |
| Replay support | The review consumes the BTPC L2 replay corpus, requires non-executing replay boundaries, and keeps `local_proxy_can_feed_replay_review=true` while `local_proxy_satisfies_live_required_facts=false` |
| Local monitor sequence | `run_strategygroup_runtime_local_monitor_sequence.py` now runs `btpc_local_fact_proxy_review` after `btpc_l2_shadow_fact_quality_review` |
| Boundary | BTPC proxy review is not live RequiredFacts, tier-policy mutation, L2 promotion authority, L4 scope expansion, candidate authority, FinalGate authority, Operation Layer authority, exchange-write authority, or real-order authority |
| Verification | `tests/unit/test_strategygroup_btpc_local_fact_proxy_review.py`, `tests/unit/test_strategygroup_btpc_l2_shadow_fact_quality_review.py`, and `tests/unit/test_strategygroup_runtime_local_monitor_sequence.py` assert proxy coverage, forbidden-effect blocking, monitor integration, and no live-authority expansion |
| Safety | Local review work only; no Tokyo call, deploy, FinalGate live call, Operation Layer live submit, exchange write, OrderLifecycle call, withdrawal, transfer, secrets mutation, live profile mutation, sizing mutation, leverage reduction, or real order |

### 2026-06-18 Cutover Deploy and Cache-Read Alignment Checkpoint

The first bounded live-order closure target remains active and waiting for a
real fresh selected StrategyGroup signal. The current deployed runtime includes
the live-submit-proof closure contract, and local low-noise status checks now
report cache reads as `L0_local_cache_read` / zero remote interactions instead
of making healthy waiting look like another Tokyo probe.

| Item | Evidence |
| --- | --- |
| Deployed runtime head | `1e97edf52eba8b2fc6a6cec588c3ad6d0490d8c6` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-1e97edf5-live-submit-proof` |
| Deploy apply | `output/tokyo-git-deploy-apply-1e97edf5.json`: `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `mutates_remote_files=true`, `calls_finalgate=false`, `calls_operation_layer=false`, `calls_exchange_write=false`, `places_order=false` |
| Postdeploy acceptance | `output/tokyo-runtime-deploy-session-1e97edf5.json`: `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, `remote_interaction_count=1`, `mutates_remote_files=false`, `approaches_real_order=false` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` expects runtime head `1e97edf52eba8b2fc6a6cec588c3ad6d0490d8c6` |
| Cache-read fix | `81745bfb fix(runtime): report cache heartbeat as local read` keeps `interaction.level=L0_local_cache_read`, `remote_interaction_count=0`, and stores the prior collection in `cached_report_interaction` |
| Low-noise monitor | `run_strategygroup_runtime_daily_check.py --auto-cache --heartbeat`: `DONT_NOTIFY`, `waiting_for_market`, `interaction.level=L0_local_cache_read`, `remote_interaction_count=0` |
| Goal progress | `run_strategygroup_runtime_goal_progress_audit.py --owner-progress`: `P0=waiting_for_market`, `P0.5=ready`, `blockers=[]`, `product_gaps=[]`, `remote_interaction_count=0` |
| Completion audit | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5` |
| Verification | `89 passed` for daily check, goal progress, P0 completion audit, live cutover readiness, quiet monitor, and monitor frequency tests |
| Safety | Deploy apply mutated server files only for the bounded runtime release. Postdeploy and cache checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Completion Audit Interaction Field Checkpoint

The P0 completion audit now exposes its own machine-readable interaction
classification. This prevents downstream status readers from inferring whether
the completion audit contacted Tokyo, touched server files, or approached a
real order from prose-only Owner progress text.

| Item | Evidence |
| --- | --- |
| Completion audit interaction | `runtime_first_bounded_live_order_completion_audit.py` emits `interaction.level=L0_local_completion_audit`, `remote_interaction_count=0`, `mutates_remote_files=false`, `approaches_real_order=false`, `calls_finalgate=false`, `calls_operation_layer=false`, `calls_exchange_write=false`, and `places_order=false` |
| Completion audit safety | `safety_invariants` still reports `server_files_mutated=false`, `calls_finalgate=false`, `calls_operation_layer=false`, `calls_exchange_write=false`, `places_order=false`, `approaches_real_order=false`, and `withdrawal_or_transfer_created=false` |
| Owner progress | The completion audit Owner progress includes `交互等级: L0_local_completion_audit` and `远端交互次数: 0` |
| Current audit output | `output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `interaction.remote_interaction_count=0` |
| Verification | `40 passed` for P0 completion audit, goal progress audit, and daily-check cache-read coverage; `py_compile` passed for `runtime_first_bounded_live_order_completion_audit.py` |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Closure Waiting-State Clarity Checkpoint

The P0 first bounded live-order closure target remains active and waiting for a
real fresh selected StrategyGroup signal. The local goal-progress report now
keeps the live closure evidence boundary explicit while waiting for market:
instead of showing `0/0` closure stages, it reports `0/9`, the first incomplete
stage as `fresh_signal`, and the market-dependent waiting keys from the live
cutover contract.

| Item | Evidence |
| --- | --- |
| Owner progress clarity | `run_strategygroup_runtime_goal_progress_audit.py --owner-progress` reports `Live Closure Evidence Boundary` with `Completed stages: 0/9`, `Expected stages: 9`, and `First incomplete stage: fresh_signal` |
| P0 state | `status=waiting_for_market`, `P0.5=ready`, `blockers=[]`, `product_gaps=[]`, `remote_interaction_count=0` |
| Contract source | Expected closure stages and waiting keys come from the current live cutover readiness contract, not from synthetic live evidence |
| Verification | `25 passed` for `tests/unit/test_strategygroup_runtime_goal_progress_audit.py`; `py_compile` passed for `run_strategygroup_runtime_goal_progress_audit.py` |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Completion Proof Strictness Checkpoint

The P0 completion audit now requires a complete live-closure evidence boundary,
not merely a `status=complete` label, before it can mark the first bounded live
order closure goal complete. Completion proof now requires true live closure
flags, nonzero stage count, all closure stages completed, no missing evidence
keys, and no reject reasons.

| Item | Evidence |
| --- | --- |
| Completion proof strictness | `_live_closure_boundary_complete()` requires `first_bounded_real_order_complete=true`, `real_order_closure_proven=true`, `completed_stage_count == stage_count > 0`, no `missing_evidence_keys`, and no `reject_reasons` |
| Weak proof rejection | `test_completion_audit_rejects_weak_complete_live_closure_boundary` rejects `live_closure_evidence_boundary={"status": "complete"}` when the detailed proof fields are absent |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `15 passed` for `tests/unit/test_runtime_first_bounded_live_order_completion_audit.py`; `py_compile` passed for `runtime_first_bounded_live_order_completion_audit.py` |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Completion Audit Input Freshness Checkpoint

The P0 completion audit now checks that `goal_progress` is not older than the
`daily_check` input when both inputs expose generated timestamps. This prevents
a stale goal-progress packet from being used as completion evidence after a
newer daily check has refreshed runtime state.

| Item | Evidence |
| --- | --- |
| Input freshness guard | `runtime_first_bounded_live_order_completion_audit.py` reports `goal_progress:generated_before_daily_check` when `goal_progress.generated_at_utc < daily_check.generated_at_utc` |
| Stale input rejection | `test_completion_audit_rejects_goal_progress_older_than_daily_check` marks that shape as `needs_non_market_repair` under the input-source traceability requirement |
| Current audit output | Sequential local refresh reports `status=not_complete_waiting_for_market`, `input_source_gaps=[]`, `non_market_gaps=[]`, `remote_interaction_count=0` |
| Verification | `16 passed` for `tests/unit/test_runtime_first_bounded_live_order_completion_audit.py`; `py_compile` passed for `runtime_first_bounded_live_order_completion_audit.py` |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Closure Evidence Duplicate-ID Guard Checkpoint

The live-closure evidence verifier now rejects a completion packet when two or
more required closure evidence fields reuse the same non-empty evidence id.
This keeps the first bounded live-order closure proof stage-specific instead of
allowing one artifact id to satisfy multiple required closure stages.

| Item | Evidence |
| --- | --- |
| Duplicate-id guard | `runtime_live_closure_evidence_verifier.py` adds `duplicate_evidence_id` as a global reject reason when required closure evidence ids repeat |
| Weak proof rejection | `test_live_closure_evidence_verifier_rejects_duplicate_required_evidence_id` rejects a packet where `required_facts_readiness_packet_id` reuses `live_watcher_signal_packet_id` |
| Complete proof compatibility | `test_live_closure_evidence_verifier_marks_complete_when_all_contract_keys_present` still passes with distinct official live evidence ids and live submit proof |
| Verification | `8 passed` for `tests/unit/test_runtime_live_closure_evidence_verifier.py`; `py_compile` passed for `runtime_live_closure_evidence_verifier.py` |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Closure Evidence-ID Shape Guard Checkpoint

The live-closure evidence verifier now requires required closure evidence
values to resolve to evidence-id strings. Non-empty arbitrary objects, lists,
or booleans can no longer satisfy required first-live-closure evidence keys
just because they are truthy. Structured values remain compatible when they
carry an id-like field such as `id`, `evidence_id`, `packet_id`, `ref_id`, or
`reference_id`.

| Item | Evidence |
| --- | --- |
| Evidence-id shape guard | `runtime_live_closure_evidence_verifier.py` adds `malformed_evidence_id` as a global reject reason when a required evidence key is present but cannot resolve to an evidence id |
| Weak proof rejection | `test_live_closure_evidence_verifier_rejects_malformed_required_evidence_id` rejects a packet where `candidate_id` is an arbitrary dict and `runtime_grant_id` is `true` |
| Structured evidence compatibility | `test_live_closure_evidence_verifier_accepts_structured_evidence_id_values` still accepts structured evidence values that carry an `id` field |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `10 passed` for `tests/unit/test_runtime_live_closure_evidence_verifier.py`; `111 passed` for the P0 runtime-monitor/live-closure regression set; `py_compile` passed for the touched runtime-monitor and live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Submit Proof Result-ID Binding Checkpoint

The first-live-closure contract now requires live submit proof to bind back to
the same `exchange_submit_execution_result_id` used as real exchange acceptance
evidence. A packet with `live_exchange_called=true` and `real_order_placed=true`
is no longer enough if the proof omits or mismatches the accepted exchange
submit execution result id.

| Item | Evidence |
| --- | --- |
| Contract binding | `runtime_live_cutover_readiness.py` adds `live_submit_proof_result_id_mismatch` to the `real_exchange_acceptance` reject reasons |
| Verifier binding | `runtime_live_closure_evidence_verifier.py` rejects live closure evidence when `live_submit_proof.exchange_submit_execution_result_id` does not match the required `exchange_submit_execution_result_id` |
| Packet builder binding | `runtime_live_closure_evidence_packet.py` copies the accepted `exchange_submit_execution_result_id` into `live_submit_proof` when building official live closure evidence |
| Weak proof rejection | `test_live_closure_evidence_verifier_rejects_live_submit_proof_result_id_mismatch` rejects a packet where live submit proof points to a different exchange result |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `19 passed` for the live-closure verifier/packet/cutover tests; `123 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched runtime-monitor and live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Submit Proof Source-Consistency Checkpoint

The live-closure evidence packet builder now derives `live_exchange_called` and
`real_order_placed` only from source packets that carry the same accepted
`exchange_submit_execution_result_id`. It no longer allows an unrelated source
packet with true submit markers to complete the live submit proof for a
different exchange result.

| Item | Evidence |
| --- | --- |
| Contract source guard | `runtime_live_cutover_readiness.py` adds `live_submit_proof_result_source_missing` to the `real_exchange_acceptance` reject reasons |
| Verifier source guard | `runtime_live_closure_evidence_verifier.py` requires `live_submit_proof.result_source_matched=true` before real exchange acceptance can complete |
| Packet builder source binding | `runtime_live_closure_evidence_packet.py` reads live submit markers only from packets matching the accepted `exchange_submit_execution_result_id` |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_cross_source_live_submit_markers` rejects a packet where submit markers exist only in an unrelated source |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `21 passed` for the live-closure verifier/packet/cutover tests; `125 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched runtime-monitor and live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Post-Submit Close-Loop Result Binding Checkpoint

The live-closure evidence packet builder now requires post-submit close-loop
evidence to be source-bound to the same accepted
`exchange_submit_execution_result_id`. `runtime_post_submit_finalize_packet_id`,
`post_submit_reconciliation_evidence_id`, `post_submit_budget_settlement_id`,
and `submit_outcome_review_id` can no longer complete first-live-order closure
when they come from a source packet that does not reference the same exchange
submit execution result.

| Item | Evidence |
| --- | --- |
| Contract close-loop binding | `runtime_live_cutover_readiness.py` adds `post_submit_close_loop_proof_missing`, `post_submit_finalize_result_source_missing`, and `post_submit_close_loop_result_source_missing` to post-submit closure reject reasons |
| Packet builder close-loop proof | `runtime_live_closure_evidence_packet.py` emits `post_submit_close_loop_proof` with present, matched, and missing source-match evidence keys |
| Verifier close-loop guard | `runtime_live_closure_evidence_verifier.py` rejects complete live closure when post-submit evidence is present but `post_submit_close_loop_proof` is missing or does not bind to the accepted exchange result |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_unbound_post_submit_close_loop` and verifier tests reject unbound post-submit closure evidence |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `24 passed` for the live-closure verifier/packet/cutover tests; `128 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched runtime-monitor and live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Exchange-Native Protection Result Binding Checkpoint

The live-closure evidence packet builder now requires exchange-native
protection evidence to be source-bound to the same accepted
`exchange_submit_execution_result_id`. A standalone
`exchange_native_hard_stop_order_id` can no longer complete the
first-live-order closure unless its source packet also references the same
exchange submit execution result.

| Item | Evidence |
| --- | --- |
| Contract protection binding | `runtime_live_cutover_readiness.py` adds `exchange_native_protection_proof_missing`, `exchange_native_protection_result_id_mismatch`, and `exchange_native_protection_result_source_missing` to the `exchange_native_protection` reject reasons |
| Packet builder protection proof | `runtime_live_closure_evidence_packet.py` emits `exchange_native_protection_proof` with the hard-stop id, accepted exchange result id, source match status, and source count |
| Verifier protection guard | `runtime_live_closure_evidence_verifier.py` rejects complete live closure when exchange-native protection evidence is present but the protection proof is missing, mismatched, or not source-bound to the accepted exchange result |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_unbound_exchange_native_protection`, `test_live_closure_evidence_verifier_rejects_missing_exchange_native_protection_proof`, and `test_live_closure_evidence_verifier_rejects_unbound_exchange_native_protection` reject isolated or unbound protection evidence |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `27 passed` for the live-closure verifier/packet/cutover tests; `131 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Post-Submit Close-Loop Truth Checkpoint

The first bounded live-order closure proof now requires post-submit evidence to
prove the four close-loop outcomes, not only carry evidence ids bound to the
accepted exchange submit result. A live closure cannot complete unless the
source packets prove finalize completion, reconciliation match, budget
settlement, and submit-outcome review recording.

| Item | Evidence |
| --- | --- |
| Contract close-loop truth | `runtime_live_cutover_readiness.py` adds `post_submit_finalize_not_complete`, `post_submit_reconciliation_not_matched`, `post_submit_budget_not_settled`, and `submit_outcome_review_not_recorded` to the post-submit closure reject contract |
| Official producer truth fields | `runtime_official_post_submit_finalize_proof.py` emits `post_submit_finalize_complete`, `post_submit_reconciliation_matched`, `post_submit_budget_settled`, and `submit_outcome_review_recorded` from the official post-submit proof packet |
| Packet builder close-loop truth | `runtime_live_closure_evidence_packet.py` emits `finalize_complete`, `reconciliation_matched`, `budget_settled`, and `review_recorded` inside `post_submit_close_loop_proof` |
| Verifier close-loop truth guard | `runtime_live_closure_evidence_verifier.py` rejects complete live closure when bound post-submit evidence is present but any close-loop truth field is not true |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_incomplete_post_submit_truth` and `test_live_closure_evidence_verifier_rejects_incomplete_post_submit_truth` reject ids-only post-submit closure evidence |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `85 passed` for the targeted live-closure/cutover/snapshot tests; `148 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Official Proof Auth Env Isolation Checkpoint

The official proof login helper now resets proof-local operator credentials
immediately before each TestClient login. This prevents `src.interfaces.api`
composition-root import from reloading `.env.local` with `override=True` and
overwriting the proof credentials that the local official proof chain expects.

| Item | Evidence |
| --- | --- |
| Root cause | `src.interfaces.api` imports load `.env.local` with `override=True`; after import, the proof password hash and TOTP secret no longer matched the local proof login payload |
| Fix | `runtime_official_server_prepare_integration_proof.py` resets proof credentials inside `_login()` immediately before posting `/api/auth/login` |
| Scope | This changes local official proof/test credential isolation only; it does not modify production secrets, live profile, order sizing, Tokyo files, FinalGate, Operation Layer, exchange write, or real order behavior |
| Verification | `36 passed` for `test_runtime_official_*proof.py`; post-submit proof no longer fails with `rtf088_login_failed:401` |
| Known warning | The official proof suite still emits an existing async cleanup warning: `coroutine 'Connection._cancel' was never awaited`; all assertions pass |

### 2026-06-18 Pre-Submit Authorization Chain Binding Checkpoint

The live-closure evidence packet builder now requires the candidate,
runtime-grant, action-time FinalGate, and official Operation Layer authorization
evidence to bind to the same `fresh_submit_authorization_id`. This prevents a
future real signal from being marked ready by stitching together stale
FinalGate or Operation Layer arm evidence from another authorization chain.

| Item | Evidence |
| --- | --- |
| Contract pre-submit binding | `runtime_live_cutover_readiness.py` adds `pre_submit_authorization_chain_proof_missing`, `pre_submit_authorization_chain_id_mismatch`, `candidate_authorization_chain_source_missing`, `finalgate_authorization_chain_source_missing`, and `operation_layer_authorization_chain_source_missing` to the relevant pre-submit stage reject reasons |
| Packet builder chain proof | `runtime_live_closure_evidence_packet.py` emits `pre_submit_authorization_chain_proof` anchored by `fresh_submit_authorization_id` with present, matched, and missing source-match evidence keys |
| Verifier chain guard | `runtime_live_closure_evidence_verifier.py` rejects complete live closure when candidate/auth, FinalGate, or Operation Layer evidence is present but not bound to the same fresh submit authorization chain |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_unbound_pre_submit_authorization_chain`, `test_live_closure_evidence_verifier_rejects_missing_pre_submit_authorization_chain_proof`, and `test_live_closure_evidence_verifier_rejects_unbound_pre_submit_authorization_chain` reject missing or stale-chain pre-submit evidence |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `30 passed` for the live-closure verifier/packet/cutover tests; `134 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Signal Chain Binding Checkpoint

The live-closure evidence packet builder now requires RequiredFacts readiness
and candidate evidence to bind to the same `live_watcher_signal_packet_id`.
This prevents a future real signal from being marked ready by stitching
together stale facts or stale candidates from another signal window.

| Item | Evidence |
| --- | --- |
| Contract signal binding | `runtime_live_cutover_readiness.py` adds `live_signal_chain_proof_missing`, `live_signal_chain_id_mismatch`, `required_facts_signal_source_missing`, and `candidate_signal_source_missing` to the relevant signal/facts/candidate stage reject reasons |
| Packet builder signal proof | `runtime_live_closure_evidence_packet.py` emits `live_signal_chain_proof` anchored by `live_watcher_signal_packet_id` with present, matched, and missing source-match evidence keys |
| Verifier signal guard | `runtime_live_closure_evidence_verifier.py` rejects complete live closure when RequiredFacts or candidate evidence is present but not bound to the same live signal |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_unbound_live_signal_chain`, `test_live_closure_evidence_verifier_rejects_missing_live_signal_chain_proof`, and `test_live_closure_evidence_verifier_rejects_unbound_live_signal_chain` reject missing or stale-signal facts/candidate evidence |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `33 passed` for the live-closure verifier/packet/cutover tests; `137 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Runtime Boundary Binding Checkpoint

The live-closure evidence packet builder now emits `runtime_boundary_proof`
for the first bounded live-order closure chain. A complete live-closure packet
must not only show live signal, RequiredFacts, candidate/auth, FinalGate,
Operation Layer, exchange acceptance, exchange-native protection, finalize,
reconciliation, settlement, and review evidence. It must also prove that those
source packets remain inside the same selected StrategyGroup, runtime profile,
allocated subaccount, symbol, side, notional, and leverage boundary. Once the
chain reaches candidate/auth evidence, missing boundary fields are rejected as
hard live-closure proof gaps; signal/facts-only in-progress packets can still
remain in progress without being mislabeled as failed closure.

| Item | Evidence |
| --- | --- |
| Boundary proof | `runtime_live_closure_evidence_packet.py` emits `runtime_boundary_proof` with observed, missing, conflicting, and normalized boundary values from source packets that carry the required live-closure evidence ids |
| Contract guard | `runtime_live_cutover_readiness.py` adds `live_closure_contract_requires_runtime_boundary_binding=true` and rejects missing proof, missing boundary fields, or mismatches from `candidate_authorization_bound` through close-loop completion |
| Verifier guard | `runtime_live_closure_evidence_verifier.py` rejects official live closure evidence when `runtime_boundary_proof` is missing, required boundary fields are missing after candidate/auth starts, or conflicts are reported for StrategyGroup, runtime profile, subaccount, symbol, side, notional, or leverage |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_runtime_boundary_missing_after_candidate`, `test_live_closure_evidence_packet_rejects_runtime_boundary_mismatch`, `test_live_closure_evidence_verifier_rejects_missing_runtime_boundary_proof`, `test_live_closure_evidence_verifier_rejects_runtime_boundary_missing_fields`, and `test_live_closure_evidence_verifier_rejects_runtime_boundary_mismatch` reject stitched or unbounded completion shapes |
| Product-state compatibility | Goal-progress and Tokyo snapshot auto-verification fixtures now include the same runtime boundary proof, so the Owner progress layer remains `waiting_for_market` with no product gaps when no real live closure has started |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `43 passed` for the live-closure verifier/packet/cutover/refresh tests; `142 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Exchange Acceptance Proof Checkpoint

The `real_exchange_acceptance` stage now requires more than an exchange submit
execution result id plus generic live-submit markers. A first-live-order
closure packet must prove that the matched result source says the entry submit
was accepted by the exchange and carries an entry exchange order id. This keeps
`exchange_submit_execution_result_id` from being treated as enough proof when
the submit attempt was only called, locally shaped, rejected before acceptance,
or missing the exchange order identity needed for protection and
reconciliation.

| Item | Evidence |
| --- | --- |
| Contract acceptance guard | `runtime_live_cutover_readiness.py` adds `exchange_submit_not_accepted` and `exchange_order_id_missing` to `real_exchange_acceptance` reject reasons and to the live-submit truth contract check |
| Packet builder acceptance proof | `runtime_live_closure_evidence_packet.py` derives `live_submit_proof.exchange_accepted` and `live_submit_proof.exchange_order_id_present` only from source packets bound to the same `exchange_submit_execution_result_id` |
| Verifier acceptance guard | `runtime_live_closure_evidence_verifier.py` rejects official live closure evidence when matched live-submit proof does not show exchange acceptance or an entry exchange order id |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_exchange_result_without_acceptance` and `test_live_closure_evidence_verifier_rejects_unaccepted_live_submit_proof` reject called-but-not-accepted live submit shapes |
| Product-state compatibility | Refresh, goal-progress, and Tokyo snapshot fixtures now include the same exchange acceptance proof, so complete official packets still verify while weak packets are rejected |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `81 passed` for the live-closure verifier/packet/cutover/refresh/goal-progress/snapshot tests; `144 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Exchange-Native Protection Truth Checkpoint

The `exchange_native_protection` stage now requires the hard-stop proof to
show more than a hard-stop id source-bound to the entry exchange result. The
matched protection source must also prove that the hard stop is exchange-native,
accepted by the exchange, and reduce-only. This prevents a local-only stop
shape, an unaccepted protection order, or a non-reduce-only stop from being
treated as sufficient first-live-order closure protection.

| Item | Evidence |
| --- | --- |
| Contract protection truth guard | `runtime_live_cutover_readiness.py` adds `hard_stop_not_accepted` and `hard_stop_not_reduce_only` beside `local_only_stop` in the `exchange_native_protection` reject reasons and contract check |
| Packet builder protection truth | `runtime_live_closure_evidence_packet.py` derives `exchange_native_protection_proof.exchange_native`, `hard_stop_accepted`, and `reduce_only` only from source packets carrying the bound hard-stop evidence |
| Verifier protection truth | `runtime_live_closure_evidence_verifier.py` rejects official live closure evidence when protection proof is missing exchange-native, accepted, or reduce-only truth |
| Weak proof rejection | `test_live_closure_evidence_packet_rejects_local_unaccepted_non_reduce_only_stop` and `test_live_closure_evidence_verifier_rejects_local_unaccepted_non_reduce_only_stop` reject local/unaccepted/non-reduce-only hard-stop shapes |
| Product-state compatibility | Refresh, goal-progress, and Tokyo snapshot fixtures now include the same exchange-native protection truth proof, so complete official packets still verify while weak packets are rejected |
| Current audit output | `runtime_first_bounded_live_order_completion_audit.py --owner-progress`: `status=not_complete_waiting_for_market`, `goal_complete=false`, `non_market_gaps=[]`, `market_dependent_remaining=5`, `remote_interaction_count=0` |
| Verification | `83 passed` for the live-closure verifier/packet/cutover/refresh/goal-progress/snapshot tests; `146 passed` for the P0 runtime-monitor/live-closure/snapshot regression set; `py_compile` passed for the touched live-closure scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Completion Audit Full Contract Guard Checkpoint

The P0 completion audit now treats the live-cutover contract itself as a
first-order proof surface. It no longer checks only a small subset of live
closure contract fields; it requires all 13 official first-live closure
evidence keys and all first-order live proof guards to remain present before a
healthy waiting state can be reported.

This checkpoint also fixes the local monitor sequence so it refreshes
`latest-live-cutover-readiness.json` before goal-progress and completion-audit.
That prevents a stale live-cutover packet from creating false non-market gaps
or hiding a real contract regression during the no-signal waiting window.

| Item | Evidence |
| --- | --- |
| Completion audit contract guard | `runtime_first_bounded_live_order_completion_audit.py` now checks `LIVE_CLOSURE_REQUIRED_EVIDENCE_KEYS` and `LIVE_CLOSURE_REQUIRED_CONTRACT_CHECKS` |
| Local sequence order | `run_strategygroup_runtime_local_monitor_sequence.py` runs `daily_check -> live_cutover_readiness -> goal_progress -> completion_audit` |
| Test isolation | `test_strategygroup_runtime_local_monitor_sequence.py` writes fake live-cutover packets under `tmp_path`, not `output/runtime-monitor/latest-live-cutover-readiness.json` |
| Automation prompt | `tokyo-runtime-quiet-monitor` now names live-cutover readiness refresh inside the local zero-remote sequence |
| Current audit output | `run_strategygroup_runtime_local_monitor_sequence.py --daily-check-mode cache --owner-progress`: `status=waiting_for_market`, `blockers=[]`, `non_market_gaps=[]`, `remote_interaction_count=0` |
| Verification | `46 passed` for completion-audit, local-monitor-sequence, monitor-frequency, and goal-progress tests; `py_compile` passed for the touched runtime monitor/audit scripts |
| Safety | This is local audit/reporting work only. It did not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Standing First-Real-Submit Authorization Checkpoint

The first-real-submit API flow now treats Owner standing authorization as a
valid execution guard for the selected bounded runtime path. This removes a
non-market chat-confirmation style blocker where `execute` mode required an
extra `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT` env value even after the
runtime path had already produced scoped evidence, action-time FinalGate, and
official Operation Layer readiness.

| Item | Evidence |
| --- | --- |
| Execute guard | `runtime_first_real_submit_api_flow.py` still requires `--execute-real-submit`; when `--standing-authorized-first-real-submit` is present, it no longer requires the legacy env confirmation string |
| Evidence guard | Real submit still requires prearmed evidence ids for trusted submit facts, idempotency, attempt outcome, protection failure, local registration, Owner real-submit authorization, OrderLifecycle submit enablement, exchange adapter enablement, exchange action authorization, deployment readiness, and exchange adapter result |
| Followup wording | `runtime_active_observation_followup.py` now points from disabled smoke to fresh-signal standing-authorized official Operation Layer chain instead of waiting for explicit per-order authorization |
| Action packet wording | `build_runtime_first_real_submit_action_authorization_packet.py` can mark the authorization guard satisfied by standing authorization while still waiting for prearmed exchange-submit evidence |
| Verification | `py_compile` passed; targeted tests `57 passed` across first-real-submit API flow, action authorization packet, and active-observation followup |
| Deployment | Not deployed in this checkpoint; deploy only after a stage-worthy batch, fresh-signal unblock, or explicit Owner request |
| Safety | Local code/tests only. No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Operation Layer Standing Authorization Relay Checkpoint

The Runtime Signal Watcher resume dispatcher now carries the same standing
authorization semantics into the official Operation Layer command and submit
packets. The API-compatible `owner_confirmed_for_first_real_submit_action=true`
query parameter remains the official real-submit switch, but the packet now
states that it is satisfied by the selected bounded standing authorization, not
by a new per-order chat confirmation or legacy env confirmation.

| Item | Evidence |
| --- | --- |
| Command plan semantics | `runtime_signal_watcher_resume_dispatcher.py` now emits `standing_authorized_first_real_submit=true`, `owner_chat_confirmation_required_for_real_submit=false`, and `legacy_owner_confirmation_env_required=false` for the official Operation Layer command plan |
| Submit precondition guard | The dispatcher blocks before official Operation Layer submit if standing authorization semantics regress back to missing standing authorization, chat confirmation required, or legacy env required |
| Submit result semantics | Real submit packets mark `standing_authorization_consumed_for_real_submit=true`; disabled smoke packets keep it `false` so disabled smoke cannot be treated as real execution proof |
| Regression test | `test_dispatcher_blocks_real_submit_if_standing_authorization_semantics_regress` fixes the first-live cutover rule that old Owner confirmation semantics must not become an in-boundary real-submit blocker |
| Local validation | `py_compile` passed for the dispatcher; `test_runtime_signal_watcher_resume_dispatcher.py`: `40 passed` |
| Local monitor sequence | `run_strategygroup_runtime_local_monitor_sequence.py --daily-check-mode cache --owner-progress`: `status=waiting_for_market`, blockers empty, non-market gaps empty, remote interactions `0` |
| Deployment | Not deployed; batch with the next stage-worthy runtime cutover fix or fresh-signal unblock |
| Safety | Local code/tests/cache reads only. No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Standing Authorization Dry-Run Audit Checkpoint

The standing authorization relay check is now part of the daily dry-run audit
contract, not just a dispatcher unit test. This lets the low-noise goal monitor
detect a future regression where the first-live submit path silently reverts to
per-order chat confirmation or legacy env confirmation semantics.

| Item | Evidence |
| --- | --- |
| Dry-run relay check | `runtime_dry_run_audit_chain.py` adds `standing_authorization_bound_for_first_real_submit`, `owner_chat_confirmation_not_required_for_first_real_submit`, and `legacy_owner_confirmation_env_not_required` to `operation_layer_relay_checks` |
| Required check | `operation_layer_standing_authorization_relay_checked` is now emitted in `checks`, `required_checks`, and `summary` |
| Monitor integration | `run_strategygroup_runtime_daily_check.py` and `run_strategygroup_runtime_goal_progress_audit.py` include the new check in the entry fast-chain readiness boundary |
| Local validation | `py_compile` passed; dry-run, goal-progress, and daily-check tests: `67 passed` |
| Generated packet | `runtime_dry_run_audit_chain.py --output-json output/runtime-monitor/latest-runtime-dry-run-audit-chain.json`: `status=passed`, `scenario_count=14`, `operation_layer_standing_authorization_relay_checked=true` |
| Local monitor sequence | `run_strategygroup_runtime_local_monitor_sequence.py --daily-check-mode cache --owner-progress`: `status=waiting_for_market`, blockers empty, non-market gaps empty, remote interactions `0` |
| Deployment | Not deployed; this is local audit/monitor hardening |
| Safety | Local code/tests/cache reads only. No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |
