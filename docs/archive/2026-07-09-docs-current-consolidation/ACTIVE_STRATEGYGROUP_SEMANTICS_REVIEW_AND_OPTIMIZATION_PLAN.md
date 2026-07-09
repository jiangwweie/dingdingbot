---
title: ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN
status: CURRENT_REVIEW
authority: docs/current/ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN.md
last_verified: 2026-07-06
---

# Active StrategyGroup Semantics Review And Optimization Plan

## Purpose

This document reviews whether the current active StrategyGroup semantics,
entries, exits, protection rules, and runtime event boundaries are coherent
enough for the PG-backed pre-trade chain.

It covers the five active StrategyGroups:

```text
CPM-RO-001
MPG-001
MI-001
SOR-001
BRF2-001
```

This is a design and review document. It does not tune strategy parameters,
authorize new sides, authorize live profile expansion, or create exchange-write
authority.

## Known Objective Facts

| Fact | Evidence |
| --- | --- |
| Active StrategyGroups and symbols are defined in the Pre-Trade Runtime Contract | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| Owner-confirmed event specs are recorded in the temporary L2-L7 reset draft and partially landed into durable runtime/DB docs | `docs/current/L2_L7_PRETRADE_CHAIN_RESET_TEMPORARY_DRAFT.md`, `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Current code has `CPM-RO-001`, `MPG-001`, `MI-001`, `SOR-001`, and `BRF2-001` semantics bindings | `src/domain/strategy_semantics.py` |
| Current code shows `BRF2-001` supported side as `short`, so the older concern that it still lists long is resolved in current code | `src/domain/strategy_semantics.py` |
| Current SOR binding still declares `supported_sides=["long", "short"]` while its reference role is short-oriented | `src/domain/strategy_semantics.py` |
| Current SOR session detector computes a session breakout shape, but does not fully close separate `SOR-LONG` and `SOR-SHORT` event specs as runtime semantics | `scripts/build_sor_session_scope_detector.py` |
| Runtime signal planning currently has SOR short-specific stop logic, but no symmetric SOR long stop logic in the inspected branch | `src/application/runtime_strategy_signal_planning_service.py` |

## Review Standard

A StrategyGroup is semantically acceptable only when it can answer these
questions without relying on old JSON, broad constants, or Owner manual
interpretation:

| Question | Required answer |
| --- | --- |
| What market event does it eat? | One versioned event spec |
| Which symbols are allowed? | PG candidate scope rows |
| Which side is allowed? | Strategy-specific side, not forced mirroring |
| What facts prove entry? | Machine-evaluable RequiredFacts |
| What facts disable entry? | Machine-evaluable disable facts |
| What protects the trade? | Event-derived protection reference |
| What exits or reviews the trade? | Versioned exit/review policy |
| What rejects the trade? | Negative tests and PG constraints |

## Current Scope Summary

| StrategyGroup | Symbols | Side | Event spec | Overall semantic status |
| --- | --- | --- | --- | --- |
| **CPM-RO-001** | ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT | long only | `CPM-LONG` | Reasonable, needs hard PG facts and rejection tests |
| **MPG-001** | OPUSDT, SOLUSDT, AVAXUSDT, SUIUSDT | long only | `MPG-LONG` | Reasonable, needs exhaustion/overextension disable hardening |
| **MI-001** | AVAXUSDT, ETHUSDT, SOLUSDT | long only / long-first | `MI-LONG` | Reasonable only if relative strength becomes hard fact |
| **SOR-001** | ETHUSDT, SOLUSDT, AVAXUSDT, BTCUSDT | long and short via explicit events | `SOR-LONG`, `SOR-SHORT` | Highest semantic risk; needs event split in code/tests |
| **BRF2-001** | BTCUSDT, AVAXUSDT, ETHUSDT | short only | `BRF2-SHORT` | Directionally aligned now; needs squeeze/uptrend disable hardening |

## CPM-RO-001 Review

### Plain Meaning

**CPM-RO-001** eats a continuation long setup:

```text
larger trend still upward
-> price pulls back without breaking the trend
-> 1h reclaim confirms continuation
-> long candidate may be considered
```

### Entry, Protection, Exit

| Area | Current target |
| --- | --- |
| Entry event | `CPM-LONG` |
| Entry facts | `htf_trend_intact`, `pullback_depth_normal`, `reclaim_confirmed`, `public_facts_ready` |
| Protection | `pullback_low_reference` or structural stop |
| Exit/review | Partial take-profit plus runner; review continuation quality, false reclaim, and stop effectiveness |

### Problems Or Suggestions

| # | Issue | Impact | Optimization |
| --- | --- | --- | --- |
| **CPM-1** | `pullback_depth_normal` needs explicit machine operator/threshold | Pullback can be judged inconsistently | Store threshold in `brc_strategy_event_required_facts` |
| **CPM-2** | Reclaim confirmation must use closed 1h candle time | Intrabar reclaim could create false freshness | Enforce `event_time_ms = trigger_candle_close_time_ms` |
| **CPM-3** | 4h trend intact must not be a prose judgment | Different builders may disagree | Define `htf_trend_intact` from versioned expression ref |
| **CPM-4** | Pullback low reference is required for protection but can be missing in weak data | Candidate could reach ticket without stop anchor | Reject promotion/ticket when protection ref is missing |
| **CPM-5** | Optional funding caveats must not block entry unless promoted to hard facts | Funding review can become ambiguous | Keep funding as review-only unless a future event version makes it required |

### Judgment

**CPM-RO-001 is semantically reasonable** as a long-only pullback/reclaim
StrategyGroup. It should not support short unless a new variant is created.

## MPG-001 Review

### Plain Meaning

**MPG-001** eats a long momentum continuation setup:

```text
market is already showing upward momentum
-> momentum persists rather than spikes once
-> continuation or breakout is confirmed by a closed 1h candle
-> long candidate may be considered
```

### Entry, Protection, Exit

| Area | Current target |
| --- | --- |
| Entry event | `MPG-LONG` |
| Entry facts | `htf_trend_up`, `one_hour_momentum_positive`, `breakout_close_confirmed`, `consecutive_higher_closes`, `volume_or_range_confirmation` |
| Disable facts | `overextension_disable=false`, `momentum_exhaustion=false` |
| Protection | `momentum_floor_reference` |
| Exit/review | Partial TP plus momentum runner; review breakout failure and follow-through |

### Problems Or Suggestions

| # | Issue | Impact | Optimization |
| --- | --- | --- | --- |
| **MPG-1** | Momentum persistence must be distinguished from a single spike | Chasing one candle can increase false entries | Require consecutive close / range / volume confirmation facts |
| **MPG-2** | Overextension and exhaustion disables must be hard blockers | Entering late can destroy right-tail profile | Store disable facts as `disable_on_match=true` |
| **MPG-3** | Momentum floor reference must be generated before ticket | Protection may be guessed later | Ticket requires `protection_ref_id` |
| **MPG-4** | Leader/relative momentum quality is currently not a strong shared abstraction | Candidate ranking may be arbitrary | Add signal-quality score derived from PG facts for arbitration only |
| **MPG-5** | Short-side MPG must remain rejected | Mechanical mirroring would change strategy thesis | Negative tests: `MPG-001 + short` rejected before signal |

### Judgment

**MPG-001 is semantically reasonable** as a long-only momentum continuation
StrategyGroup. Its main optimization is not a new side, but better exhaustion
and overextension filters.

## MI-001 Review

### Plain Meaning

**MI-001** eats a long impulse setup:

```text
allowed high-beta asset has a strong 12h impulse
-> relative strength confirms it is not just market-wide noise
-> fast reversal / exhaustion is absent
-> long candidate may be considered
```

### Entry, Protection, Exit

| Area | Current target |
| --- | --- |
| Entry event | `MI-LONG` |
| Entry facts | `twelve_hour_close_to_close_return_pct >= threshold`, `closed_1h_candle_count >= 13`, `relative_strength_confirmed=true` |
| Disable facts | `momentum_exhaustion=false`, `fast_reversal_after_impulse=false` |
| Protection | Impulse invalidation or fast reversal threshold |
| Exit/review | Review impulse continuation, reversal speed, and whether runner was capped too early |

### Problems Or Suggestions

| # | Issue | Impact | Optimization |
| --- | --- | --- | --- |
| **MI-1** | Relative strength must be hard RequiredFact | Raw impulse can be broad-market beta, not strategy edge | Seed `relative_strength_confirmed=true` as required |
| **MI-2** | 12h impulse threshold must be versioned | Threshold drift can change historical meaning | Bind threshold to event spec / RequiredFacts version |
| **MI-3** | Fast reversal after impulse must invalidate quickly | High-beta impulses can reverse sharply | Add action-time fact freshness shorter than public signal window |
| **MI-4** | Allowed symbols are narrower than generic high-beta universe | Expansion pressure can creep in | Require Owner policy + PG candidate scope for any new symbol |
| **MI-5** | Exit policy must treat large winners and fast failures differently | Single exit rule can cap right tail or hold reversals | Review runner and invalidation outcomes separately |

### Judgment

**MI-001 is conditionally reasonable**. It is acceptable only if relative
strength and fast-reversal facts become machine-enforced, not optional prose.

## SOR-001 Review

### Plain Meaning

**SOR-001** eats session opening-range events:

```text
session opening range forms
-> price breaks above or below that range
-> follow-through confirms
-> reclaim / invalidation facts stay clean
-> long or short candidate may be considered depending on the exact event
```

### Entry, Protection, Exit

| Area | Current target |
| --- | --- |
| Long event | `SOR-LONG`: closed 15m breakout above opening range high |
| Short event | `SOR-SHORT`: closed 15m breakdown below opening range low |
| Protection long | Opening range low / long invalidation |
| Protection short | Opening range high / reclaim invalidation |
| Exit/review | Same-session follow-through, failed breakout/breakdown, reclaim behavior |

### Problems Or Suggestions

| # | Issue | Impact | Optimization |
| --- | --- | --- | --- |
| **SOR-1** | Code declares both sides, but reference evaluator is short-oriented | Long and short can be conflated | Split event specs/evaluators into `SOR-LONG` and `SOR-SHORT` |
| **SOR-2** | Existing session detector is breakout-shaped but not full bidirectional runtime semantics | Long may have detector facts while short relies on different logic | Build one shared opening-range engine with two side-specific outputs |
| **SOR-3** | Same-session validity must be explicit | Stale session events can re-enter later | Ticket expires at session boundary or next 15m freshness window |
| **SOR-4** | Long/short conflict on same symbol/session needs arbitration rule | Opposite signals can create contradictory candidates | Reject simultaneous opposite-side ticket for same symbol/session unless one supersedes the other |
| **SOR-5** | Stop reference differs by side and must be enforced | Operation Layer cannot guess protection | `SOR-LONG` ticket requires range-low protection; `SOR-SHORT` requires range-high protection |

### Judgment

**SOR-001 is the highest-priority semantic repair**. Conceptually it can be
bidirectional, but code and PG constraints must make long and short two
separate events. Generic SOR freshness should be rejected.

## BRF2-001 Review

### Plain Meaning

**BRF2-001** eats bearish rally-failure setups:

```text
market rallies
-> the rally weakens or fails
-> bearish rejection / follow-through appears
-> short-squeeze risk is not extreme
-> short candidate may be considered
```

### Entry, Protection, Exit

| Area | Current target |
| --- | --- |
| Entry event | `BRF2-SHORT` |
| Entry facts | `strong_htf_uptrend=false`, `rally_extension_confirmed`, `rejection_confirmed`, `failure_reversal_confirmed` |
| Disable facts | `squeeze_risk_extreme=false`, `funding_not_extreme=true` |
| Protection | `rally_high_reference` |
| Exit/review | Review squeeze risk, reversal follow-through, stop effectiveness |

### Problems Or Suggestions

| # | Issue | Impact | Optimization |
| --- | --- | --- | --- |
| **BRF2-1** | Strong uptrend disable is central and must be hard | Shorting strong trend can be structurally wrong | Store `strong_htf_uptrend=false` as required |
| **BRF2-2** | Short squeeze risk must be machine-checkable | Squeeze risk can turn strategy into forced cover risk | Add `short_squeeze_risk_reviewed` and `squeeze_risk_extreme=false` |
| **BRF2-3** | Rally failure must be more than one red candle | False reversal risk is high | Require rally extension plus rejection plus bearish follow-through |
| **BRF2-4** | Long side must remain rejected | Rally-failure does not imply long thesis | Negative test: `BRF2-001 + long` rejected before signal |
| **BRF2-5** | Exit must handle fast short squeezes | Slow exit can turn small invalidation into large loss | Add fast reclaim / squeeze stop review fields |

### Judgment

**BRF2-001 is semantically reasonable as short-only**. Current code appears
aligned on side support, but disable facts and protection refs must be made
hard in PG.

## Cross-Strategy Findings

| Priority | Finding | Affected strategies | Required fix |
| --- | --- | --- | --- |
| **P0** | Event specs must become the runtime semantic source | All | PG event specs and candidate scope bindings |
| **P0** | SOR needs real side/event split | SOR-001 | Separate long/short facts, evaluator outputs, tests |
| **P0** | Unsupported sides must reject before signal | CPM, MPG, MI, BRF2 | Negative tests and PG constraints |
| **P1** | RequiredFacts need operator/value versions | All | `brc_strategy_event_required_facts` seed and validators |
| **P1** | Protection refs must be event-derived | All | `brc_protection_references` required before ticket |
| **P1** | Review fields should differ by strategy failure mode | All | Strategy-specific review outcome schema |

## Optimization Design

### Event Spec Seed

The current seed must include exactly these event specs:

| Event spec | Side | Symbols | Freshness |
| --- | --- | --- | --- |
| `CPM-LONG` | long | ETH, SOL, AVAX, SUI | 1h |
| `MPG-LONG` | long | OP, SOL, AVAX, SUI | 1h |
| `MI-LONG` | long | AVAX, ETH, SOL | 1h |
| `SOR-LONG` | long | ETH, SOL, AVAX, BTC | 15m same-session |
| `SOR-SHORT` | short | ETH, SOL, AVAX, BTC | 15m same-session |
| `BRF2-SHORT` | short | BTC, AVAX, ETH | 1h |

### Required Negative Tests

```text
CPM-RO-001 short rejected
MPG-001 short rejected
MI-001 short rejected
BRF2-001 long rejected
SOR-001 generic signal rejected
SOR-LONG using SOR-SHORT facts rejected
SOR-SHORT using SOR-LONG facts rejected
generated_at as event_time_ms rejected
ticket without event-derived protection rejected
```

### Implementation Sequence

| Batch | Goal | Capability unlocked |
| --- | --- | --- |
| **A** | Seed/validate event specs and RequiredFacts | Unsupported side/symbol/event fails closed |
| **B** | Split SOR evaluator/detector semantics | SOR long/short can be separately promoted |
| **C** | Add strategy-specific protection refs | Ticket can bind valid protection |
| **D** | Add review outcome fields per strategy | Strategy learning becomes structured |

## Chain Position

```text
chain_position: strategy_semantics_review
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: semantic_design_review
first_blocker: SOR side/event semantics and cross-strategy RequiredFacts are not fully executable as PG-enforced runtime constraints
evidence: current contracts, temporary Owner confirmations, and inspected code paths
next_action: implement event-spec seed validation and SOR-LONG/SOR-SHORT semantic split
stop_condition: unsupported sides/events reject before live signal, and every valid event has RequiredFacts plus protection refs
owner_action_required: no
authority_boundary: strategy semantics only; no FinalGate, Operation Layer, exchange write, profile mutation, or sizing mutation
```
