# TRIX-001 Thin Sample and Concentration Boundary

Status: ACTIVE_RIGHT_TAIL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current boundary for `TRIX-001` triple-EMA momentum
research.

It is research-only. It is not a StrategyGroup handoff, runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Current Evidence |
| --- | --- |
| Candidate packet | `candidate-packets/TRIX-001-triple-ema-momentum-packet.md` |
| Replay report | `trix-triple-ema-replay/trix-triple-ema-summary.md` |
| Raw / accepted events | `7823` raw signals, `181` accepted events |
| Main useful branch | `trix_zero_cross_long_72h` |
| Main branch sample | `8` events across `7` symbols |
| Main branch category split | `7` equity-like perpetual events and `1` industrial-metal perpetual event |
| Main branch full 2x | `117.088679%` |
| Main branch best 90d 2x | `121.251707%` |
| Main branch max DD 2x | `-1.881580%` |
| Main branch proxy liquidation | `0` 2x events and `0` 5x events |
| Current cabinet status | `right_tail_candidate` |
| Current handoff status | No handoff pack. Not ready for main-control runtime intake. |

## Strategy Semantics

`TRIX-001` should be read as a **triple-EMA zero-cross acceleration** lane.

The preserved semantic is:

```text
TRIX crosses from negative to positive
-> smoothed momentum regime turns up
-> short 72h long follow-through attempt
```

The preserved semantic is not:

```text
broad TRIX positive persistence
simple TRIX signal-line reclaim
short-side TRIX reversal
always-on TRIX momentum system
high-leverage TRIX acceleration
generic equity or metal trend strategy
```

## Branch Boundary

| Branch | Current Decision | Reason |
| --- | --- | --- |
| `trix_zero_cross_long_72h` | Preserve as thin-sample right-tail review branch. | Positive full 2x, best-90d 2x above `100%`, low DD, and `0/0` 2x/5x proxy liquidation events. |
| `trix_signal_reclaim_long_48h` | Disable as primary branch. | Full 2x is slightly negative and DD 2x reaches `-43.726354%`. |
| `trix_positive_persistence_long_72h` | Disable as primary branch. | Full 2x is `-91.838583%`, DD 2x is `-92.508550%`, and 5x proxy liquidation appears. |
| `trix_regular_signal_long_24h` | Ignore until sample improves. | Only `1` accepted event. |
| `trix_zero_cross_short_72h` | Disable as primary branch. | Full 2x is `-5.878421%` and best-window evidence is weak. |
| `trix_negative_persistence_short_72h` | Window-revival only, not current short strategy. | Best-90d 2x clears `100%`, but full 2x is `-94.451776%`, DD 2x is `-97.993223%`, and 5x proxy liquidation appears. |

## Concentration Review

The useful `trix_zero_cross_long_72h` branch is too small to hand off.

| Concentration Fact | Evidence |
| --- | --- |
| Event count | `8` accepted events |
| Symbol count | `7` symbols |
| Positive contribution concentration | `INTCUSDT` contributes two accepted events and the largest combined net 1x contribution. |
| Largest single winner | `CRCLUSDT` contributes a large positive event with net 1x `15.140757%`. |
| Negative / weak events | `COINUSDT`, `EWYUSDT`, and `COPPERUSDT` are negative in the accepted lead branch. |
| Session split | Only `2` of the `8` lead events occur in regular-session rows. |

The current lead branch may describe a real short-window momentum turn, but it
is not yet robust enough to become a StrategyGroup handoff or armed-observation
candidate.

## Monthly Context

The all-rule monthly attribution warns against broad TRIX activation.

| Month | Accepted Events | 2x Return |
| --- | ---: | ---: |
| `2025-12` | `2` | `4.764596%` |
| `2026-01` | `12` | `38.166219%` |
| `2026-02` | `33` | `-86.245417%` |
| `2026-03` | `38` | `-83.269888%` |
| `2026-04` | `39` | `-73.711118%` |
| `2026-05` | `42` | `-24.723185%` |
| `2026-06` | `15` | `45.595638%` |

This is not evidence of an always-on TRIX family. It is evidence that the
zero-cross branch deserves preservation while broad TRIX rows become disable
facts.

## RequiredFacts Boundary

| RequiredFact | Use | Missing Behavior |
| --- | --- | --- |
| `trix_state` | TRIX value, signal line, histogram, deltas, parameters, and closed-candle timestamp. | `no_signal` |
| `trix_zero_cross_quality_state` | Confirms negative-to-positive zero-cross and rejects weak reclaim-only states. | `no_signal` |
| `trix_thin_sample_state` | Tracks event count, symbol count, and sample sufficiency. | `no_handoff_candidate` |
| `trix_symbol_concentration_state` | Flags INTC/CRCL-style concentration and weak symbols. | `no_handoff_candidate` |
| `trix_persistence_failure_state` | Blocks broad positive-persistence reuse. | `observe_only` |
| `trix_short_side_failure_state` | Blocks short-side TRIX symmetry reuse. | `observe_only` |
| `trix_window_decay_state` | Separates favorable short windows from broad monthly decay. | `no_handoff_candidate` |
| `tradfi_product_universe_state` | Confirms current Binance product availability and instrument type. | `no_handoff_candidate` |
| `tradfi_session_gap_state` | Separates underlying-market session from 24/7 perpetual trading. | `no_handoff_candidate` |
| `fill_gap_slippage_state` | Covers next-open gap, spread, and slippage behavior. | `no_handoff_candidate` |
| `real_exchange_margin_liquidation_model` | Replaces proxy liquidation with real margin behavior. | `no_handoff_candidate` |

## Sample Boundary Packet

```json
{
  "strategy_id": "TRIX-001",
  "status": "right_tail_candidate_not_handoff",
  "decision": "no_handoff_candidate",
  "preserved_branch": "trix_zero_cross_long_72h",
  "blocked_branches": [
    "trix_signal_reclaim_long_48h",
    "trix_positive_persistence_long_72h",
    "trix_regular_signal_long_24h",
    "trix_zero_cross_short_72h",
    "trix_negative_persistence_short_72h"
  ],
  "reason": "zero_cross_long_has_right_tail_but_sample_size_concentration_and_broad_trix_decay_block_handoff",
  "missing_facts": [
    "trix_thin_sample_state",
    "trix_symbol_concentration_state",
    "trix_window_decay_state",
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

`TRIX-001` can move toward an observe-only handoff draft only if all of the
following become true:

1. The zero-cross long branch expands beyond the current `8` accepted events
   without losing full-sequence behavior.
2. Symbol concentration is either reduced or explicitly bounded in a small
   universe.
3. A signal-time zero-cross quality filter preserves the right-tail branch
   without using post-entry labels.
4. Monthly / rolling-window decay facts can emit `no_signal` or
   `no_handoff_candidate` during weak TRIX regimes.
5. Product availability, session gap, mark/funding, fill/gap, and real margin
   facts are attached.
6. `5x` remains disabled and `3x` remains stress-only until real margin and
   liquidation evidence improve.

## Current Decision

Keep `TRIX-001` in the Strategy Cabinet as `right_tail_candidate`.

Do not create a StrategyGroup handoff pack in this batch. The next useful work
is sample expansion, symbol-concentration review, signal-time zero-cross
quality hardening, and live-like product, session, fill, and margin fact
attachment.
