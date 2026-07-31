---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: CURRENT
last_verified: 2026-07-30
---

# Tokyo Runtime Deployment Contract

## Runtime State Authority

Exact production commit, immutable tag, certification, measured resource state,
and remaining gates belong only to `MAIN_CONTROL_ROADMAP.md`. This contract owns
the procedure and limits used to deploy and evaluate that state.

## Deployment Model

Tokyo runs committed releases only. Local SSH is the control plane; ad hoc
server source edits are forbidden. Production workers are persistent systemd
services with bounded polling, restart-on-failure, and a shared resource slice.
Timer-based worker cold starts are forbidden.

Normal code updates use
`scripts/trading_kernel/deploy_tokyo_release.py`. One command stages the exact
commit, verifies PostgreSQL flatness and zero runtime activity, verifies
exchange flatness, zero open orders, independent sides, Cross margin, and
configured `5x` leverage for all supported instruments, then stops the old
workers and switches the release. Schema rebuild and destructive cutover
checks are outside this regular-release path.

An explicit `--protected-ticket-id` handover is a separate, one-time
fix-forward mode for an exact set of already protected Tickets. It does not
relax the normal flat-release rule: the caller must name every active Ticket,
every named `position_protected` Ticket must retain a complete active Stop and
TP1 identity, and every named `runner_protected` Ticket must retain its
complete active runner Stop and recorded TP1 fill. Projected quantity must
equal protected quantity unless that Ticket is explicitly named as an
unrecorded full-TP1 runner replay. The ENTRY lane must be idle, and there must
be zero unresolved Exchange Command or Incident. PostgreSQL
atomically rechecks those predicates while all old workers are stopped before
it rotates runtime identity. The mode permits no schema change, no new ENTRY,
no Ticket/quantity/policy mutation, and no exchange write outside the normal
Lifecycle durable-command chain. It also requires the exchange protected
position and open-order domain counts to equal the named Ticket count. It is
not a general active-position upgrade mechanism. Observation and
Reconciliation restart first for a static target identity check; Lifecycle
restarts only after that check so its intended recovery mutation cannot race
the handover certification.

After a normal switch, Observation, Lifecycle, and Reconciliation start first.
Readonly database and exchange certification repeats against the target
release. Entry starts last only when explicitly requested and every postflight
gate passes. A failure after service stop writes the Entry fence and restores
the three safety workers for fix-forward recovery.

## StrategyUniverse Deployment Gate

The versioned StrategyUniverse release is a **flat-only destructive rebuild**.
It is not activated by a local test pass or by all positions becoming flat
without an Owner release confirmation. Before its
`0001_trading_kernel_baseline_v3` rebuild, configuration, or Entry enablement,
all Ticket, position, order, Incident, Settlement and Review projections must
be terminal and exchange truth must be flat.

The approved v2-to-v3 procedure is **Terminal-History Clean Rebuild**. Entry
remains fenced while the existing exposure reaches **natural terminal
closure**; a healthy Runner is never controlled-exited merely to satisfy a
deployment window. After terminal closure, a version-controlled
**terminal-history transformer** imports the exact terminal episode into the
clean v3 schema. No target worker starts before `HISTORY_IMPORTED` proves
identity/digest parity and zero active runtime state.

After the target code and schema pass readonly certification, the Owner fixes
each Event's final **1..10** canonical USDT-perpetual members. The official
configuration CLI installs Warming Universes only. Existing Reconciliation and
Observation workers then certify, prewarm and atomically activate the current
pointer. Entry remains fenced until those safety workers and the exact active
Universe/current/profile/policy identities pass postflight. `--enable-entry`
is still an explicit final deployment action; neither configuration nor
activation can enable it.

The completed Batch is created while new ENTRY authority is disabled. The
final promotion may carry that Batch across only an exact direct-successor
policy-stage transition where
`current_policy_version = batch_policy_version + 1` and new ENTRY authority is
armed. Skipped versions, an unarmed successor, or any
risk/scope/manifest/commit/schema/seed drift invalidates the gate. Historical
Ticket policy versions remain immutable; the v3 seed uses an unoccupied later
version rather than redefining `policy-main:v2`. This is a bounded stage
transition, not a policy compatibility rule.

### Bounded Rebuild Procedure

For a small-capital, flat personal runtime, the approved path is a stopped
rebuild rather than a long sequential Warming procedure:

1. Keep Entry fenced and let Observation, Lifecycle and Reconciliation manage
   every current exposure until natural terminal closure. A deployment
   schedule does not authorize controlled exit.
2. Verify exchange flatness, no open orders, no unresolved command, no open
   Incident, released budget/Netting Domain state, Reconciliation, Settlement
   and Review.
3. Stage the exact committed release and its tested terminal-history
   transformer. Stop all four BRC workers and atomically recheck terminal and
   flat facts.
4. Export the exact v2 PostgreSQL snapshot, table/row manifest and checksum.
   The source is a controlled deployment input, not a runtime authority file.
5. Rebuild only BRC PostgreSQL state from the committed clean baseline and
   deterministic Registry/Policy/Capability seeds. Do not alter credentials,
   funds, account mode, leverage or exchange trading scope.
6. Run the terminal-history transformer in one target transaction. It must
   preserve the complete terminal Signal/Claim/Ticket/Event/Command/
   Settlement/Review lineage, preserve historical policy identity, exclude
   all old current/control rows, and complete `HISTORY_IMPORTED` only after
   parity and zero-active-state checks pass.
7. Start Observation and Reconciliation while the Entry fence remains
   present. Lifecycle and Entry remain stopped.
8. Run the official batch bootstrap once. It serially installs and awaits all
   six Warming Universes because PostgreSQL permits only one Warming Universe
   at a time; the resident workers perform the required readonly certification
   and activation work between Events under one shared bounded stage deadline.
   The deployment never waits for a separate multi-hour operator sequence per
   Event.
9. Start Lifecycle and complete its fenced flat/no-residue/terminal-history
   smoke. Then start Entry while the write fence and disabled new-ENTRY
   authority remain present.
10. Repeat readonly postflight for exact commit, clean schema, seed, historical
   parity, account mode, runtime profile, policy, Certification Batch, active
   Universe pointers, exchange flatness, worker health, and zero unresolved
   runtime state.
11. Only an explicit promotion after all postflight gates may arm new-ENTRY
   authority and remove the fence. If any step fails, keep Entry fenced and
   retain only the phase-safe workers for diagnosis or controlled recovery.

This is a forward-only fix path. The transformer is a one-time data conversion,
not a v2 runtime reader, compatibility service, dual-write path or schema
fallback. Reintroducing the retired schema evolution chain or an old writer is
not a rollback.

If batch bootstrap reports an exact Warming timeout or a terminal
certification blocker, Entry remains fenced. Inspect the bounded Universe
status, then use `abandon_strategy_universe.py` with that exact
`universe_version_id` and a stable reason code. The command changes only the
target PostgreSQL Warming state, records the reason, releases its certification
lease, and performs no exchange mutation. Restart the batch after the cause is
corrected; direct SQL and anonymous slot clearing are forbidden.

## Destructive Rebuild Decision

The completed cutover followed an explicit Owner decision to preserve no BRC
backup. Old quantitative program services, containers, releases, databases,
schemas, and PostgreSQL application data were deleted, then rebuilt from the
committed baseline and seeds. Non-quantitative programs, Nginx, Docker,
PostgreSQL host operation, and unrelated data remained outside deletion scope.

The production tag is the rollback reference for code history only. Retired BRC
program or database state is not a runtime rollback authority.

For the pending v3 cutover, the Owner superseded the prior no-history-retention
procedure only for the exact terminal episode: the final v2 snapshot is kept as
auditable source evidence and the canonical terminal lineage is transformed
into v3. Old current/control state, old workers and old schema remain retired
and are not restored as production authority.

## Version Contract

Every successful production release receives one annotated immutable tag using:

```text
tokyo-runtime-YYYY.MM.DD.N
```

The tag points to the exact deployed code commit. Documentation-only commits
after deployment are not retagged as production. A repeated release on the same
date increments `N`; an existing production tag is never moved or deleted to
represent newer code.

## Required Runtime Chain

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

No Tokyo command may bypass this chain or create an exchange mutation without a
durable Exchange Command.

The experiment profile owns capacity, stop-risk, margin utilization, leverage,
and margin-mode values. The exchange configuration is fixed rather than
selected per Ticket; the kernel freezes that fact and does not create a
leverage-mutation command. `new_entry_submit_enabled` is a new-ENTRY gate only.
Every mutating worker must match the certified commit and schema; a mismatch
records a runtime Incident and fences that writer while readonly checks remain
allowed.

## Persistent Worker Contract

| Worker | Exclusive responsibility | Idle behavior |
| --- | --- | --- |
| Observation | Read closed market data, compute Facts, run six detectors, ingest StrategySignals | Bounded poll with no file output |
| Entry | Arbitrate readiness, build CapacityClaim, issue Ticket, dispatch ENTRY | Global new-ENTRY serialization |
| Lifecycle | Install/maintain protection and execute Ticket exits | Concurrent by Ticket, bounded idle poll |
| Reconciliation | Resolve exchange truth, unknown outcomes, terminal closure, Settlement, Review | Bounded current-state queries |

Exactly one deployed service owns each role. The fixed-account leverage design
removes new `SET_LEVERAGE` production commands. Restoring periodic process
creation is a production regression.

## Resource Envelope

| Resource | Contract | Purpose |
| --- | --- | --- |
| Shared CPU | `CPUQuota=100%` | Bound all four workers to one CPU of host time |
| Shared memory | `MemoryMax=1G` | Contain BRC worker memory independently of PostgreSQL |
| Shared tasks | `TasksMax=128` | Prevent unbounded process or thread growth |
| Observation poll | 5 seconds | Closed-market-data and detector cadence |
| Entry poll | 2 seconds | Bounded new-ENTRY admission latency |
| Lifecycle poll | 2 seconds | Bounded protection and exit cadence |
| Reconciliation poll | 5 seconds | Bounded external-truth convergence |

PostgreSQL runs outside the worker slice and is measured separately. No worker
may create periodic JSON or Markdown output during healthy idle cadence.

## Operational Performance Review

The regular release path does not add a performance wait before service switch
or Entry startup. Readonly post-release supervision records the following
warning boundaries:

1. all required workers remain active and their restart counters do not
   increase during the observation window;
2. shared-slice idle memory remains below 80% of `MemoryMax`;
3. shared-slice CPU remains below 10% of one CPU over a representative idle
   sample;
4. task count remains below 50% of `TasksMax`;
5. host available memory remains at or above 1 GiB;
6. filesystem usage remains below 80%;
7. no timer worker, warning loop, generated runtime file, open Incident, or
   unresolved command appears.

A warning does not stop safety workers or add exchange calls to deployment.
Sustained breach, restart growth, or resource exhaustion triggers readonly
diagnosis and uses the existing official Entry fence when new exposure would be
unsafe. Existing exposure keeps protection, controlled exit, and reconciliation
authority. The current measured snapshot belongs only to
`MAIN_CONTROL_ROADMAP.md`.

## Full-Promotion Gates

Every condition must be current and true:

1. acceptance Ticket terminal;
2. exchange position flat;
3. no open or residual order;
4. budget and Netting Domain released;
5. Reconciliation matched;
6. Settlement complete;
7. Review complete with exact economics or explicit `funding_unavailable`;
8. zero open Incident;
9. zero unknown command outcome;
10. deployed commit, schema, seed, account mode, runtime profile, and Owner
    Policy identities agree.

## Required Evidence

- deployed git SHA and immutable production tag;
- Alembic revision, schema metadata, and exact table allowlist;
- systemd state for all four persistent workers and absence of periodic worker
  scheduling;
- readonly account mode, position, order, and protection truth;
- exact StrategySignal, CapacityClaim, Ticket, Trade Event, Exchange Command,
  position, Reconciliation, Settlement, and Review lineage;
- exact v2 terminal snapshot manifest/checksum, transformer identity,
  `HISTORY_IMPORTED` parity and excluded current/control rows;
- final flatness, no residual order, released budget/domain, zero Incident, and
  completed Owner state;
- first successful hourly observation after any deployment change.
