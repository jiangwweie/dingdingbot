---
title: P0_TRADING_KERNEL_REBUILD_DESIGN
status: CURRENT
program_id: P0-TKR
last_verified: 2026-08-11
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

The forward schema chain is `0001_trading_kernel_baseline_v4 ->
0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability ->
0004_owner_control_plane -> 0005_tradfi_instrument_center`.
The frozen `0001_trading_kernel_baseline_v4` definition remains historical
source lineage only. PostgreSQL owns current runtime truth and append-only
lifecycle facts. Exchange readonly facts own external truth. Repository
documents and generated output never own production decisions.

Strategy Registry owns only immutable Event semantics. PostgreSQL
StrategyUniverse owns each Event's unordered **1..10** member set,
certification, Warming/Active/Retired lifecycle and current pointer. Warming
scopes read facts but emit no Signal; only exact Active members can emit a new
Signal. Signal, Claim and Ticket freeze Universe version/digest; replacement
never rewrites an existing protected Ticket.

Product Compatibility is an immutable Registry-side contract, while Product
Profile, Session and bounded market status are PostgreSQL current projections.
Crypto and TradFi Events cannot share an incompatible Universe member. The
independent `SOR-US-EQ-PERP-001` Profile and Policy are observation-only;
their existence does not expand the main Crypto Policy or grant Entry.

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

Every final candidate also owns one immutable `AdmissionDecision`. An admitted
Decision commits with the CapacityClaim, Ticket, Reservation, Netting Domain
hold, aggregate, TicketIssued Event, and ENTRY Command. A rejected Decision
commits with its terminal readiness blocker and has no Ticket, Reservation, or
Exchange Command. `Shadow Outcome` is Signal-owned read-only path evidence. It
supports both an eligible portfolio rejection and a strategy observation when
Admission is intentionally not run. It never creates CapacityClaim, Ticket,
Reservation, Command dispatch, simulated PnL, or venue-write authority.

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

Policy v4 owns three concurrent Tickets, `0.02` maximum planned stop risk per
Ticket, `0.06` gross stop risk, `0.30` initial margin per Ticket, `0.90` gross
initial-margin utilization, `0.50` minimum materialization, and `0.04`
directional stop risk. Registry Events freeze an Exposure Family; Owner Policy
limits `long_continuation=1`, `opening_range=2`, and
`rally_failure_short=1`. StrategyGroup capacity is not current admission
authority. Current Reservations, available margin, Initial Stop risk, venue
minimums, and liquidation distance still bound every Ticket.

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

## Migration And Historical Cutover Model

The initial rebuild used an explicitly authorized no-backup replacement of BRC
program and database state. That completed operation is historical evidence,
not the default release model. Current schema evolution uses exact, stopped,
flat, forward-only migrations that preserve certified terminal lineage. Active
position handover, dual writes, old-schema readers, fallback, and runtime
compatibility adapters remain forbidden. Retired applications and schemas are
not rollback authorities.

## Acceptance

The rebuild is complete only when:

1. the six approved Crypto Events can naturally produce typed StrategySignals
   in their approved Product scope;
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
