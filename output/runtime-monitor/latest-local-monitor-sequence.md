## StrategyGroup Runtime Local Monitor Sequence

- 报告时间: 2026-06-29T14:12:30.416713+00:00
- 当前阶段: 等待机会
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
- BRF2 signal state: `fresh_signal_absent`
- BRF2 signal first blocker: `fresh_brf2_short_signal_absent` / `market`
- BRF2 shadow candidate shape ready: `否`
- BRF2 shadow candidate evidence: `brf2_shadow_candidate_evidence_waiting_for_fresh_signal`
- BRF2 shadow evidence ready: `否`
- BRF2 shadow evidence first blocker: `fresh_brf2_short_signal_absent` / `market`
- 三策略试验组合状态: `three_strategy_live_trial_portfolio_ready`
- 三策略席位: `MPG-001, BRF2-001, SOR-001`
- 三策略席位数: `3`
- 第五阶段状态: `phase_5_waiting_for_live_opportunity`
- 受控实盘 standby 席位: `3` / `3`
- 组合第一阻断统计 market/owner/engineering: `3` / `0` / `0`
- Tradeability Decision 状态: `tradeability_decision_ready`
- Tradeability Decision Top: `BRF2-001` / `not_tradable_market_wait`
- 第一阻断: `fresh_brf2_short_signal_absent` / `market`
- 下一检查点: `continue_brf2_armed_observation_until_fresh_signal`
- Tradeability trial-grade standby: `3`
- Trial-grade signal audit: `trial_grade_signal_gate_audit_ready`
- Trial-grade 30d observation / action-time submit: `0` / `0`
- Trial-grade hard gates relaxed: `否`
- 当前可交易数量: `0`

## Steps

| Step | Status | Returncode |
| --- | --- | ---: |
| daily_check | waiting_for_market_monitor_refresh_needed | 2 |
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
| goal_progress | waiting_for_market_monitor_refresh_needed | 0 |
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
