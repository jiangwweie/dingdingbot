## BRF2 RequiredFacts Mapping

- Status: `brf2_required_facts_mapping_ready`
- Generated: `2026-06-28T19:14:03.668223+00:00`
- Output JSON: `/Users/jiangwei/Documents/final-system-refactor-20260623/output/runtime-monitor/latest-brf2-required-facts-mapping.json`
- StrategyGroup: `BRF2-001`
- Current stage: `admitted_trial_asset`
- After next state: `armed_observation`
- Mapping ready: `是`

## Fresh Signal

- Signal id: `brf2_short_rally_failure_fresh_signal_v1`
- Side: `short`
- Timeframes: `1h_closed, 5m_closed`

## Required Facts

| Fact | Class | Source | Missing Behavior |
| --- | --- | --- | --- |
| `closed_1h_ohlcv` | `market` | `read_only_closed_candle_source` | `block_armed_observation` |
| `closed_5m_ohlcv` | `market` | `read_only_closed_candle_source` | `block_armed_observation` |
| `rally_context` | `strategy` | `brf2_strategy_classifier` | `block_armed_observation` |
| `rally_failure_trigger_state` | `strategy` | `brf2_strategy_classifier` | `block_armed_observation` |
| `short_squeeze_risk_state` | `derivatives_or_strategy_proxy` | `squeeze_classifier_or_review_proxy` | `block_armed_observation` |
| `strong_reclaim_disable_state` | `strategy` | `brf2_disable_classifier` | `block_armed_observation` |
| `liquidity_downshift_state` | `market_or_execution_context` | `spread_volume_liquidity_proxy` | `block_armed_observation` |
| `spread_liquidity_state` | `market_or_execution_context` | `spread_volume_liquidity_proxy` | `block_armed_observation` |

## Boundary

- This mapping does not satisfy live facts.
- It does not call FinalGate, Operation Layer, or exchange write.
- It only closes the BRF2 mapping gap for armed observation.
