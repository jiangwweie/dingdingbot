---
title: P0_TRADING_KERNEL_REBUILD_DESIGN
status: CURRENT
program_id: P0-TKR
last_verified: 2026-07-31
---

# P0 Trading Kernel Rebuild Design

## Decision

The repository and Tokyo runtime use one multi-position Trading Kernel and one
unbranched PostgreSQL revision chain. A flat, exact, forward-only migration may
preserve terminal history between certified revisions. There is no active-
position schema handover, dual write, old-schema reader, fallback, or alternate
execution chain.

## Authoritative Chain

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

Strategy code ends at `StrategySignal`. It cannot assign account capital,
create a Ticket, write to the exchange, or mutate lifecycle state.

## Core Invariants

1. One Exposure Episode owns exactly one immutable Ticket.
2. Adding to an existing position is forbidden.
3. One Ticket may produce only one ENTRY command generation.
4. New ENTRY admission is globally serialized.
5. Existing protected Tickets progress concurrently.
6. One active Ticket is allowed per Netting Domain:
   `venue + account + instrument + position_side`.
7. Long and short are independent Netting Domains and may coexist by default.
8. Multi-position is architectural; policy may bound capacity without changing
   the model.
9. Authoritative ENTRY rejection is terminal and is not retried.
10. Unknown exchange outcome is reconciled and never blindly resent.
11. Partial ENTRY fill is an Incident followed by exact remainder cancellation
    and controlled flatten.
12. Strategy kill occurs only after exposure is flat and terminal.
13. Binance raw order responses are consumed only through frozen typed protocol
    snapshots and exact frozen-command identity validation.
14. Trade Review facts are append-only revisions; the Aggregate `review_id`
    points to the sole current effective revision.
15. Every terminal Ticket transition atomically materializes
    `owner:ticket:<ticket_id>` as the canonical completed Owner projection.
16. Readonly interfaces never create, update, or refresh runtime projections.

## Code And Data Ownership

```text
src/trading_kernel/domain         pure lifecycle and identity rules
src/trading_kernel/application    typed use cases and ports
src/trading_kernel/infrastructure PostgreSQL and venue adapters
src/trading_kernel/interfaces     bounded runtime and readonly surfaces
```

The tracked database head is `0002_sor_v3_strategy_group_capacity`; the frozen
`0001_trading_kernel_baseline_v4` definition remains only as the source schema
for the certified forward revision. PostgreSQL owns current runtime truth and
append-only lifecycle facts. Exchange readonly facts own external truth.
Repository documents and generated output never own production decisions.

Strategy Registry owns only immutable Event semantics. PostgreSQL
StrategyUniverse owns each Event's unordered **1..10** member set,
certification, Warming/Active/Retired lifecycle and current pointer. Warming
scopes read facts but emit no Signal; only exact Active members can emit a new
Signal. Signal, Claim and Ticket freeze Universe version/digest; replacement
never rewrites an existing protected Ticket.

## Signal, Capacity, And Ticket Boundary

`StrategySignal` freezes exact strategy, version, Event, scope, instrument,
side, occurrence, expiry, and immutable Fact lineage. Ingestion validates
Registry identity, runtime scope, current Fact equality, freshness, and schema
identity, then records readiness without capital authority.

At action time, deterministic arbitration selects a bounded candidate. Current
Owner Policy, account mode, balance, margin, reservations, instrument rules,
Netting Domain occupancy, entry price, stop plan, and stop risk produce an
immutable `CapacityClaim`.

The Entry worker revalidates the Claim and atomically commits the Ticket,
budget reservation, Netting Domain hold, aggregate, first event, and durable
ENTRY command. Two Signals may coexist, but their Tickets are issued serially.

## Dynamic Policy Boundary

`RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` owns the approved capacity,
stop-risk, margin-utilization, leverage, and margin-mode values. Capacity is
calculated from current account facts and Reservations, not from fixed
per-Ticket notional amounts. `new_entry_submit_enabled` gates only new ENTRY;
after venue exposure exists, the frozen Ticket retains protection, exit,
reconciliation, Settlement, and Review authority.

The production account uses one fixed exchange leverage configuration for every
supported instrument. The Owner Policy leverage value is an absolute safety
ceiling, not a per-Ticket leverage selector. Capacity freezes the
exchange-configured fact, never emits a leverage-mutation command, and ENTRY
revalidates that same fact immediately before dispatch. A regular deployment is
blocked when any supported instrument differs from the approved profile.

An eligible Ticket uses current remaining executable margin only within the
Owner-approved per-Ticket and gross stop-risk and initial-margin ceilings owned
by `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md`. The system does not divide
capital into equal fixed slots: the first two Tickets may reach their full
risk target, while a third uses only the remaining risk and margin.
`max_concurrent_tickets` remains a concurrency ceiling rather than a promise of
three equal positions. Current Reservations, available margin, the profile
limits, Initial Stop risk, venue minimums, and liquidation distance still bound
every Ticket. These explicit ticket/gross limits become production truth only
after the active operability repair passes its certified schema deployment.

## Transaction And Exchange Model

Each aggregate mutation uses one short PostgreSQL transaction:

Terminal reductions commit the Ticket/Aggregate terminal state, lifecycle
Event, optional Review revision, and canonical Owner projection in that same
transaction. A projection failure rolls back the whole reduction; a later
readonly request is never used as a repair mechanism.

```text
lock exact current row
-> validate expected version and authority
-> append Trade Event
-> update Aggregate and projections
-> persist Exchange Command or Incident effect
-> commit
```

Venue I/O occurs only after a durable command lease commits. Its result is
recorded in a separate short transaction. Unknown outcomes block redispatch
until exact exchange truth resolves them.

## Runtime Model

Production cadence is owned by four persistent systemd services:

```text
Observation Worker
Entry Worker
Lifecycle Worker
Reconciliation Worker
```

They are long-running processes with bounded polling and restart-on-failure.
Timer-based cold starts are retired because repeated Python import and
initialization cost exceeded the constrained Tokyo host budget. Exact resource
limits and release-time performance checks belong to
`TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`.

Before any exchange mutation, the writer must match the certified runtime commit
and schema. A mismatch creates a runtime-scoped Incident and fences that writer;
readonly observation remains available and the exact certified writer may resume
durable safety work for already-exposed Tickets.

## Destructive Cutover Model

For this cutover, the Owner explicitly authorized no backup of BRC program or
database state. Old BRC services, containers, releases, and PostgreSQL data were
deleted, including the application data volume, then rebuilt from committed
code, the tracked schema head, and deterministic Registry/Policy seed. Non-quantitative
programs and their data were outside scope and had to remain unaffected.

This was a forward-only replacement. The retired application and schema are
not rollback authorities.

## Acceptance

The rebuild is complete only when:

1. the six registered Events can naturally produce typed StrategySignals;
2. current authority can issue serial Tickets and manage concurrent protected
   positions across independent Netting Domains;
3. lifecycle, fault, unknown-outcome, and reconciliation branches are certified;
4. retired code, tests, tables, migrations, deployment units, and current
   document references are absent;
5. the clean baseline rebuilds from empty PostgreSQL;
6. Tokyo runs the exact commit, schema, seed, and four persistent workers;
7. one natural real-funds Ticket reaches terminal exchange-flat state with no
   residual order;
8. budget and domain holds release, Reconciliation matches, Settlement and
   Review complete, and Incident count is zero;
9. `promote-full` passes its hard gates;
10. the final requirement audit finds no unverified requirement or fallback.

Current completion evidence for these acceptance items belongs only to
`MAIN_CONTROL_ROADMAP.md`.
