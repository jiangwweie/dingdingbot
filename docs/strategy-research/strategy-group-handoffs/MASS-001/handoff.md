# MASS-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `MASS-001` |
| Name | Mass Index Range Expansion Reversal |
| Family | Range expansion reversal / continuation |
| Default Mode | `observe_only` |
| Execution Status | Research-only draft; no runtime registration or order authority. |

`MASS-001` is a Mass Index range-expansion observer. Mass Index itself is
non-directional, so every usable signal must attach a prefix-safe direction
context before it can be interpreted. The current clean lead is
`mass_bulge_reversal_long_48h`; the continuation long branch is preserved as
support / right-tail review but remains drawdown-blocked.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | `long` |
| Support Side | `short_support_only` for precious-metal or reversal context. |
| Lead Mode | `mass_bulge_reversal_long_48h` |
| Research Symbols | `CRCLUSDT`, `COINUSDT`, `MUUSDT`, `MSTRUSDT`, `INTCUSDT`, `MRVLUSDT`, `HOODUSDT`, `TSLAUSDT`, `ORCLUSDT`, `CBRSUSDT`, `SPCXUSDT`, `AVGOUSDT`, `AMZNUSDT`, `PLTRUSDT`, `SNDKUSDT` |
| Unsupported Scope | Directionless Mass Index activation, primary short-side activation, precious-metal promotion, and high-leverage promotion. |

## Signal Ready Rule

The observe-only signal is fresh only when a closed 1h Mass Index bulge setup
and contraction trigger are present, and a prefix-safe prior trend context
assigns long direction. Mass Index must not be treated as a directional signal
by itself.

The current research recommendation is observe-only. A fresh MASS packet may
support Strategy Picker vocabulary and watcher exploration, but the research
window does not allow candidate preparation or execution authority.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `mass_index_state` | Required for Mass Index value, setup, trigger, parameters, and closed-candle timestamp. |
| `mass_bulge_trigger_state` | Required because activation depends on bulge setup and contraction trigger. |
| `mass_direction_context_state` | Required because Mass Index has no directional bias. |
| `mass_reversal_quality_state` | Required for the current clean reversal-long lead. |
| `mass_range_expansion_continuation_state` | Required because the largest right-tail branch is continuation-like but drawdown-blocked. |
| `mass_short_side_failure_state` | Required because short-side rows are currently negative or support-only. |
| `mass_window_decay_state` | Required because June 2026 decay appears in monthly attribution. |
| `mass_symbol_concentration_state` | Required because CRCL/COIN/MU/MSTR/INTC concentration carries much of the right tail. |
| `mass_asset_role_state` | Required because equity-like rows work and precious-metal rows are weak. |
| `fill_gap_slippage_state` | Required before runtime or armed-observation discussion. |
| `real_exchange_margin_liquidation_model` | Required before leverage promotion. |

## Risk Defaults

| Field | Value |
| --- | --- |
| Interpretation | Research proposal only, not live order-sizing defaults. |
| Risk Tier | `tiny` |
| Default Leverage | `1x` |
| Max Research Leverage | `2x` |
| Stress Only | `3x` |
| Disabled | `5x` |
| Exit Horizon | `48h` observe-only review lane. |
| Protection | Requires stop-loss and explicit exit plan before any future armed review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `mass_index_state_missing` | Mass Index cannot be evaluated. |
| `mass_bulge_trigger_missing` | No bulge setup / contraction trigger exists. |
| `mass_direction_context_missing` | Direction cannot be assigned. |
| `non_directional_mass_index_used_as_direction` | Mass Index itself has no directional bias. |
| `short_side_requested_as_primary` | Current short-side rows are negative or support-only. |
| `precious_metal_promotion_requested` | Precious-metal category evidence is weak. |
| `mass_window_decay_unresolved` | June decay and monthly persistence need further review. |
| `mass_symbol_concentration_unbounded` | Right tail is concentrated in a small set of equity-like symbols. |
| `continuation_branch_promoted_without_drawdown_disable` | Continuation branch has large DD despite large best-window returns. |
| `product_session_policy_missing` | Binance 2026 equity-like products need session/product handling. |
| `fill_gap_slippage_missing` | Next-open and session fill risk remain unresolved. |
| `real_margin_model_missing` | Leverage promotion is blocked. |
| `high_leverage_requested` | 3x is stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks signal interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Candidate pool | Raw signals `1234`; accepted events `125`; full 2x `1504.589885%`; best 90d 2x `4543.361872%`; DD 2x `-64.749326%`; 2x/5x proxy liquidation `0/0`. |
| Current lead | `mass_bulge_reversal_long_48h`. |
| Current lead performance | Events `33`; full 2x `395.155223%`; best 90d 2x `338.952327%`; DD 2x `-10.652922%`; 2x/5x proxy liquidation `0/0`. |
| Support branch | `mass_range_expansion_continuation_long_48h` full 2x `367.350795%`; best 90d 2x `1211.621762%`; DD 2x `-71.259030%`. |
| Category split | Equity-like full 2x `1579.901861%`; precious-metal full 2x `-4.483118%`. |
| Monthly blocker | June 2026 return 2x `-33.545406%`; May drawdown 2x `-63.193714%`. |
| Negative scope | Short-side and precious-metal branches are support-only or negative in current evidence. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `MASS-001` as an observe-only handoff draft. It is
useful for Strategy Picker vocabulary, signal watcher exploration, and future
range-expansion reversal research. It should not be treated as armed
observation until direction-context, fill/gap/session/product, concentration,
decay, and real exchange-margin facts improve.
