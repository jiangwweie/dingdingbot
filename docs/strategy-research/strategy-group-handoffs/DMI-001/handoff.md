# DMI-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `DMI-001` |
| Name | ADX Directional Ignition |
| Family | ADX / DMI directional movement ignition |
| Default Mode | `observe_only` |
| Execution Status | Research-only draft; no runtime registration or order authority. |

`DMI-001` is not a generic ADX strategy. The current usable semantic is the
narrow `dmi_long_equity_adx_rising` branch with a `24h` time-stop. It watches
for closed-candle directional movement ignition in equity-like Binance symbols,
but it remains observe-only until live-like spread, gap, session, product-risk,
and real exchange-margin facts are attached.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | `long` |
| Lead Mode | `dmi_long_equity_adx_rising_24h` |
| Research Symbols | `CRCLUSDT`, `FLNCUSDT`, `MRVLUSDT`, `NBISUSDT`, `ORCLUSDT`, `HOODUSDT`, `METAUSDT`, `EWYUSDT`, `COINUSDT`, `MSTRUSDT`, `PLTRUSDT`, `MUUSDT`, `SNDKUSDT`, `NVDAUSDT`, `TSLAUSDT` |
| Unsupported Scope | Generic DMI, short-side DMI, and precious-metal generalization. |

## Signal Ready Rule

The observe-only signal is fresh only when a closed 1h candle provides the DMI
state and asset-role facts. Direction must come from +DI / -DI. ADX is only
used as a trend-strength ignition state.

The current research recommendation is observe-only. A fresh DMI packet may
prepare review context for main control, but the research window does not allow
candidate preparation or execution authority.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `dmi_adx_trend_strength_state` | Required because the branch depends on ADX >= 25 and rising. |
| `dmi_directional_spread_state` | Required because direction comes from +DI / -DI spread. |
| `dmi_di_cross_state` | Required to prevent generic DMI claims. |
| `directional_decay_disable_state` | Required before treating the branch as persistent. |
| `dmi_asset_role_state` | Required because equity-like rows work and metal rows currently drag. |
| `dmi_raw_pool_classifier_state` | Required to prove classifiers are signal-time only. |
| `dmi_exit_horizon_state` | Required because the lead semantic moved to the `24h` time-stop. |
| `dmi_fill_gap_slippage_sensitivity_state` | Required because the branch is cost-sensitive above moderate extra cost. |
| `dmi_live_spread_proxy_state` | Required before runtime or armed-observation discussion. |
| `dmi_low_history_product_risk_state` | Required for newly listed equity-like contracts. |
| `fill_gap_slippage_state` | Required before any real candidate preparation. |
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
| Exit Horizon | `24h` observe-only review lane. |
| Protection | Requires stop-loss and explicit exit plan before any future armed review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `generic_dmi_mode_requested` | Generic DMI evidence is not promotion evidence. |
| `short_side_requested` | Current short-side DMI rows fail. |
| `precious_metal_generalization_requested` | Current metal rows are negative or drag. |
| `dmi_adx_trend_strength_missing` | Trend-strength ignition cannot be verified. |
| `dmi_directional_spread_missing` | Direction cannot be verified. |
| `dmi_exit_horizon_missing` | The current lead depends on the 24h time-stop. |
| `dmi_fill_gap_slippage_sensitivity_missing` | Cost sensitivity is part of the current boundary. |
| `extra_cost_tolerance_exceeded` | The branch weakens near 0.50% extra cost and breaks by 1.00%. |
| `product_session_policy_missing` | Equity-like perps require product/session handling. |
| `real_margin_model_missing` | Leverage promotion is blocked. |
| `high_leverage_requested` | 3x is stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks signal interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Original lead | `dmi_strength_long_72h` full 2x `168.728555%`; best 90d 2x `366.822160%`; DD 2x `-66.773603%`. |
| Current lead | `dmi_long_equity_adx_rising` at `24h`. |
| Current lead performance | Events `169`; full 2x `481.350915%`; best 90d 2x `852.623789%`; second-half 2x `254.307331%`; DD 2x `-50.301484%`; 2x/5x proxy liquidation `0/0`. |
| 0.25% extra-cost stress | Full 2x `150.419770%`; best 90d 2x `377.840803%`; DD 2x `-57.197553%`. |
| 0.50% extra-cost stress | Full 2x `7.411572%`; best 90d 2x `139.176383%`; DD 2x `-63.156964%`. |
| 1.00% extra-cost stress | Full 2x `-80.492724%`; candidate breaks on full sequence. |
| Negative scope | Short-side and precious-metal generalization fail current evidence. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `DMI-001` as an observe-only handoff draft. It is useful
for Strategy Picker vocabulary, signal watcher exploration, and later P1
follow-up, but should not be treated as armed observation until live-like
spread/gap/session/product/margin facts are available.
