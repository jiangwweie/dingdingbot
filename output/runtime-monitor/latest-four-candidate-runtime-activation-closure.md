## Four-Candidate Runtime Activation Closure

- Status: `four_candidate_runtime_activation_closure_ready`
- P0 closed: `是`
- P1 closed: `是`
- Action-time boundary ready rows: `3`
- Live-submit allowed: `0`
- Venue basis: `coinbase_spot_proxy`
- Execution venue match: `false`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-four-candidate-runtime-activation-closure.json`

## Activation Rows

| Priority | Strategy | Watcher symbols | Expanded read-only symbols | Boundary ready | Next blocker |
| --- | --- | --- | --- | ---: | --- |
| `P0` | `CPM-RO-001` | `ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT` | `SOLUSDT, AVAXUSDT, SUIUSDT` | `true` | `fresh_cpm_long_signal_absent_or_action_time_facts` |
| `P0` | `MPG-001` | `BTCUSDT, ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT` | `SOLUSDT, AVAXUSDT, SUIUSDT` | `true` | `strong_symbol_action_time_facts_not_live_collected` |
| `P1` | `SOR-001` | `BTCUSDT, ETHUSDT, SOLUSDT, AVAXUSDT` | `SOLUSDT, AVAXUSDT` | `true` | `session_breakout_action_time_facts_not_live_collected` |
| `P1` | `MI-001` | `AVAXUSDT, ETHUSDT, SOLUSDT, SUIUSDT` | `AVAXUSDT, ETHUSDT, SOLUSDT, SUIUSDT` | `false` | `formal_registry_admission_not_requested_for_mi` |

## Boundary

- Replay and watcher contracts are not live signals.
- No live profile change, order-sizing change, FinalGate call, Operation Layer call, exchange write, or order creation.
