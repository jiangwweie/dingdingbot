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
| MPG-001 | OPUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| MI-001 | AVAXUSDT | candidate_engineering_blocked | detector_not_attached | attach_detector_for_candidate_symbol |
| SOR-001 | ETHUSDT | candidate_runtime_input_blocked | watcher_tick_missing | refresh_readonly_watcher_for_candidate_symbol |
| BRF2-001 | BTCUSDT | candidate_engineering_blocked | detector_not_attached | attach_detector_for_candidate_symbol |

## Per-Symbol Readiness

| StrategyGroup | Symbol | Facts | Signal | Scope | Promotion | First blocker |
| --- | --- | --- | --- | --- | --- | --- |
| CPM-RO-001 | ETHUSDT | computed_not_satisfied | absent | trial_scope_proposed | idle | computed_not_satisfied |
| CPM-RO-001 | AVAXUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| CPM-RO-001 | SOLUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| CPM-RO-001 | SUIUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| MPG-001 | OPUSDT | computed_not_satisfied | absent | trial_scope_proposed | idle | computed_not_satisfied |
| MPG-001 | AVAXUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| MPG-001 | SOLUSDT | computed_not_satisfied | absent | trial_scope_proposed | idle | computed_not_satisfied |
| MPG-001 | SUIUSDT | computed_not_satisfied | absent | readonly_only | idle | computed_not_satisfied |
| MI-001 | AVAXUSDT | missing | absent | trial_scope_proposed | idle | detector_not_attached |
| MI-001 | ETHUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| MI-001 | SOLUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| SOR-001 | ETHUSDT | missing | absent | trial_scope_proposed | idle | watcher_tick_missing |
| SOR-001 | AVAXUSDT | missing | absent | readonly_only | idle | watcher_tick_missing |
| SOR-001 | BTCUSDT | missing | absent | readonly_only | idle | watcher_tick_missing |
| SOR-001 | SOLUSDT | missing | absent | trial_scope_proposed | idle | watcher_tick_missing |
| BRF2-001 | BTCUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| BRF2-001 | AVAXUSDT | missing | absent | readonly_only | idle | detector_not_attached |
| BRF2-001 | ETHUSDT | missing | absent | readonly_only | idle | detector_not_attached |
