# Daily Live Enablement Table

- Source JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-daily-live-enablement-table.json`
- Generated: `2026-07-02T08:03:53.998977+00:00`
- Rank 1 lane: `MPG-001:SOLUSDT`

| Rank | StrategyGroup | Symbol | Stage | First blocker | Owner action | Next action | Stop condition |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `MPG-001` | `SOLUSDT` | `armed` | `watcher_tick_missing` | `no` | `refresh_or_repair_watcher_fact_source` | watcher/public facts tick is present for the selected lane |
| 2 | `SOR-001` | `SOLUSDT` | `armed` | `watcher_tick_missing` | `no` | `refresh_or_repair_watcher_public_fact_input` | watcher/public facts tick is present for the selected lane |
| 3 | `MI-001` | `AVAXUSDT` | `admission` | `scope_not_attached` | `no` | `build_trial_asset_admission_proposal` | scoped live observation proposal is attached or Owner scope decision is required |
| 4 | `CPM-RO-001` | `ETHUSDT` | `armed` | `computed_not_satisfied` | `no` | `continue_observation_with_failed_fact_matrix` | failed fact matrix clears or blocker reclassifies after next detector tick |
| 5 | `BRF2-001` | `brf2_research_supported_symbols_only` | `armed` | `computed_not_satisfied` | `no` | `continue_brf2_armed_observation_until_disable_clears` | failed fact matrix clears or blocker reclassifies after next detector tick |

This table is a non-authority read model. It does not call FinalGate, Operation Layer, or exchange write.
