# Unified P0 Runtime Closure Program Design

> **Status:** Owner-directed unified design; self-reviewed and ready for implementation planning

## 1. Purpose

This design completes three dependent P0 closures as one system program:

1. **P0-1 Execution Eligibility Authority**
2. **P0-2 Durable Exchange Command And Unknown-Outcome Recovery**
3. **P0-3 Multi-Strategy Runtime Supervision, Semantic Admission, And Allocation-Ready Control**

The goal is not to make one current StrategyGroup trade through a local patch.
The goal is to establish a single-Owner, multi-StrategyGroup,
multi-instrument, multi-side execution system that can later absorb additional
asset classes and capital-allocation policies without replacing its authority,
command, lifecycle, or monitoring core.

The current production scope may remain Binance crypto contracts. The core
model must also remain valid for venue-supported equity-linked contracts,
precious-metals contracts, expiring contracts, session-bound instruments, and
future contract asset classes. This design does not grant those products live
scope or assert that a specific product is currently available at a venue.

## 2. Durable Owner Principles

### 2.1 Goal And Decision Ownership

The Owner defines:

- final product objective;
- loss-capable capital scope;
- live venue, account, instrument, side, and runtime-profile scope;
- StrategyGroup enable/pause/retire decisions;
- irreversible production boundaries.

Codex owns:

- architecture and core abstractions;
- task sequencing;
- schema and migration design;
- implementation and negative tests;
- short maintenance-window deployment inside approved scope;
- deletion of obsolete internal compatibility paths.

Ordinary technical choices must not become repeated Owner confirmation gates.

### 2.2 Extension-Ready, Not Speculative

Known dimensions must be first-class and independent:

```text
StrategyGroup
strategy/event version
canonical instrument
asset class
venue
side
runtime profile
Owner policy
allocation policy
ticket
exchange command
lifecycle
review
```

Extension readiness means shared typed abstractions, versioned state, stable
identities, and negative invariants. It does not mean building multi-tenant
permissions, a distributed event platform, generic workflow engines, or
institutional rollout systems without a current requirement.

### 2.3 Aggressive Single-Owner Engineering

Prefer:

- short maintenance windows;
- breaking internal migrations;
- direct replacement of wrong paths;
- deletion of obsolete adapters;
- one current PG authority;
- focused core refactors.

Do not add:

- long-lived dual write;
- rolling-schema compatibility;
- PG + JSON authority;
- multi-user approval systems;
- enterprise gray release machinery.

Aggressive engineering never weakens duplicate-submit, exchange-outcome,
stale-fact, scope, protection, FinalGate, Operation Layer, credential,
withdrawal, or transfer boundaries.

## 3. Current Evidence And Confirmed Gaps

### 3.1 P0-1

The current evaluators emit observe-only signals. Before P0-1, those signals
could enter promotion, action-time lane, ticket, Runtime Safety, and protected
submit state without a typed execution-eligibility envelope.

P0-1 local implementation now adds:

- typed signal grade and execution mode;
- Event Spec maximum authority;
- fail-closed migration 104;
- immutable authority propagation;
- independent rejection at promotion, ticket, Runtime Safety, and protected
  submit;
- correct Owner-facing classification for observe-only evidence.

P0-1 is locally verified and not yet deployed.

### 3.2 P0-2

The current real-submit API already uses the correct high-level transaction
shape:

```text
PG prepare transaction commits
-> exchange call outside the PG transaction
-> PG result transaction commits
```

The remaining gap is command granularity and crash/timeout recovery:

- `submit_prepared` is aggregate attempt state;
- ENTRY, SL, and TP1 commands live primarily inside request/result JSON;
- a network exception is compressed into `exchange_submit_failed` even when the
  exchange may have accepted the order;
- a crash after exchange acceptance but before result persistence leaves an
  unresolved prepared attempt;
- partial command success lacks a durable per-command recovery identity;
- monitor classification does not distinguish fresh prepared work from an
  overdue unknown outcome.

### 3.3 P0-3

Confirmed systemic gaps remain after P0-2:

- process/systemd outcomes can be confused with valid business no-op or blocked
  outcomes;
- current projection ownership validation does not fully prove projection
  freshness and runtime-head alignment;
- Owner monitoring is incomplete for exchange-command and post-submit lifecycle
  states;
- active evaluator semantics are hard-coded observe-only rather than supplied
  by versioned Event Spec capability;
- current promotion arbitration selects one winner but is not yet expressed as
  a versioned allocation-policy decision;
- monitoring and semantic admission must work across every active
  StrategyGroup, instrument, and supported side.

## 4. Alternatives

### Option A: Local Patches

Patch timeout handling, add one monitor notification, and change individual
evaluators from observe-only to trial-live.

**Advantages:** smallest diff.

**Rejected because:** it recreates the same authority and recovery defects for
the next StrategyGroup, instrument, side, or asset class.

### Option B: Extend The Existing PG Core Vertically

Extend the current Event Spec, ticket, protected-submit, lifecycle, projection,
instrument, and monitor abstractions. Add normalized exchange commands and a
versioned allocation decision without replacing the valid existing chain.

**Advantages:** closes the problem classes, reuses current identities and
tables, supports known future dimensions, and avoids a second source of truth.

**Cost:** coordinated migrations and changes across the vertical runtime slice.

**Decision:** selected.

### Option C: New Event-Sourced Trading Platform

Replace the runtime with a generic event bus, workflow engine, allocator, and
new execution service.

**Advantages:** theoretical clean sheet.

**Rejected because:** speculative institutional complexity, unnecessary
operational surface, and duplicate authority during migration.

## 5. Target Architecture

```text
Strategy Asset And Event Semantics
-> Multi-Instrument Candidate Scope
-> Live Fact And Signal Evaluation
-> Execution Eligibility
-> Promotion Candidate Set
-> Allocation Policy Decision
-> Action-Time Lane
-> Ticket / Runtime Safety / FinalGate / Operation Layer
-> Durable Exchange Commands
-> Exchange Outcome Reconciliation
-> Order / Position / Protection Lifecycle
-> Current Projections / Monitor / Owner Explanation
-> Settlement / Review / Strategy Governance
```

Authority remains monotonic:

```text
semantic capability
>= current execution eligibility
>= Owner policy and runtime scope
>= allocation selection
>= action-time safety
>= exchange command authority
```

No later layer may upgrade authority rejected by an earlier layer.

## 6. Multi-Asset Instrument Boundary

The existing core remains authoritative:

```text
brc_symbols
brc_exchange_instruments
brc_symbol_instrument_mappings
exchange_instrument_id
asset_class
```

P0 work must use `exchange_instrument_id` for exchange commands and canonical
symbol/instrument mappings for runtime scope. No string replacement may infer
instrument identity.

Asset-specific facts belong behind versioned instrument and fact contracts.
Core code must not assume:

- 24x7 trading;
- perpetual funding;
- no expiry;
- crypto-style quantity steps;
- USDT settlement;
- identical market sessions;
- identical stop-order or reduce-only support.

When a future asset class is integrated, its required contract/session/expiry/
precision fields extend the existing instrument authority. It must not create a
parallel strategy or execution runtime.

## 7. P0-1 Execution Eligibility Authority

### 7.1 State

P0-1 local implementation is accepted as the foundation. It must be deployed
before P0-2 production use.

### 7.2 Final Invariant

```text
observe-only or invalid signal
-> may remain review evidence
-> cannot create a real-submit promotion
-> cannot create a real-submit lane
-> cannot create an actionable ticket
-> cannot produce submit_allowed
-> cannot prepare or submit a real exchange command
```

### 7.3 Deployment

Single-Owner maintenance-window sequence:

```text
verify no unresolved submitted lifecycle
-> stop watcher / dispatcher / lifecycle timers
-> apply migration 104
-> deploy matching code
-> run read-only schema and state checks
-> restart timers
```

No online compatibility is required.

## 8. P0-2 Durable Exchange Command And Unknown-Outcome Recovery

### 8.1 Core Entity

Migration 105 introduces `brc_ticket_bound_exchange_commands` as a normalized
child of the protected-submit attempt.

One row represents exactly one exchange order command role:

```text
ENTRY
SL
TP1
RUNNER_SL or later recovery role when explicitly authorized
```

Required fields:

```text
exchange_command_id
protected_submit_attempt_id
ticket_id
operation_submit_command_id
account_id
strategy_group_id
runtime_profile_id
order_role
local_order_id
client_order_id
command_generation
exchange_instrument_id
side
request_fingerprint
gateway_order_type
gateway_side
amount
price
trigger_price
reduce_only
command_state
exchange_order_id
exchange_status
outcome_class
dispatch_attempt_count
last_error_class
prepared_at_ms
dispatch_started_at_ms
resolved_at_ms
updated_at_ms
authority_source_ref
```

Financial fields use `Decimal`/PG numeric types.

### 8.2 Command State Machine

```text
prepared
-> dispatching
-> confirmed_submitted
-> confirmed_rejected
-> outcome_unknown
-> reconciled_submitted
-> reconciled_absent
-> hard_stopped
```

Allowed transitions are explicit. `confirmed_rejected` requires an authoritative
exchange rejection. Network errors, timeouts, incomplete responses, and process
interruption never become `confirmed_rejected` or generic `submit_failed`.

### 8.3 Identity And Idempotency

`client_order_id` is deterministic from:

```text
ticket_id
operation_submit_command_id
order_role
command_generation
```

Constraints enforce:

- unique active `client_order_id`;
- one initial command per ticket and order role;
- request fingerprint immutability;
- no new generation while the prior generation is unknown;
- no retry until prior outcome is authoritatively resolved.

P0-2 performs no automatic resubmit after `reconciled_absent`. That resolution
closes the current attempt. A later action requires a current signal, a new
ticket, fresh Runtime Safety, and the official gates again. This avoids using an
old ticket as hidden retry authority.

### 8.4 Transaction Boundary

```text
Transaction A:
  validate ticket graph
  materialize attempt
  materialize all initial exchange command rows
COMMIT

For each command:
  Transaction B: prepared -> dispatching
  COMMIT
  exchange call with bounded timeout
  Transaction C: persist confirmed or unknown outcome
  COMMIT
```

No exchange call occurs inside a DB transaction.

### 8.5 Unknown-Outcome Reconciliation

Any `dispatching` command that exceeds its bounded dispatch window becomes
`outcome_unknown`. Recovery queries exchange truth using the stable identity:

```text
exchange_order_id when known
-> client_order_id
-> open and closed orders
-> recent trades
-> current position and protection state
```

Resolution rules:

- matching exchange order or trade -> `reconciled_submitted`;
- explicit exchange rejection -> `confirmed_rejected`;
- authoritative absence plus no trade/position evidence after the configured
  reconciliation window -> `reconciled_absent`;
- contradictory or incomplete evidence -> remain unknown or `hard_stopped`;
- unknown state freezes new submit for the exact
  `account + StrategyGroup + instrument + side` scope.

No unknown exchange-only order is automatically cancelled or adopted.

### 8.6 Partial Sequence

ENTRY, SL, and TP1 resolve independently. Aggregate protected-submit state is
derived from command truth:

| Command truth | Aggregate result |
| --- | --- |
| ENTRY rejected before acceptance | entry rejected; no position lifecycle |
| ENTRY unknown | exact-scope hard freeze and reconcile |
| ENTRY submitted, SL unknown | unprotected-position emergency lifecycle |
| ENTRY and SL submitted, TP1 rejected/unknown | protected but degraded lifecycle |
| all required commands confirmed | submitted lifecycle may continue |

### 8.7 Existing Core Integration

P0-2 extends rather than replaces:

- `brc_ticket_bound_protected_submit_attempts` as aggregate attempt;
- deterministic local order IDs;
- `OrderLifecycleService` as local order state owner;
- `ExchangeGateway` as venue communication boundary;
- current lifecycle safety and scope-freeze machinery;
- `brc_state_transition_events` for append-only transition audit.

Submit request/result JSON remains audit detail only. Runtime recovery reads the
normalized command rows.

## 9. P0-3 Multi-Strategy Runtime Supervision, Semantic Admission, And Allocation

### 9.1 Process Outcome Is Not Business Outcome

Migration 106 introduces or extends one PG current projection for runtime
process outcomes. Each process run records:

```text
process_name
scope_key
run_id
process_state
business_state
first_blocker
started_at_ms
completed_at_ms
runtime_head
source_watermark
projector_owner
updated_at_ms
```

`process_state` distinguishes:

```text
succeeded
noop
business_blocked
retryable_failure
hard_failure
```

Valid market wait, observe-only evidence, no eligible promotion, and an exact
business blocker are successful process runs. They must not become systemd
failure or restart storms.

### 9.2 Projection Ownership And Freshness

Each current projection has one writer owner. Validation must prove:

- registered owner matches actual projector;
- projection timestamp satisfies its cadence SLA;
- source watermark is not older than required upstream state;
- runtime head matches the deployed runtime head;
- cross-StrategyGroup or cross-instrument Runtime Safety refs are rejected;
- generated JSON/MD is not read as current state.

Stale monitor cache remains a reporting refresh condition, not a trading gate.

### 9.3 Server Monitor Coverage

The existing Tokyo monitor remains the production Owner notification path. It
must read PG current state and cover:

- process liveness and process failure;
- execution-eligibility blocker;
- promotion/lane/ticket progression;
- durable exchange command unknown/overdue/hard-stop;
- submitted but unprotected position;
- post-submit reconciliation and recovery overdue;
- settlement/review closure;
- current projection freshness.

Owner-facing states remain product states:

```text
running
waiting_for_opportunity
processing
temporarily_unavailable
needs_intervention
paused
completed
```

Internal blocker codes stay in audit detail.

### 9.4 Full Active Strategy Semantic Admission

P0-3 audits every current active event:

```text
CPM-LONG
MPG-LONG
MI-LONG
SOR-LONG
SOR-SHORT
BRF2-SHORT
```

For every active `StrategyGroup + candidate instrument + supported side`, the
implementation must bind:

- StrategyGroup version;
- Event Spec version;
- time authority;
- RequiredFacts version;
- evaluator capability grade;
- execution-eligibility state;
- protection reference;
- runtime profile and Owner policy;
- replay/live parity evidence;
- explicit unsupported-side rejection.

Evaluator capability must come from the versioned semantic binding supplied by
the application layer. A pure evaluator may express the bound capability but
cannot read policy or authorize itself. The watcher still independently checks
the output against the Event Spec.

Each event receives one machine conclusion:

```text
trial_grade_capable
observe_only_by_design
semantics_incomplete
facts_incomplete
strategy_quality_blocked
safety_blocked
```

Completing semantics does not automatically enable live submit. Current
eligibility, Owner policy, allocation, and action-time safety remain separate.

### 9.5 Allocation Policy V0

Current promotion arbitration becomes an explicit versioned allocation policy,
not a hard-coded permanent single-strategy assumption.

Migration 106 introduces:

```text
brc_allocation_decisions
allocation_decision_id
allocation_policy_version
max_new_action_time_lanes
selected_candidate_count
capital_scope_ref
created_at_ms
```

Promotion candidates carry:

```text
allocation_decision_id
allocation_rank
requested_risk_at_stop
allocated_risk_at_stop
allocation_state
```

V0 policy:

- consumes all current eligible promotion candidates;
- selects at most one new action-time lane;
- allocates only inside current Owner capital scope;
- uses risk-at-stop reservation;
- never upgrades signal, policy, or Runtime Safety authority;
- records why other eligible candidates were deferred.

Future policies may select more than one lane or allocate across asset classes
without changing Event Spec, signal, ticket, exchange-command, or lifecycle
contracts.

## 10. Data Flow

```text
wide multi-instrument observation
-> per-event evaluator capability
-> watcher Event Spec validation
-> execution-eligible live signal
-> promotion candidate set
-> allocation decision v0
-> one action-time lane
-> ticket / facts / budget / protection
-> FinalGate / Operation Layer
-> durable exchange commands
-> confirmed or reconciled command outcomes
-> lifecycle / protection / reconciliation / settlement / review
-> PG current projections
-> Tokyo monitor and Owner explanation
```

## 11. Performance And Cadence

### No-Signal Cadence

- zero JSON/MD files;
- zero exchange-command rows;
- current readiness/process projections update only at their existing bounded
  cadence;
- no heavy full-history builder.

### Submit Cadence

- at most one allocation decision for a promotion arbitration cycle;
- normally three initial command rows per ticket: ENTRY, SL, TP1;
- one short transaction before and after each exchange call;
- every network call timeout-bounded;
- unknown reconciliation runs only while unresolved commands exist.

### Storage And Retention

- current projections remain bounded one-row-per-key;
- exchange commands and state transitions are durable trade lineage;
- no recurring report files;
- history cleanup is explicit archive/retention work and never deletes unresolved
  lifecycle evidence.

## 12. Implementation Order

### Stage 1: P0-1 Deploy And Verify

Deploy migration 104 and matching code in a maintenance window. Verify all
existing Event Specs and signals are fail-closed observe-only unless explicitly
versioned later.

### Stage 2: P0-2

Implement migration 105, normalized exchange commands, per-command executor,
unknown reconciliation, exact-scope freeze, and monitor visibility.

### Stage 3: P0-3

Implement migration 106, process outcome separation, projection freshness,
monitor lifecycle coverage, active event semantic admission, and Allocation
Policy V0.

Core execution files are changed sequentially, never by concurrent workers.

## 13. Test Strategy

### P0-1

- observe-only signal cannot progress at every boundary;
- eligible fixture still reaches disabled smoke;
- grade/mode/source mismatch fails closed;
- migration backfills all existing rows.

### P0-2

- command rows commit before gateway call;
- deterministic identity and fingerprint;
- explicit rejection;
- network timeout with exchange acceptance;
- crash before call;
- crash after call before result persistence;
- ENTRY accepted and SL unknown;
- ENTRY/SL accepted and TP1 unknown;
- duplicate runner invocation;
- restart recovery;
- contradictory exchange truth hard stop;
- no exchange call inside DB transaction.

### P0-3

- business no-op returns process success;
- process failure remains distinct and notifies;
- stale/cross-scope projection rejected;
- monitor covers unknown command and post-submit overdue states;
- all active Event Specs have a machine semantic conclusion;
- unsupported side mirroring rejected;
- multi-instrument identity uses canonical mappings;
- Allocation Policy V0 selects at most one lane;
- allocation cannot upgrade eligibility or exceed Owner capital scope;
- future multi-select policy can be introduced without ticket schema replacement.

### Global

- production runtime file-I/O audit clear;
- output artifact scope valid;
- migration chain single head;
- focused unit/integration suite;
- full affected runtime suite;
- read-only Tokyo postdeploy verification.

## 14. Rollback And Maintenance

This single-Owner system uses maintenance-window rollback:

- stop timers;
- do not downgrade past a migration that has unresolved command/lifecycle rows;
- roll application back only when the old code can safely read the migrated
  schema;
- otherwise apply a forward repair migration;
- never delete unknown command or submitted lifecycle evidence;
- restart only after read-only invariant checks pass.

No dual-write rollback path is introduced.

## 15. Acceptance And Stop Conditions

### P0-1 Complete

All observe-only evidence is structurally excluded from real submit and Tokyo
is running migration 104 code.

### P0-2 Complete

Every exchange command reaches one of:

```text
confirmed_submitted
confirmed_rejected
reconciled_submitted
reconciled_absent
hard_stopped
```

An unknown outcome never creates a duplicate order.

### P0-3 Complete

- every active StrategyGroup/instrument/side row has an exact semantic and
  readiness conclusion;
- current projections have one owner and verified freshness;
- monitor distinguishes business wait, process failure, command unknown,
  lifecycle processing, and Owner intervention;
- Allocation Policy V0 selects at most one lane without embedding a permanent
  single-strategy assumption;
- no runtime file authority exists;
- remaining blockers are market, explicit Owner policy, strategy quality, or
  live-only outcome calibration.

## 16. Owner Decision Boundary

No Owner decision is required for the architecture, schemas, migrations,
refactors, tests, short downtime, or deployment mechanics described here.

Owner confirmation remains required only for:

- new live venue/account/instrument/side scope;
- expanded capital or sizing defaults;
- enabling execution eligibility for a specific production Event Spec when the
  change expands current live authority;
- multi-lane live-submit policy activation;
- irreversible production evidence deletion;
- credential, withdrawal, or transfer changes.

The multi-asset vision is a design constraint, not current live authorization.

## 17. Design Uncertainty Assessment

No Owner-level uncertainty blocks implementation.

The following are implementation facts to discover, not product choices:

- exact venue query capabilities for client-order identity reconciliation;
- asset-class-specific session, expiry, precision, and protection facts when a
  new instrument class is actually integrated;
- which current Event Specs earn trial-grade capability after semantic and
  replay/live parity tests.

These facts are handled fail-closed. They do not require speculative design or
delay P0-2/P0-3 infrastructure work.
