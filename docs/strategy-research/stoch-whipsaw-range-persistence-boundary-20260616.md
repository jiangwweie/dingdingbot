# STOCH-001 Whipsaw and Range-Persistence Boundary

Status: ACTIVE_PARKED_VOCABULARY_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current research boundary for `STOCH-001`.

`STOCH-001` means **Stochastic oscillator range-persistence / whipsaw
vocabulary**, not a broad stochastic crossover strategy. The only preserved
idea is the short-window `stoch_bullish_range_persistence_long_72h` branch, and
even that branch stays parked because it fails the 90d right-tail gate and the
full sequence collapses.

This is research-only. It is not a StrategyGroup handoff, runtime registry,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Evidence |
| --- | --- |
| Replay script | `scripts/run_stoch_momentum_reversal_replay.py` |
| Replay data | Cached Binance 1h futures klines and funding rows |
| Universe | Binance 2026 equity/ETF, precious-metal, and industrial-metal perpetuals |
| Signal discipline | Closed 1h signal candle, next 1h open entry |
| Cost model | `0.30%` round trip plus funding over holding window |
| Raw signals | `8564` |
| Accepted events | `218` |
| Rejected events | `8346` |
| Rules with accepted events | `6` |
| Best preserved branch | `stoch_bullish_range_persistence_long_72h` |
| Preserved branch events / symbols | `73` events across `30` symbols |
| Preserved branch full 2x | `-90.790585%` |
| Preserved branch best 30d 2x | `246.716521%` |
| Preserved branch best 60d 2x | `196.054074%` |
| Preserved branch best 90d 2x | `80.874239%` |
| Preserved branch DD 2x | `-95.696757%` |
| Preserved branch 2x / 5x proxy liquidation | `0 / 2` |

## Strategy Semantics

The only preserved semantic is:

```text
Stochastic %K / %D stay in the upper momentum range
-> price attempts continuation while the oscillator remains elevated
-> some 30d / 60d bursts appear
-> the signal decays before the 90d gate and collapses in the full sequence
```

The strategy is not:

```text
generic stochastic oversold cross long
generic stochastic midline reclaim long
generic stochastic overbought cross short
symmetric long/short stochastic system
always-on oscillator strategy
handoff-ready StrategyGroup
```

## Rule Boundary

| Rule | Events | Full 2x | Best 30d 2x | Best 60d 2x | Best 90d 2x | DD 2x | 2x/5x Proxy | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `stoch_bullish_range_persistence_long_72h` | `73` | `-90.790585%` | `246.716521%` | `196.054074%` | `80.874239%` | `-95.696757%` | `0/2` | Preserve as parked vocabulary only. |
| `stoch_midline_reclaim_long_48h` | `39` | `-23.774662%` | `82.332508%` | `78.108019%` | `53.445406%` | `-50.324132%` | `0/1` | Negative / support vocabulary only. |
| `stoch_oversold_cross_long_48h` | `26` | `-17.668499%` | `31.796919%` | `31.796919%` | `31.796919%` | `-43.207960%` | `0/0` | Negative. |
| `stoch_regular_oversold_cross_long_24h` | `1` | `-2.092336%` | `0.000000%` | `0.000000%` | `0.000000%` | `-2.092336%` | `0/0` | Thin negative row. |
| `stoch_overbought_cross_short_48h` | `34` | `-85.392452%` | `7.430952%` | `-7.810999%` | `-7.810999%` | `-85.392452%` | `0/1` | Short-side failure. |
| `stoch_bearish_range_persistence_short_72h` | `45` | `-88.126094%` | `57.584471%` | `57.584471%` | `57.584471%` | `-95.015753%` | `0/3` | Short-side failure. |

## Window Boundary

STOCH is useful as a warning about oscillator window decay. The best branch has
large 30d / 60d bursts, but it fails the 90d gate and collapses in full-sample
stress.

| Month | Events | 1x Return | 2x Return | Avg Event 1x |
| --- | ---: | ---: | ---: | ---: |
| 2025-12 | `4` | `-3.964989%` | `-7.932980%` | `-0.990865%` |
| 2026-01 | `14` | `23.249460%` | `42.095062%` | `1.769250%` |
| 2026-02 | `43` | `-45.149586%` | `-74.402827%` | `-1.227061%` |
| 2026-03 | `45` | `-75.728930%` | `-96.091590%` | `-2.832771%` |
| 2026-04 | `47` | `26.931630%` | `27.427885%` | `0.715404%` |
| 2026-05 | `47` | `-20.882893%` | `-47.730655%` | `-0.314829%` |
| 2026-06 | `18` | `-53.764283%` | `-88.741038%` | `-3.334551%` |

Current interpretation:

1. The January and April windows explain why the vocabulary should not be
   deleted.
2. February, March, May, and June explain why it must stay parked.
3. The signal is vulnerable to chop, continuation failure, and late-window
   decay.
4. `5x` is disabled; `3x` is not useful because the best branch already reaches
   `-100.000000%` full 3x.

## Asset Role Boundary

| Asset role | Evidence | Decision |
| --- | --- | --- |
| Equity-like perpetuals | `159` events, full 2x `-99.904991%`, best 90d 2x `61.576037%`, DD 2x `-99.942145%`. | Park. Use as equity oscillator whipsaw evidence. |
| Precious metals | `53` events, full 2x `-0.910061%`, best 90d 2x `58.061087%`, DD 2x `-52.079480%`. | Context only. Not a PMR promotion. |
| Industrial metals | `6` events, full 2x `4.253814%`, best 90d 2x `0.946240%`. | Too thin; context only. |

## RequiredFacts Boundary

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `stoch_state` | `%K`, `%D`, lookback, smoothing, threshold zone, range position, and closed-candle timestamp. | No signal. |
| `stoch_cross_quality_state` | Separates meaningful crosses from noisy oscillator whipsaw. | Keep parked. |
| `stoch_bullish_range_persistence_state` | Captures the only branch worth preserving. | Keep parked. |
| `stoch_whipsaw_disable_state` | Blocks chop, late-window decay, and false continuation. | Block revival. |
| `stoch_short_side_failure_state` | Prevents short-side symmetry assumptions. | Block short-side handoff. |
| `stoch_window_decay_state` | Tracks 30d / 60d / 90d decay and monthly attribution. | Block handoff. |
| `tradfi_session_gap_state` | 24/7 Binance product behavior versus underlying market sessions. | Block handoff. |
| `fill_gap_slippage_state` | Next-open gap, spread, and slippage sensitivity. | Block handoff. |
| `real_exchange_margin_liquidation_model` | Real margin and liquidation model for leveraged interpretation. | `2x` research only; `3x` stress only; `5x` disabled. |

## Sample Boundary Packet

```json
{
  "strategy_id": "STOCH-001",
  "status": "parked_vocabulary_not_handoff",
  "preserved_branch": "stoch_bullish_range_persistence_long_72h",
  "supported_side": "long_context_only",
  "default_mode": "observe_only",
  "signal_ready": false,
  "reason": "best_30d_60d_windows_exist_but_90d_gate_and_full_sequence_fail",
  "blocked_branches": [
    "stoch_oversold_cross_long_48h",
    "stoch_midline_reclaim_long_48h",
    "stoch_regular_oversold_cross_long_24h",
    "stoch_overbought_cross_short_48h",
    "stoch_bearish_range_persistence_short_72h"
  ],
  "required_missing_before_revival": [
    "stoch_whipsaw_disable_state",
    "stoch_window_decay_state",
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

`STOCH-001` can move out of parked vocabulary only if all of the following
change:

1. A signal-time whipsaw / continuation-quality classifier materially improves
   the full sequence.
2. A stochastic branch clears the 90d right-tail gate without full-sequence
   collapse.
3. Short-side stochastic rows remain disabled unless separately proven.
4. Equity-like, precious-metal, and industrial-metal roles are split.
5. Product/session/fill/gap and real margin facts are attached.
6. `5x` remains disabled and `3x` remains stress-only unless separate margin
   evidence proves otherwise.

## Current Decision

Keep `STOCH-001` in the strategy cabinet as:

```text
parked_or_research_vocab
observe_only
oscillator whipsaw / range-persistence vocabulary
not handoff-ready
```

The useful idea is **stochastic range-persistence can create short bursts**.
The current blocker is that stochastic signals are too noisy and decay too hard
to become a standalone candidate.
