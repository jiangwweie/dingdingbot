## BRF2 Runtime Signal Capture

- Status: `brf2_runtime_signal_capture_ready`
- Generated: `2026-06-23T10:44:12.085537+00:00`
- Output JSON: `output/runtime-monitor/latest-brf2-runtime-signal-capture.json`
- StrategyGroup: `BRF2-001`
- Fact input present: `是`
- Watcher tick present: `是`
- Signal state: `fresh_signal_absent`
- First blocker: `fresh_brf2_short_signal_absent`
- Candidate packet ready: `否`
- Fact authority: `readonly_proxy_not_action_time_required_fact`
- Action-time RequiredFacts satisfied: `否`
- Actionable now: `否`
- Real order authority: `否`

## No-Action Attribution

- Missing required facts: `rally_context, rally_failure_trigger_state`
- Active disable facts: `none`

## Boundary

- This packet is watcher-facing and non-executing.
- Read-only observation facts can classify armed observation, but cannot satisfy action-time submit facts.
- It does not call FinalGate, Operation Layer, or exchange write.
- A fresh signal here can only prepare the next non-executing candidate packet shape.
