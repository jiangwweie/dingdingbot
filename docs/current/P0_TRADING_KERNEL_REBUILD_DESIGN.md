---
title: P0_TRADING_KERNEL_REBUILD_DESIGN
status: OWNER_APPROVED_IMPLEMENTATION
program_id: P0-TKR
last_verified: 2026-07-22
---

# P0 Trading Kernel Rebuild Design

## Decision

The repository and Tokyo runtime are replaced by one multi-position trading
kernel and one clean PostgreSQL baseline. There is no compatibility migration,
dual write, or retired-runtime fallback.

## Final Chain

```text
StrategyGroup observer
-> ActionableSignal
-> persisted readiness
-> globally serialized Ticket issuance
-> durable ENTRY command
-> Initial Stop
-> concurrent Ticket lifecycle
-> EXIT / recovery
-> exchange reconciliation
-> settlement
-> review
```

## Core Invariants

1. One Exposure Episode owns one immutable Ticket.
2. Adding to a position is forbidden.
3. Each Ticket may have one ENTRY generation only.
4. New ENTRY work is globally serialized.
5. Existing Ticket lifecycle work is concurrent.
6. One active Ticket exists per Netting Domain.
7. Long and short are independent sides and may coexist.
8. Multi-position is a default capability, not a fixed two-position model.
9. Policy may impose bounded account capacity without changing the architecture.
10. ENTRY rejection is terminal.
11. Unknown outcome is reconciled and never blindly resent.
12. Partial ENTRY fill is an incident followed by exact remainder cancel and
    controlled flatten.

## Code Ownership

```text
src/trading_kernel/domain         pure lifecycle and identity rules
src/trading_kernel/application    typed use cases and ports
src/trading_kernel/infrastructure PostgreSQL and venue adapters
src/trading_kernel/interfaces     bounded worker and readonly surfaces
```

No production module outside this package may own trading execution behavior.

## Signal Boundary

`ActionableSignal` is the only strategy-to-kernel command. It freezes:

- signal, StrategyGroup, strategy version, event, scope, instrument, and side;
- occurrence and expiry;
- fact digest;
- typed entry, quantity, notional, leverage, risk-at-stop, Initial Stop, and
  take-profit terms.

The kernel persists the signal, validates current scope/profile/policy/account
mode/instrument/capability, and records readiness. A globally serialized issuer
selects one ready signal, revalidates authority, builds the deterministic Ticket,
and commits the Ticket, budget, exposure, aggregate, event, and ENTRY command in
one transaction.

Two fresh signals may be persisted concurrently. Their Tickets are issued
serially. Once the first Ticket has protected exposure or a proven terminal
pre-exposure outcome and releases the lane, the next unexpired ready signal may
issue a Ticket.

## Persistence Model

The clean baseline contains stable registry, policy, observation, lifecycle,
and operations tables only. Signal ticket terms use typed columns. JSONB is
limited to bounded metadata, fact summaries, command payloads, and review data.

Key lifecycle authorities are:

```text
brc_signal_events
brc_readiness_current
brc_entry_lane_current
brc_trade_tickets
brc_trade_aggregates
brc_trade_events
brc_exchange_commands
brc_positions_current
brc_budget_reservations
brc_runtime_incidents
brc_trade_reviews
```

## Transaction Model

Every aggregate mutation performs one short PostgreSQL transaction:

```text
lock exact current row
-> validate expected version and current authority
-> append Trade Event
-> update Aggregate and projections
-> materialize Exchange Command or incident effect
-> commit
```

Venue I/O happens after a durable command lease commits and before its result is
recorded in a second short transaction.

## Cutover

The old writers are fenced only after exchange flatness, order absence,
protection absence, and outcome certainty are proven. A crash-safe state machine
takes a short-lived backup, recreates the application schema from `0001_initial`,
seeds current authority, deploys the exact commit, and restores capabilities in
stages.

## Acceptance

The rebuild is complete only when:

1. typed live signal reaches frozen Ticket without retired code;
2. serial Ticket issuance can create concurrent protected positions across
   distinct Netting Domains;
3. same-instrument long and short remain isolated;
4. all lifecycle and fault branches are certified;
5. retired code, tests, tables, migrations, units, and current documents are
   absent;
6. the clean baseline rebuilds from empty PostgreSQL;
7. Tokyo runs the exact commit and schema;
8. one controlled real-funds Ticket reaches terminal review and final flatness;
9. the final audit finds no unverified requirement or fallback path.

## Exchange-Write Hard Stops

Wrong identity, invalid account mode, stale facts, same-domain occupancy,
missing budget, missing protection, duplicate command, unknown outcome,
code/schema mismatch, old-writer overlap, credential mutation, withdrawal,
transfer, and official-path bypass all fail closed.
