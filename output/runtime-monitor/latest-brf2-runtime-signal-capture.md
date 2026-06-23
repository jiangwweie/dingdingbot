## BRF2 Runtime Signal Capture

- Status: `brf2_runtime_signal_capture_ready`
- Generated: `2026-06-23T09:42:54.620139+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-brf2-runtime-signal-capture.json`
- StrategyGroup: `BRF2-001`
- Fact input present: `否`
- Watcher tick present: `否`
- Signal state: `fact_input_missing`
- First blocker: `brf2_watcher_fact_input_missing`
- Candidate packet ready: `否`
- Actionable now: `否`
- Real order authority: `否`

## No-Action Attribution

- Missing required facts: `closed_1h_ohlcv, closed_5m_ohlcv, rally_context, rally_failure_trigger_state, short_squeeze_risk_state, strong_reclaim_disable_state, liquidity_downshift_state, spread_liquidity_state`
- Active disable facts: `none`

## Boundary

- This packet is watcher-facing and non-executing.
- It does not call FinalGate, Operation Layer, or exchange write.
- A fresh signal here can only prepare the next non-executing candidate packet shape.
