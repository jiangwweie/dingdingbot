## BRF2 Runtime Signal Facts

- Status: `brf2_runtime_signal_facts_ready`
- Generated: `2026-06-23T10:44:11.901366+00:00`
- Output JSON: `output/runtime-monitor/latest-brf2-runtime-signal-facts.json`
- Fact input present: `是`
- Watcher tick present: `是`
- First blocker: `none` / `runtime`
- Fact authority: `readonly_proxy_not_action_time_required_fact`
- Action-time RequiredFacts satisfied: `否`

## Boundary

- This packet is local/read-only and non-executing.
- BRF reference derived facts are observation proxies, not action-time live RequiredFacts.
- Missing watcher fact input is an engineering gap, not a market signal absence.
- It does not call FinalGate, Operation Layer, exchange write, or order creation.
