# Main-Control Strategy Cabinet Intake Sprint

Status: ACTIVE_HANDOFF_RECOMMENDATION
Last updated: 2026-06-16

## Purpose

This document records the strategy-research recommendation that the next main
control step should consume the current Strategy Cabinet instead of expanding
strategy count further.

The current strategy research line has already produced:

| Item | Current State |
| --- | --- |
| Strategy Cabinet version | `2026-06-16-r1` |
| Strategy semantics | `24` |
| Main-control reviewable handoff / observe-only handoff packs | `12` |
| Current handoff index | `docs/strategy-research/strategy-group-handoffs/main-control-handoff-index.md` |
| Current strategy cabinet | `docs/strategy-research/strategy-cabinet/strategy-cabinet.json` |

The next useful product step is:

```text
strategy-cabinet.json
-> Strategy Cabinet ingest
-> StrategyGroup inventory
-> RequiredFacts gap view
-> watcher observation state
-> SignalEvaluation shadow ledger
-> OrderCandidate preview
-> Owner review queue
```

This is a non-executing intake recommendation. It is not runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, or order-sizing
authority.

## Known Facts

The strategy line currently has enough candidate quantity for the next main
control sprint.

| Layer | Strategies | Meaning |
| --- | --- | --- |
| First-batch core / conditional / overlay | `MPG-001`, `FBS-001`, `TEQ-001`, `PMR-001`, `SOR-001` | Existing handoff packs with P0 hardening supplements. |
| Observe-only / scorer / confirmer handoff drafts | `VCB-001`, `RSR-001`, `NLPD-001`, `DMI-001`, `SCF-001`, `MASS-001`, `UO-001` | Reviewable by main control as non-executing observation candidates. |
| Non-handoff research / facts / revival candidates | `LCF-001`, `MDS-001`, `EFI-001`, `HAT-001`, `LSR-001`, `RBR-001`, `TRIX-001`, `PSAR-001`, `ICH-001`, `CCI-001`, `AEB-001`, `STOCH-001` | Preserved in the Strategy Cabinet but not ready for runtime intake. |

Adding more strategy IDs now has lower value than making main control able to
read, display, observe, disable, and review the existing strategy semantics.

## Intake Goal

The recommended main-control sprint is a **Strategy Cabinet to Watcher Shadow
Intake** sprint.

Its goal is not to execute trades. Its goal is to prove that main control can
consume strategy-research outputs as a product-readable and audit-readable
inventory.

The minimum read model should answer:

| Question | Required Output |
| --- | --- |
| Which StrategyGroups are observable? | `strategy_group_id`, status, role, priority, default mode. |
| Which strategies can enter armed observation? | Admission recommendation and blocking facts. |
| Which facts are missing or stale? | RequiredFacts gap and missing-fact behavior. |
| When should a strategy be disabled or parked? | Disable facts, parking facts, revival condition. |
| Why is a strategy not executable? | `non_execution_flags`, promotion blockers, hard stops. |
| What does a signal look like? | Sample signal, no-signal, stale, and conflict packets. |

## Recommended Intake Scope

### P0: First Strategy Picker / Watcher Intake

| Strategy | Suggested Main-Control State | Why |
| --- | --- | --- |
| `MPG-001` | `armed_observation` | Clearest core momentum-persistence family and best first StrategyGroup candidate. |
| `TEQ-001` | `observe_first_or_armed_observation` | Matches the small-capital right-tail product thesis through Binance 2026 equity-like products. |
| `FBS-001` | `armed_observation_facts_heavy` | High right-tail elasticity, but only when derivatives facts are fresh. |
| `VCB-001` | `observe_only` | Low-cost watcher candidate for compression and breakout readiness. |
| `NLPD-001` | `observe_only` | Natural small-capital event-window observer for listing and low-history products. |

### P1: Observation Pool / Overlay / Support Intake

| Strategy | Suggested Main-Control State | Main-Control Role |
| --- | --- | --- |
| `PMR-001` | `observe_only_overlay` | Precious-metal regime support or disable overlay. |
| `SOR-001` | `conditional_observation` | Narrow session branch observer, not broad ORB. |
| `RSR-001` | `scorer` | Ranking support for TEQ / MPG selection. |
| `SCF-001` | `structure_confirmer` | Session confluence support for TEQ-like strategies. |
| `DMI-001` | `observe_only` | Directional ignition support, overlapping with MPG. |
| `MASS-001` | `observe_only` | Range-expansion reversal observation with external direction context. |
| `UO-001` | `observe_only` | Bullish-divergence observation only. |

### P2: Keep In Cabinet, Do Not Intake Yet

| Strategy | Current Role | Reason |
| --- | --- | --- |
| `LCF-001` | `facts_pipeline_required` | Needs force-order, liquidation-cluster, OI, depth, ADL, spread, and margin facts before runtime intake. |
| `EFI-001` | `right_tail_candidate` | Right-tail evidence exists, but drawdown and disable classifier quality block handoff. |
| `HAT-001` | `research_candidate` | Heikin-Ashi smoothing lag, stop-fill, and drawdown remain unresolved. |
| `LSR-001` | `research_candidate` | Local windows are strong, but full-sequence behavior is near wipeout. |
| `TRIX-001` | `right_tail_candidate` | Thin sample and symbol concentration block handoff. |
| `PSAR-001` | `right_tail_candidate` | Whipsaw and single-loss concentration block handoff. |
| `ICH-001` | `research_candidate` | No-future-cloud policy is required and full-sequence decay remains heavy. |
| `AEB-001` | `research_candidate` | Short-window strength is not yet stable across 60d / 90d windows. |
| `STOCH-001` | `parked_or_research_vocab` | Useful as range-persistence vocabulary, not as runtime activation. |
| `RBR-001` | `parked_or_research_vocab` | Needs materially different range classifier before revival. |
| `MDS-001` | `overlay_candidate` | Needs target-specific pairings before standalone intake. |
| `CCI-001` | `research_candidate` | Asset-role split and precious-metal concentration block handoff. |

## RequiredFacts Registry Priority

Main control should consume the Strategy Cabinet by normalizing RequiredFacts
before attempting any execution-adjacent flow.

| RequiredFacts Category | Serves | Priority |
| --- | --- | --- |
| OHLCV, closed candles, volume, ATR, realized volatility | `MPG-001`, `VCB-001`, `DMI-001`, `MASS-001`, `UO-001` | Highest |
| ExchangeInfo, symbol status, min notional, step size, tick size, delist state | `TEQ-001`, `NLPD-001`, `VCB-001`, all live candidates | Highest |
| Mark price, index price, funding | `FBS-001`, perp `MPG-001`, perp `VCB-001` | Highest |
| Spread, book ticker, depth | `TEQ-001`, `VCB-001`, `NLPD-001`, `FBS-001` | Highest |
| Session calendar, session gap, after-hours policy | `TEQ-001`, `SOR-001`, `PMR-001`, `SCF-001` | High |
| OI, top-trader ratio, ADL, liquidation stream | `FBS-001`, `LCF-001` | High cost, high value |
| Symbol concentration and basket ranking | `MPG-001`, `TEQ-001`, `RSR-001` | Medium-high |
| Negative evidence index | All strategies | High |

The safe order is:

1. Build common facts first.
2. Add strategy-specific facts second.
3. Add high-cost derivatives stress facts last.

## Watcher Observation Lifecycle

Main control should not reduce strategies to only `active` or `inactive`.

Recommended observation states:

```text
registered
-> facts_missing
-> observing
-> stale
-> conflict
-> signal_ready
-> candidate_preview
-> blocked
-> parked
-> killed
```

This state model matches the current handoff fields:

| Handoff Field | Observation Use |
| --- | --- |
| `required_facts` | `facts_missing`, `observing`, `blocked`. |
| `activation_facts` | `signal_ready`. |
| `disable_facts` | `blocked`, `parked`, `killed`. |
| `parking_facts` | `parked`. |
| `freshness_window` | `stale`. |
| `sample_signal_packet` | `signal_ready` / shadow ledger example. |
| `sample_stale_signal_packet` | `stale`. |
| `sample_conflict_packet` | `conflict`. |
| `non_execution_flags` | Prevents handoff-ready from becoming executable-ready. |

## Recommended Main-Control Work Order

| Order | Work | Execution Proximity |
| ---: | --- | --- |
| 1 | Strategy Cabinet ingest | Non-executing |
| 2 | StrategyGroup inventory read model | Non-executing |
| 3 | RequiredFacts registry and gap view | Non-executing |
| 4 | Watcher observation state | Non-executing |
| 5 | SignalEvaluation shadow ledger | Non-executing |
| 6 | OrderCandidate preview | Non-executing preview |
| 7 | Strategy Picker / Console read model | Non-executing product surface |
| 8 | Runtime-aware FinalGate review path | Execution-adjacent, still gated |
| 9 | Owner-gated controlled integration | Execution-capable only after official gates pass |

## Non-Goals

Do not use this intake sprint to:

1. Add more strategy IDs for its own sake.
2. Mark all twelve handoff packs as armed.
3. Treat `handoff_ready` as `executable_ready`.
4. Promote `FBS-001` or `LCF-001` without derivatives and liquidation facts.
5. Treat overlay strategies such as `PMR-001`, `MDS-001`, `RSR-001`, or
   `SCF-001` as standalone execution strategies.
6. Modify FinalGate, Operation Layer, exchange gateway, live profile,
   credentials, deploy files, or order-sizing defaults from the strategy
   research workspace.

## Main-Control Acceptance Shape

A good main-control intake should produce:

| Output | Meaning |
| --- | --- |
| `StrategyGroupInventoryReadModel` | All observable strategy semantics and current statuses. |
| `RequiredFactsGap` | Missing, stale, partial, and fresh facts by strategy. |
| `WatcherObservationState` | Registered, observing, stale, conflict, signal-ready, blocked, parked. |
| `SignalEvaluationShadowLedger` | Every signal judgment preserved without producing an order. |
| `OrderCandidatePreview` | Candidate-shaped preview that remains non-executing. |
| `OwnerReviewQueue` | Only abnormal or decision-worthy items reach Owner review. |

## Current Recommendation

The strategy research line should pause broad pool expansion as the main thrust.
It can continue narrow P2 maintenance and evidence preservation, but the next
high-value project step is for main control to ingest the current Strategy
Cabinet and prove the non-executing watcher-shadow path.

In short:

```text
Do not make the strategy cabinet bigger first.
Make the current strategy cabinet observable first.
```
