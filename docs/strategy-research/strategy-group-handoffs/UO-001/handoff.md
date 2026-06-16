# UO-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `UO-001` |
| Name | Ultimate Oscillator Bullish Divergence |
| Family | Oscillator divergence / multi-window momentum |
| Default Mode | `observe_only` |
| Execution Status | Research-only draft; no runtime registration or order authority. |

`UO-001` is not a generic Ultimate Oscillator strategy. The current usable
semantic is the narrow `uo_bullish_divergence_long_72h` branch: closed-candle
price weakness with improving Ultimate Oscillator behavior, followed by an
observe-only long reversal review window.

Generic midline persistence, bearish divergence short, and symmetric oscillator
reversal are negative or revival-only evidence and must not be promoted through
this handoff.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | `long` |
| Lead Mode | `uo_bullish_divergence_long_72h` |
| Research Symbols | `TSLAUSDT`, `AMZNUSDT`, `XAUUSDT`, `PLTRUSDT`, `HOODUSDT`, `XPTUSDT`, `INTCUSDT`, `COPPERUSDT`, `GOOGLUSDT`, `CRCLUSDT`, `MUUSDT`, `METAUSDT`, `AAPLUSDT`, `DISUSDT`, `XPDUSDT`, `MSTRUSDT`, `COINUSDT`, `QQQUSDT`, `XAGUSDT`, `EWJUSDT`, `NVDAUSDT`, `TSMUSDT`, `LITEUSDT`, `BRKBUSDT`, `VUSDT` |
| Unsupported Scope | Generic UO midline momentum, bearish divergence short, overbought-failure short as action, and broad category activation. |

## Signal Ready Rule

The observe-only signal is fresh only when a closed 1h candle provides the UO
state, bullish-divergence quality facts, and prior-price-weakness facts.

The research recommendation is observe-only. A fresh UO packet may prepare
review context for main control, but this research window does not allow
candidate preparation, armed observation, or execution authority.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `ultimate_oscillator_state` | Required because UO value and 7/14/28 buying-pressure ratios define the indicator. |
| `uo_bullish_divergence_quality_state` | Required because only bullish divergence has current right-tail evidence. |
| `uo_prior_price_weakness_state` | Required to prove this is divergence after weakness, not generic momentum. |
| `uo_midline_persistence_failure_state` | Required to block generic midline-persistence semantics. |
| `uo_short_side_failure_state` | Required because bearish divergence short and overbought-failure short are not validated. |
| `uo_window_persistence_state` | Required to distinguish local right-tail windows from broad stable alpha. |
| `uo_asset_role_state` | Required because equity-like, precious-metal, and industrial-metal rows differ. |
| `uo_symbol_concentration_state` | Required because the lead branch has only `25` symbols and symbol mix matters. |
| `tradfi_session_gap_state` | Required because evidence comes from 2026 24/7 TradFi-like perps. |
| `fill_gap_slippage_state` | Required because replay uses next-open 1h entries. |
| `real_exchange_margin_liquidation_model` | Required before leverage interpretation can move beyond proxy stress. |

## Risk Defaults

| Field | Value |
| --- | --- |
| Interpretation | Research proposal only, not live order-sizing defaults. |
| Risk Tier | `tiny` |
| Default Leverage | `1x` |
| Max Research Leverage | `2x` |
| Stress Only | `3x` |
| Disabled | `5x` |
| Exit Horizon | `72h` observe-only review lane. |
| Protection | Requires stop-loss and explicit exit plan before any future armed review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `generic_uo_mode_requested` | Generic UO evidence is not promotion evidence. |
| `midline_persistence_requested` | UO midline persistence long collapses full sequence. |
| `short_side_requested` | Current UO short-side rows fail or are revival-only. |
| `uo_state_missing` | Indicator state cannot be verified. |
| `uo_bullish_divergence_quality_missing` | The lead semantic cannot be verified. |
| `uo_prior_price_weakness_missing` | Divergence after weakness cannot be verified. |
| `uo_window_persistence_missing` | Window durability cannot be reviewed. |
| `uo_asset_role_missing` | Product role cannot be verified. |
| `product_session_policy_missing` | Equity/metal perps require product/session handling. |
| `fill_gap_slippage_missing` | Next-open replay assumptions are unverified. |
| `real_margin_model_missing` | Leverage promotion is blocked. |
| `high_leverage_requested` | 3x is stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks signal interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Lead mode | `uo_bullish_divergence_long_72h` |
| Lead events / symbols | `52` events across `25` symbols. |
| Lead full 2x | `77.534009%` |
| Lead best 90d 2x | `197.155957%` |
| Lead DD 2x | `-44.564941%` |
| Lead 2x / 5x proxy liquidation | `0/0` |
| Negative midline | `uo_midline_persistence_long_72h` full 2x `-94.765397%`, DD 2x `-95.161331%`. |
| Negative short side | `uo_bearish_divergence_short_72h` full 2x `-42.897881%`, DD 2x `-80.557114%`. |
| Category attribution | Broad equity, precious-metal, and industrial-metal category attribution is negative. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `UO-001` as an observe-only handoff draft. It is useful
for Strategy Picker vocabulary, watcher exploration, and future P1 follow-up,
but should not be treated as armed observation until divergence-quality,
session/fill/product, symbol concentration, and real-margin facts are available.
