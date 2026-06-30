## BRF2 Runtime Signal Facts

- Status: `brf2_runtime_signal_facts_ready`
- Generated: `2026-06-30T01:54:24.844827+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-brf2-runtime-signal-facts.json`
- Fact input present: `是`
- Watcher tick present: `是`
- First blocker: `none` / `runtime`
- Fact authority: `readonly_proxy_not_action_time_required_fact`
- Action-time RequiredFacts satisfied: `否`

## Boundary

- This artifact is local/read-only and non-executing.
- BRF reference derived facts are observation proxies, not action-time live RequiredFacts.
- Missing watcher fact input is an engineering gap, not a market signal absence.
- It does not call FinalGate, Operation Layer, exchange write, or order creation.
