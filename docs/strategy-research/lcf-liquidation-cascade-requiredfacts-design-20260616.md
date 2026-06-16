# LCF-001 Liquidation Cascade RequiredFacts Design

Status: ACTIVE_RESEARCH_FACT_DESIGN
Last updated: 2026-06-16

## Scope

`LCF-001` is a research-only RequiredFacts design packet for liquidation
cascade follow-through.

It is not a StrategyGroup handoff, not a runtime registration, not a
FinalGate input, not an Operation Layer input, not an order authority, not a
leverage setting, and not a live profile.

## Thesis

`LCF-001` studies whether forced-flow events can create short-lived
continuation or reversal windows after liquidation clusters.

The candidate is worth preserving because liquidation cascades can create
small-capital right-tail opportunities when market impact, forced closing, and
crowded positioning happen together. The same structure is dangerous when the
facts are incomplete, because price-only candles can confuse ordinary volatility
with real forced-flow pressure.

## Current Decision

| Field | Decision |
| --- | --- |
| Strategy id | `LCF-001` |
| Semantic name | Liquidation Cascade Follow-through |
| Current status | `facts_pipeline_required` |
| Default mode | `observe_only` |
| Handoff state | No handoff pack yet |
| Runtime state | Not registered |
| Main-control intake | Not ready |
| Execution authority | None |

## RequiredFacts Matrix

| RequiredFact | Meaning | Current Evidence | Missing Behavior | Promotion Meaning |
| --- | --- | --- | --- | --- |
| `force_order_event_stream` | Liquidation event stream or archive, including symbol, side, quantity, and event time. | Missing locally. | `BLOCK_HANDOFF` | Cannot distinguish true forced-flow cascade from candle volatility. |
| `liquidation_cluster_state` | Clustered liquidation pressure over a bounded time window. | Missing locally; depends on `force_order_event_stream`. | `BLOCK_HANDOFF` | Needed before any fresh-signal rule can exist. |
| `historical_open_interest_window` | OI level and change through the candidate window. | Current snapshot field shape exists; 2024-2025 window coverage missing. | `BLOCK_PROMOTION` | Needed to separate position decay, crowding buildup, and squeeze risk. |
| `open_interest_change_state` | Recent OI expansion or contraction around the event. | Recent Binance public endpoint shape exists. | `FIELD_SHAPE_ONLY` | Useful for dry-run facts, not historical promotion evidence. |
| `funding_window_sum` | Funding pressure during the candidate window. | Partial local coverage for BTC, ETH, SOL, XRP, and ADA. | `OBSERVE_ONLY` | Useful as carry/crowding context, insufficient alone. |
| `global_long_short_ratio_window` | Account-side crowding during the candidate window. | Current/recent endpoint shape exists; historical local coverage missing. | `BLOCK_PROMOTION` | Needed before directional cascade interpretation. |
| `top_trader_position_ratio_window` | High-margin trader crowding during the candidate window. | Current/recent endpoint shape exists; historical local coverage missing. | `BLOCK_PROMOTION` | Needed to avoid trading against dominant leveraged positioning blindly. |
| `adl_quantile_state` | ADL or liquidation-engine risk proxy. | Missing locally. | `BLOCK_PROMOTION` | Needed before levered or crowded-position interpretation. |
| `orderbook_depth_slippage_state` | Depth, spread, and slippage around cascade periods. | Missing locally. | `BLOCK_PROMOTION` | Needed before any candidate can approach action preparation. |
| `mark_price_deviation_window` | Mark/last or mark/spot divergence during stress. | Partial mark-price coverage exists for major symbols. | `OBSERVE_ONLY` | Needed to avoid false price-only triggers. |
| `real_exchange_margin_liquidation_model` | Venue-specific margin, liquidation, and funding behavior. | Missing locally. | `BLOCK_PROMOTION` | Current leverage outputs remain research scores only. |
| `same_symbol_position_order_state` | Existing active position and open-order state. | Runtime-side fact, not strategy research fact. | `MAIN_CONTROL_REQUIRED` | If ever admitted, main control must block conflict with active exposure. |

## Data Source Map

| Source | Current State | Use |
| --- | --- | --- |
| `docs/strategy-research/derivatives-leverage-requiredfacts-data-plan.md` | Active derivatives fact plan. | Defines current leverage, funding, mark, OI, and ratio gaps. |
| `docs/strategy-research/btpc-derivatives-reviewability/btpc-derivatives-reviewability-summary.md` | Active derivatives reviewability audit. | Shows why strong right-tail derivative scores cannot promote without OI, ratio, and margin facts. |
| `docs/strategy-research/external-data/binance-futures-context-20260613/futures-context-summary.md` | Public read-only current endpoint field-shape proof. | Proves recent OI and ratio fields are capturable; does not prove 2024-2025 windows. |
| Binance USD-M public market data endpoints | Public read-only source. | Candidate source for OI, long-short ratio, top-trader ratio, mark price, funding, and force-order stream capture. |

## Minimal Capture Plan

1. Capture a public read-only `forceOrder` stream or archive into research
   evidence with symbol, side, quantity, price, and event timestamp.
2. Build historical OI, global long-short ratio, and top-trader position-ratio
   windows aligned to the same closed-candle replay windows.
3. Attach mark-price deviation, funding-window sum, and depth/slippage facts
   for the liquidation event window.
4. Add an exchange-margin and liquidation-engine model before interpreting any
   levered result as more than a research score.
5. Produce one no-signal/facts-missing packet before any signal-ready packet.

## No-Signal Packet Shape

```json
{
  "strategy_group_id": "LCF-001",
  "version": "2026-06-16-r0",
  "status": "facts_missing",
  "default_mode": "observe_only",
  "decision": "no_candidate",
  "missing_facts": [
    "force_order_event_stream",
    "liquidation_cluster_state",
    "historical_open_interest_window",
    "global_long_short_ratio_window",
    "top_trader_position_ratio_window",
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

## Handoff Preconditions

`LCF-001` can move from `facts_pipeline_required` to a handoff draft only when:

1. `force_order_event_stream` is reproducibly captured.
2. Historical OI and long-short facts cover the target replay windows.
3. Depth/slippage and mark-price deviation facts are available around the event.
4. The first packet is a no-signal or facts-missing packet with stable semantics.
5. Any later signal packet keeps leverage at `1x` by default and marks `2x` or
   `3x` as research stress only.

Until then, `LCF-001` remains a strategy-cabinet entry and RequiredFacts design
task, not a main-control handoff.
