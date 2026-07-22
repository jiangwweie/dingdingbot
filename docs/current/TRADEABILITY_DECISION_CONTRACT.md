---
title: TRADEABILITY_DECISION_CONTRACT
status: CURRENT
last_verified: 2026-07-22
---

# Tradeability Decision Contract

## Purpose

The Tradeability Decision is the single current answer to:

```text
Can this StrategyGroup + instrument + side produce a new Ticket now?
```

## Required Fields

| Field | Meaning |
| --- | --- |
| `runtime_scope_id` | Exact current observation and trading scope |
| `strategy_group_id` | Strategy identity |
| `event_spec_id` | Versioned signal meaning |
| `exchange_instrument_id` | Canonical venue instrument |
| `position_side` | Independent long or short side |
| `can_issue_ticket_now` | Current boolean result |
| `first_blocker` | One class from the blocker contract |
| `signal_event_id` | Current fresh signal when present |
| `facts_valid_until_ms` | Earliest current fact deadline |
| `owner_action_required` | Whether a scoped policy/intervention decision is required |
| `updated_at_ms` | Projection time |

## Authority Boundary

The decision may permit Ticket issuance but does not itself dispatch an exchange
command. The immutable Ticket, current runtime safety checks, durable command,
and venue adapter remain required.

Replay, generated files, chat, and stale database rows cannot set
`can_issue_ticket_now=true`.
