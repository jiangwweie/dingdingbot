---
title: TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-08
---

# Ticket-Bound Lifecycle Safety Core Implementation Plan

## Purpose

This document turns the ticket-bound order lifecycle design into an
implementation-ready engineering plan.

It unifies four previously separate workstreams:

```text
Lifecycle Safety Core
Official Runner Mutation Path
Exchange Protection Reconciler
Sequential Submit Failure Recovery
```

These are one engineering closure, not four independent fixes. A real ticket is
not lifecycle-safe until the system can prove:

```text
ENTRY submit / fill
-> SL + TP1 protection
-> TP1 fill
-> RUNNER_SL official mutation
-> exchange truth reconciliation
-> final exit
-> settlement
-> review
```

## Authority Boundary

The implementation must preserve the current authority model:

```text
Owner controls policy.
System executes process.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

This plan does not authorize:

- FinalGate bypass;
- Operation Layer bypass;
- exchange write outside the official ticket-bound path;
- live profile expansion;
- order sizing expansion;
- credential mutation;
- withdrawal or transfer;
- runtime or trading decisions from repo MD/JSON/output/report files.

## Current Code Facts

| Area | Current fact | Implementation meaning |
| --- | --- | --- |
| Protected submit request | Creates ENTRY, SL, and TP1 orders from one Action-Time Ticket | The submit envelope exists, but sequential failures still need lifecycle states |
| Submit execution | API path places orders one by one through the gateway | It is not an atomic exchange-native bracket |
| Exit protection materializer | Records PG lifecycle/protection rows from submitted order refs | It is a proof materializer, not an exchange mutation service |
| Runner protection adjuster | Records RUNNER_SL proof after TP1 fill and official runner SL ref | It is a proof materializer, not the cancel/replace executor |
| Post-submit closure | Closes PG lifecycle when final exit, reconciliation, settlement, and review refs exist | It summarizes closure; it does not discover exchange truth by itself |
| Ops health | Can detect TP1 without runner SL, incomplete protection, lifecycle/closure drift | It must become part of the acceptance gate |

### Current Implementation Progress

As of the 2026-07-08 lifecycle-safety-core branch, the implementation has
advanced from proof-only protection rows to a broader local lifecycle safety
core:

| Area | Current implementation | Remaining boundary |
| --- | --- | --- |
| Full-chain simulation | `full_chain_simulation_harness` runs constructed PG input through signal, lane, ticket, safety, protected submit, protection, runner command, runner proof, final closure | It uses mock exchange result and does not grant live exchange authority |
| Sequential submit failure | `record_ticket_bound_protected_submit_result` materializes submit failures into lifecycle states such as `submit_failed`, `protection_missing`, and `protection_submit_failed`; `protection_recovery_command` prepares and executes missing SL/TP1 recovery locally through an injected gateway | Production scheduling/API wiring remains behind explicit Owner deploy approval |
| Protection reconciliation | `protection_reconciler` compares PG protection rows with caller-provided exchange snapshots and writes current lifecycle blockers; linked SL/TP1 must match exchange existence, reduce-only flag, side, and bounded qty | It consumes already-fetched facts and does not call exchange APIs |
| Runner mutation command | `runner_mutation_command` creates PG command intent and records official-path results for old SL cancel / RUNNER_SL submit | Command rows are intent/result records, not proof of runner protection |
| Runner mutation executor | `runner_mutation_executor` consumes a prepared PG command, calls injected gateway cancel/place, and records the PG result | Executor is mockable locally and still cannot call FinalGate, change profile/sizing, or use file authority |
| Ops health | Tokyo ops health reads exact lifecycle attention states and runner commands without runner proof | It remains readonly and non-mutating |

## Target Core

### Single Lifecycle Owner

`TicketBoundLifecycleSafetyCore` is the conceptual owner of post-submit
lifecycle state. It can be implemented as services/materializers, but there
must be one state model and one current first-blocker vocabulary.

It owns:

- lifecycle state transitions;
- sequential submit failure classification;
- protection set completeness;
- runner mutation readiness;
- exchange protection reconciliation;
- final exit closure preconditions;
- current lifecycle blocker projection.

It must not own:

- strategy semantics;
- Owner policy;
- FinalGate approval;
- Operation Layer authorization;
- direct exchange mutation outside official operation commands.

### Required State Machine

```text
ticket_finalgate_ready
-> submit_prepared
-> entry_submit_sent
-> entry_accepted
-> entry_fill_pending
-> entry_filled
-> protection_submit_pending
-> protection_submitted
-> protection_reconciliation_pending
-> position_protected
-> tp1_fill_pending
-> tp1_filled
-> runner_mutation_pending
-> runner_sl_submitted
-> runner_reconciliation_pending
-> runner_protected
-> final_exit_detected
-> final_reconciliation_pending
-> reconciliation_matched
-> budget_settled
-> review_recorded
-> lifecycle_closed
```

Terminal hard stops:

```text
submit_failed
entry_unknown
entry_orphaned
entry_partial_fill_unhandled
protection_missing
protection_submit_failed
protection_reconciliation_mismatch
tp1_or_sl_orphaned
runner_mutation_failed
runner_reconciliation_mismatch
position_closed_protection_live
final_exit_unknown
settlement_blocked
review_blocked
```

## Official Mutation Boundary

### Allowed Exchange Mutations

| Mutation | Allowed only when | Required lineage |
| --- | --- | --- |
| ENTRY submit | Ticket has Runtime Safety State `live_submit_ready` and Operation Layer submit command | `ticket_id`, `finalgate_pass_id`, `operation_submit_command_id` |
| SL submit | Same ticket-bound protected submit envelope or official recovery command | `ticket_id`, `protected_submit_attempt_id`, `entry_exchange_order_id` |
| TP1 submit | Same ticket-bound protected submit envelope or official recovery command | `ticket_id`, `protected_submit_attempt_id`, `entry_exchange_order_id` |
| Protection recovery submit | ENTRY fill confirmed and SL/TP1 missing after sequential submit failure | `ticket_id`, `protected_submit_attempt_id`, `lifecycle_run_id`, `entry_exchange_order_id` |
| Old SL cancel | TP1 fill confirmed and runner mutation command approved | `ticket_id`, `exit_protection_set_id`, `old_sl_exchange_order_id` |
| RUNNER_SL submit | TP1 fill confirmed and remaining runner qty positive | `ticket_id`, `exit_protection_set_id`, `tp1_exchange_order_id` |
| Orphan protection cancel | Position flat or wrong protection proven by reconciler | `ticket_id` or explicit orphan identity proof |

### Forbidden Shortcuts

The following are invalid even if they look operationally convenient:

- proof materializer directly calling exchange cancel/replace;
- runner adjuster creating exchange orders;
- reconciler silently rewriting PG to match exchange without an event;
- treating an exchange order id in a JSON/report as current truth;
- closing lifecycle without current flat-position proof;
- continuing new entries while a submitted ticket has unresolved protection.

## Exchange Truth Model

### Required Exchange Snapshot Inputs

The reconciler must read current exchange/account facts through official
read-only adapters:

| Snapshot | Required fields |
| --- | --- |
| Open orders | exchange order id, client order id, symbol, side, reduce-only, qty, price, trigger price, status |
| Recent fills | exchange order id, fill qty, average price, fee, timestamp |
| Position | symbol, side/direction, position qty, entry price, unrealized PnL, liquidation price if available |
| Account | margin mode, available balance, margin used, account id/profile |

These snapshots are runtime facts. They belong in PG/current projections or
read-only service results, not repo/output/report files.

### Reconciliation Rules

| Condition | Required state |
| --- | --- |
| PG says SL exists but exchange lacks it | `protection_reconciliation_mismatch` |
| PG says TP1 exists but exchange lacks it | `protection_reconciliation_mismatch` |
| Exchange has protection order not linked to PG | `tp1_or_sl_orphaned` until identity is proven |
| SL or TP1 side is not reduce-only close side | `protection_reconciliation_mismatch` |
| Open SL qty exceeds current remaining position beyond step tolerance | `protection_reconciliation_mismatch` |
| TP1 filled and old full-size SL still open | `runner_mutation_pending` or `runner_reconciliation_mismatch` |
| TP1 filled and RUNNER_SL missing | `runner_mutation_pending` |
| Position flat and protection still open | `position_closed_protection_live` |
| Position open and no valid SL exists | `protection_missing` |

Exchange truth wins over PG projection when there is a conflict. PG must be
updated through reconciliation events, not by silent overwrite.

## Sequential Submit Failure Matrix

| Failure point | Risk | Lifecycle state | Required next action |
| --- | --- | --- | --- |
| ENTRY rejected before any fill | No position | `submit_failed` | Mark attempt failed and release/expire ticket scope |
| ENTRY call timed out / unknown | Possible position or order | `entry_unknown` | Run exchange/order reconciliation before retry |
| ENTRY accepted but local OrderLifecycle write failed | Exchange has order, local state incomplete | `entry_orphaned` | Reconcile exchange order into PG/local lifecycle before any new submit |
| ENTRY partially filled | Residual exposure with uncertain protection qty | `entry_partial_fill_unhandled` | Reconcile fill qty and create protection only for actual filled qty |
| ENTRY filled, SL rejected | Naked position | `protection_missing` | Official recovery command: submit SL or flatten |
| ENTRY filled, SL accepted, TP1 rejected | Position has stop but no TP1 | `protection_submit_failed` | Official recovery command: submit TP1 or mark degraded and block new entries |
| ENTRY/SL/TP1 all accepted, PG record incomplete | Exchange may be protected, PG cannot prove it | `protection_reconciliation_mismatch` | Reconcile and materialize missing PG rows from exchange truth |
| TP1 filled, old SL not adjusted | Remaining position may have wrong stop qty | `runner_mutation_pending` | Official runner mutation command |
| Runner SL submit rejected | Remaining position may be unprotected or overprotected | `runner_mutation_failed` | Retry official runner mutation or flatten recovery |
| Final exit filled, protection still open | Residual reduce-only orders may later trigger unexpectedly | `position_closed_protection_live` | Official cleanup cancel command |

## Implementation Batches

### Batch 1: Full Chain Simulation Harness

Goal:

```text
constructed PG input
-> signal
-> promotion
-> lane
-> ticket
-> safety/finalgate/handoff
-> protected submit
-> mocked exchange result
-> lifecycle/protection
-> TP1 fill
-> runner protection
-> final exit
-> closure
```

Acceptance:

| Requirement | Proof |
| --- | --- |
| Active event specs covered | CPM long, MPG long, MI long, SOR long, SOR short, BRF2 short |
| No exchange write | Mock gateway/evidence only |
| No file authority | PG or typed in-memory fixtures only |
| Negative paths included | Missing SL, missing TP1, partial fill, duplicate submit, missing runner SL |

### Batch 2: Sequential Submit Recovery

Goal: turn every sequential submit failure into an explicit lifecycle state and
first blocker.

Acceptance:

| Requirement | Proof |
| --- | --- |
| ENTRY unknown handled | No retry before reconciliation |
| Protection missing handled | New entries blocked while naked-position risk is unresolved |
| Partial fill handled | Protection qty cannot be computed from requested qty when fill qty differs |
| Duplicate submit handled | Existing prepared/submitted attempt blocks new attempt |

Implementation status:

1. **Implemented**: failed protected submit results materialize exact lifecycle
   states including `protection_missing` and `protection_submit_failed`.
2. **Implemented**: `protection_recovery_command` prepares one PG recovery
   command for an ENTRY-filled attempt with missing SL and/or TP1.
3. **Implemented**: recovery executor submits only missing reduce-only SL/TP1
   orders through an injected gateway and records success/failure in PG.
4. **Implemented**: successful recovery repairs the protected submit attempt so
   the existing exit protection materializer can create the canonical SL/TP1
   protection proof set.
5. **Remaining production integration**: wire recovery executor into deployed
   Operation Layer scheduling/API only after explicit Owner deploy approval.

### Batch 3: Protection Reconciler

Goal: compare PG, OrderLifecycle, and exchange truth for active lifecycle rows.

Acceptance:

| Requirement | Proof |
| --- | --- |
| SL/TP1 existence checked | Missing exchange order becomes current blocker |
| Reduce-only checked | Wrong side or non-reduce-only order becomes hard stop |
| Qty checked | Protection qty cannot exceed remaining position beyond tolerance |
| Orphans checked | Exchange-only protection cannot silently become PG truth |

### Batch 4: Official Runner Mutation

Goal: after TP1 fill, use the official ticket-bound operation path to replace
full-size SL protection with remaining-runner SL protection.

Acceptance:

| Requirement | Proof |
| --- | --- |
| TP1 fill is detected | Lifecycle enters `tp1_filled` or `runner_mutation_pending` |
| Old SL mutation is official | Cancel/replace command binds ticket and protection set |
| RUNNER_SL is official | New exchange ref is produced by official path |
| Reconciliation closes it | `runner_protected` only after exchange/PG refs match |

Implementation status:

1. **Implemented**: `runner_mutation_command` prepares one PG command per
   `exit_protection_set_id`.
2. **Implemented**: `runner_mutation_executor` executes prepared commands
   through an injected gateway and records success/failure results.
3. **Implemented**: full-chain simulation uses a mock runner mutation gateway,
   so every active StrategyGroup/symbol/side scope exercises cancel old SL and
   submit RUNNER_SL locally.
4. **Remaining production integration**: wire the executor into the deployed
   ticket-bound Operation Layer scheduler/API only after local acceptance and
   explicit Owner deploy approval.

### Batch 5: Final Closure

Goal: make final exit, reconciliation, settlement, and review close one
ticket-bound lifecycle.

Acceptance:

| Requirement | Proof |
| --- | --- |
| Final exit belongs to ticket | final order is SL, TP1, or RUNNER_SL under protection set |
| Flat position proven | no lifecycle closure without current flat-position proof |
| Settlement bound | budget release/consume evidence exists |
| Review bound | review evidence exists before `lifecycle_closed` |

## Test Matrix

| Test family | Required coverage |
| --- | --- |
| Full-chain impact | Every active StrategyGroup event spec can reach mocked lifecycle closure |
| Submit recovery | ENTRY reject, timeout, local write failure, partial fill, protection reject, missing SL/TP1 recovery success, recovery submit failure |
| Protection reconciliation | Missing SL, missing TP1, wrong side, wrong qty, orphan order, flat-with-live-protection |
| Runner mutation | TP1 filled with missing runner SL, cancel failure, RUNNER_SL submit failure, successful official runner SL, runner reconciliation mismatch |
| Closure | final exit proof missing, flat proof missing, settlement missing, review missing, happy closure |
| Action-time TTL | Expired ticket blocks new submit; already-submitted ticket continues post-submit lifecycle to closure |
| Ops health | active lifecycle blockers surface in readonly health checks without exchange writes |

## Runtime Cadence And Performance

| Path | Rule |
| --- | --- |
| No-signal tick | Must not create lifecycle rows |
| Submit path | Creates at most one lifecycle run per ticket |
| Reconciler | Scans only open lifecycle runs, active attempts, open protection sets, and current exchange snapshots |
| Monitor | Reports current lifecycle blockers only; historical blockers become resolved/archive facts |
| PG growth | Lifecycle events are append-only but bounded by ticket count, not watcher tick count |
| Logs | Syslog emits summaries; detailed order/fill refs remain in PG |

## Implementation Ownership

| Component | Owner role |
| --- | --- |
| `src/application/action_time/protected_submit_attempt.py` | Submit envelope and submit result identity |
| `src/application/action_time/exit_protection_materializer.py` | PG protection proof from accepted submit result |
| `src/application/action_time/runner_protection_adjuster.py` | PG runner proof from official runner SL ref |
| New lifecycle safety service | State transitions and failure classification |
| New protection reconciler | Exchange/PG/OrderLifecycle truth comparison |
| Operation Layer extension | Official runner/cancel/recovery mutation commands |
| Ops health script | Read-only lifecycle blocker projection |

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scope
stage: ticket_bound_lifecycle_safety_core
first_blocker: production_wiring_and_real_exchange_acceptance_requires_owner_approval
evidence: local PG lifecycle safety core covers full-chain simulation, sequential submit recovery, protection reconciliation, runner mutation executor, action-time TTL behavior, and final closure without file authority
next_action: complete local verification gates and review diff; request Owner approval before Tokyo deploy, server migration, service restart, production wiring, or real exchange acceptance
stop_condition: one locally mocked ticket proves entry, protection, TP1, runner, final exit, reconciliation, settlement, and review; one real ticket can be accepted only after explicit deploy approval
owner_action_required: yes_for_deploy_and_real_exchange_acceptance_only
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write outside official ticket-bound path
```
