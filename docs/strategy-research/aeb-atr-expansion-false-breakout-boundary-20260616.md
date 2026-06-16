# AEB-001 ATR Expansion and False-Breakout Boundary

Status: ACTIVE_WINDOW_REVIVAL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current research boundary for `AEB-001`.

`AEB-001` means **ATR / True Range expansion breakout revival**, not a broad
ATR breakout system. The only preserved branch is the short-window
`aeb_atr24_equity_expansion_long_48h` branch over Binance 2026 equity-like
perpetuals.

This is research-only. It is not a StrategyGroup handoff, runtime registry,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Evidence |
| --- | --- |
| Replay script | `scripts/run_aeb_atr_expansion_breakout_replay.py` |
| Replay data | Cached Binance 1h futures klines and funding rows |
| Universe | Binance 2026 equity/ETF, precious-metal, and industrial-metal perpetuals |
| Signal discipline | Closed 1h signal candle, next 1h open entry |
| Cost model | `0.30%` round trip plus funding over holding window |
| Raw signals | `1558` |
| Accepted events | `158` |
| Rejected events | `1400` |
| Rules with accepted events | `4` |
| Best preserved branch | `aeb_atr24_equity_expansion_long_48h` |
| Preserved branch events / symbols | `71` events across `22` symbols |
| Preserved branch full 2x | `2.502514%` |
| Preserved branch best 30d 2x | `218.708454%` |
| Preserved branch best 60d 2x | `76.706965%` |
| Preserved branch best 90d 2x | `31.950523%` |
| Preserved branch DD 2x | `-67.294342%` |
| Preserved branch 2x / 5x proxy liquidation | `0 / 0` |

## Strategy Semantics

The preserved semantic is:

```text
ATR14 expands versus the recent ATR regime
-> price breaks the prior 24h upper channel
-> Binance equity-like perpetual attempts a 48h continuation burst
-> the result is evaluated as a 30d revival window, not a broad always-on strategy
```

The strategy is not:

```text
broad ATR breakout
regular-session equity breakout
failed-breakout short system
precious-metal breakdown short system
industrial-metal breakout system
high-leverage volatility expansion system
```

## Rule Boundary

| Rule | Events | Full 2x | Best 30d 2x | Best 90d 2x | DD 2x | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `aeb_atr24_equity_expansion_long_48h` | `71` | `2.502514%` | `218.708454%` | `31.950523%` | `-67.294342%` | Preserve as 30d revival only. |
| `aeb_regular_equity_atr_breakout_long_24h` | `20` | `-39.721333%` | `1.884009%` | `1.884009%` | `-40.835989%` | Negative. Do not handoff. |
| `aeb_precious_atr_breakdown_short_48h` | `22` | `-17.601520%` | `25.265220%` | `12.227539%` | `-45.560457%` | PMR support/boundary evidence only. |
| `aeb_failed_atr_breakout_short_48h` | `45` | `-77.105587%` | `63.035122%` | `37.602007%` | `-84.192061%` | False-breakout negative evidence. |

## Window Boundary

The strongest AEB evidence is a short-window burst, not durable persistence.

| Month | Events | 1x Return | 2x Return | 3x Return | 5x Return |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-12 | `1` | `2.853972%` | `5.707944%` | `8.561916%` | `14.269860%` |
| 2026-01 | `6` | `9.974350%` | `16.783334%` | `20.752039%` | `21.414951%` |
| 2026-02 | `10` | `-8.773617%` | `-22.176117%` | `-38.232023%` | `-71.262631%` |
| 2026-03 | `32` | `30.671555%` | `58.463409%` | `78.239016%` | `76.634107%` |
| 2026-04 | `38` | `-45.968090%` | `-75.048565%` | `-90.599422%` | `-100.000000%` |
| 2026-05 | `46` | `-18.507348%` | `-47.821234%` | `-77.162414%` | `-100.000000%` |
| 2026-06 | `25` | `-19.761446%` | `-41.193252%` | `-60.752651%` | `-87.478548%` |

Current interpretation:

1. `AEB-001` captures a **March 2026 volatility expansion burst**.
2. The April to June sequence is strongly negative.
3. The 30d right-tail window is worth preserving, but the 60d / 90d decay
   blocks handoff.
4. High leverage amplifies the decay; `5x` remains disabled and `3x` is
   stress-only.

## Symbol Concentration

The preserved ATR24 branch is equity-like only. The largest positive 1x
contributions are concentrated in a small set of symbols.

| Symbol | Events | Net 1x Contribution |
| --- | ---: | ---: |
| `CRCLUSDT` | `5` | `37.853583%` |
| `INTCUSDT` | `10` | `27.567262%` |
| `SNDKUSDT` | `3` | `16.481950%` |
| `MUUSDT` | `3` | `14.029553%` |
| `CBRSUSDT` | `1` | `7.505393%` |
| `NVDAUSDT` | `3` | `3.757225%` |

Largest adverse branch examples include `PLTRUSDT`, `COINUSDT`, `MSTRUSDT`,
`MSFTUSDT`, `ORCLUSDT`, and `CSCOUSDT`. This means AEB cannot be promoted
without a signal-time quality filter and symbol/session/fill facts.

## Asset Role Boundary

| Asset role | Evidence | Decision |
| --- | --- | --- |
| Equity-like perpetuals | Preserved branch has `71` events and best 30d 2x `218.708454%`, but broad category full 2x is `-88.880979%`. | Preserve only the narrow ATR24 branch. |
| Precious metals | Category full 2x is positive, but the AEB precious breakdown rule itself is negative. | Use as PMR boundary/support evidence only. |
| Industrial metals | Only `3` accepted events in the replay. | Context only. |

## RequiredFacts Boundary

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `atr_true_range_state` | True Range components, ATR period, smoothing method, and closed-candle timestamp. | No signal. |
| `atr_expansion_ratio_state` | ATR14 versus recent ATR regime and ATR percentile rank. | No signal. |
| `atr_breakout_quality_state` | Prior 24h upper-channel break distance, candle body, and trend alignment. | No signal. |
| `aeb_window_decay_state` | 30d / 60d / 90d and monthly attribution state. | Block handoff; observe-only research. |
| `aeb_false_breakout_disable_state` | Signal-time evidence that avoids failed upper-breakout short traps. | Block handoff. |
| `aeb_asset_role_state` | Equity-like, precious-metal, and industrial-metal role split. | Block handoff. |
| `tradfi_session_gap_state` | 24/7 Binance product behavior versus underlying market sessions. | Block armed observation. |
| `fill_gap_slippage_state` | Next-open gap, spread, and slippage sensitivity. | Block armed observation. |
| `real_exchange_margin_liquidation_model` | Real margin and liquidation model for leveraged interpretation. | `2x` research only; `3x` stress only; `5x` disabled. |

## Sample Boundary Packet

```json
{
  "strategy_id": "AEB-001",
  "status": "window_revival_not_handoff",
  "preserved_branch": "aeb_atr24_equity_expansion_long_48h",
  "supported_symbols_role": "binance_2026_equity_like_perpetuals_only",
  "supported_side": "long",
  "default_mode": "observe_only",
  "signal_ready": false,
  "reason": "short_window_right_tail_exists_but_60d_90d_decay_and_false_breakout_risk_block_handoff",
  "blocked_branches": [
    "aeb_regular_equity_atr_breakout_long_24h",
    "aeb_precious_atr_breakdown_short_48h",
    "aeb_failed_atr_breakout_short_48h"
  ],
  "required_missing_before_handoff": [
    "aeb_false_breakout_disable_state",
    "aeb_window_decay_state",
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

## Upgrade Conditions

`AEB-001` can move from research candidate to handoff discussion only if all of
the following improve:

1. The 30d burst extends into materially stronger 60d / 90d persistence.
2. Failed-breakout and whipsaw cases have a prefix-safe signal-time disable
   classifier.
3. The branch remains valid after product/session/fill/gap review.
4. Equity-like product availability is current, not only cached replay history.
5. Real exchange margin and liquidation behavior is attached.
6. `5x` remains disabled and `3x` remains stress-only unless separate margin
   evidence proves otherwise.

## Current Decision

Keep `AEB-001` in the strategy cabinet as:

```text
research_candidate
observe_only
window-revival vocabulary
not handoff-ready
```

The useful idea is **ATR expansion as a short-window right-tail revival handle**.
The current blocker is that broad ATR expansion and false-breakout variants
destroy the full sequence.
