---
title: P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN
status: CURRENT_DESIGN
authority: docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md
last_verified: 2026-07-11
---

# P0 Production Lifecycle Wiring And Continuous Reconciliation Design

Implementation order and verification commands live in
`docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_IMPLEMENTATION_PLAN.md`.
This document owns the current P0-LC integration and progress semantics. Older
P0-C/P0-D/P0-F component documents retain their non-conflicting scheduler,
recovery, reconciliation, and lifecycle invariants.

## Decision

The next medium-scale mainline is:

```text
P0-LC Production Lifecycle Wiring And Continuous Reconciliation
closure scope: Exchange Truth, Durable Command Authority And Lifecycle Closure
```

This program extends the existing ticket-bound lifecycle core and the existing
`brc_ticket_bound_exchange_commands` command authority. It must not create a
second scheduler, exchange-command table, recovery path, runner path,
reconciliation source, settlement authority, or file-backed evidence path.

The program is engineering-complete when every production-shaped ticket can
progress from a committed protected-submit result to one of:

```text
lifecycle_closed + one Live Outcome row
or
one exact current lifecycle hard blocker + one bounded recovery command/freeze
```

Only exchange-specific live calibration remains market-dependent after this
program: actual visibility latency, real partial fills, fees/funding/slippage,
and venue acceptance of protection/runner operations.

## Current Verified Facts

| Area | Current fact | Consequence |
| --- | --- | --- |
| Tokyo release | `5f40c62d`, migration `112` | This design starts from the deployed real-signal-to-Ticket baseline |
| Pre-trade scopes | 20/22 `market_wait_validated`; CPM/SUI and MPG/SUI retain historical action-time blockers | Current blocker relevance must be repaired before lifecycle claims are trusted |
| Lifecycle timer | 30-second oneshot, `Persistent=false`, mutation enabled | Production entry exists, but only no-active-lifecycle has been observed |
| Production lifecycle rows | No real submitted lifecycle; existing attempts are disabled smoke or blocked | Active lifecycle behavior is not production-certified |
| Scheduler transaction | Gateway binding, exchange reads/writes, and PG updates share one `engine.begin()` | Exchange success can outlive a rolled-back PG transaction |
| Time budget | Up to 8 selected scopes and repeated 8-second snapshots under `TimeoutStartSec=25s` | The current worst-case runtime cannot satisfy its service deadline |
| Exchange identity | PG canonical symbol can reach CCXT gateway methods directly | Position/order truth can be fetched for the wrong or unsupported symbol identity |
| Protection visibility | Snapshot provider reads only the default open-order view | Conditional SL/RUNNER_SL orders can be falsely classified missing |
| Fill projection | TP1 fill is detected but not projected to the PG TP1 order row | Runner mutation can remain unreachable without a privileged fixture |
| Finalization | Settlement/review/closure/Live Outcome exist as isolated consumers | Production scheduler stops before a complete lifecycle outcome |

## Rejected Approaches

| Approach | Benefit | Rejection reason |
| --- | --- | --- |
| Patch individual missing dictionary fields | Small diff | Repeats the producer/consumer escape that caused the Action-Time failures |
| Keep the timer read-only and leave mutation/manual closure to APIs | Lowest immediate mutation risk | Turns the Owner into an operator and leaves protection recovery dependent on manual action |
| Build a new unified lifecycle engine beside current modules | Clean-slate model | Creates duplicate authority for recovery, runner, reconciliation, and closure |
| Add a separate lifecycle command-claim table | Isolates the refactor | Duplicates the durable command state, deterministic identity, and `outcome_unknown` semantics already owned by `brc_ticket_bound_exchange_commands` |

## Selected Architecture

The selected architecture keeps one ticket-bound state machine and adds five
bounded capabilities around it:

```text
Batch 0  Current blocker relevance
Batch 1  Typed exchange truth and order ownership
Batch 2  Fill projection and monotonic lifecycle transitions
Batch 3  Existing exchange-command authority extension and unknown-outcome recovery
Batch 4  Operational finalization, settlement, review, and Live Outcome
Batch 5  Production-shaped certification, deploy acceptance, and ops health
```

## Batch 0: Current Blocker Relevance

### Problem

`brc_runtime_process_outcomes` is one current row per process/scope, but an
event-scoped terminal outcome can remain indefinitely after its source signal,
promotion, lane, and Ticket are all expired/closed. Candidate Pool currently
converts every failure-shaped lane outcome into a current persistent blocker.

### Rule

A process outcome is current for pre-trade blocking only when its
`source_watermark` still resolves to one current chain object:

- fresh live signal;
- open promotion candidate;
- open action-time lane;
- active Action-Time Ticket;
- current unresolved safety/lifecycle object.

The current row remains inspectable after source expiry until the same
process/scope is superseded. It must not override a new
`market_wait_validated` readiness row. `brc_runtime_process_outcomes` is a
current projection, not an append-only history ledger: a later success replaces
the prior current row, while signal/Ticket/lifecycle event lineage preserves
the underlying operational provenance.

For the current compatibility batch, `action_time_ticket_sequence` watermarks
are exact Signal or Ticket identities produced by that sequence. Relevance is
an exact identity match against the current lane lineage; a different Signal ID
on the same StrategyGroup/symbol/side is a different event and must not inherit
the old blocker. A future multi-process watermark contract must add explicit
`source_object_type + source_object_id`; consumers must not infer types from
arbitrary strings.

### Acceptance

- expired CPM/SUI and MPG/SUI terminal identities remain queryable;
- they do not block current no-signal readiness;
- a fresh/open source with the same failure still blocks;
- a later successful process result supersedes the prior current outcome while
  existing event lineage remains auditable;
- Goal Status, Candidate Pool, Daily Table, Tradeability, and Monitor agree.

## Batch 1: Typed Exchange Truth

### Ticket-Bound Exchange Scope

Every gateway call must consume a typed exchange scope resolved from PG:

```text
ticket_id
-> exchange_instrument_id
-> canonical symbol
-> venue exchange_symbol
-> position side / order side
-> account/runtime profile
```

PG identity remains canonical. Only the adapter boundary uses the venue symbol.

### Snapshot Views

The official snapshot provider must merge and deduplicate:

- default open orders;
- stop/conditional orders;
- venue-specific STOP_MARKET view when required;
- recent fills;
- side-scoped position state.

Missing or malformed position data is `unknown`, never `flat`.

### Order Ownership

An exchange order is unknown only after comparing it with all active PG-linked
ticket-bound order identities for the same account/instrument. An order owned
by another Ticket is first classified as `owned_elsewhere`; whether it blocks
then depends on account, instrument, position mode, and position side. Orders in
the same net-position domain still require `active_position_resolution`.
Only an independently isolated subaccount or a verified hedge-mode side may be
non-blocking for the current Ticket.

### Evidence

Every snapshot used for a state transition must have PG lineage. Recurring
JSON/MD snapshot files are forbidden. This program reuses the compact
reconciliation-tick summary as the snapshot projection. Only a state change or
command result writes a lifecycle event containing the snapshot hash and the
minimum required order/fill facts. It does not add a second snapshot table or
timer-cadence evidence stream.

## Batch 2: Fill Projector And Monotonic State

Exchange fills must project into the canonical ticket-bound rows before a
consumer makes a lifecycle decision.

| Exchange fact | Required PG transition |
| --- | --- |
| ENTRY partial fill | Record actual filled quantity; protection uses filled quantity only; remaining ENTRY is reconciled before expansion |
| ENTRY filled | Lifecycle enters filled/protection-required state |
| TP1 filled | TP1 order becomes `filled`; remaining quantity is computed; runner mutation becomes eligible |
| SL filled | Final exit candidate is recorded; position must still be proven flat |
| RUNNER_SL filled | Final exit candidate is recorded; position must still be proven flat |
| Position flat with live linked protection | Enter cleanup state; cancel only PG-linked reduce-only protection |
| Position flat with matching final fill and no residual protection | Enter reconciliation-matched finalization |

Transitions are monotonic. Repeated snapshots cannot revive an earlier state or
create duplicate lifecycle events/commands.

## Batch 3: Existing Command Authority And External-Side-Effect Safety

### Core Invariant

No exchange read or write may occur while an uncommitted transaction contains
the only record of command intent or command result.

### One Command Source Of Truth

All protected-submit, protection-recovery, runner-mutation, and orphan-cleanup
exchange mutations use `brc_ticket_bound_exchange_commands`. The existing
durable command core already owns deterministic client IDs, generations,
`outcome_unknown`, and reconciliation states. This batch extends it with:

- `command_kind`: place or cancel;
- `command_source`: protected submit, protection recovery, runner mutation, or
  orphan cleanup;
- cancel target identity and lifecycle plan reference;
- lease owner, claimed time, and lease deadline;
- kind-specific constraints for place versus cancel commands.

Recovery, runner, and cleanup tables may retain their business plan/state, but
they must not independently own the exchange execution result.

The shared durable state remains:

```text
prepared
-> dispatching with committed lease
-> confirmed_submitted / confirmed_rejected
| outcome_unknown
-> reconciled_submitted / reconciled_absent
| hard_stopped
```

Required claim/extension fields:

- command kind, command source, and command id;
- ticket/scope identity;
- lease owner and lease deadline;
- deterministic client order ids or cancel target ids;
- execution attempt count;
- last exchange observation/result reference;
- current blocker and next action.

### Transaction Phases

```text
short PG transaction: select/claim and commit
-> network I/O outside PG transaction
-> short PG transaction: persist result/outcome_unknown and commit
-> optional bounded read-only verification
-> short PG transaction: reconcile/advance state
```

Timer and API callers compete through `FOR UPDATE SKIP LOCKED` or an equivalent
PG lease on the existing command row. Only one caller owns a command at a time.
If a `dispatching` lease expires or the process terminates, the command becomes
`outcome_unknown` and must be reconciled before it can be claimed again.

### Unknown Outcome

Timeout or connection loss after a submit/cancel call is not ordinary failure.
It becomes `outcome_unknown`. The next action is query/reconcile by deterministic
client/exchange order identity before any retry. Automatic retry is forbidden
until absence is proven.

### Time Budget

- one mutation-capable scope per service invocation;
- every gateway read/write has an explicit timeout;
- a global deadline stops selecting new scopes before systemd termination;
- systemd timeout exceeds the declared global deadline plus shutdown margin;
- one scope failure cannot roll back another committed scope.

## Batch 4: Operational Closure And Outcome

### Closure Order

The current test-only review/closure cycle is replaced by this production order:

```text
final exit fill + flat position
-> residual protection cleanup
-> reconciliation_matched event
-> independent ticket-bound budget settlement evidence
-> lifecycle status budget_settled / post-submit review_ready
-> system review consumes terminal facts and defaults to needs_more_samples
-> review_recorded event
-> lifecycle_closed
-> one final Live Outcome materialized from the closed lifecycle
```

This preserves the existing rule that final `closed` requires review evidence.
Review consumes final fills, flat proof, residual-cleanup proof, and settlement
evidence directly; it does not depend on a prematurely materialized Outcome.
Live Outcome remains terminal truth and is created only after lifecycle closure.

### Ticket-Bound Settlement

An independent, idempotent ticket-bound settlement service validates that the
Ticket owns one consumed `brc_budget_reservations` row and that current exchange
truth proves the position flat. In one short transaction it releases the
reservation and records a deterministic `budget_settled` lifecycle event. The
closure coordinator only consumes that settlement event; its own
`runtime_budget_mutated` flag remains false. Settlement never creates execution
authority.

### Review

Normal automatic closure records `needs_more_samples` with a bounded reason
code only after final fill, flat proof, residual protection cleanup, settlement
evidence, and minimum result fields are complete. Otherwise it enters
`review_blocked`; it must not force closure through a default review. This is
governance input, not Owner approval and not trading authority. Owner/agent
review may later revise the decision without reopening the closed order
lifecycle.

### Live Outcome

The outcome projector must source, when available:

- entry and final-exit fill price/quantity/time;
- SL/TP1/RUNNER_SL identities;
- fees and funding;
- realized PnL;
- initial risk and R multiple;
- lifecycle defects and recovery history.

A bare `lifecycle_closed` status without required event lineage is invalid.
Hard-blocked and recovered outcomes update the same ticket identity
monotonically.

## Batch 5: Production-Shaped Certification

### Required Matrix

| Dimension | Cases |
| --- | --- |
| Exchange identity | canonical vs venue symbol, hedge side, same symbol across StrategyGroups |
| Order visibility | normal, conditional stop, duplicate views, missing/malformed response |
| Fills | no fill, partial ENTRY, full ENTRY, TP1, SL, RUNNER_SL, duplicate fill |
| Command result | success, explicit reject, timeout before acceptance, timeout after acceptance, process termination |
| Recovery | missing SL, missing TP1, runner submit, old SL cancel, partial cleanup, retry exhaustion |
| Cadence | first tick, repeated unchanged ticks, post-expiry tick, recovery check, concurrent timer/API caller |
| Closure | final exit, flat proof, residual protection, settlement, review, hard blocker, idempotent closed replay |
| Scope | five StrategyGroups, six current Event Specs, 22 candidate scopes in an isolated test DB |

This matrix is a `pre_live_rehearsal_ready` certification using a test database,
mock gateway, and synthetic producer input. It must not write Tokyo production
PG, create a production signal/Ticket, or be presented as live-market
calibration.

### Deploy Acceptance

Postdeploy verification must prove:

- lifecycle unit files match the release;
- timer enabled/active and latest oneshot result successful;
- migration/table set includes the existing command authority extensions,
  reconciliation ticks, freezes, closures, settlement lineage, and outcomes;
- no-active-lifecycle tick performs zero exchange calls and writes no no-op rows;
- a transaction-rollback production probe cannot lose command intent;
- the commit-bound isolated rehearsal report proves active lifecycle behavior
  without writing Tokyo production PG;
- production file-I/O audit remains clear.

### Ops Health

Ops health must include lifecycle timer/service, current active scopes, command
leases, unknown outcomes, freezes, unprotected attempts, residual protection,
closure gaps, and Live Outcome gaps. Ops Health returns non-zero and notifies
for a current critical lifecycle state; false-green `ok` is invalid. The
lifecycle worker itself still exits zero after it correctly records a
`business_blocked` result in PG. Only database, network, projector, or command
state persistence/reconciliation process failures make the worker process fail.

## Cadence And Performance Boundary

| Dimension | Required behavior |
| --- | --- |
| No active lifecycle | One bounded PG selection, zero gateway calls, zero new rows/files |
| Active selection | Oldest/due ticket first; at most one mutation-capable scope per run |
| Network | Outside long PG transactions; explicit per-call and global deadlines |
| PG growth | Bounded by tickets, state transitions, and command attempts; never timer ticks alone |
| Disk | Zero recurring JSON/MD files; syslog summary only |
| Retention | Current rows retained while active; append-only lifecycle events and one terminal outcome per ticket retained by ticket policy |
| Catch-up | `Persistent=false`; no restart catch-up storm |

## Interrupt And Recovery Priority

Runtime safety always outranks engineering cadence:

```text
unprotected position or unknown exchange outcome
-> next different-identity natural signal acceptance event
-> non-urgent P0-LC implementation work
```

When a new `signal_event_id` appears and no higher safety incident is active,
the system pauses the current engineering batch only at a committed transaction
boundary, runs the natural-signal acceptance path, persists the result, and
then resumes P0-LC. The old same-lane process outcome cannot block the new
identity.

## Rollback And Forward-Fix

Rollback means disabling the mutation timer while keeping readonly
reconciliation and current-state inspection available. Unknown commands,
lifecycle evidence, and settlement evidence are never deleted. Database rollback
must not erase a command whose exchange effect may have occurred; those rows are
forward-fixed through exchange reconciliation.

## Authority Boundary

This program may read exchange state and execute only recovery/runner/cleanup
commands for an existing ticket-bound lifecycle under current policy.

It must not:

- create a new ENTRY order;
- create a signal, promotion, lane, Ticket, FinalGate pass, or Operation Layer
  handoff;
- cancel or adopt an exchange-only unknown order;
- expand live profile, notional, leverage, symbol, side, or attempt caps;
- perform withdrawal, transfer, or credential mutation;
- use replay/synthetic evidence as live exchange truth;
- use repo/output/report JSON or Markdown as current authority;
- automatically execute `emergency_reduce` without a future explicit Owner
  policy decision.

## Chain Position

```text
chain_position: post_submit_lifecycle_certification
strategy_group_id: CPM-RO-001 / MPG-001 / MI-001 / SOR-001 / BRF2-001
symbol: 22 active candidate scopes
stage: production_lifecycle_partially_wired
first_blocker: exchange_truth_identity_and_command_atomicity_not_production_certified
evidence: canonical symbol reaches gateway; conditional orders are not fully visible; TP1 fill is not projected; exchange I/O occurs inside a long PG transaction; finalization has no production caller
next_action: implement Batch 0 through Batch 5 in order with red-green tests
stop_condition: every production-shaped ticket reaches lifecycle_closed plus one outcome, or one deterministic hard blocker, without duplicate/ambiguous exchange mutation
owner_action_required: no
authority_boundary: no new ENTRY path, no FinalGate/Operation Layer bypass, no profile/sizing expansion, no unknown-order mutation
```
