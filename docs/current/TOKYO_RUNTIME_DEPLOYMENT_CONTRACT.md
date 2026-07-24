---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: CURRENT
last_verified: 2026-07-24
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

After switching, Observation, Lifecycle, and Reconciliation start first.
Readonly database and exchange certification repeats against the target
release. Entry starts last only when explicitly requested and every postflight
gate passes. A failure after service stop writes the Entry fence and restores
the three safety workers for fix-forward recovery.

## Destructive Rebuild Decision

The completed cutover followed an explicit Owner decision to preserve no BRC
backup. Old quantitative program services, containers, releases, databases,
schemas, and PostgreSQL application data were deleted, then rebuilt from the
committed baseline and seeds. Non-quantitative programs, Nginx, Docker,
PostgreSQL host operation, and unrelated data remained outside deletion scope.

The production tag is the rollback reference for code history only. Retired BRC
program or database state is not a runtime rollback authority.

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
- final flatness, no residual order, released budget/domain, zero Incident, and
  completed Owner state;
- first successful hourly observation after any deployment change.
