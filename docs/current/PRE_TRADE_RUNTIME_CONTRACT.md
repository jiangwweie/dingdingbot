---
title: PRE_TRADE_RUNTIME_CONTRACT
status: CURRENT
authority: docs/current/PRE_TRADE_RUNTIME_CONTRACT.md
last_verified: 2026-07-02
---

# Pre-Trade Runtime Contract

## Purpose

The current live-enablement management model is:

```text
multi-StrategyGroup, multi-symbol pre-trade readiness
-> fresh-signal promotion
-> single action-time lane input
-> single protected submit intent through FinalGate and Operation Layer
```

This replaces the old interpretation that main control should advance only one
fixed `StrategyGroup + symbol` lane per day. A single lane remains required only
after a concrete fresh signal has been promoted toward action-time checks.

## Core Principle

```text
Observation is wide.
Candidate readiness is medium-wide.
Promotion can hold multiple candidates.
Action-time narrows to one lane.
Real submit narrows to one explicit order intent.
```

The project must not confuse wider observation with wider trading authority.
Read-only observation, pre-trade readiness, and promotion candidates are not
FinalGate input, Operation Layer input, exchange-write authority, live profile
expansion, or order-sizing expansion.

## Active StrategyGroups

The V0 pre-trade runtime carries these active StrategyGroups:

| Slot | StrategyGroup | V0 role |
| --- | --- | --- |
| `P0-A` | `CPM-RO-001` | Pullback/reclaim long candidates across several crypto symbols |
| `P0-B` | `MPG-001` | Momentum/leader continuation candidates across several crypto symbols |
| `P1-A` | `MI-001` | Relative-strength/admission candidates across several crypto symbols |
| `P1-B` | `SOR-001` | Session/flow candidates across several crypto symbols |
| `P2-A` | `BRF2-001` | Conditional short-side candidates while disable facts remain decision-relevant |

Non-active StrategyGroups remain support-only unless the WIP contract replaces
one of these active StrategyGroups.

## Candidate Universe

Each active StrategyGroup may carry a bounded candidate symbol set. V0 expects
at least two candidate symbols per active StrategyGroup and normally no more
than four unless the Owner explicitly changes the WIP budget.

Candidate symbols mean:

```text
worth observing
worth computing facts for
eligible to emit promotion candidates when fresh signal appears
```

They do not mean:

```text
live submit allowed
FinalGate ready
Operation Layer ready
order authorized
```

## Per-Symbol Readiness Row

The machine-readable management unit before action-time is:

```text
StrategyGroup + symbol + readiness state + first blocker + next action + stop condition
```

Each row must expose:

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | Active StrategyGroup |
| `symbol_or_basket` | Candidate symbol or future basket key |
| `asset_class` | Asset class, for example `crypto_perpetual` |
| `side` | Candidate side |
| `candidate_role` | `primary`, `secondary`, `support`, or `conditional` |
| `observation_scope` | `none`, `readonly`, or `active_observation` |
| `detector_state` | `missing`, `ready`, `running`, or `stale` |
| `watcher_state` | `missing`, `fresh`, or `stale` |
| `public_facts_state` | `missing`, `computed_not_satisfied`, or `satisfied` with fact details |
| `signal_state` | `absent`, `fresh`, `stale`, or `invalidated` |
| `risk_state` | `acceptable`, `warning`, or `disable` |
| `scope_state` | `readonly_only`, `trial_scope_proposed`, or `live_submit_allowed` |
| `promotion_state` | `idle`, `promotion_candidate`, `action_time_lane`, or `blocked` |
| `first_blocker` | One blocker class from `BLOCKER_CLASSIFICATION_CONTRACT.md` |
| `next_action` | One action that moves or reclassifies the row |
| `stop_condition` | Concrete condition that exits, parks, or advances the row |
| `evidence_ref` | One artifact, runtime, or code reference |

## Promotion Rules

Fresh-signal promotion is deterministic and non-executing:

| Condition | Result |
| --- | --- |
| `signal_state=fresh` and public facts satisfied and risk acceptable and `scope_state=readonly_only` | `promotion_candidate` with scope decision required |
| `signal_state=fresh` and public facts satisfied and risk acceptable and `scope_state=trial_scope_proposed` | `promotion_candidate` awaiting action-time scope closure |
| `signal_state=fresh` and public facts satisfied and risk acceptable and `scope_state=live_submit_allowed` | `action_time_lane` input may be generated |
| stale or absent signal | no promotion |
| missing or failed public facts | no promotion |
| `risk_state=disable` | blocked |

Promotion candidates must not call FinalGate, Operation Layer, exchange APIs,
order lifecycle, or mutate runtime budget.

## Action-Time Narrowing

Only an `action_time_lane` row may generate action-time lane input, and that
input must name:

```text
StrategyGroup
symbol or basket
side
runtime profile
fresh signal timestamp/state
public facts
action-time private facts required
risk state
scope state
```

V0 allows many readiness rows and many promotion candidates, but at most one
real-submit candidate may be selected for the official path at a time.

## Arbitration

If multiple candidates are fresh, arbitration must first eliminate anything
without live-submit scope, anything stale, anything risk-disabled, and anything
with active position or open-order conflict. Remaining action-time candidates
are ordered by configured StrategyGroup priority until portfolio/basket logic is
explicitly introduced.

Arbitration is not strategy-return optimization. It is a safety and process
selector for one bounded action-time lane.

## Daily Table Relationship

The Daily Live Enablement Table is now the summary surface for this pre-trade
runtime. It may still show the highest-priority unresolved blocker, but that
rank does not suppress fresh-signal promotion from another candidate symbol.

The current control snapshot is:

```text
output/runtime-monitor/latest-strategy-live-candidate-pool.json
```

It must include:

- one strategy-level row per active StrategyGroup for compatibility;
- one readiness row per active `StrategyGroup + symbol` candidate;
- promotion candidate rows;
- action-time lane input rows;
- arbitration state;
- no-trade audit explaining why no action-time lane exists.

## Authority Boundary

This contract does not authorize:

- FinalGate bypass;
- Operation Layer bypass;
- exchange write;
- live profile expansion;
- order-sizing expansion;
- treating read-only signals as live-submit signals;
- multiple simultaneous real-submit candidates in V0.

It authorizes only read-only observation, fact computation, blocker
classification, non-executing promotion records, and non-executing action-time
lane input generation inside the current runtime boundaries.
