---
title: OWNER_RUNTIME_OPERATING_MODEL
status: CURRENT
last_verified: 2026-07-22
---

# Owner Runtime Operating Model

## Normal Operation

```text
Owner enables StrategyGroup and capital scope
-> system observes and evaluates
-> system serializes eligible new ENTRY work
-> system protects and manages concurrent Tickets
-> system reconciles, settles, and reviews
-> Owner supervises product state
```

The Owner controls policy. The system owns normal process execution. Routine
facts, readiness, Ticket creation, command dispatch, protection, reconciliation,
and settlement are not manual Owner workflow steps.

## Owner Decisions

- enable, pause, resume, retire, or kill a StrategyGroup;
- select account, venue, instrument, side, runtime profile, and capital scope;
- change budget capacity or live-submit authority;
- approve the production cutover stage;
- intervene when the product reports a genuine safety or recovery condition.

## System Responsibilities

- consume typed live StrategyGroup signals;
- validate current strategy, scope, policy, account mode, facts, budget, and
  runtime capability;
- issue one immutable Ticket per Exposure Episode;
- dispatch one durable ENTRY command through the global lane;
- install and reconcile Initial Stop protection;
- manage existing Ticket lifecycle concurrently;
- record exchange truth, incidents, settlement, and review;
- expose one concise current status.

## Owner-Facing States

| State | Meaning |
| --- | --- |
| `not_enabled` | Policy does not enable the StrategyGroup |
| `running` | Observation and runtime are healthy |
| `waiting_for_opportunity` | All non-market readiness conditions pass and no fresh signal exists |
| `processing` | A signal, Ticket, command, position, or settlement is active |
| `temporarily_unavailable` | A current non-Owner condition blocks use |
| `needs_intervention` | A safety or policy action requires Owner attention |
| `paused` | Owner or system pause is active |
| `completed` | The latest Ticket is terminal and reviewed |

The primary Owner surface uses product language. Internal identities and
diagnostic fields remain available for audit without turning the Owner into an
execution operator.

## Multi-Position Meaning

Multi-position is the default kernel capability. Different Netting Domains can
hold protected positions concurrently, including long and short sides of the
same instrument. New ENTRY admission remains globally serialized. Capacity is
controlled by current Owner budget policy, not by a hard-coded two-position
architecture.

The approved runtime policy allows up to three concurrent Tickets and derives
size from current account facts, `0.03` planned stop risk, `0.90` initial-margin
utilization, maximum `10` leverage, and `cross` margin. Supported instruments
are operationally configured at fixed `5x`; the kernel adopts and revalidates
that fact without mutating leverage. A Ticket may use current remaining
executable margin instead of reserving equal shares for empty future slots.
Disabling `new_entry_submit_enabled` stops only new ENTRY; it does not remove
protection or recovery authority from a Ticket that already has exchange
exposure.
