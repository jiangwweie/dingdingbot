---
title: TP1 Runner And Protected Handover Structural Repair Design
status: LOCAL_IMPLEMENTED_DEPLOYMENT_PENDING
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-28
revision: 3
---

# TP1 Runner And Protected Handover Structural Repair Design

## Decision Gate

The Owner approved the target behavior and authorized local implementation
after test-first RED coverage. Local production-code changes are complete; this
document does not authorize Tokyo deployment, Tokyo database mutation, or
exchange mutation.

Current tracked code, PostgreSQL and exchange readonly facts, and
`docs/current/*` remain authoritative until implementation is separately
approved, certified, committed, and deployed.

## Objective

Make the normal Trading Kernel reliably complete this lifecycle:

```text
ENTRY filled
-> Initial Stop confirmed
-> TP1 confirmed
-> exact TP1 target fully filled
-> cost-adjusted break-even Stop requested
-> new Stop confirmed
-> exact prior Stop cancelled
-> runner_protected
-> closed-candle structural trailing
-> monotonic Runner Stop replacements
-> terminal flatness
-> reconciliation
-> settlement
-> review
```

The repair must preserve the system objective: bounded downside and the ability
for a small remaining position to capture asymmetric right-tail returns. It
must not flatten a healthy runner merely to simplify deployment or recovery.

## Scope

| Area | In scope | Out of scope |
| --- | --- | --- |
| TP1 truth | Exact exchange order identity, full-fill proof, remaining quantity | New TP allocation or strategy changes |
| Break-even protection | Cost-adjusted floor, durable replacement, exact old-Stop cancel | Direct database status repair |
| Runner | Closed candles, monotonic movement, restart-safe event reload | New trailing formula or fixed TP2 |
| Protected handover | Exact Ticket manifest, Entry exclusion, phase-aware failure | General active-position deployment |
| Persistence safety | Ticket, Aggregate, Position, Reservation, Exposure, Event parity | New table or compatibility schema |
| Verification | Unit, PostgreSQL integration, full-chain, architecture tests | Real exchange writes |

There is no change to strategy selection, Entry semantics, Ticket sizing,
planned stop risk, fixed exchange leverage, margin mode, instrument scope, or
Owner capital authority.

## Known Facts

### Normal Lifecycle

- The current domain already models `TakeProfitFilled`,
  `RunnerStopRequested`, durable `REPLACE_PROTECTION`, exact old-Stop cancel,
  and `runner_protected`.
- The current adapter reads TP1 truth by persisted exchange order ID.
- The current reducer prepares a replacement before it prepares cancellation
  of the prior Stop.
- BTC and SOL demonstrated that the intended chain can move a live Runner Stop.

### Structural Gaps

- Protected handover currently accepts `--enable-entry`.
- Exchange handover certification compares domain counts rather than exact
  domain, position, and order identities.
- A failed protected postflight can restart Lifecycle even though the protected
  certification did not pass.
- The PostgreSQL handover gate does not prove exact active Reservations or
  exact Account Exposure totals.
- `TradeEvent` and the PostgreSQL event model registry are separate manual
  lists.
- `--tp1-replay-ticket-id` remains a reusable deployment option even though it
  represented one historical recovery condition.

## Alternatives

| Approach | Safety | Complexity | Long-term maintenance | Decision |
| --- | --- | --- | --- | --- |
| Add only three local `if` checks to the deployment script | Medium | Low | Leaves count-only and duplicated authority | Rejected |
| Add one typed exact handover manifest and retain the existing Lifecycle chain | High | Moderate and bounded | One reusable certification boundary | Selected |
| Create a recovery service, recovery table, or second lifecycle state machine | Locally high | High | Parallel authority and permanent operational burden | Rejected |

The selected approach extends the existing Kernel and deployment certification.
It does not add a second exchange path, recovery worker, compatibility adapter,
file-backed authority, or direct business-state repair.

## Canonical-Only Rule

This repair supports only the current Trading Kernel schema, Event set, command
payloads, Aggregate states, and exchange-order identity model. It must not make
the target release understand or translate retired program generations.

The protected handover manifest is a verifier, not a compatibility layer:

- it reads current canonical facts and performs no write or transformation;
- it never maps an old status, Event name, command payload, column, or order
  namespace to a current one;
- it never infers a missing TP1 fill, Budget Reservation, Exposure row, order
  identity, or Event;
- it never tries an old table, field, endpoint, or namespace after a canonical
  lookup fails;
- it never dual-reads or dual-writes current and retired representations;
- it is not persisted and cannot become a second runtime authority.

An active Ticket that cannot satisfy the current canonical invariants blocks
handover. It must converge through the existing source-version Lifecycle and
Reconciliation path, or become flat and terminal before a normal release. The
target release must not coerce, backfill, synthesize, or silently accept it.

The historical `tp1_replay_ticket_ids` branch is deleted without a replacement
alias or projection exception. The existing narrowly scoped leverage-unknown
recovery capability is neither reused nor generalized by this repair.

## Target Lifecycle Semantics

### 1. TP1 Observation

Lifecycle reads one exact persisted TP1 exchange order identity. The venue
response must provide:

- exact exchange order ID;
- instrument and position side;
- full executed quantity;
- positive average fill price;
- terminal filled status;
- observation timestamp.

The decision is:

| Venue truth | Required result |
| --- | --- |
| Filled quantity is zero | No lifecycle mutation |
| Filled quantity is between zero and frozen target | Fail closed as unsupported partial TP1; keep current Stop |
| Filled quantity equals target but remaining position differs | Reconciliation required; keep current Stop |
| Filled quantity equals target and remaining position equals runner quantity | Record `TakeProfitFilled` |
| Filled quantity exceeds target or identity contradicts Ticket | Incident/reconciliation required; no replacement |

The worker must never infer a TP1 fill solely from a reduced account position.

### 2. Cost-Adjusted Break-Even Floor

The first Runner Stop is calculated from the frozen Ticket and exact fee facts:

```text
runner_quantity = entry_quantity - tp1_target_quantity
break_even_floor =
  entry cost allocated to runner
  + exit taker fee allowance
  + configured slippage ticks
```

For a long position, the floor is rounded upward to the venue price tick. For a
short position, it is rounded downward. All calculations use `Decimal`.

`TakeProfitFilled` atomically:

- reduces Aggregate position quantity to the runner quantity;
- records TP1 filled quantity and average price;
- records the cost-adjusted floor;
- changes status to `runner_replacement_pending`;
- materializes one durable `REPLACE_PROTECTION` command.

No network call occurs in this transaction.

### 3. Submit New Stop Before Cancelling Old Stop

Replacement ordering is mandatory:

```text
durably prepare REPLACE_PROTECTION
-> dispatch new reduce-only conditional Stop
-> confirm exact new order ID, side, quantity, and trigger
-> make the new Stop active in the Aggregate
-> durably prepare exact old-Stop cancellation
-> cancel only the prior conditional Stop identity
-> confirm prior Stop absent
-> runner_protected
```

No path may cancel the last confirmed Stop before a replacement is confirmed.
If new placement is rejected or unknown, the old Stop remains active. If old
cancel fails, both reduce-only Stops may remain temporarily visible while only
the exact old identity is retried.

### 4. Runner Tracking

Only `runner_protected` Tickets are eligible. Evaluation uses the immutable
Exit Policy and fully closed candles:

```text
long:
  candidate = structure_low - ATR buffer
  move only when candidate > current Stop

short:
  candidate = structure_high + ATR buffer
  move only when candidate < current Stop
```

An open candle, repeated candle watermark, insufficient ATR window, stale
facts, or a non-improving candidate creates no replacement command. The
existing confirmed exchange Stop remains active.

Every accepted movement records `RunnerStopRequested` and creates a new durable
replacement generation. Event reload after process restart must reconstruct the
same Aggregate and must not duplicate the generation.

### 5. Terminal Closure

When the runner becomes flat:

```text
exact position flat
-> exact residual-order cleanup
-> ReconciliationMatched
-> Budget Reservation and Netting Domain release
-> Settlement
-> Review with attributable TP1 and runner economics
```

The Review must retain exact TP1 and final runner fills. No DML-created status
or fabricated zero economics is allowed.

## Protected Handover Redesign

### Decision

Protected handover remains an emergency fix-forward capability for a named,
already-consistent protected Ticket set. It is not a normal release mode.

The generic `--tp1-replay-ticket-id` option is retired. Future TP1 recovery must
occur through exact Lifecycle and Reconciliation truth, not through a
deployment projection exception.

### Typed Handover Manifest

One read-only certification use case builds a frozen manifest:

```text
ProtectedHandoverManifest
  source_runtime_commit
  schema_revision
  account_id
  observed_at_ms
  tickets[]
  semantic_digest

ProtectedHandoverTicket
  ticket_id
  netting_domain
  aggregate_status
  position_quantity
  protected_quantity
  active_stop_order
  tp1_order | recorded_tp1_fill
  budget_reservation
```

For `position_protected`:

- position quantity equals Aggregate position and protected quantity;
- one exact active conditional Stop exists for the full quantity;
- one exact active TP1 exists for the frozen target quantity;
- no extra owned protection order exists.

For `runner_protected`:

- position quantity equals remaining runner and protected quantity;
- one exact active conditional Runner Stop exists for the full runner quantity;
- TP1 fill is recorded and no active TP1 order remains;
- no prior Stop remains open.

Every order comparison includes exchange order ID, instrument, position side,
order side, quantity, reduce-only flag, namespace, and trigger/limit price.
Counts are display-only and cannot authorize handover.

### PostgreSQL Exactness

While all workers are stopped, one short PostgreSQL transaction locks and
rechecks:

1. exact nonterminal Ticket set equals the named set;
2. each Ticket owns its exact active Netting Domain;
3. each Aggregate has complete protection and no pending mutation;
4. each non-flat Position belongs to one named Ticket and has exact quantity;
5. each named Ticket has exactly one active Budget Reservation;
6. Reservation notional, risk, margin, policy, venue, and account equal the
   frozen Ticket;
7. Account Exposure equals the sum of active Ticket notional and stop risk;
8. global Entry lane is idle;
9. unresolved Exchange Command count is zero;
10. open Ticket and runtime Incident count is zero;
11. runtime profile, policy, Registry, schema, and seed identities are
    unchanged.

Only runtime commit and capability certification commit are rotated.

### Deployment Phases

```text
Phase 0: install committed target release
Phase 1: exact source manifest and readonly exchange certification
Phase 2: stop all four workers and write Entry fence
Phase 3: repeat exact source certification with workers stopped
Phase 4: atomically recheck PostgreSQL and rotate runtime identity
Phase 5: activate target release while every worker remains stopped
Phase 6: run exact target certification directly from target release
Phase 7: start Observation, Lifecycle, and Reconciliation
Phase 8: verify exact service identity and readonly runtime facts
Phase 9: finish with Entry still fenced
```

`protected_ticket_ids` and `enable_entry` are mutually exclusive at model,
CLI, and service-start boundaries.

No worker starts before Phase 6 passes. Reconciliation is treated as mutating
because it can materialize cleanup commands; it is not part of static target
certification.

### Failure Semantics

| Failure phase | Required result |
| --- | --- |
| Before service stop | Leave current services unchanged |
| After stop, before identity rotation | Keep every worker stopped and Entry fenced; rerun exact source evidence before any new handover attempt |
| During identity rotation transaction | Roll back the transaction, keep every worker stopped and Entry fenced, then fix forward from fresh evidence |
| After identity rotation or target activation | Do not start old or target mutating workers; keep Entry fenced; fix forward |
| Target exact certification fails | All workers remain stopped; exchange-native Stops remain authoritative |
| Safety service start is partial | Stop the partially started set and keep Entry fenced |
| Any exact position/order contradiction | Refuse handover; no identity rotation |

The Owner has already accepted temporary service pause while exchange-native
Stops remain live. That permits strict fail-closed behavior after the identity
commit point.

## Event Registry Closure

`TradeEvent` persistence uses one canonical registry. The accepted direction is:

```text
EVENT_MODELS: tuple[type[TicketEvent], ...]
TradeEvent = union derived from or checked against EVENT_MODELS
Postgres deserializer = mapping derived from EVENT_MODELS
```

If Python typing constraints require the union to remain explicitly declared,
an architecture test must prove exact set equality and unique event names. A
new event cannot be merged when it is writable but not reloadable.

## Runtime And Transaction Ownership

| Operation | Owner | Transaction/network rule |
| --- | --- | --- |
| TP1/market facts | Lifecycle facts adapter | Bounded venue I/O outside PostgreSQL |
| TP1 decision and replacement preparation | Lifecycle use case and reducer | One short UOW transaction |
| Stop placement/cancel | Existing command dispatcher | Only after durable command claim commits |
| Runner evaluation | Lifecycle worker | One bounded runner per tick |
| Event reload | PostgreSQL event repository | Exact Ticket history ordered by sequence |
| Handover DB manifest | New read-only certification use case | Short read transaction |
| Handover venue manifest | Existing venue adapter through a typed port | No open DB transaction |
| Runtime identity rotation | Runtime authority seed UOW | One short locked transaction |

No new service, scheduler, timer, report file, exchange writer, or database
authority is introduced.

No compatibility package, legacy reader, translation mapper, schema fallback,
old-table query, dual-write path, or synthetic historical Event is introduced.

## Persistence Impact

### DDL

No DDL or Alembic migration is required.

Existing tables already hold Ticket, Aggregate, Position, Reservation, Account
Exposure, Exchange Command, Event, Incident, Settlement, and Review facts.
The exact handover manifest is an in-memory/read-only result and is never
persisted as runtime authority.

### DML

No one-time business-state DML is part of this design. Runtime identity rotation
continues to update only existing runtime metadata and capability identity
rows. TP1 and Runner state changes occur only through normal Trade Events and
durable Exchange Commands.

## Performance Bound

- TP1 facts remain one exact order read plus the existing bounded position and
  fill reads.
- Runner OHLCV remains bounded to `max(atr_period + 2,
  structure_window_bars + 1)`.
- Protected handover performs at most one position snapshot and two exact order
  reads per named Ticket per certification pass.
- Normal no-signal and no-runner ticks create zero files and no unchanged
  append-only events.
- No runtime full-account history scan is introduced.

The added cost occurs only during an explicit deployment handover, not during
normal middle/low-frequency cadence.

## Planned Code Boundaries

| Boundary | Expected change |
| --- | --- |
| `application/runtime_facts.py` | Typed exact protected-order and manifest facts |
| `infrastructure/venue_adapter.py` | Exact order truth read by ID and namespace |
| `infrastructure/runtime_authority_seed.py` | Reservation and Exposure equality gates |
| `scripts/trading_kernel/deploy_tokyo_release.py` | Entry exclusion and phase-aware recovery |
| `scripts/trading_kernel/seed_runtime_authority.py` | Remove TP1 replay deployment option |
| `infrastructure/pg_repositories.py` | Canonical event registry consumption |
| Tests | RED coverage and full TP1-to-Runner chain |

Production implementation must remain inside the existing Kernel boundaries.

## Test-First Sequence

1. Characterize the currently working TP1-to-break-even-to-runner chain.
2. RED: protected handover plus Entry is rejected.
3. RED: wrong-domain or incomplete Stop/TP1 exchange facts block handover.
4. RED: protected postflight failure starts no mutating worker.
5. RED: missing Reservation or mismatched Account Exposure blocks identity
   rotation.
6. RED: Event registry differs from `TradeEvent` fails architecture audit.
7. RED: generic TP1 replay deployment option is absent.
8. Implement the smallest changes needed to turn each family green.
9. Run targeted, PostgreSQL integration, full-chain, architecture, Ruff, Mypy,
   and file-I/O verification.

The exact cases are defined in
`2026-07-28-tp1-runner-and-protected-handover-structural-repair-test-cases.md`.

## Deployment And Fix-Forward

Implementation does not authorize deployment.

After implementation approval:

1. certify locally from a disposable `0001_initial` PostgreSQL database;
2. wait for an Owner deployment decision;
3. keep current live Entry fenced until the P1 gates are green;
4. deploy by exact protected handover only if active Tickets still exist;
5. otherwise use the simpler regular flat-release path;
6. verify exact exchange position and protection identities after release.

After runtime identity rotates, rollback to code that does not understand the
current persisted Event set is forbidden. Recovery is fix-forward.

## Acceptance

The repair is complete only when:

1. exact full TP1 truth naturally produces one `TakeProfitFilled`;
2. one durable replacement raises protection to the cost-adjusted floor;
3. the old Stop is cancelled only after the new Stop is confirmed;
4. the Ticket reaches `runner_protected` with exact remaining quantity;
5. closed-candle Runner decisions move Stops monotonically and restart safely;
6. final Settlement and Review retain TP1 and runner economics;
7. protected handover cannot enable Entry;
8. exact Ticket, domain, position, Stop, TP1, Reservation, Exposure, command,
   Incident, runtime, and schema facts agree before identity rotation;
9. no mutating worker starts after a failed protected postflight;
10. no generic TP1 replay deployment option remains;
11. every persisted Trade Event is reloadable by construction or parity test;
12. no DDL, direct business-state DML, second chain, or recurring file output
    is introduced;
13. a noncanonical historical Ticket is rejected rather than translated,
    backfilled, or accepted through fallback;
14. no compatibility module, legacy reader, dual read/write, old-field alias,
    synthetic Event, or replacement replay exception is introduced;
15. all required tests and static audits pass;
16. Tokyo readonly evidence is collected only after separate deployment
    authorization.

## Owner Approval Boundary

Approval of this draft authorizes an implementation plan and production-code
TDD. It does not itself authorize Tokyo deployment, Entry enablement, or any
real exchange mutation.
