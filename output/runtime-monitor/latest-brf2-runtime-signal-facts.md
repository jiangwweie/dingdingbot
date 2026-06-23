## BRF2 Runtime Signal Facts

- Status: `brf2_runtime_signal_facts_missing_watcher_input`
- Generated: `2026-06-23T09:42:54.571142+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-brf2-runtime-signal-facts.json`
- Fact input present: `否`
- Watcher tick present: `否`
- First blocker: `brf2_watcher_fact_input_missing` / `engineering`

## Boundary

- This packet is local/read-only and non-executing.
- Missing watcher fact input is an engineering gap, not a market signal absence.
- It does not call FinalGate, Operation Layer, exchange write, or order creation.
