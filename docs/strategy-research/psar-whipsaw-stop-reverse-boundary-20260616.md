# PSAR-001 Whipsaw and Stop-Reverse Boundary

Status: ACTIVE_RIGHT_TAIL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current boundary for `PSAR-001` Parabolic SAR
stop-and-reverse research.

It is research-only. It is not a StrategyGroup handoff, runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Current Evidence |
| --- | --- |
| Candidate packet | `candidate-packets/PSAR-001-stop-reverse-packet.md` |
| Replay report | `psar-stop-reverse-replay/psar-stop-reverse-summary.md` |
| Raw / accepted events | `14511` raw signals, `205` accepted events |
| Main useful branch | `psar_flip_long_48h` |
| Main branch sample | `32` events across `16` symbols |
| Main branch category split | `19` equity-like perpetual events, `12` precious-metal perpetual events, and `1` industrial-metal perpetual event |
| Main branch full 2x | `33.292646%` |
| Main branch best 90d 2x | `124.602670%` |
| Main branch max DD 2x | `-57.821226%` |
| Main branch proxy liquidation | `0` 2x events and `0` 5x events |
| Broad equity category full 2x | `-99.957002%` |
| Current cabinet status | `right_tail_candidate` |
| Current handoff status | No handoff pack. Not ready for main-control runtime intake. |

## Strategy Semantics

`PSAR-001` should be read as a **bullish flip burst** lane.

The preserved semantic is:

```text
Parabolic SAR flips from bearish to bullish
-> immediate 48h long burst attempt
-> exit before broad continuation decay dominates
```

The preserved semantic is not:

```text
always-in-market PSAR stop-and-reverse system
broad bullish continuation after PSAR is already below price
bearish flip short strategy
precious-metal standalone short
high-leverage trend follower
generic equity trend-following strategy
```

## Branch Boundary

| Branch | Current Decision | Reason |
| --- | --- | --- |
| `psar_flip_long_48h` | Preserve as right-tail review branch. | Best-90d 2x clears `100%`, full 2x is positive, and proxy liquidation is `0/0`; but DD remains too high for handoff. |
| `psar_continuation_long_72h` | Disable as primary branch. | Full 2x is `-95.136259%`, DD 2x is `-95.873733%`, and 5x proxy liquidation appears. |
| `psar_regular_flip_long_24h` | Ignore until sample improves. | Only `2` accepted events and negative full 2x. |
| `psar_flip_short_48h` | Disable as primary branch. | Full 2x is `-40.482886%` and DD remains severe. |
| `psar_continuation_short_72h` | Disable as primary branch. | Full 2x is `-99.470914%`, DD 2x is `-99.680350%`, and both 2x and 5x proxy liquidation appear. |
| `psar_precious_metal_short_48h` | Support / negative evidence only. | Sample is tiny, full 2x is negative, and best-window evidence is not enough for strategy semantics. |

## Whipsaw and Concentration Review

The useful `psar_flip_long_48h` branch is not ready for handoff because the
path still contains severe adverse events and large contribution concentration.

| Review Fact | Evidence |
| --- | --- |
| Event count | `32` accepted events |
| Symbol count | `16` symbols |
| Session split | Only `3` of `32` lead events occur in regular-session rows. |
| Largest symbol contribution | `SNDKUSDT` contributes two accepted events and net 1x `22.401890%`. |
| Largest single winner | `SNDKUSDT` on `2026-05-04` contributes net 1x `20.656538%`. |
| Largest single loss | `HOODUSDT` on `2026-02-10` contributes net 1x `-18.480414%` with path MAE `-19.114780%`. |
| Broad category warning | Equity-like category full 2x is `-99.957002%`; the lead branch cannot be generalized to all PSAR equity signals. |

The current lead branch may describe short-lived post-flip burst behavior, but
it does not validate a continuous PSAR stop-and-reverse system.

## Monthly Context

The all-rule monthly attribution warns against always-on PSAR activation.

| Month | Accepted Events | 2x Return |
| --- | ---: | ---: |
| `2025-12` | `2` | `1.879669%` |
| `2026-01` | `12` | `164.769472%` |
| `2026-02` | `39` | `-99.227722%` |
| `2026-03` | `48` | `-91.607382%` |
| `2026-04` | `43` | `-60.764179%` |
| `2026-05` | `46` | `-22.964952%` |
| `2026-06` | `15` | `-64.777337%` |

This is not evidence of broad PSAR alpha. It is evidence that a narrow bullish
flip burst deserves preservation while continuation and short-side PSAR become
disable facts.

## RequiredFacts Boundary

| RequiredFact | Use | Missing Behavior |
| --- | --- | --- |
| `psar_state` | PSAR value, side, flip flag, run length, acceleration settings, and closed-candle timestamp. | `no_signal` |
| `psar_flip_quality_state` | Confirms first bullish flip and rejects weak or late flips. | `no_signal` |
| `psar_whipsaw_disable_state` | Blocks chop, immediate adverse movement, and poor range/volume context. | `no_handoff_candidate` |
| `psar_continuation_failure_state` | Blocks continuation and always-in-market stop-reverse reuse. | `observe_only` |
| `psar_short_side_failure_state` | Blocks bearish flip and bearish continuation reuse. | `observe_only` |
| `psar_window_decay_state` | Separates January / best-window evidence from broad monthly decay. | `no_handoff_candidate` |
| `psar_symbol_concentration_state` | Tracks SNDK/MU/XAG winner concentration and HOOD-style adverse events. | `no_handoff_candidate` |
| `tradfi_product_universe_state` | Confirms current Binance product availability and instrument type. | `no_handoff_candidate` |
| `tradfi_session_gap_state` | Separates underlying-market session from 24/7 perpetual trading. | `no_handoff_candidate` |
| `fill_gap_slippage_state` | Covers next-open gap, spread, and slippage behavior. | `no_handoff_candidate` |
| `real_exchange_margin_liquidation_model` | Replaces proxy liquidation with real margin behavior. | `no_handoff_candidate` |

## Sample Boundary Packet

```json
{
  "strategy_id": "PSAR-001",
  "status": "right_tail_candidate_not_handoff",
  "decision": "no_handoff_candidate",
  "preserved_branch": "psar_flip_long_48h",
  "blocked_branches": [
    "psar_continuation_long_72h",
    "psar_regular_flip_long_24h",
    "psar_flip_short_48h",
    "psar_continuation_short_72h",
    "psar_precious_metal_short_48h"
  ],
  "reason": "bullish_flip_long_has_best_window_right_tail_but_drawdown_whipsaw_and_broad_stop_reverse_decay_block_handoff",
  "missing_facts": [
    "psar_flip_quality_state",
    "psar_whipsaw_disable_state",
    "psar_window_decay_state",
    "psar_symbol_concentration_state",
    "tradfi_product_universe_state",
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

`PSAR-001` can move toward an observe-only handoff draft only if all of the
following become true:

1. A signal-time bullish-flip quality filter reduces whipsaw and DD without
   using post-entry labels.
2. Broad PSAR continuation and short-side rows remain explicitly disabled.
3. Monthly / rolling-window decay facts can emit `no_signal` or
   `no_handoff_candidate` during weak PSAR regimes.
4. Symbol concentration and extreme adverse event handling are explicit.
5. Product availability, session gap, mark/funding, fill/gap, and real margin
   facts are attached.
6. `5x` remains disabled and `3x` remains stress-only until real margin and
   liquidation evidence improve.

## Current Decision

Keep `PSAR-001` in the Strategy Cabinet as `right_tail_candidate`.

Do not create a StrategyGroup handoff pack in this batch. The next useful work
is bullish-flip quality hardening, whipsaw disable design, window-decay review,
and live-like product, session, fill, and margin fact attachment.
