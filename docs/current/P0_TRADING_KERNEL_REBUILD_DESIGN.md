---
title: P0_TRADING_KERNEL_REBUILD_DESIGN
status: OWNER_APPROVED_IMPLEMENTATION
authority: docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md
program_id: P0-TKR
last_verified: 2026-07-22
owner_policy_change: none
exchange_write_authority: unchanged_until_certified_cutover
supersedes_on_cutover:
  - legacy ExecutionOrchestrator / OrderLifecycleService execution path
  - runtime_execution_* shadow execution model
  - current stage-table-heavy action_time ticket lifecycle implementation
---

# P0 Trading Kernel Rebuild Design

## 1. Decision

The project will replace the current three-generation execution implementation
with one new trading kernel. This is not an in-place cleanup and not a
compatibility migration.

```text
freeze old runtime
-> build a new isolated kernel and new PostgreSQL baseline
-> certify the complete multi-position lifecycle offline
-> prove production is flat and quiescent
-> stop all writers
-> delete the old program and old schema
-> create and seed the new schema
-> deploy the new runtime
-> restore capabilities in stages
-> run one controlled real-funds acceptance lifecycle
```

The development branch may contain old and new code temporarily for behavioral
comparison. Production never dual-writes and never treats both models as
authority.

## 2. Owner Decisions

The following decisions are final and override historical implementation tests,
stale designs, compatibility behavior, and archived data.

1. Full application downtime is allowed.
2. The old application may be deleted completely.
3. The PostgreSQL schema may be dropped and recreated.
4. A new Alembic baseline replaces the current incremental history.
5. Old experimental history has no product value and is not migrated.
6. Old test semantics are not acceptance authority.
7. One Exposure Episode owns exactly one Ticket.
8. Adding to an existing position is forbidden.
9. One active Ticket is allowed per `account + instrument + position_side`.
10. Long and short Tickets may coexist by default and require no product toggle.
11. Supported accounts must expose independent long/short position sides.
12. A rejected ENTRY is never retried.
13. Normal partial-fill lifecycle support is out of scope. A reported partial
    fill is an abnormal incident and is flattened through the controlled exit
    path after the remainder is cancelled.
14. Strategy kill is allowed only after the Owner has already closed exposure
    and the system proves the scope is flat and terminal.
15. New ENTRY Action-Time work is globally serialized; protected existing
    Tickets may run lifecycle work concurrently.
16. The remaining decisions use the recommendations recorded in the 2026-07-22
    Owner/Codex architecture dialogue.

## 3. Objective

The completed system must provide:

```text
multi-StrategyGroup observation
+ multi-instrument and multi-side candidacy
+ globally serialized new ENTRY admission
+ multiple concurrently protected Tickets and positions
+ durable exchange command execution
+ protection, exit, reconciliation, settlement, and review
+ one readable current truth
+ one minimal PostgreSQL authority model
```

Completion requires the new system to operate without importing, querying,
calling, or falling back to the old execution model.

## 4. Current Objective Facts

As observed on 2026-07-22:

| Fact | Current value | Consequence |
| --- | ---: | --- |
| Traditional core execution files | more than 10,800 lines | In-place cleanup does not remove the mixed ownership model |
| `runtime_execution_*` code family | about 21,905 lines | A retired shadow execution generation remains in the repository |
| `src/application/action_time/` | about 50,937 lines | The current Ticket generation has already accumulated excessive stage logic |
| Tokyo PostgreSQL tables | 187 | Operational truth and historical stages are over-modelled |
| Exact-empty Tokyo tables | 64 | Many inactive capabilities remain in the production schema |
| Tokyo database table/index size | about 742 MB | Current/history projection growth dominates storage |
| Local Alembic head | 146 | The current incremental chain is no longer the target baseline |
| Tokyo runtime/schema | `8c61a208` / 143 | Tokyo remains on the old runtime until destructive cutover |

Sources: tracked source, Alembic, and read-only Tokyo PostgreSQL/systemd checks.

## 5. Authority Model

The global product authority remains:

```text
Owner controls policy.
System executes process.
Tradeability answers can-trade.
Runtime safety answers may-write-now.
Review updates strategy governance.
```

The rebuilt kernel narrows technical ownership further:

| Fact | Single owner |
| --- | --- |
| Strategy and event semantics | Strategy Registry |
| Owner capital and scope | Owner Policy |
| Current fact satisfaction | Readiness Projector |
| One proposed exposure | Trade Ticket |
| One current exposure lifecycle | Trade Aggregate |
| One external side effect | Exchange Command |
| What happened | Trade Event |
| Current venue position truth | Position Current Projector |
| Abnormal unresolved state | Runtime Incident |

No lower layer may create or upgrade authority that was not frozen into the
Ticket and revalidated by the official gates.

## 6. Core Identity

### 6.1 Ticket identity

One Ticket identifies exactly one Exposure Episode:

```text
ticket_id
+ exposure_episode_id
+ strategy_group_id
+ strategy_version_id
+ event_spec_id
+ account_id
+ runtime_profile_id
+ exchange_instrument_id
+ position_side
+ owner_policy_version
+ signal_event_id
```

The Ticket freezes the complete execution decision. After Ticket creation, the
normal execution path must not rebuild the decision from a wide collection of
promotion, lane, policy, fact, or report tables.

### 6.2 Netting domain

The Netting Domain is:

```text
venue_id
+ account_id
+ exchange_instrument_id
+ position_side
```

There may be one active Ticket per Netting Domain. Long and short are separate
domains and may both be active.

### 6.3 Global new-entry lane

The global new-entry lane serializes only the interval from Action-Time claim
through either:

- protected exposure; or
- proven absence/terminal pre-exposure outcome.

It does not serialize protection, exit, reconciliation, settlement, or review
for already active Tickets.

## 7. Target Code Architecture

The new implementation lives under an isolated package and may not import old
application execution services.

```text
src/trading_kernel/
  domain/
    identities.py
    ticket.py
    aggregate.py
    events.py
    commands.py
    position.py
    incident.py
    reducer.py
    effects.py
  application/
    ports.py
    issue_ticket.py
    advance_ticket.py
    dispatch_exchange_command.py
    reconcile_ticket.py
    settle_ticket.py
    runtime.py
  infrastructure/
    pg_models.py
    pg_unit_of_work.py
    pg_repositories.py
    venue_adapter.py
    runtime_bootstrap.py
  interfaces/
    worker.py
    readonly_api.py
```

### 7.1 Domain

The domain package is pure Python business logic:

- no SQLAlchemy;
- no HTTP or CCXT;
- no filesystem access;
- no logging framework dependency;
- `Decimal` for all financial quantities;
- frozen Pydantic or dataclass inputs with explicit enums;
- deterministic reducer output.

### 7.2 Application

Application services coordinate typed ports and transactions. They do not
contain venue parsing, SQL construction, current-state report generation, or
hidden retry loops.

### 7.3 Infrastructure

Infrastructure owns PostgreSQL and venue translation. Venue-specific rules do
not leak into Ticket or Aggregate identity.

### 7.4 Runtime

The runtime owns one bounded loop:

```text
load one actionable aggregate or durable command
-> run one deterministic application action
-> commit current state and event/command result
-> stop or continue only when the same bounded invocation requires it
```

There is no subprocess/stdout JSON protocol between kernel stages.

## 8. Target PostgreSQL Schema

The new baseline targets fewer than 40 production tables. New tables represent
stable business aggregates, events, commands, current projections, or policy.
They must not represent temporary implementation stages.

### 8.1 Registry and policy

| Table | Responsibility |
| --- | --- |
| `brc_strategy_groups` | StrategyGroup identity and active version |
| `brc_strategy_versions` | Immutable strategy semantics version |
| `brc_event_specs` | Versioned detector/execution event contract |
| `brc_fact_definitions` | Typed RequiredFact definitions |
| `brc_event_required_facts` | Event-to-fact relation |
| `brc_instruments` | Canonical venue-independent instrument identity |
| `brc_instrument_rules_current` | Current venue contract/precision/session rules |
| `brc_owner_policy_events` | Append-only Owner policy changes |
| `brc_owner_policy_current` | Current policy projection |
| `brc_runtime_scopes_current` | Current StrategyGroup/instrument/side/profile scope |
| `brc_runtime_profiles` | Account and execution environment binding |

### 8.2 Observation and admission

| Table | Responsibility |
| --- | --- |
| `brc_facts_current` | Latest typed facts by source and lane |
| `brc_signal_events` | Immutable live signal events |
| `brc_readiness_current` | Current per-lane readiness and first blocker |
| `brc_entry_lane_current` | The one global new-entry claim/current state |
| `brc_runtime_capabilities_current` | Deployed and enabled capability truth |

### 8.3 Trading lifecycle

| Table | Responsibility |
| --- | --- |
| `brc_trade_tickets` | Immutable Ticket decision plus terminal summary |
| `brc_trade_aggregates` | Current lifecycle projection for one Ticket |
| `brc_trade_events` | Append-only lifecycle audit events |
| `brc_exchange_commands` | Durable exactly-once venue side effects |
| `brc_positions_current` | Current exchange position projection by Netting Domain |
| `brc_budget_reservations` | Ticket-bound capital reservation |
| `brc_account_exposure_current` | Account-level gross exposure projection |
| `brc_runtime_incidents` | Current and historical unresolved abnormalities |
| `brc_trade_reviews` | Terminal strategy/lifecycle review outcome |

### 8.4 Operations

| Table | Responsibility |
| --- | --- |
| `brc_monitor_current` | Current Owner-facing runtime state |
| `brc_monitor_events` | Material notification/incident transitions only |
| `brc_retention_runs` | Bounded retention execution audit |
| `brc_schema_metadata` | Baseline and seed identity |

Read-model JSON/Markdown files are exports only and are not required by the new
runtime.

## 9. Transaction Model

### 9.1 One aggregate mutation

Every aggregate transition uses one PostgreSQL transaction:

```text
lock aggregate/current claim
-> validate expected version
-> append one or more Trade Events
-> update Aggregate Current
-> create/update required Exchange Commands
-> update budget/exposure/incident projection when required
-> commit
```

### 9.2 External I/O

No database transaction remains open during exchange network I/O:

```text
claim durable command in short transaction
-> commit lease
-> call venue outside transaction
-> record authoritative result in short transaction
-> reduce result into aggregate/events/effects
```

### 9.3 Exactly once

`brc_exchange_commands` has unique constraints for:

- `command_id`;
- `idempotency_key`;
- deterministic venue client order identity;
- Ticket + command role + generation.

Unknown results block a new command generation until exchange absence or the
original effect is proven.

## 10. Testing Authority

The new test suite is written from this design and later accepted corrections.
Old tests are evidence inputs only.

### 10.1 Retain by rewrite

- real-funds safety invariants;
- idempotency and unknown-outcome behavior;
- identity conservation;
- protection and exit correctness;
- restart and reconciliation behavior;
- multi-position isolation;
- database constraints;
- file-authority prohibition.

### 10.2 Delete

- tests of old class names, tables, callbacks, packet/proof artifacts, or
  subprocess protocols;
- tests that require legacy compatibility;
- tests that preserve retired intermediate statuses;
- tests that treat generated JSON/Markdown as runtime authority;
- coverage-only tests with no accepted business invariant.

### 10.3 Test layers

```text
pure reducer tests
-> application port tests
-> PostgreSQL transaction/constraint tests
-> fake venue fault tests
-> restart and duplicate-delivery tests
-> production-shaped full-chain simulation
-> readonly Tokyo/exchange certification
-> one controlled real-funds acceptance lifecycle
```

All new production behavior follows test-first red/green/refactor cycles.

## 11. Deletion Scope

After the new kernel passes offline certification, the current branch deletes
the old implementation before production cutover.

Deletion includes:

- `src/application/execution_orchestrator.py` and its official assembly path;
- old order lifecycle orchestration and callback wiring;
- `runtime_execution_*` application/domain/infrastructure families;
- stage-table-heavy Action-Time implementation replaced by the kernel;
- obsolete repositories and ORM models;
- old runtime CLIs and systemd units;
- old schema migrations and compatibility tests;
- old file/report interfaces;
- old database tables and data during cutover.

Generic utilities are retained only when they have no old business semantic and
are imported through a stable, small interface.

## 12. Cutover

Cutover requires:

```text
exchange positions = flat
exchange open orders = none
exchange protection orders = none
old Tickets = terminal
old budgets = released
reconciliation = matched
all production writers = stopped and fenced
```

The destructive sequence is:

1. stop watcher, lifecycle, monitor writers, API writers, and command workers;
2. run final signed read-only venue and PostgreSQL verification;
3. take one short-lived operational rollback snapshot;
4. drop the old application schema;
5. install the new Alembic baseline;
6. seed current registry, policy, instrument, account, and runtime scope rows;
7. deploy the exact rebuilt runtime commit;
8. verify the schema, code identity, PG permissions, and readonly runtime;
9. enable observation and current projections;
10. enable non-writing Action-Time certification;
11. enable exchange-command capability only after all prior checks pass;
12. run one bounded real-funds Ticket through terminal review;
13. remove the operational rollback snapshot and old deployment releases.

No old program or schema is restored as a production fallback after the new
schema is accepted. Failures are fixed forward while exchange-write capability
remains disabled.

## 13. Performance And Retention

- no-signal cadence creates zero JSON/Markdown files;
- current fact/readiness/coverage state is upserted rather than appended;
- Trade Events and Exchange Commands are append-only audit facts;
- normal healthy monitor and reconciliation cycles do not append full snapshots;
- network and subprocess work is timeout-bounded;
- there is no production full-schema reflection or full-state scan;
- archive/export work is manual, bounded, and outside runtime cadence.

## 14. Acceptance

The rebuild is complete only when all are true:

1. multiple protected Tickets can coexist across distinct Netting Domains;
2. long and short can coexist for one instrument without cross-mutation;
3. new ENTRY work is globally serialized;
4. the new kernel completes Ticket-to-review without old code;
5. protection, exit, recovery, reconciliation, and settlement are certified;
6. all new behavior is covered by new-authority tests;
7. old execution model imports and table references are zero;
8. the new database is created from one clean baseline;
9. runtime file authority and recurring file writes are zero;
10. Tokyo is running the exact rebuilt commit and schema;
11. one controlled real-funds lifecycle reaches terminal review;
12. final requirement-by-requirement audit finds no compatibility fallback or
    unverified required behavior.

## 15. Hard Stops

Even with full DB/server/real-funds authorization, the rebuild must stop before
exchange write when any of these are true:

- wrong account, venue, instrument, side, or runtime profile;
- account is not in independent long/short mode;
- stale or contradictory action-time facts;
- active same-Netting-Domain Ticket, position, order, or hold;
- missing budget or protection plan;
- duplicate or unknown exchange command outcome;
- missing Initial Stop after exposure;
- FinalGate or Operation Layer bypass;
- production schema/code identity mismatch;
- credential mutation, withdrawal, or transfer requirement.

