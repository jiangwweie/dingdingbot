# CCI-001 Asset Role and Failure Boundary

Status: ACTIVE_WINDOW_REVIVAL_BOUNDARY_NOT_HANDOFF
Last updated: 2026-06-16

## Scope

This document fixes the current boundary for `CCI-001` Commodity Channel Index
trend escape / failure research.

It is research-only. It is not a StrategyGroup handoff, runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Known Facts

| Fact | Current Evidence |
| --- | --- |
| Candidate packet | `candidate-packets/CCI-001-trend-escape-packet.md` |
| Base replay report | `cci-trend-escape-replay/cci-trend-escape-summary.md` |
| Classifier report | `cci-asset-session-classifier/cci-asset-session-classifier-summary.md` |
| Base raw / accepted events | `7898` raw signals, `212` accepted events |
| Classifier count | `12` fixed signal-time classifiers |
| Cleanest branch | `cci_failure_short_precious_metal_only` |
| Cleanest branch sample | `77` events across `4` precious-metal symbols |
| Cleanest branch full 2x | `72.496535%` |
| Cleanest branch best 90d 2x | `105.400734%` |
| Cleanest branch second-half 2x | `3.882768%` |
| Cleanest branch max DD 2x | `-74.614868%` |
| Cleanest branch 2x proxy liquidation | `0` |
| Current cabinet status | `research_candidate` |
| Current handoff status | No handoff pack. Not ready for main-control runtime intake. |

## Strategy Semantics

`CCI-001` should be read as an **asset-role split revival** lane.

The preserved semantic is:

```text
CCI moves above +100
-> CCI then fails / rolls over
-> precious-metal perpetual short review lane
-> explicit asset role and drawdown controls required
```

The preserved semantic is not:

```text
generic CCI overbought short
generic CCI +100 breakout long
generic CCI -100 reclaim long
equity CCI short strategy
industrial-metal CCI strategy
always-on CCI oscillator system
```

## Branch Boundary

| Branch | Current Decision | Reason |
| --- | --- | --- |
| `cci_failure_short_precious_metal_only` | Preserve as window-revival branch. | Positive full 2x, best-90d 2x above `100%`, second-half still positive, and `0` 2x proxy liquidation events. |
| `cci_reclaim_long_equity_weekday` | Window-revival only. | Best-90d 2x is very large, but full 2x, second-half 2x, and DD are all unacceptable. |
| `cci_reclaim_long_equity_clean_impulse` | Window-revival only. | Large best-window evidence but full-sequence and second-half collapse. |
| `cci_failure_short_equity_regular_proxy` | Window-revival only. | Best-window evidence exists, but full 2x is `-95.853497%` and DD is severe. |
| `cci_escape_long_equity_weekday` | Window-revival only. | Best-window evidence exists, but full 2x is `-76.702846%`. |
| `cci_failure_short_baseline_reslot` | Disable as primary branch. | Generic failure short full 2x is `-98.970166%`. |
| `cci_escape_long_precious_metal_only` | Disable as primary branch. | Precious-metal escape long full 2x is `-94.393589%`. |
| `cci_reclaim_long_industrial_metal_only` | Support / negative evidence only. | Single-symbol industrial-metal behavior does not generalize. |

## Asset Role Review

The current useful lane is precious-metal specific, not CCI-wide.

| Review Fact | Evidence |
| --- | --- |
| Lead classifier | `cci_failure_short_precious_metal_only` |
| Symbols | `XAGUSDT`, `XAUUSDT`, `XPDUSDT`, `XPTUSDT` |
| Session split | `23` regular-session rows and `54` off-session rows |
| Largest symbol contributor | `XAGUSDT` contributes net 1x `36.000028%` across `18` events. |
| Weakest symbol contributor | `XPDUSDT` contributes net 1x `-0.471512%` across `26` events. |
| Largest single winner | `XAGUSDT` on `2026-01-30` contributes net 1x `21.862491%`. |
| Largest single loss | `XPTUSDT` on `2026-02-24` contributes net 1x `-12.195536%`. |
| Broad baseline warning | Base `cci_100_failure_short_72h` full 2x is `-90.019611%` with DD 2x `-93.634072%`. |

## Monthly Context

The lead classifier has positive full 2x, but its month profile is not stable
enough for handoff.

| Month | Lead Events | Approx 2x Net From Event Sum |
| --- | ---: | ---: |
| `2025-12` | `1` | `1.874148%` |
| `2026-01` | `1` | `43.724982%` |
| `2026-02` | `12` | `-22.331368%` |
| `2026-03` | `21` | `75.903230%` |
| `2026-04` | `17` | `-24.164338%` |
| `2026-05` | `16` | `-34.445740%` |
| `2026-06` | `9` | `54.348116%` |

This supports a bounded right-tail research lane, not a stable always-on
strategy.

## RequiredFacts Boundary

| RequiredFact | Use | Missing Behavior |
| --- | --- | --- |
| `cci_state` | CCI period, typical price, moving average, mean deviation, CCI value, and closed-candle timestamp. | `no_signal` |
| `cci_threshold_cross_state` | Separates +100 escape, +100 failure, -100 reclaim, zero reclaim, and breakdown facts. | `no_signal` |
| `cci_asset_role_state` | Separates equity, precious-metal, and industrial-metal behavior. | `no_handoff_candidate` |
| `cci_precious_metal_failure_state` | Captures +100 failure short over XAG/XAU/XPD/XPT only. | `no_signal` |
| `cci_failure_quality_state` | Requires failure quality, CCI delta, bounded prior move, and volume/session context. | `no_handoff_candidate` |
| `cci_reclaim_disable_state` | Blocks equity reclaim and generic reclaim rows when full-sequence decay appears. | `observe_only` |
| `cci_window_decay_state` | Separates March/June revival from February/April/May weakness. | `no_handoff_candidate` |
| `tradfi_offhour_mark_index_state` | Handles 24/7 metal perpetuals outside underlying market or reference-market hours. | `no_handoff_candidate` |
| `fill_gap_slippage_state` | Covers next-open gap, spread, and slippage behavior. | `no_handoff_candidate` |
| `real_exchange_margin_liquidation_model` | Replaces proxy liquidation with real margin behavior. | `no_handoff_candidate` |

## Sample Boundary Packet

```json
{
  "strategy_id": "CCI-001",
  "status": "window_revival_not_handoff",
  "decision": "no_handoff_candidate",
  "preserved_branch": "cci_failure_short_precious_metal_only",
  "blocked_branches": [
    "cci_100_escape_long_48h",
    "cci_zero_reclaim_long_48h",
    "cci_minus100_reclaim_long_72h",
    "cci_minus100_breakdown_short_48h",
    "cci_100_failure_short_72h",
    "cci_regular_escape_long_24h",
    "cci_failure_short_equity_only",
    "cci_escape_long_precious_metal_only",
    "cci_reclaim_long_industrial_metal_only"
  ],
  "reason": "precious_metal_failure_short_has_window_revival_edge_but_drawdown_asset_role_offhour_and_margin_facts_block_handoff",
  "missing_facts": [
    "cci_asset_role_state",
    "cci_precious_metal_failure_state",
    "cci_failure_quality_state",
    "cci_window_decay_state",
    "tradfi_offhour_mark_index_state",
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

`CCI-001` can move toward an observe-only handoff draft only if all of the
following become true:

1. Precious-metal failure short remains isolated from generic CCI failure short.
2. A signal-time failure-quality classifier reduces drawdown without using
   post-entry labels.
3. XAG/XAU/XPD/XPT role split and symbol concentration are explicit.
4. Monthly / rolling-window decay facts can emit `no_signal` or
   `no_handoff_candidate` during weak CCI regimes.
5. Product availability, off-hour mark/index, fill/gap, and real margin facts
   are attached.
6. `5x` remains disabled and `3x` remains stress-only until real margin and
   liquidation evidence improve.

## Current Decision

Keep `CCI-001` in the Strategy Cabinet as `research_candidate`.

Do not create a StrategyGroup handoff pack in this batch. The next useful work
is precious-metal failure-quality hardening, asset-role decay review,
off-hour mark/index fact design, and live-like fill and real-margin attachment.
