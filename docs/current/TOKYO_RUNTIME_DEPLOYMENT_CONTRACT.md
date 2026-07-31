---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: CURRENT
last_verified: 2026-07-31
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

After a normal switch, Observation, Lifecycle, and Reconciliation start first.
Readonly database and exchange certification repeats against the target
release. Entry starts last only when explicitly requested and every postflight
gate passes. A failure after service stop writes the Entry fence and restores
the three safety workers for fix-forward recovery.

## Flat Compatible Upgrade

The only schema-changing release path is an exact, forward-only, stopped
upgrade:

```text
0001_trading_kernel_baseline_v4
-> 0002_sor_v3_strategy_group_capacity
```

It preserves terminal PostgreSQL lineage; it does not preserve an active v2
runtime. An active-position handover, dual write, v4 reader, schema fallback,
manual DML conversion and direct SQL lifecycle mutation are forbidden.

The compatible-upgrade preflight requires all of the following to be current:

1. zero nonterminal Ticket and zero non-flat projected or exchange position;
2. zero open exchange order or internal protection residue;
3. zero active Budget Reservation and released Netting Domains;
4. every terminal Ticket has Settlement/Review evidence;
5. zero unresolved Exchange Command and zero open Incident;
6. Entry is fenced and every old writer is stopped before the final check;
7. source revision, target revision, commit, account, venue and policy identity
   match the exact plan.

The official bounded sequence is:

1. Use the Lifecycle and Reconciliation chain to terminate every old exposure;
   migration never substitutes for an EXIT or settlement operation.
2. Stage the exact target release and run source-schema plus exchange readonly
   preflight.
3. Fence Entry, stop all four writers and atomically repeat the flat checks.
4. Compute and persist a canonical SHA-256 manifest over every frozen `0001`
   table and column; `alembic_version` and `0002`-only columns are excluded.
5. Run the single certified Alembic revision without `DROP SCHEMA`.
6. Recompute the same frozen `0001` manifest and require an exact digest match.
7. In one PostgreSQL transaction, retire SOR v2 Registry authority, activate
   SOR v3, create the next Owner Policy version with unchanged capital limits,
   move scope to v3 and rotate schema/commit/seed capability identity.
8. Activate the target release and start Observation, Lifecycle and
   Reconciliation while Entry remains fenced.
9. Run one bounded six-Event StrategyUniverse bootstrap; PostgreSQL may
   serialize the Warming slot internally, but the operator does not install
   Events one at a time.
10. Repeat database, history, exchange, Universe, worker and identity postflight;
    start Entry last and remove the fence only when explicitly requested.

The journaled cutover state machine and `deploy_tokyo_release.py` use the same
gates and authority transition. They must not evolve into different migration
semantics. A failure after migration remains Entry-fenced and proceeds by
target-schema fix-forward; the `0001` runtime is never restarted against
`0002`.

## StrategyUniverse Deployment Gate

After target identity activation, the official configuration CLI installs only
Warming Universes. Observation and Reconciliation certify and atomically switch
the current pointer to v3. Entry remains fenced until the exact active Universe,
profile, Policy, schema, preservation and runtime identities pass postflight.
Neither configuration nor activation independently grants new-ENTRY authority.

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
