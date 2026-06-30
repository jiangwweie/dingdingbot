## Four-Candidate Runtime Activation Contract

- Status: `four_candidate_runtime_activation_contract_ready`
- P0 contract declared: `是`
- P1 contract declared: `是`
- Runtime artifact ready rows: `3`
- Action-time boundary ready rows: `3`
- Live-submit allowed: `0`
- Venue basis: `coinbase_spot_proxy`
- Execution venue match: `false`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-four-candidate-runtime-activation-closure.json`

## Activation Rows

| Priority | Strategy | Watcher symbols | Expanded read-only symbols | Runtime artifact ready | Boundary ready | Next blocker |
| --- | --- | --- | --- | ---: | ---: | --- |
| `P0` | `CPM-RO-001` | `ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT` | `SOLUSDT, AVAXUSDT, SUIUSDT` | `true` | `true` | `fresh_cpm_long_signal_absent_or_action_time_facts` |
| `P0` | `MPG-001` | `BTCUSDT, ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT` | `SOLUSDT, AVAXUSDT, SUIUSDT` | `true` | `true` | `binance_usdm_runtime_artifact_ready` |
| `P1` | `SOR-001` | `BTCUSDT, ETHUSDT, SOLUSDT, AVAXUSDT` | `SOLUSDT, AVAXUSDT` | `true` | `true` | `binance_usdm_runtime_artifact_ready` |
| `P1` | `MI-001` | `AVAXUSDT, ETHUSDT, SOLUSDT, SUIUSDT` | `AVAXUSDT, ETHUSDT, SOLUSDT, SUIUSDT` | `false` | `false` | `formal_registry_admission_not_requested_for_mi` |

## Boundary

- Replay and declared watcher contracts are not live signals.
- MPG/SOR declared contracts do not count as runtime-ready without watcher, RequiredFacts, and rehearsal artifacts.
- No live profile change, order-sizing change, FinalGate call, Operation Layer call, exchange write, or order creation.
