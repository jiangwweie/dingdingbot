# Daily Live Enablement Table

- Source JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-daily-live-enablement-table.json`
- Generated: `2026-07-01T16:23:57.735674+00:00`
- Rank 1 lane: `MPG-001:OPUSDT`

| Rank | StrategyGroup | Symbol | Stage | First blocker | Owner action | Next action | Stop condition |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `MPG-001` | `OPUSDT` | `armed` | `scope_not_attached` | `no` | `produce_scoped_live_observation_or_scope_proposal` | scoped live observation proposal is attached or Owner scope decision is required |
| 2 | `SOR-001` | `ETHUSDT` | `armed` | `scope_not_attached` | `no` | `produce_scoped_live_observation_or_scope_proposal` | scoped live observation proposal is attached or Owner scope decision is required |
| 3 | `CPM-RO-001` | `ETHUSDT` | `armed` | `computed_not_satisfied` | `no` | `continue_observation_with_failed_fact_matrix` | failed fact matrix clears or blocker reclassifies after next detector tick |
| 4 | `BRF2-001` | `brf2_research_supported_symbols_only` | `armed` | `computed_not_satisfied` | `no` | `continue_brf2_armed_observation_until_disable_clears` | failed fact matrix clears or blocker reclassifies after next detector tick |
| 5 | `MI-001` | `AVAXUSDT` | `admission` | `policy_scope_missing` | `yes` | `record_scoped_owner_policy` | Owner scoped policy is recorded or lane exits mainline |

This table is a non-authority read model. It does not call FinalGate, Operation Layer, or exchange write.
