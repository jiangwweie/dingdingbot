---
title: Terminal Recovery Structural Repair Design
status: IMPLEMENTED_LOCAL_PENDING_TOKYO_RELEASE
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-27
revision: 1
---

# Terminal Recovery Structural Repair Design

## Decision Gate

The Owner approved this design for implementation. It is locally implemented
and certified, but does not change Tokyo runtime authority until the committed
release, flat-runtime reset, deployment, and readonly postflight complete.
The current tracked code, PostgreSQL, exchange facts, and `docs/current/*`
remain authoritative.

## Objective

Close three structural gaps exposed by the July 27 recovery without creating a
second execution chain:

1. freeze the exact venue order namespace and lifecycle purpose in every new
   cancel Exchange Command;
2. resolve every Ticket-scoped Incident atomically when exact reconciliation
   proves that the exposure and all residual orders are absent;
3. let the Reconciliation worker record an honest terminal Review when an
   externally-flat Ticket has no Ticket-attributable exit economics after a
   bounded visibility window.

The target chain remains:

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

## Scope

| Repair | In scope | Out of scope |
| --- | --- | --- |
| Exact cancel identity | Command payload, order snapshots, command effects, dispatch mapping, venue routing, unknown recovery | New order types, cancel-all endpoints, manual exchange adoption |
| Incident closure | Exact Ticket query, aggregate transition, atomic resolution, authority release | Deleting Incident history, resolving runtime-global Incidents |
| External-flat Review | Review completeness model, bounded visibility, typed metrics, strategy-evidence exclusion | Fabricated PnL, manual trade attribution, strategy changes |

There is no sizing, leverage, strategy, entry admission, position-capacity, or
exit-policy change.

## Known Facts

### Cancel Identity

- Binance USD-M regular orders and Algo conditional orders use separate cancel
  endpoints and separate identity parameter names
  ([Cancel Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order),
  [Cancel Algo Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Algo-Order)).
- The current `CancelCommandPayload` freezes only `exchange_order_id`.
- The current adapter first attempts a regular cancel and retries in the
  conditional namespace only after an order-not-found response.
- The current result mapper infers cancel purpose from mutable aggregate status
  and known order identifiers.

### Incident Closure

- A Ticket may legitimately accumulate more than one Incident before becoming
  flat.
- The current repository returns only the newest open Incident for a Ticket.
- `ReconciliationMatched` currently resolves at most one Incident kind before
  releasing capital authority.
- Runtime-global Incidents use `ticket_id = NULL`; Ticket lifecycle Incidents
  use the exact Ticket identity.

### Review Closure

- The current worker retries indefinitely when exact exit fills are missing.
- The current completeness model supports only `complete` and
  `funding_unavailable`.
- An external-flat Ticket can be proven flat and order-free while its exit
  cannot be attributed to a BRC-owned client order identity.
- A zero-valued PnL or R multiple would be fabricated evidence and is forbidden.

## Alternatives

| Approach | Exactness | Runtime complexity | Operational burden | Decision |
| --- | --- | --- | --- | --- |
| Keep current local fixes and document one-time DML/manual Review | Low | Low in code | Repeats manual recovery | Rejected |
| Add exact typed identity and closure semantics inside the existing Kernel | High | Moderate and bounded | Normal worker closure | Selected |
| Add a separate recovery service and recovery tables | High locally | High system-wide | New deployment and authority | Rejected |

The selected approach extends the existing domain, application, infrastructure,
and Reconciliation worker boundaries. It does not add a recovery application,
parallel state machine, dual write, compatibility dispatcher, or file-backed
authority.

## Repair 1: Exact Cancel Target

### Decision

Every newly prepared cancel command freezes one exact `CancelTarget` and one
exact `CancelPurpose`.

```text
CancelCommandPayload
  exchange_order_id
  order_namespace = regular | conditional

CancelPurpose
  entry_remainder
  runner_old_stop
  reconciliation_cleanup
```

The exchange order identity, namespace, and purpose are immutable command
payload fields. The cancel command retains its own deterministic venue client
identity; reconciliation snapshots preserve their separately observed client
identity and namespace.

### Identity Ownership

| Cancel source | Namespace owner | Purpose | Required namespace |
| --- | --- | --- | --- |
| Partial ENTRY remainder | Original ENTRY command | `entry_remainder` | `regular` |
| Runner replaced stop | Original protection command | `runner_old_stop` | `conditional` |
| Known Initial Stop, TP1, or runner residue | Aggregate plus original command lineage | `reconciliation_cleanup` | `conditional` |
| Reconciliation-discovered BRC regular residue | Typed venue order snapshot | `reconciliation_cleanup` | `regular` |
| Reconciliation-discovered BRC conditional residue | Typed venue order snapshot | `reconciliation_cleanup` | `conditional` |

`VenueOrderSnapshot`, `VenueOrderTruth`, and the admission/reconciliation venue
rows must preserve `order_namespace`. The infrastructure adapter discovers the
namespace while reading the regular and conditional endpoint results; the
application does not infer it from numeric identifiers.

### Command Preparation

The cancel effects carry the complete target and purpose. The PostgreSQL unit
of work persists that complete payload before venue I/O. Retry generations copy
the same target namespace, target identities, and purpose. Only generation and
command identity change.

The result mapper uses the frozen `CancelPurpose` and verifies the compatible
aggregate state before selecting the domain event:

| Purpose | Accepted event | Rejected event | Unknown event |
| --- | --- | --- | --- |
| `entry_remainder` | `EntryRemainderCancelConfirmed` | `EntryRemainderCancelRejected` | `EntryRemainderCancelOutcomeUnknown` |
| `runner_old_stop` | `ProtectionCancelConfirmed` | `ProtectionCancelRejected` | `ProtectionCancelOutcomeUnknown` |
| `reconciliation_cleanup` | `OwnedOrphanCancelConfirmed` | `CancelOrderRejected` | `CancelOrderOutcomeUnknown` |

An aggregate state incompatible with the frozen purpose is an identity
contradiction. It does not fall through to another event type.

### Venue Execution

The adapter sends exactly one signed cancel request:

```text
regular -> CCXT cancel request with `conditional=false`
conditional -> CCXT cancel request with `conditional=true`
```

There is no mutation-based namespace probing and no regular-to-conditional fallback.

- order-not-found is a terminal rejected command result; reconciliation may
  subsequently prove the target absent;
- timeout or transport ambiguity becomes `OUTCOME_UNKNOWN`;
- an accepted response with a contradictory target identity becomes
  `OUTCOME_UNKNOWN` plus exact truth recovery;
- unknown recovery queries the same frozen namespace and never probes another
  namespace.

### Historical Command Boundary

This release uses the approved one-time flat-runtime reset. It removes every
historical Ticket, command, Incident, Review, reservation, and observation
fact before the release; registry, policy, capabilities, runtime identity, and
schema metadata remain. Therefore no legacy cancel decoder or compatibility
payload reader is introduced. The reset and release preflight must find:

```text
zero nonterminal legacy cancel command
zero active Ticket whose recovery depends on a legacy cancel command
zero unknown exchange outcome
```

This is historical decoding, not an execution fallback. New code never creates
the old shape.

## Repair 2: Atomic Ticket Incident Closure

### Decision

`ReconciliationMatched` resolves all open Incidents for the exact Ticket in the
same PostgreSQL transaction that releases budget, account capacity, and the
Netting Domain.

The closure proof remains strict:

```text
exact aggregate is RECONCILIATION_PENDING
and exact venue position quantity is zero
and no venue open order remains in the Netting Domain
and no known cleanup order identity remains
and no pending cancel identity remains
and no Ticket command has OUTCOME_UNKNOWN
```

If any condition is false, no Incident is resolved and no capital authority is
released.

### Repository And Effect

Add one exact bounded repository operation:

```text
resolve_all_open_for_ticket(
    ticket_id,
    resolved_at_ms,
)
```

It updates only rows with the exact `ticket_id` and `status = open`.

The reducer emits one `ResolveTicketIncidentsAtClosure` effect before
`ReleaseCapitalAuthorities`. The unit of work applies all effects in one
transaction. Any failure rolls back:

- the Trade Event append;
- aggregate transition;
- every Incident resolution;
- budget release;
- account-capacity release;
- Netting Domain release.

### Resolution Scope

All exact Ticket-scoped Incidents are resolved because flatness, absence of
orders, and absence of unknown commands prove that their exposure hazard no
longer exists. Resolution preserves the Incident record and its original kind;
it does not delete or rewrite the incident history.

The operation must not resolve:

- runtime-global Incidents with `ticket_id = NULL`;
- Incidents owned by another Ticket;
- open Incidents when reconciliation prerequisites are incomplete.

The existing single-latest-Incident query may remain for owner display but must
not participate in closure decisions.

## Repair 3: External-Flat Review Completeness

### Decision

Add a third Review completeness state:

```text
external_exit_unavailable
```

It means:

```text
the Ticket entry is exact
the Ticket is terminal, exchange-flat, and order-free
the closure event is ExternalFlatDetected
the visibility deadline has elapsed
no complete Ticket-attributable exit fill set exists
therefore realized PnL and R multiples are unavailable, not zero
```

### Visibility Window

Add one runtime setting:

```text
review_economics_visibility_grace_ms = 300000
```

Five minutes is a bounded operational visibility allowance, not an Owner risk
policy. Before the deadline, missing or incomplete exit fills schedule another
Reconciliation tick. At or after the deadline:

| Closure and facts | Result |
| --- | --- |
| Exact complete Ticket-bound exit fills | Normal complete Review |
| External flat and no complete attributable exit fill set | `external_exit_unavailable` Review |
| Kernel-commanded exit and missing fills | Remain pending and open an explicit Review Incident |
| Ticket, instrument, side, quantity, or client identity contradiction | Remain pending and open an identity Incident |

The unavailable outcome is not used to hide contradictory facts.

### Typed Review Payload

Replace free-form application input with a typed Review payload union:

```text
CompleteReviewMetrics
FundingUnavailableReviewMetrics
ExternalExitUnavailableReviewMetrics
```

`ExternalExitUnavailableReviewMetrics` contains:

```text
economics_completeness = external_exit_unavailable
unavailable_reason = external_flat_without_complete_ticket_exit_fills
entry quantity and exact entry facts
planned and actual stop-risk facts
entry_time_ms and external_flat_time_ms
visibility_deadline_ms
eligible_for_strategy_evidence = false
```

It forbids:

```text
gross_realized_pnl
net_realized_pnl
trading_fees_total
funding_pnl
planned_r_multiple
actual_r_multiple
```

The Owner projection displays "unavailable" and the reason. It must not display
zero economics. Strategy evaluation excludes the Review from payoff, expectancy,
win-rate, and R-multiple evidence while retaining it in lifecycle reliability
and incident-rate evidence.

### Idempotence

The Review identity remains deterministic:

```text
review:<ticket_id>
```

Repeated worker ticks after a committed Review produce no second review, no
second event, and no metrics mutation.

## Transaction And Runtime Ownership

| Operation | Owner | Transaction/network rule |
| --- | --- | --- |
| Cancel target selection | Domain/application effect preparation | Pure and committed with the durable command |
| Cancel mutation | Existing command dispatcher and venue adapter | Network I/O after command lease commit |
| Cancel unknown truth | Existing Reconciliation worker | Network I/O outside the database transaction |
| Incident closure | `ReconciliationMatched` unit of work | One exact PostgreSQL transaction |
| Review visibility/read | Existing Reconciliation worker | Network I/O outside the database transaction |
| Review persistence | Existing Review application use case | One short PostgreSQL transaction |

No new service, scheduler, table, report file, or deployment unit is introduced.

## Persistence Impact

### DDL

No DDL and no Alembic migration are required.

- cancel namespace and purpose live in the existing Exchange Command JSON
  payload;
- Review completeness and typed metrics live in the existing Review JSON
  payload;
- Incident resolution uses existing Incident columns and details JSON.

### One-Time Reset DML

The approved deployment uses exactly one guarded reset script,
`scripts/trading_kernel/reset_flat_runtime.sql`, after all writers are stopped
and exchange flatness is rechecked. It requires the expected database, schema,
runtime commit, AVAX Ticket identity, exact Ticket count, zero unresolved
commands, and an explicit confirmation token. It deletes historical runtime
and trade facts only; registry, Owner policy, capabilities, runtime identity,
and schema metadata are preserved. It is not invoked by normal cadence.

## Failure Semantics

| Failure | Required behavior |
| --- | --- |
| Missing cancel namespace or purpose on a new command | Refuse preparation or dispatch |
| Namespace contradiction in venue truth | Incident and fail-closed recovery |
| Cancel timeout | `OUTCOME_UNKNOWN`; no redispatch before exact truth |
| Incident-resolution transaction failure | Roll back event, release, and every resolution |
| External exit facts temporarily absent | Retry until visibility deadline |
| External exit facts permanently unattributable | Honest unavailable Review |
| Normal kernel exit facts absent | Retry fail-closed; no unavailable fallback |
| Review identity contradiction | Retry fail-closed; no Review record |

## Performance Bound

- cancel dispatch changes from up to two signed mutation requests to exactly
  one;
- reconciliation adds one exact Ticket-scoped Incident update;
- Review remains one bounded Ticket history read and at most one venue economics
  read per selected Review tick;
- no full account history scan, filesystem output, or new persistent worker is
  introduced.

This is suitable for the current middle/low-frequency workload and constrained
Tokyo host.

## Deployment And Fix-Forward

Before service switch:

1. stage and certify the exact target;
2. fence new ENTRY;
3. require zero nonterminal legacy cancel command and zero unknown outcome;
4. stop the old workers;
5. switch the release;
6. start Reconciliation and Lifecycle, then Observation, then Entry last.

Before the first new exact cancel payload or new Review payload is persisted,
the release may be switched back if the old release remains otherwise valid.
After a new payload is written, recovery is fix-forward because the older code
does not understand the added frozen fields.

The release does not require database rebuild, DDL, or one-time data repair.

## Documentation Impact After Approval

Implementation approval permits focused updates to:

- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`;
- `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`;
- `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`;
- `docs/current/MAIN_CONTROL_ROADMAP.md` only after current runtime evidence
  changes.

This draft itself never becomes runtime authority.

## Acceptance

The repair is complete only when:

1. every new cancel command freezes namespace, target identities, and purpose;
2. one cancel command produces at most one signed mutation request;
3. unknown recovery stays in the same namespace;
4. all exact Ticket Incidents resolve atomically with authority release;
5. no other Ticket or runtime Incident is modified;
6. an external-flat Ticket automatically reaches an honest unavailable Review
   after the visibility window;
7. no unavailable Review contains fabricated PnL, fees, funding, or R metrics;
8. the complete production-failure regression passes as one full chain;
9. the full Trading Kernel suite, Ruff, Mypy, schema, architecture, and
   production file-I/O audits pass;
10. Tokyo readonly postflight proves expected service, command, Incident,
    Review, position, and order state.

## Owner Approval Boundary

Approval of this design authorizes writing the failing tests and a detailed
implementation plan. It does not by itself authorize Tokyo deployment or any
exchange mutation.
