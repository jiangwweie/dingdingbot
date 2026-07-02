# Daily Live Enablement Table

- Source JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-daily-live-enablement-table.json`
- Generated: `2026-07-02T14:42:09.077702+00:00`
- Rank 1 lane: `SOR-001:ETHUSDT`

| Rank | StrategyGroup | Symbol | Stage | First blocker | Owner action | Next action | Stop condition |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `SOR-001` | `ETHUSDT` | `armed` | `watcher_tick_missing` | `no` | `refresh_readonly_watcher_for_candidate_symbol` | blocker moves, repeats through stop review, or symbol exits candidate universe |
| 2 | `MI-001` | `AVAXUSDT` | `admission` | `detector_not_attached` | `no` | `attach_detector_for_candidate_symbol` | blocker moves, repeats through stop review, or symbol exits candidate universe |
| 3 | `BRF2-001` | `BTCUSDT` | `armed` | `detector_not_attached` | `no` | `attach_detector_for_candidate_symbol` | blocker moves, repeats through stop review, or symbol exits candidate universe |
| 4 | `CPM-RO-001` | `ETHUSDT` | `armed` | `computed_not_satisfied` | `no` | `continue_observation_with_failed_fact_matrix` | blocker moves, repeats through stop review, or symbol exits candidate universe |
| 5 | `MPG-001` | `OPUSDT` | `armed` | `computed_not_satisfied` | `no` | `continue_observation_with_failed_fact_matrix` | blocker moves, repeats through stop review, or symbol exits candidate universe |

This table is a non-authority read model. It does not call FinalGate, Operation Layer, or exchange write.
