## StrategyGroup Runtime Local Monitor Sequence

- 报告时间: 2026-06-22T05:28:28.068877+00:00
- 当前阶段: 等待机会
- 当前动作: 刷新本地 runtime monitor 缓存
- 风险等级: L0_local_monitor_sequence
- Owner 介入: 否
- 交互等级: L0_local_monitor_sequence
- 远端交互次数: 0
- 服务器修改: 否
- 接近真实订单: 否

## Steps

| Step | Status | Returncode |
| --- | --- | ---: |
| daily_check | waiting_for_market_monitor_refresh_needed | 2 |
| runtime_dry_run_audit_chain | passed | 0 |
| live_cutover_readiness | live_cutover_waiting_for_fresh_signal | 0 |
| goal_progress | waiting_for_market_monitor_refresh_needed | 0 |
| completion_audit | not_complete_waiting_for_market | 0 |
| replay_lab | passed | 0 |
| signal_coverage | mainline_no_signal_low_priority_broader_would_enter | 0 |
| signal_coverage_expansion_review | low_priority_observe_only_would_enter_parked | 0 |
| l2_readiness_review | l2_readiness_review_already_enabled | 0 |
| l2_intake_dry_run | l2_intake_dry_run_no_candidates | 0 |
| l2_tier_policy_review | l2_tier_policy_review_no_candidates | 0 |
| post_revision_replay_review | passed | 0 |
| opportunity_decision_loop | decision_loop_ready | 0 |
| btpc_l2_shadow_fact_quality_review | btpc_l2_shadow_fact_quality_review_ready | 0 |
| btpc_local_fact_proxy_review | btpc_local_fact_proxy_review_ready | 0 |
| btpc_proxy_replay_quality_review | btpc_proxy_replay_quality_review_ready | 0 |
| opportunity_decision_loop_final | decision_loop_ready | 0 |
| btpc_l2_keep_revise_fact_source_decision | btpc_l2_keep_revise_fact_source_decision_ready | 0 |
| btpc_live_derivatives_fact_source_mapping | btpc_live_derivatives_fact_source_mapping_ready_without_live_authority | 0 |
| btpc_classifier_rule_review | btpc_classifier_rule_review_recorded_without_live_authority | 0 |
| strategygroup_decision_ledger | decision_ledger_ready | 0 |
| strategygroup_quality_wave | quality_wave_ready | 0 |
| strategygroup_handoff_boundary_closure | handoff_boundary_closure_ready | 0 |
| strategygroup_btpc_fact_classifier_guard | btpc_fact_classifier_guard_ready | 0 |
| strategygroup_lifecycle_rehearsal | lifecycle_rehearsal_ready | 0 |
| strategygroup_pre_live_rehearsal_readiness | pre_live_rehearsal_ready | 0 |
| strategygroup_live_submit_readiness_bridge | live_submit_standby_waiting_for_market | 0 |

## Checks

- Blockers: none
- Non-market gaps: none
