---
title: POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN
status: CURRENT_DESIGN
authority: docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md
last_verified: 2026-07-09
---

# Post-Submit Reconciliation And Recovery Command Design

## Purpose

This document defines the **P0-3 Post-Submit Reconciliation First Tick** and
**P0-4 Recovery Command Matrix Hardening** design.

The goal is:

```text
protected submit result recorded
-> immediate first exchange-truth reconciliation tick
-> exact PG lifecycle state
-> deterministic recovery command when unsafe or inconsistent
-> protected / closed state or one exact hard blocker
```

This is not a new trading authority. It does not create signals, promotions,
lanes, tickets, FinalGate passes, Operation Layer handoffs, new ENTRY orders,
live profile changes, sizing changes, withdrawals, transfers, or runtime
decisions from JSON/Markdown/report files.

## Confirmed Owner Defaults

The Owner confirmed these defaults on 2026-07-09:

| Decision | Default |
| --- | --- |
| **TP1 missing** | `protection_degraded`; automatically recoverable; never `protection_complete` |
| **SL missing after ENTRY fill/open position** | P0 emergency; recover immediately |
| **Runner SL mutation order** | Submit new runner SL first, confirm it, then cancel old SL |
| **Old SL cancel failure** | Allow short double-protection window, then cleanup/reconcile; never mark complete |
| **Recovery retries** | Same command, same ticket, max 3 attempts |
| **Freeze scope** | `strategy_group_id + symbol + side` |
| **First tick visibility grace** | 30 seconds for exchange eventual visibility |
| **ENTRY filled or position open with SL missing** | No grace wait; recover immediately |
| **Exchange-only unknown order** | Do not auto-cancel; do not auto-adopt as normal protection; freeze scope and notify |
| **PG-linked orphan protection after flat position** | May be cleaned through bounded PG-linked cleanup command |

## Authority Boundary

### Allowed

This design may:

- read existing PG ticket-bound lifecycle state;
- read exchange open orders, recent fills, and positions through official
  gateway read methods;
- write PG reconciliation ticks, lifecycle events, recovery commands, and
  current blocker states;
- execute only already-supported ticket-bound recovery mutations when explicitly
  enabled by the production lifecycle scheduler;
- freeze new submits for one `strategy_group_id + symbol + side` scope when
  current state is unsafe or inconsistent.

### Forbidden

This design must not:

- create a new ENTRY order;
- create a new ticket;
- create or import a live signal;
- call FinalGate or Operation Layer outside the already approved ticket path;
- bypass FinalGate or Operation Layer;
- cancel unknown exchange-only orders;
- mutate credentials, live profile, leverage, or sizing defaults;
- withdraw or transfer;
- use repo MD/JSON, `output/**`, report-dir JSON, or evidence files as current
  lifecycle authority.

## P0-3: Post-Submit Reconciliation First Tick

### Definition

The first tick is the first read-only exchange-truth comparison after a
ticket-bound protected submit result is recorded.

```text
brc_ticket_bound_protected_submit_attempt.submit_result
-> expected ENTRY / SL / TP1 shape
-> official exchange read snapshot
-> first reconciliation tick row
-> lifecycle state update or recovery command
```

### Trigger

The first tick must be requested immediately after
`record_ticket_bound_protected_submit_result` records a non-disabled
`real_gateway_action` result.

Valid trigger conditions:

| Condition | Action |
| --- | --- |
| **submit result status = `exchange_submit_orders_submitted`** | Create `first_post_submit` reconciliation tick |
| **ENTRY submit failed before exchange acceptance** | Close failed ticket without exchange snapshot unless identity is unknown |
| **exchange write called but result incomplete / timeout / unknown** | Create first tick and query by `client_order_id` |
| **attempt was disabled smoke** | No first tick; disabled smoke is rehearsal, not live exchange truth |

### Inputs

| Input | Source | Rule |
| --- | --- | --- |
| **Action-Time Ticket** | PG | Provides stable StrategyGroup, symbol, side, profile, and policy identity |
| **Protected submit attempt** | PG | Provides submit request and result |
| **Expected orders** | PG submit request/result | ENTRY, SL, TP1 local IDs, client IDs, exchange IDs when available |
| **Open orders** | official gateway read | Read-only; timeout bounded |
| **Recent fills** | official gateway read | Read-only; filtered by symbol/client/exchange order IDs |
| **Positions** | official gateway read | Read-only; symbol-scoped |

### Output Projection

Target current projection:

```text
brc_ticket_bound_reconciliation_ticks
```

Minimum fields:

| Field | Meaning |
| --- | --- |
| `reconciliation_tick_id` | Stable ID for ticket + tick kind + attempt |
| `ticket_id` | Action-Time Ticket |
| `protected_submit_attempt_id` | Submit attempt |
| `tick_kind` | `first_post_submit`, `scheduled`, or `recovery_check` |
| `status` | `pending_visibility`, `matched`, `mismatch`, `recovery_required`, `hard_stopped` |
| `strategy_group_id`, `symbol`, `side` | Scope identity |
| `entry_state` | `missing`, `accepted`, `filled`, `rejected`, `unknown` |
| `sl_state` | `missing`, `open`, `filled`, `mismatch`, `unknown` |
| `tp1_state` | `missing`, `open`, `filled`, `mismatch`, `unknown` |
| `position_state` | `flat`, `open`, `unknown`, `mismatch` |
| `first_blocker` | First current lifecycle blocker |
| `next_action` | Recovery command or waiting action |
| `exchange_snapshot_ref` | PG/internal snapshot reference, not a file path |
| `visibility_deadline_ms` | First-tick grace deadline |
| `created_at_ms`, `updated_at_ms` | Runtime timestamps |

### Visibility Grace

Exchange state may be eventually visible. The default grace window is 30
seconds.

| Situation | Status |
| --- | --- |
| **Fresh submit, exchange refs not visible, no position/fill proof** | `pending_visibility` |
| **Still not visible after 30 seconds** | `mismatch` or `entry_unknown` |
| **ENTRY fill or open position exists and SL is missing** | `recovery_required` immediately |
| **ENTRY accepted, SL open, TP1 missing** | `recovery_required` with `submit_missing_tp1` |
| **All expected ENTRY/SL/TP1 refs match exchange truth** | `matched` |

The grace window is not a permission to delay naked-position recovery.

### First Tick State Machine

```text
submit_result_recorded
-> first_tick_requested
-> exchange_snapshot_collected
-> pending_visibility | matched | mismatch | recovery_required | hard_stopped
```

Hard transitions:

| Observation | State | Next action |
| --- | --- | --- |
| **ENTRY rejected and no position** | `submit_failed` | `close_failed_ticket` |
| **ENTRY unknown after timeout** | `entry_unknown` | `query_by_client_order_id` |
| **ENTRY filled/open position + SL missing** | `protection_missing` | `submit_missing_sl` |
| **SL present + TP1 missing** | `protection_degraded` | `submit_missing_tp1` |
| **PG expected order missing from exchange after grace** | `protection_reconciliation_mismatch` | recovery command or hard stop |
| **Unknown exchange-only order present** | `exchange_orphan_detected` | freeze scope and notify |

## P0-4: Recovery Command Matrix Hardening

### Definition

Every non-terminal unsafe lifecycle blocker must map to exactly one recovery
command or one hard stop.

Invalid target state:

```text
status = protection_missing
first_blocker = sl_exchange_order_missing
next_action = inspect_manually
```

Valid target state:

```text
status = protection_missing
first_blocker = sl_exchange_order_missing
recovery_command = submit_missing_sl
next_action = execute_ticket_bound_recovery_command
```

### Recovery Command Table

| Command | Trigger | Exchange mutation | Scope |
| --- | --- | --- | --- |
| `close_failed_ticket` | ENTRY rejected before position exists | No | Ticket |
| `query_by_client_order_id` | ENTRY unknown, network timeout, incomplete result | No | Ticket/order IDs |
| `submit_missing_sl` | ENTRY filled/open position, SL missing or invalid | Yes | Existing ticket-bound position |
| `submit_missing_tp1` | SL exists, TP1 missing or invalid | Yes | Existing ticket-bound position |
| `replace_runner_sl` | TP1 filled and runner SL missing | Yes | Existing exit protection set |
| `cancel_old_sl_after_runner` | New runner SL confirmed and old SL still open | Yes | PG-linked old SL only |
| `cleanup_pg_linked_orphan_protection` | Position flat and PG-linked reduce-only protection still open | Yes | PG-linked protection only |
| `freeze_new_submits_for_scope` | Severe PG/exchange inconsistency or unknown exchange-only order | No | StrategyGroup + symbol + side |
| `mark_hard_stopped` | Unsafe state cannot be recovered automatically | No | Ticket or scope |

### Failure Matrix

| Failure | Lifecycle status | First blocker | Recovery command |
| --- | --- | --- | --- |
| **ENTRY rejected, no position** | `submit_failed` | `entry_rejected` | `close_failed_ticket` |
| **ENTRY unknown / network timeout** | `entry_unknown` | `entry_exchange_state_unknown` | `query_by_client_order_id` |
| **ENTRY accepted, SL failed** | `protection_missing` | `sl_exchange_order_missing` | `submit_missing_sl` |
| **ENTRY accepted, TP1 failed** | `protection_degraded` | `tp1_exchange_order_missing` | `submit_missing_tp1` |
| **SL open, TP1 missing** | `protection_degraded` | `tp1_exchange_order_missing` | `submit_missing_tp1` |
| **TP1 filled, runner SL missing** | `runner_mutation_pending` | `runner_sl_exchange_order_id_required` | `replace_runner_sl` |
| **New runner SL accepted, old SL cancel failed** | `runner_mutation_degraded` | `old_sl_cancel_not_confirmed` | `cancel_old_sl_after_runner` |
| **PG has protection, exchange missing** | `protection_reconciliation_mismatch` | `pg_present_exchange_missing` | `submit_missing_sl` or `submit_missing_tp1` when identity is safe; otherwise `mark_hard_stopped` |
| **Exchange has unknown order, PG missing** | `exchange_orphan_detected` | `exchange_only_unknown_order` | `freeze_new_submits_for_scope` |
| **Position flat, PG-linked protection open** | `position_closed_protection_live` | `pg_linked_protection_open_after_flat` | `cleanup_pg_linked_orphan_protection` |

### Retry And Freeze Rules

| Rule | Value |
| --- | --- |
| **Retry counter key** | ticket + command + target order role |
| **Max retries** | 3 |
| **Retry exhaustion status** | `hard_stopped` |
| **Freeze scope** | `strategy_group_id + symbol + side` |
| **Freeze meaning** | New promotion/ticket/submit for same scope must stop until resolved |
| **Owner notification** | Required after retry exhaustion, unknown exchange-only order, or unrecoverable protection mismatch |

Retry exhaustion must not freeze unrelated StrategyGroups, symbols, or sides.

### Unknown Exchange-Only Orders

An exchange-only unknown order is an order visible on the exchange that cannot
be tied to current PG ticket-bound lifecycle rows by one of:

- `client_order_id`;
- exchange order ID stored in PG;
- ticket-bound metadata;
- explicit PG-linked protection command lineage.

Default behavior:

```text
do not cancel
do not auto-adopt as normal protection
freeze strategy_group_id + symbol + side
notify Owner / developer diagnostics
```

PG-linked orphan protection after a flat position is different. It can be
cleaned only when PG proves the order belongs to the ticket-bound protection
set and the position is flat.

## Scheduler Integration

The production lifecycle scheduler must use this order:

```text
select existing lifecycle/protection scope
-> if first post-submit tick is due, run read-only first tick
-> if recovery command is prepared and mutation is allowed, execute command
-> run scheduled reconciliation
-> run runner mutation / cleanup when due
-> write exact current lifecycle status
```

No active lifecycle rows means:

```text
one PG read
zero exchange calls
zero files
zero no-op rows
```

## Cadence And Performance

| Dimension | Rule |
| --- | --- |
| **First tick trigger** | Event-triggered immediately after real submit result record |
| **Scheduled fallback cadence** | Existing lifecycle maintenance timer, default 30 seconds |
| **No active lifecycle** | No exchange call, no file write, no report directory output |
| **Exchange read timeout** | Bounded per gateway read method |
| **Exchange mutation timeout** | Bounded by recovery executor |
| **Max lifecycle scopes per tick** | Scheduler default 4 |
| **Max recovery actions per scope per tick** | Scheduler default 16 or stricter command-specific cap |
| **PG row growth** | Only state transition ticks, recovery commands, lifecycle events; no no-op rows |
| **Retention** | Closed lifecycle rows retained compactly; heavy snapshots archive-only outside runtime cadence |

## Implementation Plan

### Step 1: First Tick Projection

Add PG-backed first-tick materializer/service:

```text
submitted real protected submit attempt
-> first reconciliation tick row
-> matched / pending_visibility / mismatch / recovery_required / hard_stopped
```

### Step 2: Recovery Command Determinism

Extend recovery command preparation so every failure matrix row maps to one
command or one hard stop.

### Step 3: Scheduler Wiring

Make lifecycle maintenance select first-tick due rows before routine scheduled
reconciliation.

### Step 4: Anti-Regression Tests

Add focused tests for:

- first tick created after real submit result;
- disabled smoke does not create first tick;
- pending visibility before grace expiry;
- ENTRY filled + SL missing creates immediate `submit_missing_sl`;
- TP1 missing creates `protection_degraded` and `submit_missing_tp1`;
- unknown exchange-only order freezes scope and does not cancel;
- retry count 3 freezes exact `strategy_group_id + symbol + side`;
- no active lifecycle means no exchange call and no file output.

## Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **First tick exists** | Real submit result records one first reconciliation tick |
| **Grace window deterministic** | Temporary invisibility is `pending_visibility`, not false success |
| **Naked position recovery immediate** | ENTRY filled/open position + missing SL bypasses grace and prepares `submit_missing_sl` |
| **TP1 degraded not complete** | Missing TP1 is recoverable but cannot set `protection_complete=true` |
| **Recovery command unique** | Every lifecycle blocker maps to one recovery command or hard stop |
| **Freeze scoped** | Retry exhaustion freezes only `strategy_group_id + symbol + side` |
| **Unknown exchange order safe** | Unknown exchange-only order is not cancelled and not adopted silently |
| **File authority clear** | Production path adds no repo/output/report JSON or Markdown source |
| **Performance bounded** | No active lifecycle creates no exchange calls and no no-op PG rows |

## Chain Position

```text
chain_position: post_submit_lifecycle_wiring
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scopes
stage: p0_3_p0_4_design_confirmed
first_blocker: first_tick_and_recovery_command_implementation_pending
evidence: Owner confirmed first-tick visibility, SL/TP1 recovery, runner mutation order, retry, freeze-scope, and unknown-exchange-order defaults on 2026-07-09
next_action: implement PG first-tick projection, recovery command determinism, scheduler integration, focused tests, deploy, and postdeploy acceptance
stop_condition: every real protected submit result reaches matched/protected, pending visibility, deterministic recovery command, or one exact hard stop without file authority
owner_action_required: no for implementation; yes only for future policy expansion or abnormal unrecoverable live recovery
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no new ENTRY submit / no unknown-order cancel / no live profile or sizing mutation / no withdrawal or transfer
```
