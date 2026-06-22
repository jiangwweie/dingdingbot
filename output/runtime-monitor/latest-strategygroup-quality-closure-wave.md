# StrategyGroup Quality Closure Wave

## Summary

- Status: `quality_closure_wave_ready`
- Closed problem: Strategy capture findings, identity ambiguity, Owner explanation, MPG member review, and forward/no-action evidence are now projected from current audit/ledger sources into one comparable packet.
- Capability unlocked: Owner can review strategy-quality decisions without reading raw would_enter/no_action samples, while runtime authority remains false.
- Next bottleneck: Owner policy decision is required before promote, park, kill, lane change, or live-profile changes.
- Real order authority: `false`
- Live permission change: `false`

## Wave 1 Strategy Explainer

| StrategyGroup | Label | Tier | Eats structure | Why not live | Owner can decide | System action |
| --- | --- | --- | --- | --- | --- | --- |
| `MPG-001` | 动量延续 | `L4` | Directional crypto momentum with clean 1h persistence and acceptable liquidity. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | decide member tiering and exit-decay policy after review packet | `MPG-001_no_action_visibility_and_routing_audit` |
| `BTPC-001` | 熊市回抽延续 | `L2` | Downtrend continuation after weak rally or pullback, excluding strong upside reclaim regimes. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | approve or reject revised strategy direction after evidence packet | `BTPC-001_classifier_fact_source_revision_review` |
| `LSR-001` | 流动性扫盘/短线复活 | `L1` | Liquidity sweep, reclaim, and short-revival structures where range context is known. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | approve or reject revised strategy direction after evidence packet | `LSR-001_classifier_fact_source_revision_review` |
| `BRF-001` | 熊市反弹失败 | `L1` | Bear rally failure, rejection, and structure-extreme regimes. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | decide promote review outcome after evidence packet | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `MI-001` | MI-001 | `unknown` | current registry identity is incomplete | `decision-ledger evidence is review-only and cannot authorize execution` | decide registry identity after review packet | `MI-001_registry_identity_review` |
| `CPM-RO-001` | CPM-RO-001 | `unknown` | current registry identity is incomplete | `decision-ledger evidence is review-only and cannot authorize execution` | decide registry identity after review packet | `CPM-RO-001_registry_identity_review` |
| `FBS-001` | 资金费率/基差压力 | `L3` | Derivative crowding, negative funding, basis/premium stress, and settlement timing regimes. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | no immediate Owner action; review only if evidence changes | `FBS-001_no_action_visibility_and_routing_audit` |
| `SOR-001` | 开盘区间结构 | `L3` | TradFi-linked session opens with closed range bars, trigger bar, and post-open decay control. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | no immediate Owner action; review only if evidence changes | `SOR-001_no_action_visibility_and_routing_audit` |
| `VCB-001` | 波动压缩突破 | `L1` | Volatility compression, breakout close, and volume expansion regimes. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | no immediate Owner action; review only if evidence changes | `VCB-001_continue_observe_only` |
| `TEQ-001` | 类股权永续动量 | `L2` | Theme momentum where product/session and concentration risks are acceptable. | `runtime_state_only; requires fresh signal, live facts, candidate/auth, action-time execution gates, official submission path, protection, account, and exchange facts` | no immediate Owner action; review only if evidence changes | `continue_strategy_review` |

## Wave 2 Capture Quality Closure

| StrategyGroup | Problem | Action | Review | Would enter | High-priority no_action | WE positive | Missed NA positive |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| `BTPC-001` | 169/169 windows are attributed to stale gate or fact-source blocking. | `review_stale_gate_fact_source_classifier_attribution` | `revise` | 0 | 169 | 0 | 152 |
| `LSR-001` | side-specific short-revival has would-enter evidence but needs range-context review. | `side_specific_short_revival_range_context_review` | `revise` | 2 | 167 | 2 | 0 |
| `BRF-001` | bear-rally failure short structure appeared, but squeeze and RequiredFacts review are incomplete. | `forward_outcome_squeeze_classifier_requiredfacts_review` | `promote_review` | 1 | 168 | 0 | 136 |
| `VCB-001` | breakout structure appeared but true/false breakout quality is not strong enough for promotion. | `true_false_breakout_classifier_review` | `keep_observing_or_revise` | 2 | 167 | 2 | 135 |
| `RBR-001` | positive observe-only samples exist, but the lane remains parked without materially new edge evidence. | `material_new_edge_review_before_reactivation` | `park_unless_new_edge` | 6 | 0 | 6 | 0 |

## Wave 3 MPG Member Deepening

| Member | Role | Review focus | Recommendation |
| --- | --- | --- | --- |
| `TSI-001` | `core_member_candidate` | `right_tail_return_vs_drawdown_decay` | `keep_core_candidate_but_require_decay_control` |
| `MHI-001` | `high_risk_member` | `high_return_high_drawdown_survivability` | `downshift_or_park_review_before_live_expansion` |
| `PPO-001` | `support_member` | `middle_return_middle_drawdown_stability` | `keep_observing_as_support_member` |
| `DMI-001` | `ignition_support_or_independent_observer` | `member_vs_independent_strategy_boundary` | `identity_boundary_review` |
| `WPR-001` | `confirmation_member` | `conservative_momentum_confirmation_value` | `keep_as_confirmation_candidate` |
| `MFI-001` | `risk_damper_or_scorer` | `low_drawdown_low_return_filter_value` | `keep_as_scorer_not_primary_member` |

## Priority 1 Capture Closure

| StrategyGroup | Tier | Decision | Would enter | High-priority no_action | Forward positives | Next |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `BTPC-001` | `L2` | `revise` | 0 | 169 | 0 / 152 | `BTPC-001_classifier_fact_source_revision_review` |
| `LSR-001` | `L1` | `revise` | 2 | 167 | 2 / 0 | `LSR-001_classifier_fact_source_revision_review` |
| `BRF-001` | `L1` | `promote` | 1 | 168 | 0 / 136 | `BRF-001_forward_outcome_and_requiredfacts_review` |

## Priority 2 Owner Cards

| StrategyGroup | Label | Tier | Owner status | Review | Missing evidence |
| --- | --- | --- | --- | --- | --- |
| `BRF-001` | 熊市反弹失败 | `L1` | 待复盘 | `promote` | `promotion_evidence_review_only:BRF-001_forward_outcome_and_requiredfacts_review` |
| `BTPC-001` | 熊市回抽延续 | `L2` | 待调整 | `revise` | `classifier_fact_source_revision_review:BTPC-001_classifier_fact_source_revision_review` |
| `CPM-RO-001` | CPM-RO-001 | `unknown` | 待调整 | `revise` | `registry_identity_classification:CPM-RO-001_registry_identity_review` |
| `FBS-001` | 资金费率/基差压力 | `L3` | 等待机会 | `keep_observing` | `no_action_visibility_and_routing_summary:FBS-001_no_action_visibility_and_routing_audit` |
| `LSR-001` | 流动性扫盘/短线复活 | `L1` | 待调整 | `revise` | `classifier_fact_source_revision_review:LSR-001_classifier_fact_source_revision_review` |
| `MI-001` | MI-001 | `unknown` | 待调整 | `revise` | `registry_identity_classification:MI-001_registry_identity_review` |
| `MPG-001` | 动量延续 | `L4` | 等待机会 | `keep_observing` | `no_action_visibility_and_routing_summary:MPG-001_no_action_visibility_and_routing_audit` |
| `PMR-001` | 贵金属制度覆盖 | `L1` | 等待机会 | `keep_observing` | `role-specific replay and fact maturity before tier review` |
| `RBR-001` | 区间边界回归 | `L1` | 已暂停 | `park` | `material_new_edge_evidence_before_reactivation` |
| `SOR-001` | 开盘区间结构 | `L3` | 等待机会 | `keep_observing` | `no_action_visibility_and_routing_summary:SOR-001_no_action_visibility_and_routing_audit` |
| `TEQ-001` | 类股权永续动量 | `L2` | 等待机会 | `keep_observing` | `shadow outcomes and cost/session review before any L4 review` |
| `VCB-001` | 波动压缩突破 | `L1` | 等待机会 | `keep_observing` | `VCB-001_continue_observe_only` |

## Priority 3 Identity Review

| StrategyGroup | Would enter | Forward positive | Problem | Options |
| --- | ---: | ---: | --- | --- |
| `MI-001` | 23 | 22 | `strong_would_enter_but_smoke_or_member_identity_unclear` | `keep_as_smoke_lane`, `map_as_mpg_member_or_support_capability`, `promote_to_formal_candidate_review`, `park_until_identity_evidence_improves` |
| `CPM-RO-001` | 18 | 13 | `would_enter_present_but_registry_scope_unclear` | `keep_as_observation_asset`, `merge_into_existing_capture_family`, `park_as_mixed_quality_lane`, `kill_if_forward_quality_decays` |

## Priority 4 MPG Member Review

| Member | Role | Review focus | Recommendation |
| --- | --- | --- | --- |
| `TSI-001` | `core_member_candidate` | `right_tail_return_vs_drawdown_decay` | `keep_core_candidate_but_require_decay_control` |
| `MHI-001` | `high_risk_member` | `high_return_high_drawdown_survivability` | `downshift_or_park_review_before_live_expansion` |
| `PPO-001` | `support_member` | `middle_return_middle_drawdown_stability` | `keep_observing_as_support_member` |
| `DMI-001` | `ignition_support_or_independent_observer` | `member_vs_independent_strategy_boundary` | `identity_boundary_review` |
| `WPR-001` | `confirmation_member` | `conservative_momentum_confirmation_value` | `keep_as_confirmation_candidate` |
| `MFI-001` | `risk_damper_or_scorer` | `low_drawdown_low_return_filter_value` | `keep_as_scorer_not_primary_member` |

## Priority 5 Forward / No-Action Ledger Extension

| StrategyGroup | Class | Would enter | No action | High-priority no_action | WE positive | Missed NA positive |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `BRF-001` | `would_enter_observed` | 1 | 168 | 168 | 0 | 136 |
| `BTPC-001` | `high_priority_no_action_observed` | 0 | 169 | 169 | 0 | 152 |
| `CPM-RO-001` | `would_enter_observed` | 18 | 151 | 0 | 13 | 0 |
| `FBS-001` | `visibility_only_or_no_recent_structure` | 0 | 0 | 0 | 0 | 0 |
| `LSR-001` | `would_enter_observed` | 2 | 167 | 167 | 2 | 0 |
| `MI-001` | `would_enter_observed` | 23 | 315 | 0 | 22 | 0 |
| `MPG-001` | `visibility_only_or_no_recent_structure` | 0 | 0 | 0 | 0 | 0 |
| `RBR-001` | `would_enter_observed` | 6 | 163 | 0 | 6 | 0 |
| `SOR-001` | `visibility_only_or_no_recent_structure` | 0 | 0 | 0 | 0 | 0 |
| `VCB-001` | `would_enter_observed` | 2 | 167 | 167 | 2 | 135 |

## Owner Confirmation Checkpoint

- Owner confirmation required: `true`
- Runtime Owner intervention required: `false`
- Decision count: `4`
- Hard stop: Do not promote, park, kill, change tier policy, change live profile, or expand real-order scope without Owner confirmation.

## Safety

| Field | Value |
| --- | --- |
| `local_review_only` | `true` |
| `server_interaction` | `false` |
| `server_files_mutated` | `false` |
| `runtime_started` | `false` |
| `strategy_parameters_changed` | `false` |
| `tier_policy_changed` | `false` |
| `live_profile_changed` | `false` |
| `l4_real_order_scope_expanded` | `false` |
| `shadow_candidate_created` | `false` |
| `execution_intent_created` | `false` |
| `final_gate_called` | `false` |
| `operation_layer_called` | `false` |
| `order_created` | `false` |
| `exchange_write_called` | `false` |
| `real_order_authority` | `false` |
| `preview_or_replay_treated_as_live_signal` | `false` |

## Output

- JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-quality-closure-wave.json`
- Markdown: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-quality-closure-wave.md`
