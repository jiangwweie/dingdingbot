---
title: P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN
status: CURRENT_DESIGN
authority: docs/current/P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md
last_verified: 2026-07-08
---

# P0-C Production Lifecycle Scheduler And Snapshot Source Design

## Purpose

This document defines the production wiring that runs after an Action-Time
Ticket has already reached the protected submit / post-submit lifecycle path.

The goal is:

```text
existing PG ticket-bound lifecycle state
-> bounded lifecycle maintenance scheduler
-> exchange snapshot source when needed
-> ticket-bound maintenance service
-> exact current PG lifecycle blocker or protected state
```

This is not a new trading authority. It does not create signals, promotions,
lanes, tickets, FinalGate passes, Operation Layer handoffs, live profiles,
sizing defaults, withdrawals, transfers, or file artifacts.

## Current Facts

| Area | Current fact |
| --- | --- |
| **Maintenance coordinator** | `run_ticket_bound_lifecycle_maintenance` exists and coordinates existing materializer/recovery/runner/reconciler/cleanup modules |
| **Default exchange write posture** | Maintenance API defaults `allow_exchange_mutation=false` |
| **Runner mutation safety** | Default plan is `submit_new_runner_sl_then_cancel_old` |
| **Reconciler input** | `protection_reconciler` consumes caller-provided exchange snapshots and does not call exchange directly |
| **PG truth** | Runtime and lifecycle state live in PG current tables; repo/output/report files are not authority |

## Target Components

| Component | Responsibility | Forbidden |
| --- | --- | --- |
| **TicketBoundExchangeSnapshotProvider** | Fetch open orders, recent fills, and position for one ticket-bound protection set through the official gateway read methods | Submit, cancel, amend, FinalGate, Operation Layer, profile/sizing changes, file writes |
| **TicketBoundLifecycleMaintenanceScheduler** | Select a bounded number of active lifecycle rows from PG and run one maintenance pass per scope | Create tickets, create signals, poll all symbols blindly, write reports, hide blockers |
| **TicketBoundLifecycleMaintenanceService** | Execute one bounded lifecycle maintenance pass over existing PG rows | Fetch exchange state internally, become a second recovery/runner authority |
| **systemd one-shot timer** | Call the scheduler runner on a bounded cadence | Store report files, run catch-up storms, bypass PG state checks |

## Scheduler Selection Rules

The scheduler only selects existing PG lifecycle/protection rows.

| State | Scheduler action |
| --- | --- |
| **No lifecycle rows** | Exit with `no_active_lifecycle`; no exchange call |
| **No open/attention lifecycle rows** | Exit with `no_maintainable_lifecycle`; no exchange call |
| **protection_missing / protection_submit_failed** | Run maintenance; exchange write only if explicitly enabled |
| **position_protected / submitted / reconciled** | Fetch snapshot and reconcile if a protection set exists |
| **runner_mutation_pending** | Fetch snapshot, prepare/execute runner mutation when enabled |
| **position_closed_protection_live** | Prepare/execute linked orphan cleanup when enabled |
| **terminal hard blocker** | Keep exact blocker visible; no hidden retries beyond bounded pass |

## Exchange Snapshot Source

The snapshot provider is intentionally separate from the reconciler.

```text
official gateway read methods
-> TicketBoundExchangeSnapshotProvider
-> normalized exchange_snapshot
-> protection_reconciler
```

Required normalized fields:

| Snapshot part | Fields |
| --- | --- |
| **open_orders** | `exchange_order_id`, `client_order_id`, `symbol`, `side`, `reduce_only`, `qty`, `price`, `trigger_price`, `status` |
| **recent_fills** | `exchange_order_id`, `symbol`, `side`, `qty`, `price`, `fee`, `timestamp_ms` |
| **position** | `symbol`, `side`, `qty`, `entry_price`, `mark_price`, `unrealized_pnl`, `liquidation_price`, `position_flat` |

The provider must call only:

```text
fetch_open_orders
fetch_my_trades
fetch_positions
```

It must use timeout-bounded calls and return a blocker instead of hanging the
timer.

## Cadence And Performance

| Dimension | Rule |
| --- | --- |
| **Timer cadence** | 30 seconds, oneshot, bounded by service timeout |
| **No active lifecycle** | One PG read pass, zero exchange calls, zero files |
| **Max lifecycle scopes per tick** | Default 4 |
| **Max maintenance actions per scope** | Default 16 |
| **Exchange call trigger** | Only when a selected lifecycle has a protection set and state needs reconciliation/runner/cleanup |
| **Timeout** | Service-level `TimeoutStartSec=25s`; per exchange fetch timeout controlled in provider |
| **Disk behavior** | No report directory writes, no JSON/MD files, stdout summary only |
| **PG row growth** | Only lifecycle/command/protection events created by actual state transitions; no no-op rows |
| **Catch-up behavior** | `Persistent=false`; missed timer windows are not replayed |

## Authority Boundary

The scheduler may call exchange mutation only when all of these are true:

```text
--allow-exchange-mutation
official runtime exchange gateway binding succeeds
PG lifecycle state is already ticket-bound and recoverable
command-specific pre-execution stale checks pass
```

Allowed mutations:

| Mutation | Scope |
| --- | --- |
| **Missing SL/TP1 recovery** | Existing real protected submit attempt with ENTRY fill confirmed |
| **RUNNER_SL submit / old SL cleanup** | Existing exit protection set after TP1 fill |
| **Linked orphan protection cleanup** | Existing PG-linked reduce-only protection after flat-position proof |

Forbidden:

- new ENTRY submit;
- new ticket creation;
- FinalGate bypass;
- Operation Layer bypass;
- unknown exchange-only orphan cancellation;
- live profile / sizing / leverage expansion;
- withdrawal or transfer;
- repo/output/report file authority.

## Acceptance

| Requirement | Proof |
| --- | --- |
| **No lifecycle no-ops are cheap** | Unit test proves no selected lifecycle means no gateway calls |
| **Snapshot source is read-only** | Unit test proves provider only calls read methods and normalizes fields |
| **Recovery can run from scheduler** | Unit test proves missing TP1 goes through recovery and returns protected state |
| **Runner can run from scheduler** | Unit test proves TP1-filled lifecycle submits RUNNER_SL before old SL cleanup |
| **Cleanup can run from scheduler** | Unit test proves flat-position linked protection cleanup cancels only PG-linked reduce-only refs |
| **File authority remains clear** | `scripts/audit_production_runtime_file_io.py` reports zero suspicious runtime file authority and zero frequent report writes |
| **Output scope remains clear** | `scripts/validate_output_artifact_scope.py --git-status --git-tracked` passes |

## Chain Position

```text
chain_position: post_submit_lifecycle_wiring
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scopes
stage: p0_c_scheduler_snapshot_source_design
first_blocker: implementation_and_tokyo_deploy_acceptance_pending
evidence: lifecycle maintenance service/API exists locally; scheduler and snapshot source are defined here
next_action: implement scheduler runner, snapshot provider, systemd oneshot timer, tests, deploy, and Tokyo acceptance
stop_condition: production runner can maintain existing ticket-bound lifecycle rows or expose one exact current lifecycle blocker without file authority or report growth
owner_action_required: no
authority_boundary: no FinalGate bypass, no Operation Layer bypass, no new ENTRY submit, no live profile/sizing mutation, no withdrawal/transfer
```
