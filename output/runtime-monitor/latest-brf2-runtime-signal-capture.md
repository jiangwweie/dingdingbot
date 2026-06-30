## BRF2 Runtime Signal Capture

- Status: `brf2_runtime_signal_capture_ready`
- Generated: `2026-06-30T06:41:28.318124+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-brf2-runtime-signal-capture.json`
- StrategyGroup: `BRF2-001`
- Fact input present: `是`
- Watcher tick present: `是`
- Signal state: `blocked_by_disable_fact`
- First blocker: `short_squeeze_risk_state_disable_active`
- Shadow candidate shape ready: `否`
- Fact authority: `readonly_proxy_not_action_time_required_fact`
- Action-time RequiredFacts satisfied: `否`

## No-Action Attribution

- Missing required facts: `rally_context, rally_failure_trigger_state`
- Active disable facts: `short_squeeze_risk_state`

## Boundary

- This artifact is watcher-facing and non-executing.
- Read-only observation facts can classify armed observation, but cannot satisfy action-time submit facts.
- It does not call FinalGate, Operation Layer, or exchange write.
- A fresh signal here can only prepare the next non-executing shadow-candidate evidence shape.
