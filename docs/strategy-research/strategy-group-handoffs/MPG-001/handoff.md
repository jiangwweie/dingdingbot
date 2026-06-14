# MPG-001 Strategy Group Handoff Pack

Status: HANDOFF_READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-14
Version: 2026-06-14-r0

## Strategy

| Field | Value |
| --- | --- |
| strategy_group_id | `MPG-001` |
| Name | Momentum Persistence Group |
| Runtime role | Experimental StrategyGroup candidate for observation and signal evaluation |
| Execution status | Research-only handoff; no runtime registration or exchange action |

`MPG-001` groups Williams Percent Range, Money Flow Index, Percentage Price
Oscillator, True Strength Index, MACD Histogram, and ADX/DMI evidence into one
momentum-persistence strategy group.

The useful semantic is not oscillator reversal. The useful semantic is
closed-candle strength persistence after a strong impulse, with explicit
late-cycle and leverage downshift boundaries.

## Supported Scope

| Field | Value |
| --- | --- |
| supported_sides | `long` |
| primary_observation_universe | Binance 2026 TradFi equity / ETF perpetuals |
| support_observation_universe | Precious-metal perpetuals for support evidence only |
| default_observation_mode | `armed_observation` |
| execution_readiness | Not execution-ready; main-control gates own runtime admission and execution boundaries |

Initial research-supported symbols are the most frequent symbols in accepted
MPG event pools. They are observation candidates, not live trading allowlists:

`INTCUSDT`, `MSTRUSDT`, `COINUSDT`, `CRCLUSDT`, `HOODUSDT`, `PLTRUSDT`,
`MUUSDT`, `SNDKUSDT`, `TSLAUSDT`, `AMZNUSDT`, `EWYUSDT`, `NVDAUSDT`,
`METAUSDT`, `GOOGLUSDT`, `TSMUSDT`, `MRVLUSDT`, `AVGOUSDT`, `FLNCUSDT`,
`SOXLUSDT`, `XAGUSDT`, `XAUUSDT`.

## Signal Ready Rule

Fresh signal means all of the following are true:

1. The signal is based only on closed 1h candles.
2. One MPG member emits a long momentum-persistence signal.
3. The group classifier accepts the event as bounded impulse or regular-session
   tradeoff evidence.
4. The signal body is moderate enough to avoid the current late-cycle extension
   blocker.
5. The signal includes direction, symbol, source member, classifier, entry
   reason, invalidation reason, and protection-plan hint.
6. The signal facts are fresh inside a 120-second runtime-readiness window.

The preferred current classifier lane is `mpg_lcd_body_le_1p5` for right-tail
revival review. The cleaner tradeoff lane is the 12h regular-session proxy.
The 72h bounded impulse lane preserves the largest right tail but remains
drawdown-blocked.

## RequiredFacts

| Fact | Purpose |
| --- | --- |
| `recent_1h_candles` | Required for closed-candle momentum-persistence evaluation. |
| `mpg_member_signal_state` | Records which member fired and prevents member ambiguity. |
| `mpg_group_pool_selection_state` | Required because WPR, MFI, PPO, TSI, MHI, and DMI compete for capital slots. |
| `momentum_clean_persistence_state` | Separates strength persistence from generic oscillator reversal. |
| `mpg_late_cycle_disable_state` | Blocks overextended continuation and June-style decay. |
| `mpg_signal_body_extension_state` | Required because body-capped persistence improves the current lead. |
| `mpg_exit_horizon_state` | Required because 12h and 72h horizons have different tradeoffs. |
| `mpg_2x_tradeoff_lane_state` | Keeps the 12h regular proxy separate from revival-only rows. |
| `mpg_leverage_horizon_boundary_state` | Prevents 3x/5x stress evidence from being treated as promotion evidence. |
| `mpg_high_leverage_disable_state` | Disables 5x where proxy liquidation or near-total loss appears. |
| `mpg_drawdown_attribution_state` | Keeps drawdown forensics visible before promotion review. |
| `mpg_member_drawdown_contribution_state` | Required before excluding or promoting member signals. |
| `mpg_symbol_concentration_state` | Required before symbol concentration becomes activation or disable logic. |
| `tradfi_offhour_mark_index_state` | Required because the evidence is equity/ETF perp dominated. |
| `fill_gap_slippage_state` | Required before next-open 1h entries are live-like. |
| `real_margin_liquidation_model_state` | Required before leverage promotion. |
| `exchange_symbol_rules_state` | Main-control fact for min notional, step size, tick size, and current availability. |
| `account_conflict_state` | Main-control fact for active same-symbol positions and open orders. |

## Risk Defaults

These are research proposals for bounded observation and candidate preparation.
They are not live order-sizing defaults.

| Field | Value |
| --- | --- |
| risk_tier | `tiny` |
| max_notional_per_action_usdt | `8` research proposal |
| max_active_positions | `1` |
| max_leverage | `2` for research lane; `1` default for first runtime observation |
| requires_sl | `true` |
| requires_tp_or_exit_plan | `true` |
| default_exit_horizon | `12h` tradeoff lane; `72h` revival lane only |
| disabled_leverage | `5x` |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `active_position_same_symbol` | Do not stack observation-to-candidate flow over an existing same-symbol position. |
| `open_order_same_symbol` | Avoid duplicate exposure and stale candidate preparation. |
| `stale_market_facts` | Closed-candle facts must be current. |
| `missing_exchange_rules` | Main-control cannot prepare a candidate without min notional, step, and tick facts. |
| `no_stop_loss_plan` | MPG drawdown is unresolved; protection is mandatory. |
| `missing_exit_horizon` | 12h and 72h lanes have materially different evidence. |
| `late_cycle_extension_detected` | Overextended continuation is a known failure mode. |
| `high_leverage_requested` | 5x is disabled; 3x is stress-only. |
| `strategy_signal_conflict` | Conflicting MPG member direction or classifier state blocks candidate preparation. |
| `no_real_margin_model_for_leverage` | Leverage promotion requires exchange-margin modeling. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Member evidence | All six lead members have positive full 2x and 100%+ best-90d 2x windows. |
| Group classifier | `mpg_bounded_impulse` reaches full 2x `306.759633%` and best-90d 2x `1036.621997%`, but DD remains `-79.542357%`. |
| Exit horizon | `mpg_bounded_impulse` 72h reaches full 2x `353.763739%` and best-90d 2x `1204.646317%`; the cleaner 12h regular proxy is lower return but cleaner risk. |
| Late-cycle disable | `mpg_lcd_body_le_1p5` improves full 2x to `337.940592%` and best-90d 2x to `1433.147820%`, but DD remains `-75.753763%`. |
| Leverage envelope | 2x has research lanes; 3x is stress-only; 5x is disabled in most useful right-tail rows. |
| Drawdown attribution | Current max-DD phase is concentrated in June 2026 and led by WPR/TSI phase drag. |

## Sample Packets

The canonical sample packets are in `handoff.json`.

The JSON includes:

1. `sample_signal_packet`
2. `sample_no_signal_packet`
3. `sample_stale_signal_packet`
4. `sample_conflict_packet`

## Reproducible Evidence

```bash
python3 -m py_compile scripts/build_momentum_persistence_strategy_group.py scripts/analyze_mpg_group_decay_classifiers.py scripts/analyze_mpg_exit_horizon_reslot.py scripts/analyze_mpg_leverage_horizon_envelope.py scripts/analyze_mpg_late_cycle_disable.py scripts/analyze_mpg_drawdown_attribution.py
/Users/jiangwei/Documents/github/quant-strategies/.venv/bin/python scripts/build_momentum_persistence_strategy_group.py
/Users/jiangwei/Documents/github/quant-strategies/.venv/bin/python scripts/analyze_mpg_group_decay_classifiers.py
/Users/jiangwei/Documents/github/quant-strategies/.venv/bin/python scripts/analyze_mpg_exit_horizon_reslot.py
/Users/jiangwei/Documents/github/quant-strategies/.venv/bin/python scripts/analyze_mpg_leverage_horizon_envelope.py
/Users/jiangwei/Documents/github/quant-strategies/.venv/bin/python scripts/analyze_mpg_late_cycle_disable.py
/Users/jiangwei/Documents/github/quant-strategies/.venv/bin/python scripts/analyze_mpg_drawdown_attribution.py
```

## Main-Control Handoff

`MPG-001` is ready for main-control review as an experimental strategy-group
candidate for observation. It should not be promoted as an execution strategy.

Main-control can consume it as:

```text
Strategy Picker candidate
-> observable runtime admission review
-> RequiredFacts readiness check
-> armed observation
-> signal packet review
-> candidate preparation only if gates pass
```

The research window does not register it in runtime, bind watchers, prepare
FinalGate input, create Operation Layer calls, deploy, or place orders.
