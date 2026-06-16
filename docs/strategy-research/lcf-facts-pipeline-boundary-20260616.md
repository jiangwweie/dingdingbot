# LCF-001 Facts Pipeline Boundary

Status: P1_FACTS_PIPELINE_BOUNDARY_READY
Last updated: 2026-06-16

## Scope

`LCF-001` is a research-only facts-pipeline boundary for liquidation cascade
follow-through.

It is not a StrategyGroup handoff, not runtime registration, not FinalGate
input, not Operation Layer input, not exchange-write authority, not live-profile
authority, not leverage authority, and not an order-sizing default.

## Known Objective

`LCF-001` should stay in the strategy cabinet because liquidation cascades are
a plausible small-capital right-tail structure: forced closing, crowded
positioning, mark-price stress, and thin depth can create short-lived
continuation or reversal windows.

The same structure must remain blocked from handoff until the facts pipeline can
prove that the observed move is a forced-flow cascade rather than ordinary
high-volatility candle behavior.

## Current Decision

| Field | Decision |
| --- | --- |
| Strategy id | `LCF-001` |
| Semantic name | Liquidation Cascade Follow-through |
| Current status | `facts_pipeline_required` |
| Default mode | `observe_only` |
| Handoff state | No handoff pack |
| Candidate-prepare state | Blocked by research semantics |
| Runtime state | Not registered |
| Execution authority | None |

## Evidence Boundary

| RequiredFact | Current Boundary | Missing Behavior |
| --- | --- | --- |
| `force_order_event_stream` | Missing locally; no reproducible force-order event archive is attached. | `no_lcf_signal` |
| `liquidation_cluster_state` | Missing locally; depends on force-order event stream and bounded cluster logic. | `block_handoff` |
| `historical_open_interest_window` | Current field shape is observable, but 2024-2025 aligned windows are absent. | `block_handoff` |
| `global_long_short_ratio_window` | Recent field shape is observable, but historical aligned windows are absent. | `block_handoff` |
| `top_trader_position_ratio_window` | Recent field shape is observable, but historical aligned windows are absent. | `block_handoff` |
| `adl_quantile_state` | Missing locally; cannot classify liquidation-engine stress or ADL proximity. | `observe_only_no_handoff` |
| `orderbook_depth_slippage_state` | Missing locally; cannot estimate live-like entry, exit, or stop slippage. | `block_promotion` |
| `real_exchange_margin_liquidation_model` | Missing locally; leverage outputs are research stress labels only. | `block_leverage` |
| `funding_window_sum` | Partial coverage exists for several major symbols, but it is context only. | `observe_only_context` |
| `mark_price_deviation_window` | Partial mark coverage exists, but it does not prove forced-flow clusters. | `observe_only_context` |

## Pipeline States

| State | Meaning | Allowed Output |
| --- | --- | --- |
| `lcf_facts_absent` | Required force-order, cluster, OI, ratio, depth, ADL, and margin facts are absent. | Facts-missing no-signal packet only. |
| `lcf_field_shape_observed` | Public endpoint fields are capturable in current or recent snapshots. | Research note; not historical validation. |
| `lcf_minimum_observable` | Force-order, OI, funding/mark, and depth facts are available for current observation. | Observe-only no-candidate packet. |
| `lcf_replay_ready` | Historical force-order, OI, ratio, depth, funding, mark, and candle windows are aligned. | Research replay packet. |
| `lcf_handoff_candidate` | Replay-ready evidence plus sample signal and no-signal packets exist. | Handoff draft may be started. |

## RequiredFacts Delta

| Proposed Fact | Meaning | Missing Behavior |
| --- | --- | --- |
| `lcf_fact_pipeline_state` | Overall LCF fact-pipeline readiness state. | `no_lcf_signal` |
| `lcf_force_order_stream_state` | Force-order stream or archive is reproducibly captured. | `block_handoff` |
| `lcf_liquidation_cluster_state` | Clustered liquidation pressure is detected from force-order events. | `block_handoff` |
| `lcf_historical_oi_state` | Historical OI windows align to candidate candles. | `block_handoff` |
| `lcf_positioning_ratio_state` | Global and top-trader positioning windows align to candidate candles. | `block_handoff` |
| `lcf_adl_stress_state` | ADL or liquidation-engine stress proxy is available. | `observe_only_no_handoff` |
| `lcf_depth_slippage_state` | Orderbook depth, spread, and slippage proxy are available. | `block_promotion` |
| `lcf_margin_model_state` | Exchange margin and liquidation model is available. | `block_leverage` |
| `lcf_no_signal_when_facts_missing_state` | Missing facts always produce no-signal rather than weak signal. | `block_handoff_if_absent` |

## Facts-Missing Packet Shape

```json
{
  "strategy_group_id": "LCF-001",
  "version": "2026-06-16-r0",
  "status": "facts_missing_no_signal",
  "default_mode": "observe_only",
  "decision": "no_candidate",
  "candidate_prepare_allowed_by_research": false,
  "execution_allowed_by_research": false,
  "required_facts_state": {
    "lcf_fact_pipeline_state": "lcf_facts_absent",
    "lcf_force_order_stream_state": "missing",
    "lcf_liquidation_cluster_state": "missing",
    "lcf_historical_oi_state": "missing",
    "lcf_positioning_ratio_state": "missing",
    "lcf_adl_stress_state": "missing",
    "lcf_depth_slippage_state": "missing",
    "lcf_margin_model_state": "missing"
  },
  "missing_facts": [
    "force_order_event_stream",
    "liquidation_cluster_state",
    "historical_open_interest_window",
    "global_long_short_ratio_window",
    "top_trader_position_ratio_window",
    "adl_quantile_state",
    "orderbook_depth_slippage_state",
    "real_exchange_margin_liquidation_model"
  ],
  "non_execution_flags": [
    "not_runtime_registration",
    "not_finalgate_input",
    "not_order_authority"
  ]
}
```

## Promotion Boundary

`LCF-001` must not become a handoff pack until all of the following are true:

1. Force-order events are reproducibly captured without credentials or exchange
   writes.
2. Liquidation clusters are generated from force-order events, not from
   price-only candle labels.
3. Historical OI, global long-short, and top-trader positioning windows align
   to the same closed-candle replay windows.
4. Depth/slippage, mark deviation, funding, ADL or equivalent stress proxy, and
   margin-model facts are attached.
5. The first stable output is a facts-missing no-signal packet.
6. Any later signal packet defaults to `1x`, treats `2x` and `3x` as research
   stress only, and keeps `5x` disabled.

## Research Conclusion

`LCF-001` remains worth preserving, but only as a facts-pipeline design lane.
The next evidence work is read-only public data capture and replay alignment for
force-order, OI, positioning ratio, depth, funding, mark, ADL, and margin-model
facts. Until then, it should appear in the Strategy Cabinet as
`facts_pipeline_required`, not as a handoff, runtime candidate, or execution
candidate.
