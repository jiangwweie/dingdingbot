## Strategy Live Candidate Pool

- Status: `strategy_live_candidate_pool_ready`
- Candidate count: `5`
- Symbol readiness rows: `18`
- Fresh promotion candidates: `0`
- Top action-time candidate: `none`
- P0 cleared: `False`
- P1 cleared or waived: `False`
- Deploy ready: `False`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategy-live-candidate-pool.json`

| StrategyGroup | Symbol | Status | First blocker | Next action |
| --- | --- | --- | --- | --- |
| CPM-RO-001 | ETHUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| MPG-001 | SOLUSDT | candidate_runtime_input_blocked | watcher_tick_missing | refresh_or_repair_watcher_fact_source |
| MI-001 | AVAXUSDT | candidate_scope_decision_pending | scope_not_attached | build_trial_asset_admission_proposal |
| SOR-001 | SOLUSDT | candidate_runtime_input_blocked | watcher_tick_missing | refresh_or_repair_watcher_public_fact_input |
| BRF2-001 | brf2_research_supported_symbols_only | candidate_conditional_observation | computed_not_satisfied | continue_brf2_armed_observation_until_disable_clears |

## Per-Symbol Readiness

| StrategyGroup | Symbol | Facts | Signal | Scope | Promotion | First blocker |
| --- | --- | --- | --- | --- | --- | --- |
| CPM-RO-001 | ETHUSDT | computed_not_satisfied | absent | trial_scope_proposed | idle | computed_not_satisfied |
| CPM-RO-001 | AVAXUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| CPM-RO-001 | SOLUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| CPM-RO-001 | SUIUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| MPG-001 | OPUSDT | computed_not_satisfied | absent | readonly_only | idle | watcher_tick_missing |
| MPG-001 | AVAXUSDT | computed_not_satisfied | absent | readonly_only | idle | watcher_tick_missing |
| MPG-001 | SOLUSDT | computed_not_satisfied | absent | trial_scope_proposed | idle | watcher_tick_missing |
| MPG-001 | SUIUSDT | computed_not_satisfied | absent | readonly_only | idle | watcher_tick_missing |
| MI-001 | AVAXUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| MI-001 | ETHUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| MI-001 | SOLUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| SOR-001 | ETHUSDT | missing | absent | readonly_only | idle | watcher_tick_missing |
| SOR-001 | AVAXUSDT | missing | absent | readonly_only | idle | watcher_tick_missing |
| SOR-001 | BTCUSDT | missing | absent | readonly_only | idle | watcher_tick_missing |
| SOR-001 | SOLUSDT | missing | absent | trial_scope_proposed | idle | watcher_tick_missing |
| BRF2-001 | BTCUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| BRF2-001 | AVAXUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| BRF2-001 | ETHUSDT | missing | absent | readonly_only | idle | detector_not_attached |
