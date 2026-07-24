---
title: P0_TRADING_KERNEL_REBUILD_DESIGN
status: DEPLOYED_ACCEPTANCE_ACTIVE
program_id: P0-TKR
last_verified: 2026-07-24
---

# P0 Trading Kernel Rebuild Design

## Decision

The repository and Tokyo runtime use one multi-position Trading Kernel and one
clean PostgreSQL baseline. There is no compatibility migration, dual write,
retired-runtime fallback, or alternate execution chain.

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

## Code And Data Ownership

```text
src/trading_kernel/domain         pure lifecycle and identity rules
src/trading_kernel/application    typed use cases and ports
src/trading_kernel/infrastructure PostgreSQL and venue adapters
src/trading_kernel/interfaces     bounded runtime and readonly surfaces
```

The only database baseline is
`migrations/trading_kernel/versions/0001_initial.py`. PostgreSQL owns current
runtime truth and append-only lifecycle facts. Exchange readonly facts own
external truth. Repository documents and generated output never own production
decisions.

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

## Approved Dynamic Policy

The committed runtime seed defines one policy envelope: three concurrent
Tickets, `0.03` planned stop-risk fraction, `0.90` maximum initial-margin
utilization, maximum leverage `10`, and `cross` margin mode. Capacity is
calculated from current account facts and Reservations, not from fixed per-Ticket
notional amounts. `new_entry_submit_enabled` gates only new ENTRY; after venue
exposure exists, the frozen Ticket retains protection, exit, reconciliation,
Settlement, and Review authority.

## Transaction And Exchange Model

Each aggregate mutation uses one short PostgreSQL transaction:

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
Timer-based cold starts are retired because idle Python import and initialization
cost exceeded the 2c4g Tokyo budget.

Before any exchange mutation, the writer must match the certified runtime commit
and schema. A mismatch creates a runtime-scoped Incident and fences that writer;
readonly observation remains available and the exact certified writer may resume
durable safety work for already-exposed Tickets.

## Destructive Cutover Model

For this cutover, the Owner explicitly authorized no backup of BRC program or
database state. Old BRC services, containers, releases, and PostgreSQL data were
deleted, including the application data volume, then rebuilt from committed
code, `0001_initial`, and deterministic Registry/Policy seed. Non-quantitative
programs and their data were outside scope and had to remain unaffected.

This was a forward-only replacement. The retired application and schema are
not rollback authorities.

## Current Deployment Evidence

| Evidence | Current value |
| --- | --- |
| Tokyo commit | `44c3d7a00e2250689295d597ba8e05a675c16fc5` |
| Local certification | `401 passed`; current-document and file-I/O audits pass |
| Runtime services | **Acceptance-armed**: Observation, Lifecycle, and Reconciliation active; Entry disabled pending leverage-mutation diagnosis |
| Natural acceptance flow | Natural `SOR-001 / ETHUSDT / long` reached the durable leverage safety branch |
| Ticket | `ticket:e5c125d947e36f906b03f76dbea35b56` |
| Verified lifecycle state | Terminal `leverage_rejected`; exchange flat with no order; Incident resolved |
| Full runtime promotion | `promote-full` pending |

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

Items 1-6 are deployed and locally certified. The first natural Ticket proved
the unknown-leverage recovery path and terminated safely before ENTRY. A
protected real-funds lifecycle remains required for Items 7-10.
