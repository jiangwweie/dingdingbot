---
title: P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_DESIGN
status: CURRENT_DESIGN
authority: docs/current/P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_DESIGN.md
last_verified: 2026-07-12
---

# P1 Trade Feedback Core Consolidation Design

## Decision

The deployed `0368de6a` / migration `114` release is the **Live Candidate
Baseline**. P0 lifecycle engineering is deployed and no-active runtime health
is accepted, but no natural Action-Time Ticket has completed a real exchange
lifecycle. P1-TFC therefore improves feedback and recovery determinism without
replacing the deployed database schema or widening live authority.

The existing `src/application/action_time/lifecycle_safety_core.py` becomes the
single pure decision core for post-Ticket lifecycle vocabulary. This is an
extension of the designed lifecycle owner, not a second service or a new source
of truth.

## Goal

For every existing lifecycle state, observed event, reconciliation result, and
recovery outcome, produce one typed decision that answers:

```text
legacy PG lifecycle status
+ business lifecycle phase
+ protection state
+ reconciliation state
+ control state
+ failure stage/code
+ next recovery action
+ Owner product state
```

The same reducer must be consumed by production lifecycle callers,
production-shaped rehearsal, replay-shaped fixtures, and the standard Tokyo
ops read model. Event source and exchange-write authority remain different.

## Current Problem

Migration `101` permits 31 values in
`brc_ticket_bound_order_lifecycle_runs.status`. Those values mix normal
progress, protection condition, reconciliation verdict, process failure, and
recovery activity. The following production modules also re-derive parts of
the same decision:

| Current writer or consumer | Duplicate responsibility |
| --- | --- |
| `lifecycle_safety_core.py` | Partial status, event, and next-action mapping |
| `protection_reconciler.py` | Reclassifies status, event, and next action after the core |
| `protection_recovery_command.py` | Re-derives recovery failure lifecycle status |
| `runner_mutation_command.py` | Writes status, event, and recovery action directly |
| `ticket_bound_fill_projector.py` | Writes final-exit transition directly |
| `ticket_bound_lifecycle_finalizer.py` | Writes settlement/review transitions directly |
| `post_submit_reconciliation_tick.py` | Writes protection/entry mismatch transitions directly |
| `post_submit_closure.py` | Writes terminal closure transition directly |
| `orphan_protection_cleanup_command.py` | Writes cleanup failure/success transitions directly |
| Tokyo ops health | Lists attention statuses without one Owner product interpretation |

The database status remains current authority in P1-TFC. The defect is that its
meaning and allowed follow-up are not produced by one deterministic model.

## Typed Decision Model

### Lifecycle Phase

```text
unknown
submitting
open
reducing
exiting
closed
```

`observing`, signal detection, promotion, and Action-Time Lane are explicitly
outside this model because no Ticket exists yet.

### Orthogonal States

| Axis | Values |
| --- | --- |
| Protection | `not_applicable`, `pending`, `protected`, `degraded`, `missing`, `unknown` |
| Reconciliation | `not_required`, `pending`, `matched`, `mismatch`, `outcome_unknown` |
| Control | `automated`, `recovery_required`, `hard_stopped`, `owner_required`, `completed` |
| Owner product state | `processing`, `temporarily_unavailable`, `needs_intervention`, `completed` |

`owner_required` is derived only from explicit exhausted/unsafe evidence. A
recoverable technical failure remains system-owned and must not create an Owner
operation step merely because it is abnormal.

### Compatibility Boundary

`LifecycleDecision.status`, `.event_type`, `.next_action`, `.first_blocker`, and
`.blockers` preserve the current caller contract. New typed fields are additive
in memory and in read models only. No PG column, check constraint, API request,
runtime profile, strategy parameter, size, or exchange command authority changes
in this task.

Unknown lifecycle vocabulary fails closed into:

```text
phase = unknown
protection_state = unknown
reconciliation_state = outcome_unknown
control_state = hard_stopped
owner_state = temporarily_unavailable
next_action = repair_ticket_bound_lifecycle_inputs
```

## Reducer Contract

The pure reducer is:

```text
reduce_lifecycle_decision(
    current_status,
    target_status,
    event_type,
    blockers,
    next_action_override,
    owner_action_required,
) -> LifecycleDecision
```

It provides these invariants:

1. `lifecycle_closed` is terminal and cannot regress.
2. Every hard-stop status has a non-empty first blocker.
3. Event type and next action come from one mapping unless a typed caller
   supplies an explicit evidence-driven override.
4. Failure code is the first blocker; failure stage is derived from the target
   state family.
5. Owner state is derived from control state and never grants submit authority.
6. Normal progress may recover from a failure only through an explicit observed
   event; no monitor/read model mutates lifecycle state.

## Production Caller Migration

P1-TFC migrates decision construction, not exchange side effects:

```text
observed PG/exchange facts
-> existing classifier or caller-specific fact checks
-> reduce_lifecycle_decision
-> existing PG writer / append-only lifecycle event
-> existing durable exchange-command path when required
```

The following direct decision duplication is removed:

- protection reconciler event and next-action lookup;
- protection recovery failure/partial-recovery status lookup;
- Runner pending/failure event and next-action lookup;
- Fill projector final-exit decision;
- Finalizer reconciliation/settlement/review decision;
- first and scheduled reconciliation-tick mismatch decisions;
- post-submit terminal closure decision;
- orphan-protection cleanup failure/success decisions;
- Ops health Owner-facing interpretation of attention rows.

## Replay, Rehearsal, And Live Boundary

| Surface | Shared | Different |
| --- | --- | --- |
| Replay-shaped fixture | Typed reducer and Owner interpretation | Historical/synthetic event source, no PG or exchange authority |
| Production-shaped rehearsal | Real materializers, reducer, scheduler, failure matrix | Mock exchange outcome, no exchange write |
| Live | Real materializers, reducer, scheduler, PG events | Fresh identity, Runtime Safety State, FinalGate, Operation Layer, durable exchange command |

Replay and rehearsal may prove decision parity but can never create a fresh live
signal, Ticket authority, FinalGate pass, Operation Layer command, or exchange
write permission.

## Owner Feedback

The Tokyo ops summary consumes the reducer for lifecycle attention rows and
adds one bounded `lifecycle_owner_feedback` projection containing:

```text
status
label
reason
ticket_id
lifecycle_status
phase
protection_state
reconciliation_state
control_state
next_action
owner_action_required
```

It is a read model over PG current state. It does not write PG, call the
exchange, or become lifecycle authority.

## Cadence And Performance

| Boundary | Budget |
| --- | --- |
| No-signal watcher tick | Zero lifecycle rows and zero JSON/MD files |
| Reducer | Pure in-memory lookup; no I/O |
| Lifecycle maintenance | Existing bounded active-scope selection and timeouts |
| Exchange reads/writes | No additional calls introduced by P1-TFC |
| PG growth | No new recurring table or per-tick row |
| Ops health | At most the existing 20 attention rows; one in-memory projection |
| Retention | Existing PG lifecycle/event retention; no sidecar artifact |

## Acceptance

1. Every migration-114 lifecycle status has an explicit typed projection.
2. Unknown status and terminal regression fail closed.
3. Existing caller-visible status/event/next-action behavior remains equivalent.
4. Protection, recovery, Runner, Fill, Finalizer, reconciliation-tick,
   post-submit closure, orphan cleanup, and Ops callers consume the common
   reducer.
5. Two golden paths, the existing nine-scenario failure matrix, six Event Specs,
   and all 22 active scopes remain covered.
6. Full tests, current-doc validation, output scope validation, and production
   file-I/O audit pass.
7. No live profile, sizing, strategy, credential, transfer, withdrawal, or
   exchange-write authority changes.

## Stop Conditions

Stop and retain the deployed `0368de6a` behavior if implementation requires:

- a PG lifecycle schema migration in the first phase;
- a second lifecycle or exchange side-effect authority;
- FinalGate or Operation Layer changes;
- a live profile, size, StrategyGroup scope, or policy expansion;
- additional exchange calls on no-active or normal cadence;
- long-term old/new dual authority;
- weakening any fail-closed status to preserve a simpler enum.

## Live Enablement Position

```text
chain_position: action_time_boundary
strategy_group_id: CPM-RO-001 / MPG-001 / MI-001 / SOR-001 / BRF2-001
symbol: 22 active candidate scopes
stage: production_deployed_live_candidate_feedback_core_consolidation
first_blocker: market_wait_validated
evidence: deployed 0368de6a / migration 114; lifecycle timer active; no current Ticket; production-shaped lifecycle closure exists
next_action: replace duplicate lifecycle decisions with the single typed reducer while observation remains active
stop_condition: all existing lifecycle paths preserve behavior and the next natural fresh signal can interrupt directly into live Ticket acceptance
owner_action_required: no
authority_boundary: no FinalGate/Operation Layer bypass, no profile/sizing expansion, no synthetic-to-live authority
```
