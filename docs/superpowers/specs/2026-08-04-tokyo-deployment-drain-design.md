---
title: TOKYO_DEPLOYMENT_DRAIN_DESIGN
status: PROPOSED
date: 2026-08-04
scope: Tokyo Trading Kernel deployment control plane and 0002-to-0003 source gate
---

# Tokyo Deployment Drain Design

## Decision

Tokyo deployment gains one explicit **Deployment Drain** capability. With an
immutable Owner authorization, the local release control plane may fence new
ENTRY and ask the exact currently deployed Trading Kernel to exit every
eligible active Ticket through its existing `ExitRequested` application path.
The certified current Lifecycle worker remains the only venue writer: it
dispatches durable, reduce-only EXIT Commands; Reconciliation confirms external
flatness, removes owned protection residue, releases capital authority, and
completes Settlement and Review. Schema migration starts only after every
existing flat compatible-upgrade gate passes again from direct evidence.

Deployment Drain is not DML, manual exchange operation, active-position
handover, dual write, an old-schema reader, or a target-release worker. The
source runtime owns every position until it is terminal and flat.

The same release corrects the `0002 -> 0003` source gate so certified historical
Tickets that terminated before exchange exposure are preserved without
fabricated Settlement or Review economics. Exposure-bearing terminal Tickets
continue to require Settlement and Review.

## Problem

The current release workflow has only two states:

1. deploy when already flat; or
2. block and wait for strategy-owned Stop, TP, or session exit.

That is safe but operationally incomplete. An Owner may decide that completing
a reviewed deployment is more important than preserving the remaining strategy
holding period. The Kernel already supports `ExitRequested`, durable reduce-only
market EXIT, protection cleanup, Reconciliation, Settlement, and Review, but no
production control-plane command can request that path for deployment.

The target Release Commit `854b09e9ff77f8ac3b4509d0c9964bfec28dcf06`
also classifies every Ticket or Aggregate whose status is not literally
`terminal` as active. Production contains historical `entry_rejected` Tickets
whose `terminal_at_ms` is present, whose exposure and authorities are zero, and
whose Aggregate status correctly remains `entry_rejected`. Requiring trade
economics for those non-exposure rejections would fabricate history; treating
them as active makes the exact target commit undeployable.

## Goals

1. Make Owner-authorized pre-deployment exit a first-class, repeatable, bounded,
   resume-safe release operation.
2. Preserve the current deployed commit and schema as the sole authority for
   every active Ticket until terminal closure.
3. Ensure every exchange mutation originates from one durable Exchange Command.
4. Keep Stop and TP protection in place until external flatness is observed.
5. Start migration only after internal and exchange flatness, residual-order,
   capital, command, Incident, Settlement, Review, Entry fence, and identity
   gates all pass.
6. Preserve no-exposure historical terminal rejection lineage without creating
   synthetic Settlement or Review facts.
7. Support both regular flat releases and compatible upgrades with one explicit
   drain authorization model, while implementing and certifying the current
   `0002 -> 0003` path first.

## Non-Goals

1. No direct SQL lifecycle mutation or production DML repair.
2. No Binance UI, API, or ad hoc manual close/cancel operation.
3. No Stop, TP, strategy, capital, leverage, credential, Policy, or market-scope
   mutation.
4. No active-position transfer to the target release.
5. No new exchange command kind; the existing EXIT and CANCEL_ORDER commands
   remain authoritative.
6. No automatic drain on every deployment. The default remains fail-closed.
7. No unlimited retry after rejection or unknown outcome.
8. No `0004` migration. Revision `0003_portfolio_admission_observability` is
   still unreleased and may receive the corrected source predicate in a new
   Release Commit.

## Current Production-Shaped Evidence

The 2026-08-04 readonly Tokyo inspection found two active Tickets. Both are
`position_protected`, own nonzero projected positions and active Netting
Domains, and have accepted ENTRY, Initial Stop, and Take Profit Commands. Entry
is inactive, disabled, and write-fenced. Lifecycle and Reconciliation are
active. The current production commit contains the existing `request_exit()`
use case and the complete exit-to-review chain.

This evidence proves eligibility for the proposed source-owned drain model. It
does not itself authorize the real-funds EXIT.

## Authority Model

### Owner Authorization

Drain requires all of the following explicit CLI inputs:

```text
--drain-active-tickets
--drain-authorization-id <immutable-nonblank-identifier>
--commit <exact-target-40-hex-sha>
```

`--drain-active-tickets` without an authorization identity is invalid. The
authorization identity is persisted in each `ExitRequested.reason` together
with the exact target commit:

```text
deployment_drain:<authorization_id>:<target_commit>
```

The identifier is audit identity, not a policy or credential. It cannot select
account, venue, instrument, side, quantity, price, or Ticket.

### Ticket Scope

The operator does not supply Ticket IDs. The control plane reads the complete,
bounded active Ticket set from the exact source database and drains all eligible
Tickets for the configured production account. The set must not exceed the
source Owner Policy concurrent-Ticket limit or the hard deployment bound of
three.

An initial drain request is eligible only for Aggregate status:

```text
position_protected
runner_protected
```

These states already support `ExitRequested` in the deployed reducer. States
already progressing through EXIT, Reconciliation, Settlement, or Review are
resume states rather than new requests. Rejected EXIT, partial-fill,
protection-pending, replacement-pending, cancel-recovery, contradictory, or
unknown states block a new drain request and preserve the current workers.

### Runtime Identity

Before the first write, the control plane requires exact agreement among:

- current release marker;
- PostgreSQL runtime commit, schema revision, and seed identity;
- source revision requested by the deployment plan;
- production account, venue, position mode, margin mode, and runtime profile;
- local target commit and target schema revision.

The remote bridge imports the exact current release package from
`/opt/brc/current`; it does not import the target release against the source
schema. The target release does not manage source exposure.

The bridge wrapper is committed as part of the exact local control-plane
commit and streamed to `/opt/brc/current/.venv/bin/python` through SSH stdin. It
is never written into the server release tree. Before calling current-release
application code, it requires the exact source Alembic revision and runtime
identity inside the same database transaction. It refuses to run after the
source revision changes, and no bridge process survives migration. Therefore it
is a bounded pre-deployment control-plane adapter, not an old-schema runtime
reader or compatibility worker.

## Control-Plane Interface

The existing deployment command gains optional arguments:

```bash
python3 scripts/trading_kernel/deploy_tokyo_release.py \
  --commit <exact-target-sha> \
  --mode compatible_upgrade \
  --source-schema-revision 0002_sor_v3_strategy_group_capacity \
  --drain-active-tickets \
  --drain-authorization-id <immutable-id> \
  --drain-timeout-seconds 1800
```

Drain cannot be combined with `--enable-entry`. `--drain-timeout-seconds` must
be positive and bounds only the drain observation window; it does not weaken
any deployment gate. A timeout returns a blocked result while Entry remains
fenced and the current safety workers remain active.

The implementation keeps focused drain planning, validation, remote bridge,
and progress types in a dedicated deployment-control module rather than
further expanding the release script. `deploy_tokyo_release.py` owns sequencing
and invokes that module before the existing flat preflight.

The bridge contains no lifecycle reducer, SQL state transition, command
materializer, or venue client. Its only write-capable call is the exact current
release `request_exit()` application use case through the current release
`PostgresKernelUnitOfWork`.

## Execution Flow

### Phase 1: Readonly Orientation

1. Resolve the exact target commit locally and require a clean committed tree.
2. Read the exact current release, source commit, schema, seed, Policy, Registry,
   account, service, fence, PostgreSQL, and exchange facts.
3. Reject wrong identity, missing protection, external/internal contradiction,
   unresolved Command, open Incident, unowned order, or unsupported Ticket
   status.

### Phase 2: Fence New Exposure

1. Create or retain `/etc/brc/trading-kernel.write-fenced`.
2. disable and stop Entry;
3. prove Entry is inactive and disabled;
4. keep Observation, Lifecycle, and Reconciliation active under the exact
   source identity.

No source safety worker is stopped during drain.

### Phase 3: Request Source-Owned Exit

For each eligible active Ticket, ordered by stable Ticket identity:

1. re-read the exact Aggregate under its normal optimistic version;
2. append one `ExitRequested` Event through `request_exit()`;
3. atomically reduce the Aggregate to `exit_pending` and persist one durable
   reduce-only market EXIT Command;
4. commit before any venue I/O;
5. record the exact authorization and target commit in the Event reason.

Each Ticket uses a separate short transaction. A crash between Tickets leaves
the first request durable and the remaining protected Tickets unchanged. A
resume scan treats `exit_pending`, `exit_accepted`, `exit_outcome_unknown`,
`reconciliation_pending`, `settlement_pending`, and `review_pending` as
in-progress states and does not create duplicate EXIT generations.

### Phase 4: Current Runtime Drain

1. The current Lifecycle worker claims and dispatches prepared EXIT Commands.
2. EXIT payload remains `market`, exact current quantity, closing side, and
   `reduce_only=true`.
3. Existing Stop and TP orders remain in place until exchange flatness is
   observed.
4. Reconciliation records `PositionFlatConfirmed`, cancels each exact owned
   protection residue through durable CANCEL_ORDER Commands, and verifies their
   absence.
5. Reconciliation records `ReconciliationMatched`, releases Reservation and
   Netting Domain authority, settles, and records Review.

### Phase 5: Existing Deployment

Only after every existing source and exchange gate passes does the command enter
the current regular or compatible-upgrade sequence. For `0002 -> 0003`, that
means stopped writers, canonical source preservation manifest, forward Alembic
migration, target identity activation, six-Universe bootstrap, target
postflight, Entry still inactive/disabled/fenced, immutable tag, and roadmap
update.

## Idempotency And Resume

The database lifecycle is the drain journal. No JSON, Markdown, local cache, or
new runtime table owns progress.

- An eligible protected Ticket receives one request.
- An already progressing Ticket receives no duplicate request.
- An already terminal Ticket is omitted from the active set.
- A process crash is resumed by re-reading Ticket and Command state.
- A rejected EXIT is not retried automatically.
- An unknown EXIT outcome is never resent; Reconciliation resolves external
  truth first.
- Migration never starts while any drain state remains nonterminal.

## Failure Handling

| Failure | Required result |
| --- | --- |
| Source identity changes | Abort before a drain write |
| Internal/exchange position contradiction | Abort before a drain write |
| Missing or contradictory protection | Abort before a drain write |
| EXIT rejected | Persist Incident, block deployment, retain source workers |
| EXIT outcome unknown | Reconcile exact external truth, no blind resend |
| Position remains partially open | Remain on source runtime and block migration |
| Stop or TP wins the race | Reduce-only prevents position reversal; reconcile actual flatness |
| Protection cancel rejected or unknown | Block Settlement and deployment until resolved |
| Drain timeout | Return blocked; Entry remains fenced; safety workers remain active |
| Failure after schema migration | Target `0003` fix-forward only; never restart `0002` workers |

## Historical Terminal Classification

### Exposure-Bearing Terminal Ticket

A Ticket whose final Ticket and Aggregate status is `terminal` represents a
completed exposure lifecycle. It must have:

- terminal timestamp;
- zero position and protected quantity;
- no owned order residue;
- released Reservation and Netting Domain;
- zero unresolved Command and open Incident;
- Settlement transition;
- current effective Trade Review.

### No-Exposure Terminal Rejection

The following exact Ticket/Aggregate status pairs are terminal without trade
economics:

```text
leverage_rejected / leverage_rejected
entry_rejected / entry_rejected
entry_reconciled_absent / entry_reconciled_absent
```

They may pass source migration only when `terminal_at_ms` is present and every
position, protected quantity, order identity, Reservation, Netting Domain,
ENTRY lane, unresolved Command, and open Incident is absent or released. They
must not receive fabricated Settlement or Review rows.

The source verifier, Alembic atomic guard, and Tokyo cutover inspection must use
the same explicit classification. Any other non-`terminal` status remains a
hard blocker.

## Data And Transaction Ownership

| Concern | Owner |
| --- | --- |
| Drain authorization | Explicit CLI identity plus immutable target commit |
| Active Ticket selection | Exact bounded PostgreSQL current state |
| Exit state transition | Current release `request_exit()` transaction |
| Venue mutation | Current Lifecycle durable Exchange Command dispatcher |
| External position/order truth | Binance readonly facts |
| Cleanup and closure | Current Reconciliation worker |
| Drain progress | Existing Ticket, Aggregate, Event, Command, Incident, Settlement, and Review lineage |
| Migration preservation | Existing canonical `0002` source manifest |
| Target activation | Existing compatible-upgrade state machine |

## Security And Scope Boundaries

- No operator-provided account, venue, instrument, side, quantity, order type,
  or Ticket list.
- No credential value appears in arguments, stdout, markers, or Event reason.
- The control plane cannot enable Entry.
- The bridge has no venue adapter and cannot perform network exchange I/O.
- The exact current Lifecycle worker remains runtime-fence checked before every
  dispatch.
- A drain authorization is scoped to one exact target commit and cannot be
  reused for a different release identity.

## Test Strategy

### Domain And Application

Existing exit-chain tests remain authority. New tests prove that a deployment
reason creates the same single `ExitRequested` Event and one durable reduce-only
EXIT Command as a strategy exit, without changing Stop or TP identities.

### Control Plane

Tests cover:

1. missing or malformed authorization identity;
2. drain combined with `--enable-entry`;
3. zero active Ticket no-op;
4. one and multiple eligible protected Tickets;
5. bounded deterministic Ticket ordering;
6. in-progress resume without duplicate EXIT;
7. unsupported active status blocks before write;
8. identity, protection, Incident, Command, and exchange contradictions;
9. crash after the first Ticket request and successful resume;
10. EXIT rejection, unknown outcome, remaining quantity, cleanup residue, and
    timeout all block deployment while source safety workers remain active;
11. successful terminal closure enters the unchanged release preflight;
12. exact authorization and target commit appear in Event lineage.

### Migration

Production-shaped `0002` fixtures cover:

1. no-exposure terminal rejection without Review passes;
2. exposure-bearing terminal Ticket without Review fails;
3. every allowed rejection pair with residue fails;
4. any unclassified nonterminal status fails;
5. source verifier and Alembic atomic guard agree;
6. preservation manifest is byte-for-byte identical before and after `0003`;
7. base-to-head and exact `0002 -> 0003` rehearsals pass.

### Release Verification

Run targeted unit and PostgreSQL integration tests, the full Trading Kernel
suite, architecture tests, Ruff, Mypy, production file-I/O audit, diff checks,
and production-shaped compatible-upgrade rehearsal before creating the new
Release Commit.

## Documentation And Release Identity

`TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` will define Deployment Drain as an
explicit pre-deployment operation and clarify exposure-bearing versus
no-exposure terminal evidence. Stable documents will not contain volatile
Ticket IDs or transient counts.

The existing commit `854b09e9ff77f8ac3b4509d0c9964bfec28dcf06`
remains immutable historical candidate evidence. Implementation produces a new
exact Release Commit, and the heartbeat authorization must be updated to that
SHA before any drain or deployment write.

## Acceptance Criteria

1. Default deployment behavior remains fail-closed and performs no drain.
2. Explicit drain authorization can request exit for all and only eligible
   active Tickets through the exact current release application boundary.
3. Every venue mutation remains a durable source-runtime Exchange Command.
4. Entry remains inactive, disabled, and fenced throughout drain and target
   deployment.
5. No migration begins until all current flat-compatible gates pass.
6. Re-running after crash creates no duplicate EXIT request or command.
7. Rejection, unknown outcome, residual quantity, order residue, Incident, or
   timeout blocks deployment without stopping source safety workers.
8. Historical no-exposure terminal rejections migrate without fabricated
   economics, while exposure-bearing terminal history still requires Review.
9. Source preservation manifest matches exactly across `0002 -> 0003`.
10. The target Schema remains `0003_portfolio_admission_observability` and the
    final production release receives one new immutable Tokyo tag only after
    complete postflight evidence.
