---
title: PRE_TRADE_RUNTIME_CONTRACT
status: CURRENT
authority: docs/current/PRE_TRADE_RUNTIME_CONTRACT.md
last_verified: 2026-07-13
---

# Pre-Trade Runtime Contract

## Purpose

The current live-enablement management model is:

```text
multi-StrategyGroup, multi-symbol pre-trade readiness
-> fresh signal
-> ActionTimeInvocation with exact signal and actual-time facts
-> promotion
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

## PG-Backed L2-L7 Runtime Chain

The target pre-trade runtime is PG-backed after cutover:

```text
L2 Candidate Universe
-> L3 Runtime Coverage
-> L4 Event-Specific Facts
-> L5 Live Signal Event
-> ActionTimeInvocation
-> L6 Promotion Candidate
-> L7 Action-Time Lane
-> Action-Time Ticket
-> FinalGate ticket check
-> Operation Layer ticket handoff
-> protected submit attempt
-> post-submit closure
```

`L2-L7` means:

| Layer | Chinese name | Runtime owner |
| --- | --- | --- |
| L2 Candidate Universe | 候选交易范围 | PG candidate scope and event bindings |
| L3 Runtime Coverage | 服务器运行覆盖 | watcher coverage writer |
| L4 Market / Account Facts | 事实快照 | fact writer |
| L5 Live Signal Event | 实时事件信号 | live detector |
| ActionTimeInvocation | 行情触发的因果上下文 | action-time invocation materializer |
| L6 Promotion Candidate | 可升级候选 | promotion projector |
| L7 Action-Time Lane | 临近交易通道 | arbitration projector |
| Action-Time Ticket | 交易前正式票据 | ticket issuer |

After PG cutover, runtime and trading decisions must not depend on repo MD,
generated JSON, output artifacts, local cache, Single Lane Packet, or code
fallbacks. Those may exist only as exports, diagnostics, archives, fixtures, or
curated seed inputs.

## Runtime Lane Identity Conservation

Every current production observation is owned by one immutable
`RuntimeLaneIdentity`, resolved from current PG rows before strategy evaluation:

```text
candidate scope
+ candidate-scope/Event-Spec binding
+ Event Spec/version/time authority
+ runtime-scope binding/profile
+ selected runtime instance
+ current Owner policy
-> RuntimeLaneIdentity
-> Event-Spec-scoped evaluation
-> named signal
-> promotion
-> Action-Time Lane
-> Ticket
```

The identity includes the candidate scope, Event-Spec binding, runtime scope,
runtime instance, policy/profile, StrategyGroup/version, canonical symbol,
asset class, side, Event Spec/version/event ID, timeframe, and time authority.
Its stable `lane_identity_key`, source signal event ID, and source watermark
must remain unchanged from named signal through Ticket.

A watcher coverage row is independently sourced but must also carry a complete
`RuntimeLaneIdentity`, its matching `lane_identity_key`, and a nonblank watcher
source watermark before it can certify an Action-Time Invocation. Source:
`RuntimeLaneIdentity`, migrations **118** and **119**, and the 22-lane identity
certification tests.

## Action-Time Invocation Boundary

The production action-time path is not allowed to reselect a generic Candidate
Pool/readiness row after a natural signal has already been identified. Its only
valid execution input is:

```text
typed fresh signal
-> ActionTimeInvocation
-> actual-time account-safe/account-mode facts
-> exact event-specific action fact
-> transient invocation evidence
-> one promotion candidate and one action-time lane
-> Ticket
```

`ActionTimeInvocation` is a PG-backed causal context, not a trade lifecycle
owner. It stores the exact signal, immutable lane identity, signal watermark,
opening/expiry time, bound fact references, and eventual Ticket reference. A
Ticket remains the sole lifecycle owner after trade intent exists.

The invocation stage time is actual time for that stage. Account facts and
action facts must never be backdated to the invocation opening time. A current
coverage row can certify this path only if its full lane identity exactly equals
the invocation identity and it has its own nonblank source watermark; matching
only StrategyGroup, symbol, or side is insufficient.

Evaluator output is evidence about the resolved lane. It cannot create or
overwrite a StrategyGroup, symbol, side, Event Spec, timeframe, or runtime
identity. A generic opposite-side pattern is normal
`computed_not_satisfied` evidence for the resolved lane; a malformed claim that
it is materializable fails closed with a typed identity blocker. A monitor may
write a live signal only after revalidating the same current PG identity in its
insert transaction. Source: `RuntimeLaneIdentity`, migration **118**, and the
22-lane identity certification tests.

## Active StrategyGroups

The V0 pre-trade runtime carries these active StrategyGroups:

| Slot | StrategyGroup | Symbols | Supported side/event | V0 role |
| --- | --- | --- | --- | --- |
| `P0-A` | `CPM-RO-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | long / `CPM-LONG` | Pullback/reclaim long candidates |
| `P0-B` | `MPG-001` | `OPUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | long / `MPG-LONG` | Momentum/leader continuation candidates |
| `P1-A` | `MI-001` | `AVAXUSDT`, `ETHUSDT`, `SOLUSDT` | long / `MI-LONG` | Relative-strength/impulse candidates |
| `P1-B` | `SOR-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `BTCUSDT` | long / `SOR-LONG`; short / `SOR-SHORT` | Session opening-range candidates |
| `P2-A` | `BRF2-001` | `BTCUSDT`, `AVAXUSDT`, `ETHUSDT` | short / `BRF2-SHORT` | Bear-rally-failure short candidates |

Non-active StrategyGroups remain support-only unless the WIP contract replaces
one of these active StrategyGroups.

Unsupported opposite sides must not be created by mirroring. They require a new
StrategyGroup or a versioned strategy variant.

### Current Production Admission Boundary

The current set is **5 admitted StrategyGroups**, **22 active candidate lanes**,
and **6 current Event Specs**. Every active lane requires all of:

```text
semantic admission = trial_grade_capable
Event Spec signal grade = trial_grade_signal
Event Spec execution mode = trial_live
execution eligibility = enabled
```

There is no durable production `Observe-only StrategyGroup` state for these
five admitted groups. A detector or watcher remains non-executing by design;
that technical boundary does not downshift an admitted StrategyGroup into a
non-trading governance tier. An unadmitted variant belongs in Replay/research
or is parked. In particular, **CPM-RO-001 has four long lanes and no short
lane**; a computed CPM short pattern cannot create runtime state or an Owner
notification.

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
| `signal_lifecycle_status` | `absent`, `detected`, `facts_validated`, `stale`, `rejected`, or `superseded` |
| `signal_freshness_state` | `fresh`, `stale`, `expired`, `missing`, or `unknown` |
| `risk_state` | `acceptable`, `warning`, or `disable` |
| `scope_state` | `readonly_only`, `trial_scope_proposed`, `live_submit_allowed`, or `conditional_action_time_rehearsal_allowed` |
| `promotion_state` | `idle`, `promotion_candidate`, `action_time_lane`, or `blocked` |
| `first_blocker` | One blocker class from `BLOCKER_CLASSIFICATION_CONTRACT.md` |
| `next_action` | One action that moves or reclassifies the row |
| `stop_condition` | Concrete condition that exits, parks, or advances the row |
| `evidence_ref` | One artifact, runtime, or code reference |

## Promotion Rules

Fresh-signal promotion is deterministic and non-executing:

| Condition | Result |
| --- | --- |
| `signal_lifecycle_status=facts_validated` and `signal_freshness_state=fresh` and public facts satisfied and risk acceptable and `scope_state=readonly_only` | `promotion_candidate` with scope decision required |
| `signal_lifecycle_status=facts_validated` and `signal_freshness_state=fresh` and public facts satisfied and risk acceptable and `scope_state=trial_scope_proposed` | `promotion_candidate` awaiting action-time scope closure |
| `signal_lifecycle_status=facts_validated` and `signal_freshness_state=fresh` and public facts satisfied and risk acceptable and `scope_state=live_submit_allowed` | `action_time_lane` input may be generated |
| `signal_lifecycle_status=facts_validated` and `signal_freshness_state=fresh` and public facts satisfied and risk acceptable and `scope_state=conditional_action_time_rehearsal_allowed` | non-executing `action_time_lane` rehearsal input may be generated, but real submit remains blocked until the strategy-specific hard gates are satisfied |
| stale, expired, rejected, superseded, or absent signal | no promotion |
| missing or failed public facts | no promotion |
| `risk_state=disable` | blocked |

Promotion candidates must not call FinalGate, Operation Layer, exchange APIs,
order lifecycle, or mutate runtime budget.

Promotion requires PG-backed lineage:

```text
event spec
-> candidate scope event binding
-> runtime coverage
-> event-specific fact snapshot
-> live_signal_event
-> promotion_candidate
```

Historical replay events, old artifacts, generated timestamps, monitor refresh
times, or local cache times must not create current fresh live signal events.

A **fresh signal** is not a stored one-word lifecycle status. It is the derived
condition:

```text
live_signal_event.status = facts_validated
and live_signal_event.freshness_state = fresh
and now_ms <= live_signal_event.expires_at_ms
and event_time_ms comes from the strategy event time authority
```

## Action-Time Narrowing

Only a bound `ActionTimeInvocation` with exact transient evidence may generate
an action-time lane input. The generic `action_time_lane` readiness projection
may display the same state but is never an execution input. The generated lane
must name:

```text
StrategyGroup
symbol or basket
side
runtime profile
fresh signal event id
signal lifecycle status
signal freshness state
public facts
action-time private facts required
risk state
scope state
```

V0 allows many readiness rows and many promotion candidates, but at most one
real-submit candidate may be selected for the official path at a time.

The real-submit lane must have:

```text
lane_scope = real_submit_candidate
status in opened / facts_refreshing / ticket_pending / ticket_created
PG arbitration winner
budget reservation
fresh action-time facts
protection reference
execution policy
```

Rehearsal and paper lanes must use explicit `lane_scope` and must not masquerade
as real-submit lanes.

## Arbitration

If multiple candidates are fresh, arbitration must first eliminate anything
without live-submit scope, anything stale, anything risk-disabled, and anything
with active position or open-order conflict. Remaining action-time candidates
are ordered by configured StrategyGroup priority until portfolio/basket logic is
explicitly introduced.

Arbitration is not strategy-return optimization. It is a safety and process
selector for one bounded action-time lane.

Arbitration must be deterministic and PG-backed. It must first eliminate
unsupported scope, stale facts, missing runtime coverage, missing policy,
missing budget, missing protection, active-position conflicts, and open-order
conflicts. It then selects one winner by configured policy, signal freshness,
strategy priority, signal quality, budget fit, and deterministic tie-breaker.

Candidate Pool, Daily Table, Goal Status, and Server Monitor may display the
arbitration result. They must not independently create the real-submit winner.

## Action-Time Ticket

The Action-Time Ticket is the formal machine identity of one exact candidate
trade.

It must bind:

```text
strategy_group_id
strategy_group_version_id
symbol
exchange_instrument_id
side
event_id
event_spec_id
event_spec_version_id
event_time_ms
trigger_candle_close_time_ms
signal_event_id
action_time_invocation_id
lane_identity_key
source_watermark
promotion_candidate_id
action_time_lane_input_id
candidate_scope_id
candidate_scope_event_binding_id
runtime_scope_binding_id
runtime_instance_id
runtime_profile_id
policy_current_id
owner_policy_version
sizing_policy_version
execution_policy_version
protection_policy_version
budget_reservation_id
protection_ref_id
public_fact_snapshot_id
action_time_fact_snapshot_id
account_safe_fact_snapshot_id
ticket_hash
expires_at_ms
```

The ticket is not order authority. It may unlock non-executing preflight and
FinalGate inspection. It must not bypass FinalGate, bypass Operation Layer,
write exchange orders, mutate live profiles, mutate sizing defaults, or mutate
exchange account configuration.

Tickets are short-lived. Expired, invalidated, superseded, rejected, or submitted
tickets cannot re-enter FinalGate or Operation Layer.

Budget reservation happens before real-submit ticket progression, but the
reservation is initially scoped to the action-time lane and promotion candidate.
The reservation does not require `ticket_id` at insert time. The ticket then
binds `budget_reservation_id`, and the reservation may backfill `ticket_id` after
ticket creation. This prevents a circular dependency while preserving the rule
that FinalGate can inspect only ticket-bound budget lineage.

## FinalGate And Operation Layer Boundary

FinalGate input must be `ticket_id`.

FinalGate may inspect ticket-bound lineage and current safety facts. It must not
reconstruct trade identity from Candidate Pool, Daily Table, Goal Status, repo
MD, generated JSON, output artifacts, loose parameters, or old packets.

Operation Layer input must be:

```text
ticket_id + finalgate_pass_id
```

Operation Layer may normalize and submit the approved ticket-bound execution
intent. It must not choose StrategyGroup, symbol, side, event, notional,
leverage, order type, time-in-force, reduce-only, or protection semantics from
loose parameters.

Every real exchange write must trace to:

```text
ticket_id
finalgate_pass_id
operation_submit_command_id
protected_submit_attempt_id
post_submit_closure_id
```

The server product-state refresh sequence may auto-materialize the latest
submitted protected submit attempt into a post-submit closure by reading PG
current state. It must not infer this identity from Candidate Pool, Daily Table,
Goal Status, generated JSON, repo documents, or loose StrategyGroup / symbol /
side fields.

Watcher, monitor, projector, Candidate Pool, Daily Table, Goal Status,
FinalGate, reconciliation, and review paths must not write exchange orders.

## Protection / Reconciliation / Review Lineage

After an accepted submit command, the post-submit chain must remain connected:

```text
live_signal_event
-> promotion_candidate
-> action_time_lane_input
-> action_time_ticket
-> finalgate_pass
-> operation_submit_command
-> exchange_order
-> protection_state
-> reconciliation_state
-> review_outcome
```

Protection must be event-derived through `protection_ref_id`. Operation Layer
must not guess stops. A main order with detached or failed protection is not a
complete success.

Review may recommend future strategy governance changes. It must not directly
grant current submit authority, expand scope, increase budget, mutate active
tickets, or reinterpret historical outcomes under current strategy versions.

## Daily Table Relationship

The Daily Live Enablement Table is now the summary surface for this pre-trade
runtime. It may still show the highest-priority unresolved blocker, but that
rank does not suppress fresh-signal promotion from another candidate symbol.

The current PG-backed read model may be exported only by explicit diagnostic
command. Generated files are not runtime authority and must not be committed as
current state.

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
