# EFI-001 Drawdown and Disable Boundary

Status: ACTIVE_RIGHT_TAIL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current boundary for `EFI-001` Elder Force Index
exhaustion-reversal research.

It is research-only. It is not a StrategyGroup handoff, runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Current Evidence |
| --- | --- |
| Candidate packet | `candidate-packets/EFI-001-elder-force-index-packet.md` |
| Replay report | `efi-elder-force-index-replay/efi-elder-force-index-summary.md` |
| Raw / accepted events | `16472` raw signals, `225` accepted events |
| Candidate pool 2x | Full 2x `58.375915%`, best 90d 2x `317.778982%`, max DD 2x `-91.431725%` |
| Candidate pool leverage stress | Full 3x `-69.219079%`, full 5x `-100.000000%`, 5x proxy liquidation events `2` |
| Main useful branch | `efi_negative_exhaustion_reversal_long_72h` |
| Main branch evidence | Events `77`, full 2x `3453.608359%`, best 90d 2x `1063.134074%`, DD 2x `-55.373632%`, 2x/5x proxy `0/0` |
| Current cabinet status | `right_tail_candidate` |
| Current handoff status | No handoff pack. Not ready for main-control runtime intake. |

## Strategy Semantics

`EFI-001` should be read as a **price-volume force exhaustion** lane.

The preserved semantic is:

```text
large negative price-volume force
-> exhaustion / forced selling pressure
-> next-stage long reversal attempt
```

The preserved semantic is not:

```text
simple positive impulse long
broad Force Index momentum
distribution short
positive exhaustion short
precious-metal standalone strategy
high-leverage acceleration strategy
```

## Branch Boundary

| Branch | Current Decision | Reason |
| --- | --- | --- |
| `efi_negative_exhaustion_reversal_long_72h` | Preserve as right-tail review branch. | Very strong branch-level right tail with positive full 2x and `0/0` 2x/5x proxy liquidation events. |
| `efi_positive_exhaustion_short_48h` | Window-revival only. | Best 90d 2x clears a local window, but full 2x is negative and DD remains severe. |
| `efi_distribution_short_48h` | Disable as primary branch. | Negative full 2x, severe DD, and 5x proxy risk. |
| `efi_positive_impulse_long_48h` | Disable as primary branch. | Simple impulse does not reproduce the useful exhaustion-reversal edge. |
| `efi_regular_equity_impulse_long_24h` | Disable as primary branch. | Insufficient sample and negative local result. |
| `efi_zero_reclaim_long_48h` | Disable as primary branch. | Insufficient sample and negative local result. |

## Why This Is Not A Handoff

| Blocker | Meaning |
| --- | --- |
| Candidate-level drawdown | The candidate pool reaches max DD 2x `-91.431725%`; a strong branch cannot hide the pool-level path risk. |
| High-leverage breakdown | Full 3x and 5x break down; 5x is disabled and 3x remains stress-only vocabulary. |
| Short-side failure | Short-side symmetry fails; short rows cannot be reused as executable short strategy semantics. |
| Product/session risk | Binance 2026 equity-like and metal products need current availability, session gap, and product handling before runtime intake. |
| Fill/gap risk | Next-open replay needs live-like spread, gap, and fill facts before armed observation. |
| Real margin missing | Proxy liquidation is not enough for live leverage interpretation. |
| Disable classifier missing | The useful negative-exhaustion branch still needs a signal-time disable classifier that reduces full-path drawdown without post-entry labels. |

## RequiredFacts Boundary

| RequiredFact | Use | Missing Behavior |
| --- | --- | --- |
| `efi_state` | Raw Force Index, smoothed EFI values, normalization basis, parameters, and closed-candle timestamp. | `no_signal` |
| `efi_price_volume_force_state` | Price-change times volume pressure state. | `no_signal` |
| `efi_negative_exhaustion_reversal_state` | Negative-force exhaustion and long-reversal setup state. | `no_signal` |
| `efi_positive_impulse_failure_state` | Blocks simple positive-impulse long reuse. | `observe_only` |
| `efi_distribution_short_failure_state` | Blocks distribution and short-side symmetry reuse. | `observe_only` |
| `efi_window_decay_state` | Monthly and rolling-window decay state. | `no_handoff_candidate` |
| `efi_symbol_concentration_state` | CRCL/MSTR/PLTR/PAYP/HOOD concentration state. | `no_handoff_candidate` |
| `tradfi_product_universe_state` | Binance 2026 equity/metal product handling. | `no_handoff_candidate` |
| `tradfi_session_gap_state` | Underlying-market session versus 24/7 product behavior. | `no_handoff_candidate` |
| `fill_gap_slippage_state` | Next-open slippage, gap, and spread behavior. | `no_handoff_candidate` |
| `real_exchange_margin_liquidation_model` | Real margin and liquidation stress model. | `no_handoff_candidate` |

## Sample Boundary Packet

```json
{
  "strategy_id": "EFI-001",
  "status": "right_tail_candidate_not_handoff",
  "decision": "no_handoff_candidate",
  "preserved_branch": "efi_negative_exhaustion_reversal_long_72h",
  "blocked_branches": [
    "efi_positive_impulse_long_48h",
    "efi_distribution_short_48h",
    "efi_positive_exhaustion_short_48h",
    "efi_regular_equity_impulse_long_24h",
    "efi_zero_reclaim_long_48h"
  ],
  "reason": "negative_force_exhaustion_long_has_right_tail_but_candidate_drawdown_and_live_facts_block_handoff",
  "missing_facts": [
    "efi_window_decay_state",
    "efi_symbol_concentration_state",
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

`EFI-001` can move toward a handoff draft only if all of the following become
true:

1. The negative-exhaustion long branch is isolated by signal-time facts, not
   post-entry labels.
2. The disable classifier materially reduces candidate-level drawdown without
   deleting the right-tail window.
3. Monthly / rolling-window decay facts are explicit enough to produce
   `no_signal` or `no_handoff_candidate` during weak regimes.
4. Symbol concentration is controlled or intentionally bounded in the handoff
   universe.
5. Current product availability, session gap, mark/funding, fill/gap, and real
   margin facts are attached.
6. `5x` remains disabled and `3x` remains stress-only until real margin and
   liquidation evidence improve.

## Current Decision

Keep `EFI-001` in the Strategy Cabinet as `right_tail_candidate`.

Do not create a StrategyGroup handoff pack in this batch. The next useful work
is a signal-time disable classifier for `efi_negative_exhaustion_reversal_long_72h`
plus live-like product, session, fill, and margin fact attachment.
