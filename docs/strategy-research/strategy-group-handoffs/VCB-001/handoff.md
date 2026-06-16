# VCB-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `VCB-001` |
| Name | Volatility Compression Breakout |
| Family | Volatility compression / expansion breakout |
| Default Mode | `observe_only` |
| Execution Status | Research-only; no runtime registration or order authority. |

`VCB-001` is not a broad breakout promotion. It is an observe-only
true-breakout classifier lane. The useful semantic is the separation between
rare true follow-through expansions and common false-breakout reversals.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | `long` |
| Current Symbols | `XRPUSDT`, `LINKUSDT`, `BNBUSDT`, `SOLUSDT`, `DOGEUSDT`, `BTCUSDT`, `ETHUSDT` |
| Unsupported Side | Short/fade evidence is negative or redesign evidence unless a separate strategy is created. |

## Signal Ready Rule

The handoff draft allows observation only when a closed-candle compression
breakout candidate can be evaluated without post-entry labels.

The current research window does not allow candidate preparation from VCB
because existing pre-entry classifiers do not reproduce the offline
true-breakout edge.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `recent_1h_candles` | Required for closed-candle compression and breakout state. |
| `compression_state` | Required before breakout interpretation. |
| `breakout_strength_state` | Required to avoid weak prior-high pokes. |
| `relative_volume_state` | Required for participation context. |
| `false_breakout_state` | Required as a disable/downshift fact. |
| `cost_sensitivity_state` | Required because the narrow volume-compression lane is cost/M2M negative. |
| `slot_m2m_equity_state` | Required before treating accepted events as live-like. |
| `spread_depth_state` | Missing; required before promotion. |
| `mark_index_state` | Missing; required before futures interpretation. |
| `real_margin_liquidation_model_state` | Missing; required before leverage promotion. |

## Risk Defaults

| Field | Value |
| --- | --- |
| Interpretation | Research proposal only, not live order-sizing defaults. |
| Risk Tier | `tiny` |
| Default Leverage | `1x` |
| Max Research Leverage | `2x` |
| Stress Only | `3x` |
| Disabled | `5x` |
| Protection | Requires stop-loss and exit plan before any future armed observation review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `broad_breakout_mode_requested` | Broad breakout evidence is negative. |
| `pre_entry_classifier_missing` | Offline true-breakout labels are not entry facts. |
| `false_breakout_state_unbounded` | False-breakout reversals are severe negative evidence. |
| `cost_m2m_negative` | Volume-compression lane loses across full event-slot sequence. |
| `spread_depth_missing` | Breakout entries need liquidity and spread facts. |
| `mark_index_missing` | Futures interpretation needs mark/index facts. |
| `high_leverage_requested` | 3x is stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks observation interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Broad breakout | `all_breakouts` full 1x is `-77.092301%`; broad activation is negative. |
| True-breakout label | `true_breakout_followthrough` full 1x is `908.444211%`; best 90d 2x is `440.884098%`. |
| False-breakout label | `false_breakout_reversal` full 1x is `-98.261028%`; this is disable evidence. |
| Pre-entry classifier | `pre_entry_volume_compression` keeps a 2x best 90d window but full curve is negative. |
| Cost/M2M stress | `0.30%` cost, `2x` lane is `-77.779542%` compound with `-91.604461%` max drawdown. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `VCB-001` as an observe-only draft. It may be shown as
a candidate strategy semantic or parked observer, but it should not enter
armed observation until a signal-time classifier improves full-sequence
behavior without using post-entry labels.
