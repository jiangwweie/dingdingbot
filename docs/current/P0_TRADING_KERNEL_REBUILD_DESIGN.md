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
-> immutable StrategySignal + fact lineage
-> persisted candidate readiness
-> deterministic candidate arbitration
-> action-time CapacityClaim
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

`StrategySignal` is the only strategy-to-kernel observation input. It freezes:

- signal, StrategyGroup, strategy version, event, scope, instrument, and side;
- occurrence and expiry;
- the complete immutable Fact Bundle and its exact digest.

The strategy boundary cannot assign quantity, notional, leverage, account
budget, order price, Initial Stop order, or take-profit orders. Signal ingestion
validates Registry identity, runtime scope identity, current Fact equality,
freshness, instrument identity, and code/schema capability before recording a
candidate. Owner policy, account mode, action-time venue rules, current balance,
margin, budget, and Netting Domain occupancy are evaluated only when a fresh
candidate is narrowed and an immutable `CapacityClaim` is built.

The globally serialized issuer accepts only a current `CapacityClaim`. It
revalidates authority and atomically commits the Claim, Ticket, budget
reservation, active Netting Domain hold, aggregate, first event, and durable
ENTRY command. A `StrategySignal` can never issue a Ticket directly.

Two fresh signals may be persisted concurrently. Their Tickets are issued
serially. Once the first Ticket has protected exposure or a proven terminal
pre-exposure outcome and releases the lane, the next unexpired ready signal may
issue a Ticket.

## Persistence Model

The clean baseline contains stable registry, policy, observation, lifecycle,
and operations tables only. Signal rows contain observation identity and time;
their immutable Fact Bundles live in append-only typed snapshot rows. Financial
and order terms exist only at the CapacityClaim and Ticket boundaries. JSONB is
limited to typed fact values, bounded metadata, summaries, command payloads,
and review data.

Key lifecycle authorities are:

```text
brc_signal_events
brc_signal_fact_snapshots
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

## Runtime Ownership And Review

Production cadence is split across four independently bounded workers:

```text
Observation Worker
Entry Worker
Lifecycle Worker
Reconciliation Worker
```

The Entry Worker is the only owner of new Ticket issuance. Lifecycle and
reconciliation continue concurrently for existing Tickets. The terminal Review
records realized PnL, fees, funding, net PnL, and R-Multiple from exact Ticket
order identities. When funding cannot be attributed exactly, Review records
`funding_unavailable` and does not fabricate net economics.

## Cutover

The old writers are fenced only after exchange flatness, order absence,
protection absence, and outcome certainty are proven. A crash-safe state machine
takes a short-lived backup, recreates the application schema from `0001_initial`,
seeds current authority, deploys the exact commit, and restores capabilities in
stages.

## Acceptance

The rebuild is complete only when:

1. typed live StrategySignal reaches an action-time CapacityClaim and frozen
   Ticket without retired code;
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

Local implementation currently satisfies items 1-6 with `303 passed`, Ruff
clean, Mypy clean across 68 source files, zero runtime file-authority findings,
and one clean 33-table `0001_initial` rebuild. The Owner has authorized Tokyo
cutover and controlled real-funds acceptance; no Tokyo mutation is claimed by
this local evidence.

## Exchange-Write Hard Stops

Wrong identity, invalid account mode, stale facts, same-domain occupancy,
missing budget, missing protection, duplicate command, unknown outcome,
code/schema mismatch, old-writer overlap, credential mutation, withdrawal,
transfer, and official-path bypass all fail closed.
