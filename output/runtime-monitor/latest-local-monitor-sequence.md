## StrategyGroup Runtime Local Monitor Sequence

- 报告时间: 2026-06-30T15:14:55.590579+00:00
- 当前阶段: 监控状态需刷新
- 当前检查点: 刷新本地 runtime monitor 缓存
- 风险等级: L0_local_monitor_sequence
- Owner 介入: 否
- 交互等级: L0_local_monitor_sequence
- 远端交互次数: 0
- 服务器修改: 否
- 接近真实订单: 否
- Signal Observation grade: `signal-observation-grade-review` / `observation_active`
- Signal Observation would-enter / no-action: `1` / `4`
- 昨晚观察信号: `RBR-001` / `ADA/USDT:USDT` / `short`
- No-action 归因队列: `4`
- RBR/RBR2 role review: `1`
- 策略 intake 状态: `research_intake_review_ready`
- 策略 intake 候选: `BRF2-001, RBR2-001`
- 受控实盘候选状态: `trial_envelope_projection_ready`
- 受控实盘候选策略组: `BRF2-001`
- 做空试验候选策略组: `BRF2-001`
- 晋级范围: `intake_only`
- 准入提案状态: `trial_asset_admission_proposal_ready`
- 准入提案策略组: `BRF2-001`
- 准入提案下一状态: `armed_observation`
- Owner policy required: `否`
- BRF2 Owner policy recorded: `是`
- BRF2 next blocker: `required_facts_mapping_gap`
- BRF2 RequiredFacts mapping: `brf2_required_facts_mapping_ready`
- BRF2 fresh signal rule: `brf2_short_rally_failure_fresh_signal_v1`
- BRF2 after mapping state: `armed_observation`
- BRF2 runtime signal facts: `brf2_runtime_signal_facts_ready`
- BRF2 fact input / watcher tick: `是` / `是`
- BRF2 runtime signal capture: `brf2_runtime_signal_capture_ready`
- BRF2 signal state: `blocked_by_disable_fact`
- BRF2 signal first blocker: `short_squeeze_risk_state_disable_active` / `market`
- BRF2 shadow candidate shape ready: `否`
- BRF2 shadow candidate evidence: `brf2_shadow_candidate_evidence_waiting_for_fresh_signal`
- BRF2 shadow evidence ready: `否`
- BRF2 shadow evidence first blocker: `short_squeeze_risk_state_disable_active` / `market`
- CPM identity decision: `standalone_trial_asset`
- CPM standalone trial asset: `是`
- CPM Owner policy recorded: `是`
- CPM capital source: `action_time_exchange_available_balance`
- CPM RequiredFacts mapping: `cpm_required_facts_mapping_ready`
- CPM fresh signal rule: `cpm_long_pullback_reclaim_signal_v1`
- CPM runtime signal facts: `cpm_runtime_signal_facts_ready`
- CPM fact input / watcher tick: `是` / `是`
- CPM runtime signal capture: `cpm_runtime_signal_capture_ready`
- CPM signal state: `fresh_signal_absent`
- CPM signal first blocker: `fresh_cpm_long_signal_absent` / `market`
- CPM shadow candidate evidence: `cpm_shadow_candidate_evidence_waiting_for_fresh_signal`
- CPM shadow evidence first blocker: `fresh_cpm_long_signal_absent` / `market`
- CPM dry-run submit rehearsal: `shape_ready`
- CPM armed observation ready: `是`
- CPM submit rehearsal shape ready: `是`
- CPM fresh-signal submit rehearsal passed: `否`
- CPM rehearsal FinalGate/Operation Layer paper: `否` / `否`
- CPM synthetic fresh-signal rehearsal passed: `是`
- CPM synthetic candidate/action-time shape: `是` / `是`
- CPM synthetic FinalGate/Operation Layer paper: `是` / `是`
- CPM synthetic authority fail-closed: `是`
- Four-candidate activation contract: `four_candidate_runtime_activation_contract_ready`
- P0/P1 contract declared: `是` / `是`
- P0/P1 runtime artifacts ready: `是` / `否`
- Contract/runtime/scope/watcher/facts/candidate/rehearsal/boundary ready: `4` / `3` / `4` / `3` / `3` / `3` / `3` / `3`
- MI formal replay review opened: `1`
- Scope review decision: `four_candidate_scope_review_decision_ready` / readonly expansions `3` / live-scope changes `0`
- CPM fresh-path public facts / fresh signal / next blocker: `是` / `否` / `fresh_cpm_long_signal_absent`
- Fresh-signal action-time boundary: `strategy_fresh_signal_action_time_boundary_ready` / fresh `0` / finalgate-if-private-facts `3` / live-submit `0`
- Activation venue basis/match: `coinbase_spot_proxy` / `否`
- Activation next checkpoint: `attach_binance_usdm_readonly_watcher_facts_for_expanded_symbols`
- Armed trade candidates: `MPG-001, BRF2-001, SOR-001, CPM-RO-001`
- Armed trade candidate count: `4`
- Legacy three-strategy portfolio: `MPG-001, BRF2-001, SOR-001`
- Legacy three-strategy portfolio status/count: `three_strategy_live_trial_portfolio_ready` / `3`
- 第五阶段状态: `phase_5_waiting_for_live_opportunity`
- 受控实盘 standby 席位: `3` / `3`
- 组合第一阻断统计 market/owner/engineering: `3` / `0` / `0`
- Tradeability Decision 状态: `tradeability_decision_ready`
- Tradeability Decision Top: `BRF2-001` / `not_tradable_market_wait`
- 第一阻断: `short_squeeze_risk_state_disable_active` / `market`
- 下一检查点: `continue_brf2_armed_observation_until_disable_clears`
- CPM Tradeability row: `armed_observation` / `not_tradable_market_wait`
- CPM Tradeability blocker: `fresh_cpm_long_signal_absent` / `market`
- CPM-LONG path readiness: `ready` / `否`
- Tradeability trial-grade standby: `3`
- Trial-grade signal audit: `trial_grade_signal_gate_audit_ready`
- Trial-grade 30d observation / action-time submit: `0` / `0`
- Trial-grade hard gates relaxed: `否`
- 当前可交易数量: `0`

## Steps

| Step | Status | Returncode |
| --- | --- | ---: |
| daily_check | temporarily_unavailable_monitor_refresh_needed | 2 |
| runtime_dry_run_audit_chain | passed | 0 |
| live_cutover_readiness | live_cutover_waiting_for_fresh_signal | 0 |
| strategygroup_portfolio_board | portfolio_board_ready | 0 |
| strategygroup_research_intake_review | research_intake_review_ready | 0 |
| strategygroup_capital_trial_envelope_projection | trial_envelope_projection_ready | 0 |
| brf2_owner_trial_policy_scope | brf2_owner_trial_policy_scope_recorded | 0 |
| strategygroup_trial_asset_admission_proposal | trial_asset_admission_proposal_ready | 0 |
| brf2_required_facts_mapping | brf2_required_facts_mapping_ready | 0 |
| brf2_runtime_signal_facts | brf2_runtime_signal_facts_ready | 0 |
| brf2_runtime_signal_capture | brf2_runtime_signal_capture_ready | 0 |
| brf2_shadow_candidate_evidence | brf2_shadow_candidate_evidence_waiting_for_fresh_signal | 0 |
| cpm_identity_routing_decision | cpm_identity_routing_decision_ready | 0 |
| cpm_owner_trial_policy_scope | cpm_owner_trial_policy_scope_recorded | 0 |
| cpm_required_facts_mapping | cpm_required_facts_mapping_ready | 0 |
| binance_usdm_public_facts | binance_usdm_public_facts_ready | 0 |
| cpm_runtime_signal_facts | cpm_runtime_signal_facts_ready | 0 |
| cpm_runtime_signal_capture | cpm_runtime_signal_capture_ready | 0 |
| cpm_shadow_candidate_evidence | cpm_shadow_candidate_evidence_waiting_for_fresh_signal | 0 |
| cpm_dry_run_submit_rehearsal | cpm_dry_run_submit_rehearsal_shape_ready | 0 |
| four_candidate_runtime_activation_evidence | runtime_activation_evidence_ready | 0 |
| mpg_high_beta_scope_readiness | mpg_action_time_facts_readiness_ready | 0 |
| strategy_fresh_signal_action_time_boundary | strategy_fresh_signal_action_time_boundary_ready | 0 |
| four_candidate_runtime_activation_closure | four_candidate_runtime_activation_contract_ready | 0 |
| goal_progress | ready | 0 |
| completion_audit | not_complete_waiting_for_market | 0 |
| replay_lab | passed | 0 |
| signal_coverage | mainline_no_signal_low_priority_broader_would_enter | 0 |
| signal_coverage_expansion_review | low_priority_observe_only_would_enter_parked | 0 |
| l2_readiness_review | l2_readiness_review_already_enabled | 0 |
| l2_intake_dry_run | l2_intake_dry_run_no_candidates | 0 |
| l2_tier_policy_review | l2_tier_policy_review_no_candidates | 0 |
| post_revision_replay_review | passed | 0 |
| opportunity_review_work_loop | review_work_loop_ready | 0 |
| btpc_l2_shadow_fact_quality_review | btpc_l2_shadow_fact_quality_review_ready | 0 |
| btpc_local_fact_proxy_review | btpc_local_fact_proxy_review_ready | 0 |
| btpc_proxy_replay_quality_review | btpc_proxy_replay_quality_review_ready | 0 |
| opportunity_review_work_loop_final | review_work_loop_ready | 0 |
| btpc_l2_keep_revise_fact_source_review | btpc_l2_keep_revise_fact_source_review_ready | 0 |
| btpc_live_derivatives_fact_source_mapping | btpc_live_derivatives_fact_source_mapping_ready_without_live_authority | 0 |
| btpc_classifier_rule_review | btpc_classifier_rule_review_recorded_without_live_authority | 0 |
| strategy_asset_state | strategy_asset_state_ready | 0 |
| strategygroup_quality_wave | quality_wave_ready | 0 |
| strategygroup_handoff_boundary_closure | handoff_boundary_closure_ready | 0 |
| strategygroup_btpc_fact_classifier_guard | btpc_fact_classifier_guard_ready | 0 |
| strategygroup_lifecycle_rehearsal | lifecycle_rehearsal_ready | 0 |
| strategygroup_pre_live_rehearsal_readiness | pre_live_rehearsal_ready | 0 |
| strategygroup_runtime_safety_state | live_submit_standby_waiting_for_market | 0 |
| strategygroup_trial_grade_signal_gate_audit | trial_grade_signal_gate_audit_ready | 0 |
| three_strategy_live_trial_portfolio | three_strategy_live_trial_portfolio_ready | 0 |
| strategygroup_tradeability_decision | tradeability_decision_ready | 0 |

## Owner Runtime Issues

- Blockers: none
- Non-market gaps: none
