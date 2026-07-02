## Strategy Live Candidate Pool

- Status: `strategy_live_candidate_pool_ready`
- Candidate count: `5`
- Symbol readiness rows: `18`
- Fresh promotion candidates: `0`
- Top action-time candidate: `none`
- P0 cleared: `True`
- P1 cleared or waived: `True`
- Deploy ready: `False`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategy-live-candidate-pool.json`

| StrategyGroup | Symbol | Status | First blocker | Next action |
| --- | --- | --- | --- | --- |
| CPM-RO-001 | ETHUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| MPG-001 | OPUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| MI-001 | AVAXUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| SOR-001 | ETHUSDT | candidate_market_condition_wait | computed_not_satisfied | continue_observation_with_failed_fact_matrix |
| BRF2-001 | BTCUSDT | candidate_conditional_observation | computed_not_satisfied | continue_observation_with_failed_fact_matrix |

## Per-Symbol Readiness

| StrategyGroup | Symbol | Facts | Signal | Scope | Promotion | First blocker |
| --- | --- | --- | --- | --- | --- | --- |
| CPM-RO-001 | ETHUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| CPM-RO-001 | AVAXUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| CPM-RO-001 | SOLUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| CPM-RO-001 | SUIUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MPG-001 | OPUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MPG-001 | AVAXUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MPG-001 | SOLUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MPG-001 | SUIUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MI-001 | AVAXUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MI-001 | ETHUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| MI-001 | SOLUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| SOR-001 | ETHUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| SOR-001 | AVAXUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| SOR-001 | BTCUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| SOR-001 | SOLUSDT | computed_not_satisfied | absent | live_submit_allowed | idle | computed_not_satisfied |
| BRF2-001 | BTCUSDT | computed_not_satisfied | absent | conditional_action_time_rehearsal_allowed | idle | computed_not_satisfied |
| BRF2-001 | AVAXUSDT | missing | absent | conditional_action_time_rehearsal_allowed | idle | watcher_tick_missing |
| BRF2-001 | ETHUSDT | missing | absent | conditional_action_time_rehearsal_allowed | idle | watcher_tick_missing |
