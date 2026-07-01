## Strategy Live Candidate Pool

- Status: `strategy_live_candidate_pool_ready`
- Candidate count: `5`
- P0 cleared: `False`
- P1 cleared or waived: `False`
- Deploy ready: `False`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategy-live-candidate-pool.json`

| StrategyGroup | Symbol | Status | First blocker | Next action |
| --- | --- | --- | --- | --- |
| CPM-RO-001 | ETHUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| MPG-001 | SOLUSDT | candidate_runtime_input_blocked | watcher_tick_missing | refresh_or_repair_watcher_public_fact_input |
| MI-001 | AVAXUSDT | candidate_scope_decision_pending | scope_not_attached | build_trial_asset_admission_proposal |
| SOR-001 | ETHUSDT | candidate_runtime_input_blocked | watcher_tick_missing | refresh_or_repair_watcher_public_fact_input |
| BRF2-001 | brf2_research_supported_symbols_only | candidate_conditional_observation | computed_not_satisfied | continue_brf2_armed_observation_until_disable_clears |
