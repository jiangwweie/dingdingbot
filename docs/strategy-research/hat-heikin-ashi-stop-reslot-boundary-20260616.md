# HAT-001 Heikin-Ashi Stop-Reslot Boundary

Status: ACTIVE_REVIVAL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current research boundary for `HAT-001`.

`HAT-001` means **Heikin-Ashi smoothed trend revival with classifier and
fixed-stop reslot evidence**. It does not mean broad Heikin-Ashi trend
following, generic color flip trading, short-side HA symmetry, or a
handoff-ready StrategyGroup.

This is research-only. It is not a StrategyGroup handoff, runtime registry,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Evidence |
| --- | --- |
| Base replay script | `scripts/run_hat_heikin_ashi_trend_replay.py` |
| Classifier replay script | `scripts/analyze_hat_decay_asset_role_classifiers.py` |
| Stop-reslot script | `scripts/analyze_hat_stop_reslot.py` |
| Replay data | Cached Binance 1h futures klines and funding rows |
| Universe | Binance 2026 equity/ETF, precious-metal, and industrial-metal perpetuals |
| Signal discipline | Closed 1h signal candle, next 1h open entry |
| Base replay raw / accepted / rejected | `9917 / 199 / 9718` |
| Classifier replay accepted / rejected | `1991 / 28825` |
| Stop-reslot accepted / rejected | `6266 / 65610` |
| Base preserved branch | `hat_green_run_long_72h` |
| Best classifier full-return row | `hat_green_equity_clean_combo` |
| Best stop full-return row | `hat_green_equity_regular_proxy` stop `8.00%` |

## Strategy Semantics

The preserved semantic is:

```text
Heikin-Ashi green run smooths noisy raw candles
-> equity-like product shows trend persistence
-> signal-time classifier filters asset role, weekday, body, wick, impulse, and volume
-> fixed-stop reslot tests whether path risk can be reduced
-> right-tail survives, but drawdown and stop-fill facts still block handoff
```

The strategy is not:

```text
broad Heikin-Ashi trend following
generic bullish flip long
generic bearish flip short
precious-metal HA short
industrial-metal HA strategy
validated stop-loss execution model
handoff-ready StrategyGroup
```

## Base Replay Boundary

| Rule | Events | Full 2x | Best 90d 2x | DD 2x | 2x/5x Proxy | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `hat_green_run_long_72h` | `84` | `-80.378826%` | `124.988386%` | `-86.693457%` | `0/2` | Preserve as revival vocabulary only. |
| `hat_equity_regular_green_run_long_24h` | `5` | `38.297534%` | `38.297534%` | `-0.951606%` | `0/0` | Thin support only. |
| `hat_bullish_flip_long_48h` | `26` | `-22.291138%` | `-1.665319%` | `-33.174409%` | `0/0` | Negative. |
| `hat_bearish_flip_short_48h` | `25` | `-81.536392%` | `0.283092%` | `-82.059840%` | `0/3` | Short-side failure. |
| `hat_red_run_short_72h` | `51` | `-92.881349%` | `24.945557%` | `-94.372395%` | `0/2` | Short-side failure. |
| `hat_precious_red_run_short_48h` | `8` | `-37.242842%` | `-5.714365%` | `-39.413361%` | `0/0` | PMR negative evidence. |

## Classifier Boundary

Classifier replay improves the HAT thesis, but does not solve drawdown.

| Classifier | Accepted | Full 2x | Best 90d 2x | DD 2x | 2x/5x Proxy | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `hat_green_equity_clean_combo` | `110` | `90.789324%` | `789.739339%` | `-68.823196%` | `0/0` | Best full-return classifier; still DD-blocked. |
| `hat_green_equity_regular_proxy` | `101` | `20.836312%` | `1541.436404%` | `-88.369241%` | `0/0` | Best 90d classifier; DD too deep. |
| `hat_green_equity_weekday` | `115` | `-40.622587%` | `234.760439%` | `-85.242947%` | `0/0` | Weekday removes proxy liquidation but not DD. |
| `hat_short_red_baseline_reslot` | `136` | `-99.821142%` | `25.634500%` | `-99.916607%` | `1/5` | Confirms short-side failure. |
| `hat_pmr_red_baseline_reslot` | `102` | `-73.926089%` | `53.290520%` | `-89.143018%` | `0/0` | Confirms PMR red-run failure. |

The current best activation vocabulary is `hat_green_equity_clean_combo`:

```text
equity role
weekday
bounded impulse
strong HA body
low counter-wick
volume participation
```

This remains a research classifier, not runtime signal readiness.

## Stop-Reslot Boundary

Fixed-stop reslot preserves right-tail evidence, but it does not prove live
stop execution.

| Stop Row | Stop | Accepted | Stop Hits | Full 2x | Best 90d 2x | DD 2x | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `hat_green_equity_regular_proxy` | `8.00%` | `112` | `19` | `212.342958%` | `2753.415059%` | `-89.042297%` | Best full-return stop row; DD still too deep. |
| `hat_green_equity_clean_combo` | `12.00%` | `113` | `6` | `128.953184%` | `816.085735%` | `-72.678564%` | Best clean-combo full-return stop row; DD-blocked. |
| `hat_green_equity_clean_combo` | `8.00%` | `120` | `19` | `39.524671%` | `351.705802%` | `-72.063422%` | Preserves right-tail, weakens full return. |
| `hat_green_equity_clean_combo` | `6.00%` | `125` | `34` | `-25.555152%` | `125.733010%` | `-71.210856%` | Best DD among 100%+ 90d rows, but full sequence negative. |

Current interpretation:

1. Stop-reslot is useful risk evidence.
2. Stop-reslot does not resolve HAT drawdown.
3. Stop-fill, gap, spread, and mark/index facts are mandatory before any
   runtime-facing interpretation.
4. `5x` remains disabled; `3x` is stress-only.

## Window and Asset Boundary

| Boundary | Evidence | Decision |
| --- | --- | --- |
| Broad equity HAT | Category full 2x `-99.087715%`, best 90d 2x `42.979279%`, DD 2x `-99.369763%`. | Broad equity HAT fails. |
| Precious-metal HAT | Category full 2x `-83.364392%`, best 90d 2x `-15.765644%`, DD 2x `-89.116034%`. | PMR HAT fails. |
| Industrial-metal HAT | `2` base events and `10` classifier events in industrial-only classifier. | Context only. |
| Monthly attribution | 2026-02 to 2026-06 are all negative in base replay. | Requires decay / disable facts. |
| Symbol path risk | `SOXLUSDT`, `XAGUSDT`, `PLTRUSDT`, `MUUSDT`, and `NVDAUSDT` produce large adverse examples. | Requires exit / stop-fill facts. |

## RequiredFacts Boundary

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `heikin_ashi_state` | HA open/high/low/close, formula version, recursive seed, and closed-candle timestamp. | No signal. |
| `ha_trend_run_state` | Consecutive green HA candles, run length, and raw-price context. | No signal. |
| `ha_clean_classifier_state` | Equity role, weekday, bounded impulse, body, wick, and volume facts. | Keep research-only. |
| `ha_smoothing_lag_state` | Lag between HA color/run and raw-price reversal. | Block revival. |
| `ha_window_decay_state` | 30d/60d/90d, monthly attribution, and post-window decay. | Block handoff. |
| `ha_short_side_failure_state` | Prevents bearish flip/red-run symmetry. | Block short-side handoff. |
| `ha_asset_role_state` | Equity, PMR, and industrial split. | Block handoff. |
| `ha_stop_reslot_state` | Stop-hit time, post-stop exit time, and freed-capital reslot behavior. | Keep research-only. |
| `ha_stop_policy_tradeoff_state` | Tradeoff among stop width, full sequence, right-tail window, and drawdown. | Block handoff. |
| `stop_fill_gap_state` | Whether fixed-stop assumptions survive gap, spread, and fill reality. | Block armed observation. |
| `tradfi_session_gap_state` | 24/7 Binance product versus underlying market sessions. | Block armed observation. |
| `fill_gap_slippage_state` | Next-open and stop-fill slippage. | Block armed observation. |
| `real_exchange_margin_liquidation_model` | Real margin and liquidation model for leveraged interpretation. | `2x` research only; `3x` stress only; `5x` disabled. |

## Sample Boundary Packet

```json
{
  "strategy_id": "HAT-001",
  "status": "revival_candidate_not_handoff",
  "preserved_branch": "hat_green_equity_clean_combo",
  "supported_side": "long",
  "default_mode": "observe_only",
  "signal_ready": false,
  "reason": "classifier_and_stop_reslot_preserve_right_tail_but_drawdown_and_stop_fill_facts_block_handoff",
  "blocked_branches": [
    "hat_bullish_flip_long_48h",
    "hat_bearish_flip_short_48h",
    "hat_red_run_short_72h",
    "hat_precious_red_run_short_48h"
  ],
  "required_missing_before_handoff": [
    "ha_smoothing_lag_state",
    "ha_window_decay_state",
    "ha_stop_policy_tradeoff_state",
    "stop_fill_gap_state",
    "tradfi_session_gap_state",
    "fill_gap_slippage_state",
    "real_exchange_margin_liquidation_model"
  ],
  "non_execution_flags": [
    "not_runtime_registration",
    "not_finalgate_input",
    "not_order_authority"
  ]
}
```

## Revival Conditions

`HAT-001` can move from research candidate to handoff discussion only if all of
the following improve:

1. `hat_green_equity_clean_combo` or a successor classifier lowers drawdown
   materially without destroying full-sequence behavior.
2. Stop-reslot assumptions are replaced or confirmed by stop-fill, gap, spread,
   and mark/index facts.
3. HA smoothing lag is converted into a signal-time disable fact.
4. Short-side and PMR red-run branches remain disabled unless separately
   proven.
5. Product/session/fill and real margin facts are attached.
6. `5x` remains disabled and `3x` remains stress-only unless separate margin
   evidence proves otherwise.

## Current Decision

Keep `HAT-001` in the strategy cabinet as:

```text
research_candidate
observe_only
Heikin-Ashi green-run revival lane
not handoff-ready
```

The useful idea is **smoothed equity green-run continuation with a clean
signal-time classifier**. The current blocker is that even classifier and
stop-reslot evidence does not yet convert right-tail windows into bounded
runtime-ready risk.
