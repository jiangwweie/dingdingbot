# FBS-001 Derivatives Facts Readiness Split

Status: ACTIVE_P0_HANDOFF_HARDENING
Last updated: 2026-06-16

## Scope

This document hardens `FBS-001` for main-control review by separating
fresh, stale, and missing derivatives facts.

It is a research-only P0 supplement. It is not runtime admission, not a
FinalGate input, not an Operation Layer input, not a deploy request, not a
credential change, not an exchange write, not a live profile change, and not
an order-sizing default.

## Known Evidence

| Evidence | Current Value | Interpretation |
| --- | ---: | --- |
| `fbs_teq_extreme_negative_funding_long_72h` accepted events | `55` | Direct TEQ negative-funding squeeze lane has enough 2026 discovery evidence for observation review. |
| Direct full 2x | `1703.596239%` | Strong right-tail research score, not live execution performance. |
| Direct best-90d 2x | `1813.121179%` | Strong local window; still low-history and product-risk constrained. |
| Direct 2x drawdown | `-53.515312%` | Armed observation needs strict protection and stale-fact behavior. |
| 2x / 5x proxy liquidation events | `0` / `0` | Proxy only; does not replace exchange margin model. |
| Robustness filters preserving P1 support | `6` | Signal-time filters support the lane, but do not solve all facts. |
| 2026-06 monthly attribution | `-30.246266%` 2x | Recent month is negative; stale or weak facts should downshift. |

## Readiness Levels

| Readiness | Required Condition | Main-Control Meaning | Candidate Prepare |
| --- | --- | --- | --- |
| `fbs_derivatives_facts_fresh` | Funding, mark, premium/basis, OI, global long-short, top-trader ratio, and symbol rules are current inside the watcher freshness policy. | `FBS-001` can remain `armed_observation` if the signal packet is fresh and other account/protection facts pass. | Allowed by research semantics only; main control still owns runtime gates. |
| `fbs_derivatives_facts_partial` | Funding and mark are current, but OI or crowding ratios are absent or field-shape-only. | Keep observation, reduce confidence, and treat the packet as derivatives-stress context rather than full candidate prepare. | Block candidate prepare unless main control explicitly models the missing fact as non-required for the current lane. |
| `fbs_derivatives_facts_stale` | Funding, mark, OI, or crowding facts are outside the freshness window. | Degrade to `observe_only`; emit stale signal packet if a signal existed. | Block candidate prepare. |
| `fbs_derivatives_facts_missing` | Primary funding or mark facts are missing, or exchange symbol rules are missing. | No actionable FBS signal; keep only no-signal or missing-facts packet. | Block candidate prepare. |
| `fbs_margin_model_missing` | Real exchange margin/liquidation model is absent. | Keep 1x default and 2x research-only interpretation. | Block leverage promotion. |

## RequiredFacts Split

| RequiredFact | Fresh Behavior | Stale Behavior | Missing Behavior |
| --- | --- | --- | --- |
| `funding_rate_window` | Can evaluate FBS signal lane. | Emit stale packet and block candidate prepare. | `no_signal`; block candidate prepare. |
| `basis_or_premium_window` | Supports dislocation and carry interpretation. | Downshift to observe-only. | Observe-only unless the lane is explicitly funding-only. |
| `mark_price_state` | Allows mark/last safety interpretation. | Emit stale packet and block candidate prepare. | Block armed observation for perps. |
| `open_interest_value_change` | Supports crowding/squeeze confidence. | Downshift confidence and block promotion. | Block FBS candidate prepare for armed mode. |
| `global_long_short_ratio` | Supports account-side crowding context. | Downshift confidence and block promotion. | Block FBS candidate prepare for armed mode. |
| `top_trader_position_ratio` | Supports high-margin crowding context. | Downshift confidence and block promotion. | Block FBS candidate prepare for armed mode. |
| `funding_settlement_timing_state` | Carry timing can be interpreted. | Observe-only. | Block promotion and block carry-sensitive candidate prepare. |
| `funding_squeeze_concentration_state` | Symbol/month concentration is disclosed. | Require review or downshift. | Block promotion. |
| `real_exchange_margin_liquidation_model` | Enables promotion review beyond proxy stress. | Block leverage promotion. | Block leverage promotion. |

## Packet Behavior

| State | Packet Status | Research Recommendation |
| --- | --- | --- |
| Fresh facts and fresh signal | `ready_for_shadow_candidate_prepare` | Candidate prepare can be considered by main control after account, exchange, protection, and runtime gates pass. |
| Partial facts | `signal_context_only` | Keep observation; do not prepare candidate from research semantics alone. |
| Stale facts | `stale_signal` | Block candidate prepare and request fact refresh. |
| Missing primary facts | `no_signal` or `facts_missing` | Block candidate prepare. |
| Mark deviation spike | `signal_conflict` | Block candidate prepare and mark the signal invalid until refreshed. |

## Sample Partial-Facts Packet

```json
{
  "packet_type": "strategy_signal",
  "strategy_group_id": "FBS-001",
  "strategy_group_version": "2026-06-14-r0",
  "status": "signal_context_only",
  "symbol": "INTCUSDT",
  "direction": "long",
  "reason": "Funding and mark facts are present, but OI or crowding facts are missing or field-shape-only.",
  "readiness_state": "fbs_derivatives_facts_partial",
  "candidate_prepare_allowed_by_research": false,
  "execution_allowed_by_research": false
}
```

## Main-Control Recommendation

`FBS-001` should stay visible as a first-batch facts-heavy StrategyGroup, but
its armed observation should depend on derivatives readiness:

1. Fresh derivatives facts: keep `armed_observation`.
2. Partial derivatives facts: keep observe-only context and block candidate
   prepare.
3. Stale derivatives facts: emit stale packet and request refresh.
4. Missing primary facts: emit no-signal or facts-missing packet.
5. Missing margin model: keep leverage at `1x` default and treat `2x` only as
   research interpretation.

This reduces the chance that main-control treats all FBS blockers as a single
opaque all-or-nothing gate.
