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
| Account-mode producer | Production `account_mode` facts do not currently persist `account_id`, `exchange_id`, `account_mode`, or `position_mode_safe` | A downstream resolver can pass fixture tests while every production Ticket blocks, or can apply one account's mode to another account |
| Gateway binding | The runtime gateway identifies CCXT `binance`, but does not expose the PG `binance_usdm` exchange identity or the budget account identity | Wrong-account or wrong-venue credentials cannot be rejected before exchange I/O |
| Position identity | The gateway drops venue `positionSide`, and the snapshot provider selects the first non-zero position | Hedge-side isolation and flat-position proof are not trustworthy |
| Protection visibility | Snapshot provider reads only the default open-order view | Conditional SL/RUNNER_SL orders can be falsely classified missing |
| Order ownership | Reconciliation compares exchange orders only with the current Ticket's local ids | An order owned by another Ticket is mislabeled exchange-only unknown and can create or clear the wrong scope freeze |
| Lifecycle mutation guard | Production systemd passes `--allow-exchange-mutation` before the short-transaction command runner exists | Recovery/runner/cleanup can write through the unsafe long-transaction path |
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

The selected architecture keeps one ticket-bound state machine and adds six
bounded capabilities around it. The ordering is safety-driven: unsafe lifecycle
mutation is disabled before typed exchange truth or later lifecycle behavior is
expanded.

```text
Batch 0  Current blocker relevance
Batch 1  Mutation interlock, historical Ticket scope, and current ENTRY qualification
Batch 2  Typed exchange truth, NettingDomain ownership, and source-specific holds
Batch 3  Existing exchange-command authority extension and short-transaction runner
Batch 4  Fill projection and monotonic lifecycle transitions
Batch 5  Operational finalization, settlement, review, and Live Outcome
Batch 6  Production-shaped certification, deploy acceptance, and ops health
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

## Batch 1: Mutation Interlock And Scope Semantics

### Immediate Mutation Interlock

The current long-transaction lifecycle runner is not a permitted production
mutation path. Until Batch 3's durable command claim/result loop is deployed
and certified, every lifecycle mutation that is not already owned by a
committed `brc_ticket_bound_exchange_commands` row must fail closed before any
gateway call. Read-only exchange observation may continue.

The interlock is capability-based, not a loose CLI boolean. A current ENTRY is
also ineligible while the production lifecycle mutation capability is not
certified, because creating exposure whose recovery/runner/cleanup path is
known unsafe would violate end-to-end Runtime Safety. A natural signal may
still advance through read-only facts and produce one exact engineering
blocker; it may not turn the interlock on.

### Historical Ticket Identity Versus Current ENTRY Qualification

One resolver must not combine immutable lifecycle identity with current
new-exposure authority. The program uses two typed decisions:

| Decision | Source and time authority | Allowed use |
| --- | --- | --- |
| `TicketHistoricalExchangeScope` | Ticket, budget, referenced runtime binding, instrument mapping valid at `ticket.created_at_ms`, exchange instrument, and Ticket-bound account-mode snapshot | Read existing exchange truth and perform only validated risk-reducing lifecycle work for that Ticket |
| `CurrentEntryEligibility` | Current active mapping, current Owner policy/runtime binding, current account-mode projection, gateway binding, lifecycle capability, domain holds, Runtime Safety State, FinalGate, and Operation Layer | Decide whether a new ENTRY may be dispatched now |

Pausing a StrategyGroup, revoking a runtime binding, or retiring a mapping
blocks future ENTRY qualification. It must not make an existing position
unprotectable or uncancellable. Historical lifecycle resolution therefore uses
the Ticket's frozen `exchange_instrument_id` and the mapping/version that was
valid when the Ticket was created; it does not require that mapping to remain
current. Missing historical identity is a hard stop. Current status is returned
as context and evaluated by the operation-specific validator, not hidden inside
the identity resolver.

### Account Mode And Gateway Binding

Account mode has one production producer. For Binance USD-M it must use the
signed read-only `/fapi/v1/positionSide/dual` endpoint, not infer mode from
non-zero positions.
The producer persists both the immutable Ticket fact snapshot and one PG
current `brc_exchange_account_modes_current` projection keyed by:

```text
account_id + exchange_id
```

The typed value includes `position_mode=one_way|hedge`,
`position_mode_safe`, source identity, observed time, and validity. The Ticket
snapshot records the expected mode at creation. Every later mutation compares
that expected mode with a fresh current account-mode observation; mismatch or
unknown mode creates a hard hold before exchange write.

The runtime gateway binding must explicitly expose the same `account_id` and
canonical `exchange_id` used by PG. The current single-account deployment may
still instantiate one gateway, but it must not default or infer the account
identity from a symbol or API-key string. The production binding requires
explicit non-secret `BRC_RUNTIME_EXCHANGE_ACCOUNT_ID` and canonical
`BRC_RUNTIME_EXCHANGE_ID=binance_usdm`; the adapter may still use CCXT name
`binance`.
`account_id` or `exchange_id`
mismatch blocks before any read or write. This is the extension seam for future
capital allocation across accounts without introducing a second execution
chain.

## Batch 2: Typed Exchange Truth, Ownership, And Domain Holds

### Ticket-Bound Exchange Scope

Every gateway call is prepared from `TicketHistoricalExchangeScope`:

```text
ticket_id
-> frozen account/runtime profile
-> frozen exchange_instrument_id
-> canonical symbol retained in PG
-> venue exchange_symbol used only at adapter boundary
-> expected position mode / position side
-> typed order or reduce intent
```

String-format inference is forbidden. `SUIUSDT -> SUI/USDT:USDT` is a PG
mapping fact, not a naming rule. The same resolver must accept future
equity-linked, precious-metal, dated, and non-crypto venue identifiers without
code-level symbol rewriting.

### NettingDomainKey

Cross-Ticket conflicts are evaluated by one typed `NettingDomainKey`:

```text
one-way: account_id | exchange_id | exchange_instrument_id | NET
hedge:   account_id | exchange_id | exchange_instrument_id | HEDGE:LONG
         account_id | exchange_id | exchange_instrument_id | HEDGE:SHORT
```

`strategy_group_id`, `runtime_profile_id`, and `ticket_id` are deliberately not
part of this key. Two strategies on the same one-way account and instrument
share one net position even when their internal lanes differ. Opposite hedge
sides are isolated only after current account mode and both venue
`positionSide` values are verified.

### Complete Snapshot Views

The gateway owns capability-specific open-order aggregation. For the current
Binance/CCXT adapter, the required views are the default view and the stop /
conditional capability view (`stop=true` or the adapter-equivalent selector).
`type=STOP_MARKET` is not assumed to be an independent conditional view merely
because the order type has that name.

The official snapshot provider merges and validates:

- all adapter-declared required open-order views;
- recent fills;
- a complete position response scoped to the exchange symbol and expected
  `positionSide`;
- the current account-mode observation.

The result records which views succeeded. A required-view failure, conflicting
duplicate payload, malformed position, ambiguous side, or mode mismatch makes
the snapshot incomplete and blocks state transition. An empty position result
means `flat` only when the scoped call completed successfully and symbol, mode,
and side completeness are proven; missing or malformed data is `unknown`.
Orders deduplicate by exchange order id first and deterministic client id
second. The same identity with conflicting material fields is not first-wins;
it is contradictory exchange truth.

### Global Order Ownership

An exchange order is unknown only after comparison with all active or
unresolved PG-linked ticket-bound command and protection identities for the
same account and instrument. Classification is:

| Ownership | Meaning | Current Ticket effect |
| --- | --- | --- |
| `owned_by_current_ticket` | Exchange/client identity belongs to this Ticket | Reconcile normally |
| `owned_elsewhere_same_domain` | Another Ticket owns the order in the same `NettingDomainKey` | `active_position_resolution` and an active domain hold |
| `owned_elsewhere_other_domain` | Another Ticket owns it on a proven isolated hedge side or subaccount | Non-blocking for this Ticket; still visible and auditable |
| `unowned` | No PG command/protection identity owns it | Hard hold; never cancel or adopt automatically |
| `identity_conflict` | Exchange/client ids point to inconsistent PG owners or account/instrument scope | Hard safety stop |

### Source-Specific Domain Holds

The existing scope-freeze projection is extended into source-specific domain
holds; no second freeze authority is created. Each active hold is keyed by:

```text
NettingDomainKey + source_kind + source_id
```

The effective domain is held while any source-specific hold is active. A
successful reconciliation may resolve only its own hold using matching source
identity and resolution proof. It must not broadly clear another Ticket's
unknown outcome, unprotected-position, mode-mismatch, or unowned-order hold.
This replaces the current one-active-freeze-per-StrategyGroup/symbol/side shape,
which cannot represent multiple independent safety sources on one net domain.

### Hedge Reduce Intent

Lifecycle protection is modeled as business intent, not as one venue flag:

| Mode | Required adapter request |
| --- | --- |
| One-way | Opposite `gateway_side`, `reduce_only=true`, no `positionSide` |
| Hedge | Opposite `gateway_side`, exact `positionSide=LONG|SHORT`; the adapter may omit raw Binance `reduceOnly` when that venue rejects the combination, but the command remains typed `reduce_position` |

Entry, protection recovery, runner replacement, and cleanup commands retain
strategy side, gateway order side, expected position side, and reduce intent as
separate fields. No consumer may infer hedge position side from buy/sell alone.
Cancel APIs that do not accept `positionSide` still receive the venue
`exchange_symbol`; the durable command retains the expected domain and validates
the target order's side before cancel.

### Unified Read/Write Boundary

| Path | Venue symbol rule | Side/domain rule |
| --- | --- | --- |
| Open orders, fills, positions | Always `exchange_symbol` from historical scope | Preserve and validate venue `positionSide`; never pass canonical symbol |
| Protected ENTRY submit | `exchange_symbol` from current-qualified Ticket | Typed entry side and hedge `positionSide` when applicable |
| Protection recovery and runner submit | `exchange_symbol` from historical Ticket scope | Typed `reduce_position` intent and exact expected `positionSide` |
| Runner old-SL and orphan cleanup cancel | `exchange_symbol` from historical Ticket scope | Cancel only PG-owned target in the same `NettingDomainKey` |
| Command reconciliation | Stored `exchange_symbol` plus account/exchange binding | Query by deterministic client/exchange identity inside the same domain |

### Evidence

Every snapshot used for a state transition must have PG lineage. Recurring
JSON/MD snapshot files are forbidden. This program reuses the compact
reconciliation-tick summary as the snapshot projection. Only a state change,
hold transition, or command result writes a lifecycle event containing the
snapshot hash and minimum required order/fill facts. It does not add a second
snapshot table or timer-cadence evidence stream.

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
- canonical `exchange_id`, venue `gateway_symbol`, expected `position_mode`,
  `position_side`, `NettingDomainKey`, and typed `reduce_intent`;
- cancel target identity and lifecycle plan reference;
- lease owner, claimed time, and lease deadline;
- kind-specific constraints for place versus cancel commands.

Schema work is ordered in two migrations. Migration `113` creates the
account+exchange account-mode current projection and converts the existing
scope-freeze projection to source-specific `NettingDomainKey` holds. Migration
`114` extends the existing exchange-command table with typed scope, place/cancel
kind, source, lease, and target fields. Migration `114` must not create a
second command table, and neither migration enables mutation by itself.

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
- historical Ticket scope identity, gateway account/exchange binding,
  `NettingDomainKey`, expected position mode/side, and typed reduce intent;
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
An `outcome_unknown` command creates or retains its own source-specific domain
hold. Another successful Ticket cannot clear it.

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

The current `TimeoutStartSec=25s` and up-to-four-scope, repeated-eight-second
snapshot shape is rejected. Deadline tests must prove the configured service
timeout is greater than the application global deadline plus shutdown margin,
and the worker must stop claiming new work before that deadline. Merely
increasing systemd timeout without removing network I/O from the PG transaction
is not acceptance.

## Batch 4: Fill Projector And Monotonic State

Exchange fills must project into the canonical ticket-bound rows before a
consumer makes a lifecycle decision.

| Exchange fact | Required PG transition |
| --- | --- |
| ENTRY partial fill | Record actual filled quantity; protection uses filled quantity only; remaining ENTRY is reconciled before expansion |
| ENTRY filled | Lifecycle enters filled/protection-required state |
| TP1 filled | TP1 order becomes `filled`; remaining quantity is computed; runner mutation becomes eligible |
| SL filled | Final exit candidate is recorded; position must still be proven flat |
| RUNNER_SL filled | Final exit candidate is recorded; position must still be proven flat |
| Position flat with live linked protection | Enter cleanup state; cancel only PG-linked reduce-position protection owned in the same domain |
| Position flat with matching final fill and no residual protection | Enter reconciliation-matched finalization |

Transitions are monotonic. Repeated snapshots cannot revive an earlier state,
create duplicate lifecycle events/commands, or resolve another source's domain
hold.

## Batch 5: Operational Closure And Outcome

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

## Batch 6: Production-Shaped Certification

### Required Matrix

| Dimension | Cases |
| --- | --- |
| Historical/current scope | retired mapping or paused binding still permits validated existing-Ticket risk reduction; the same state blocks new ENTRY; missing historical lineage hard-stops |
| Exchange identity | canonical vs venue symbol, arbitrary non-crypto venue identifier, same symbol across StrategyGroups, wrong exchange binding, wrong account binding |
| Account mode | production signed-GET producer, one-way, hedge, missing, malformed, stale, account mismatch, exchange mismatch, and mode change after Ticket creation |
| Netting domain | one-way same instrument across StrategyGroups, hedge same side, hedge opposite side, separate subaccount, ambiguous/missing `positionSide` |
| Order visibility | normal plus adapter-declared conditional view, duplicate same payload, conflicting duplicate, one required view failing, missing/malformed response; no false independent `type=STOP_MARKET` assumption |
| Global ownership | current Ticket, another Ticket same domain, another Ticket isolated domain, unowned exchange order, exchange/client identity conflict |
| Domain holds | two independent hold sources on one domain, source-specific resolution, one successful Ticket unable to clear another source's hold |
| Read/write boundary | snapshot, protected submit, protection recovery, runner submit, old-SL cancel, orphan cleanup, and command reconciliation all use venue symbol; hedge-capable writes preserve typed `positionSide`/reduce intent |
| Fills | no fill, partial ENTRY, full ENTRY, TP1, SL, RUNNER_SL, duplicate fill |
| Command result | success, explicit reject, timeout before acceptance, timeout after acceptance, process termination |
| Recovery | missing SL, missing TP1, runner submit, old SL cancel, partial cleanup, retry exhaustion |
| Transaction/cadence | mutation interlock before Batch 3, committed claim before I/O, no network in PG transaction, first tick, repeated unchanged ticks, post-expiry tick, recovery check, concurrent timer/API caller, systemd deadline margin |
| Closure | final exit, flat proof, residual protection, settlement, review, hard blocker, idempotent closed replay |
| Scope | five StrategyGroups, six current Event Specs, 22 candidate scopes in an isolated test DB |
| Interrupt | same signal identity is idempotent; different natural signal preempts only after higher safety states and at a committed boundary; incomplete mutation capability remains fail-closed |

This matrix is a `pre_live_rehearsal_ready` certification using a test database,
mock gateway, and synthetic producer input. It must not write Tokyo production
PG, create a production signal/Ticket, or be presented as live-market
calibration.

### Deploy Acceptance

Postdeploy verification must prove:

- lifecycle unit files match the release;
- first deploy phase leaves lifecycle mutation fail-closed while read-only
  reconciliation remains available;
- migration `113` account-mode/domain-hold schema and migration `114` existing
  command-authority extension are present before capability enablement;
- production account-mode producer writes the exact account+exchange-scoped
  shape consumed by historical scope and current ENTRY qualification;
- timer enabled/active, deadline relationship valid, and latest read-only
  oneshot result successful;
- no legacy recovery/runner/cleanup module calls the gateway directly;
- no-active-lifecycle tick performs zero exchange calls and writes no no-op rows;
- a transaction-rollback production probe cannot lose command intent;
- the commit-bound isolated rehearsal report proves active lifecycle behavior
  without writing Tokyo production PG;
- production file-I/O audit remains clear;
- only after all prior checks pass, the second deploy phase enables the durable
  mutation capability and proves one bounded no-active run without exchange
  write.

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
| Active selection | Oldest/due ticket first; at most one claimed mutation command per run; read snapshots cached once per `NettingDomainKey` per invocation |
| Network | Outside long PG transactions; explicit per-call and global deadlines |
| PG growth | Bounded by tickets, state transitions, and command attempts; never timer ticks alone |
| Disk | Zero recurring JSON/MD files; syslog summary only |
| Retention | Current rows retained while active; append-only lifecycle events and one terminal outcome per ticket retained by ticket policy |
| Catch-up | `Persistent=false`; no restart catch-up storm |

## Engineering Certification And Natural-Signal Interrupt Priority

Engineering certification is continuous and does not wait for the market. A
different-identity natural signal is nevertheless the highest-priority
acceptance event after active real-funds safety incidents:

| Priority | Event | Required behavior |
| --- | --- | --- |
| `P0-SAFETY` | Unprotected position, `outcome_unknown`, unowned exchange order, or active critical domain hold | Reconcile/protect/freeze first; do not start new acceptance or engineering mutation |
| `P0-NATURAL` | New natural `signal_event_id` different from the last accepted identity | Pause engineering at the next committed transaction boundary, run production-chain acceptance, persist exact stage/blocker, then resume the same engineering checklist item |
| `P0-ENGINEERING` | No higher-priority event | Continue P0-LC certification, including synthetic/mock rehearsal that cannot create live authority |

A repeated observation of the same `signal_event_id` is idempotent and does not
preempt. Natural-signal priority does not bypass the mutation interlock,
FinalGate, Operation Layer, current ENTRY qualification, domain holds, or
account/exchange/mode checks. If the safe chain stops before submit, that exact
blocker is the acceptance result; the signal is not converted into authority.
An expired same-lane process outcome cannot block the new identity.

## Rollback And Forward-Fix

Rollback means disabling the durable mutation capability while keeping readonly
reconciliation and current-state inspection available. Unknown commands,
source-specific domain holds, lifecycle evidence, and settlement evidence are
never deleted or broadly cleared. Database rollback must not erase a command
whose exchange effect may have occurred; those rows are forward-fixed through
exchange reconciliation.

## Authority Boundary

This program may read exchange state and execute only recovery/runner/cleanup
commands for an existing ticket-bound lifecycle through committed durable
command authority. Risk-reducing lifecycle work uses historical Ticket identity;
new exposure still requires current ENTRY qualification. Before the durable
short-transaction capability is certified, lifecycle mutation remains
fail-closed.

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
stage: local_production_lifecycle_certification_complete_cutover_pending
first_blocker: full_verification_and_tokyo_two_phase_cutover_pending
evidence: local branch has typed account/exchange/mode/venue identity, complete order views and positionSide, global NettingDomain ownership/holds, committed short-transaction commands, fill projection, continuous reconciliation, independent settlement/finalization, one Outcome, 28-second application deadline, and producer-shaped 22-scope closure coverage
next_action: finish full verification and audits, commit/push, then execute fail-closed phase one and mechanically gated phase two on Tokyo
stop_condition: every production-shaped ticket reaches lifecycle_closed plus one outcome, or one deterministic hard blocker, without duplicate/ambiguous exchange mutation
owner_action_required: no
authority_boundary: historical Ticket risk reduction is separate from current ENTRY authority; no FinalGate/Operation Layer bypass, profile/sizing expansion, broad hold clearing, or unknown-order mutation
```
