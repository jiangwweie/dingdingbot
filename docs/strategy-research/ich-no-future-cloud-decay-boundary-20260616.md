# ICH-001 No-Future-Cloud and Decay Boundary

Status: ACTIVE_WINDOW_REVIVAL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current boundary for `ICH-001` Ichimoku cloud breakout
research.

It is research-only. It is not a StrategyGroup handoff, runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Current Evidence |
| --- | --- |
| Candidate packet | `candidate-packets/ICH-001-ichimoku-cloud-breakout-packet.md` |
| Replay report | `ichimoku-cloud-breakout-replay/ichimoku-cloud-breakout-summary.md` |
| Raw / accepted events | `2194` raw signals, `247` accepted events |
| Lookahead policy | Uses unshifted signal-time Senkou spans; does not use forward-projected cloud or Chikou activation. |
| Main useful branch | `ich_cloud_breakout_long_48h` |
| Main branch sample | `111` events across `34` symbols |
| Main branch full 2x | `-78.421778%` |
| Main branch best 90d 2x | `296.354715%` |
| Main branch max DD 2x | `-85.398509%` |
| Main branch 5x proxy liquidation | `3` events |
| Broad equity category full 2x | `-100.000000%` |
| Current cabinet status | `research_candidate` |
| Current handoff status | No handoff pack. Not ready for main-control runtime intake. |

## Strategy Semantics

`ICH-001` should be read as a **no-future-cloud breakout revival** lane.

The preserved semantic is:

```text
price closes above signal-time Ichimoku cloud
-> signal candle is closed
-> entry is next 1h open
-> review only short revival windows with explicit decay facts
```

The preserved semantic is not:

```text
using forward-projected Senkou values as entry facts
using Chikou span confirmation as entry fact
generic Ichimoku trend-following system
broad cloud-breakout alpha
cloud-breakdown short strategy
TK-cross standalone long strategy
Kijun reclaim/reject standalone strategy
```

## Branch Boundary

| Branch | Current Decision | Reason |
| --- | --- | --- |
| `ich_cloud_breakout_long_48h` | Preserve as window-revival vocabulary. | Best-90d 2x is very large, but full 2x is negative and DD is severe. |
| `ich_tk_cross_above_cloud_long_72h` | Support / negative evidence only. | Full 2x is `-21.800987%` and best-90d 2x is weak. |
| `ich_kumo_twist_momentum_long_72h` | Support / vocabulary only. | Full 2x is positive but sample is only `6` events and best-window evidence is below right-tail threshold. |
| `ich_kijun_reclaim_long_24h` | Disable as primary branch. | Full 2x is `-41.813738%` and best-window evidence is negative. |
| `ich_cloud_breakdown_short_48h` | Disable as primary branch. | Full 2x is `-100.000000%`, DD breaches `-100%`, and 2x/5x proxy liquidation appears. |
| `ich_kijun_reject_short_24h` | Support / negative evidence only. | Full 2x is slightly positive, but best-window evidence is below right-tail threshold and short-side semantics are not stable. |

## No-Future-Cloud Boundary

Ichimoku indicators are easy to misuse in replay because some common charting
views plot components forward or backward.

| Component | Runtime / Research Rule |
| --- | --- |
| `Senkou A/B` | Use only signal-time unshifted values. Forward-projected cloud values are not entry facts. |
| `Chikou` | Do not use as activation because it is plotted backward and can easily become a lookahead proxy. |
| `Tenkan / Kijun` | May be used as signal-time values only after candle close. |
| `Cloud top / bottom` | Must be derived from signal-time Senkou values, not chart-projected future locations. |
| Future path | May be used only for evaluation labels, not signal facts. |

Any future `ICH-001` replay or handoff proposal must state this policy
explicitly. A missing no-future-cloud policy should produce
`no_handoff_candidate`.

## Decay and Concentration Review

The useful branch has a striking April revival window, but the broader path is
not stable.

| Review Fact | Evidence |
| --- | --- |
| Event count | `111` lead-branch events |
| Symbol count | `34` lead-branch symbols |
| Session split | `30` regular-session rows and `81` off-session rows |
| Best month | `2026-04` all-rule 2x return is `138.676093%` |
| Weak months | `2026-01`, `2026-02`, `2026-03`, `2026-05`, and `2026-06` are negative in all-rule 2x attribution. |
| Largest lead-branch symbol contributor | `INTCUSDT` contributes net 1x `25.206891%` across `5` lead events. |
| Largest lead-branch drag | `XAGUSDT` contributes net 1x `-27.241954%` across `14` lead events. |
| Largest single lead-branch loss | `XAGUSDT` on `2026-01-28` contributes net 1x `-27.426998%` with path MAE `-33.149943%`. |

This is a revival vocabulary, not a StrategyGroup handoff candidate.

## Monthly Context

| Month | Accepted Events | 2x Return |
| --- | ---: | ---: |
| `2025-12` | `2` | `2.729833%` |
| `2026-01` | `9` | `-43.628508%` |
| `2026-02` | `43` | `-83.322286%` |
| `2026-03` | `55` | `-40.780940%` |
| `2026-04` | `54` | `138.676093%` |
| `2026-05` | `58` | `-100.000000%` |
| `2026-06` | `26` | `-75.153008%` |

The monthly profile supports the Owner's right-tail research goal because a
bounded window exists, but it does not support broad or always-on Ichimoku
activation.

## RequiredFacts Boundary

| RequiredFact | Use | Missing Behavior |
| --- | --- | --- |
| `ichimoku_cloud_state` | Tenkan, Kijun, signal-time Senkou A/B, cloud top/bottom, parameters, and closed-candle timestamp. | `no_signal` |
| `ichimoku_no_future_cloud_policy` | Proves no forward-projected cloud or Chikou activation is used. | `no_handoff_candidate` |
| `ichimoku_cloud_breakout_state` | Confirms closed-candle cloud breakout and next-open entry discipline. | `no_signal` |
| `ichimoku_cloud_breakout_disable_state` | Blocks weak months, high-MAE branches, and broad cloud-breakout decay. | `no_handoff_candidate` |
| `ichimoku_window_decay_state` | Separates April / best-window revival from full-sequence failure. | `no_handoff_candidate` |
| `ichimoku_component_role_state` | Separates TK cross, Kumo twist, Kijun reclaim/reject, and cloud breakout semantics. | `observe_only` |
| `ichimoku_short_side_failure_state` | Blocks cloud-breakdown short activation. | `observe_only` |
| `tradfi_product_universe_state` | Confirms current Binance product availability and instrument type. | `no_handoff_candidate` |
| `tradfi_session_gap_state` | Separates underlying-market session from 24/7 perpetual trading. | `no_handoff_candidate` |
| `fill_gap_slippage_state` | Covers next-open gap, spread, and slippage behavior. | `no_handoff_candidate` |
| `real_exchange_margin_liquidation_model` | Replaces proxy liquidation with real margin behavior. | `no_handoff_candidate` |

## Sample Boundary Packet

```json
{
  "strategy_id": "ICH-001",
  "status": "window_revival_not_handoff",
  "decision": "no_handoff_candidate",
  "preserved_branch": "ich_cloud_breakout_long_48h",
  "blocked_branches": [
    "ich_tk_cross_above_cloud_long_72h",
    "ich_kumo_twist_momentum_long_72h",
    "ich_kijun_reclaim_long_24h",
    "ich_cloud_breakdown_short_48h",
    "ich_kijun_reject_short_24h"
  ],
  "reason": "cloud_breakout_has_large_best_window_but_full_sequence_decay_drawdown_and_no_future_cloud_policy_block_handoff",
  "missing_facts": [
    "ichimoku_no_future_cloud_policy",
    "ichimoku_cloud_breakout_disable_state",
    "ichimoku_window_decay_state",
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

`ICH-001` can move toward an observe-only handoff draft only if all of the
following become true:

1. The no-future-cloud policy remains explicit in scripts, reports, and any
   future handoff packet.
2. A signal-time cloud-breakout disable classifier materially reduces
   full-sequence drawdown without deleting the right-tail window.
3. Component roles are separated: cloud breakout, TK cross, Kumo twist, Kijun
   reclaim/reject, and short-side breakdown must not be mixed.
4. Monthly / rolling-window decay facts can emit `no_signal` or
   `no_handoff_candidate` during weak Ichimoku regimes.
5. Product availability, session gap, mark/funding, fill/gap, and real margin
   facts are attached.
6. `5x` remains disabled and `3x` remains stress-only until real margin and
   liquidation evidence improve.

## Current Decision

Keep `ICH-001` in the Strategy Cabinet as `research_candidate`.

Do not create a StrategyGroup handoff pack in this batch. The next useful work
is no-future-cloud policy enforcement, cloud-breakout disable design,
window-decay review, and live-like product, session, fill, and margin fact
attachment.
