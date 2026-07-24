---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: DEPLOYED_ACCEPTANCE_ACTIVE
last_verified: 2026-07-24
---

# Tokyo Runtime Deployment Contract

## Current Production Identity

| Identity | Current value |
| --- | --- |
| Git commit | `4749174c64a6b369930ed91f09d7b9eba1fa0e7a` |
| Local certification | `407 passed`; focused Ruff and Mypy checks pass |
| Schema | Single 33-table `0001_initial` baseline |
| Runtime services | **Acceptance-armed**: Observation, Entry, Lifecycle, and Reconciliation enabled and active |
| Hourly supervision | All four persistent workers active; Entry remains globally serialized |
| Full policy state | `promote-full` pending |

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

The runtime seed uses the dynamic three-Ticket policy: `0.03` planned stop risk,
`0.90` maximum initial-margin utilization, maximum leverage `10`, and `cross`
margin. The exchange configuration is fixed at `5x`; the kernel freezes that
fact and does not create a leverage-mutation command. `new_entry_submit_enabled`
is a new-ENTRY gate only. Every mutating worker must match the certified commit
and schema; a mismatch records a runtime Incident and fences that writer while
readonly checks remain allowed.

## Persistent Worker Contract

| Worker | Exclusive responsibility | Idle behavior |
| --- | --- | --- |
| Observation | Read closed market data, compute Facts, run six detectors, ingest StrategySignals | Bounded poll with no file output |
| Entry | Arbitrate readiness, build CapacityClaim, issue Ticket, dispatch ENTRY | Global new-ENTRY serialization |
| Lifecycle | Install/maintain protection and execute Ticket exits | Concurrent by Ticket, bounded idle poll |
| Reconciliation | Resolve exchange truth, unknown outcomes, terminal closure, Settlement, Review | Bounded current-state queries |

Exactly one deployed service owns each role. During the current
**Acceptance-armed** stage, all four workers are active. The fixed-account
leverage design removes new `SET_LEVERAGE` production commands, so the earlier
leverage-mutation rejection remains audit history instead of a current Entry
blocker. Restoring periodic process creation is a production regression.

## Current Controlled Acceptance Baseline

Tokyo is **Acceptance-armed** with exact runtime commit `4749174c` and command
capability certified. All six supported instruments are configured at `5x`.
Three terminal `leverage_rejected` Tickets remain audit records for the retired
leverage-mutation path; all three commands are `reconciled_absent`. The
verified deployment snapshot has zero position, order, active Ticket,
unresolved command, and open Incident. Entry is active for the next natural
signal; constructed signals and direct exchange writes remain forbidden.

Do not call `promote-full` until that new Ticket is terminal, flat, reconciled,
settled, reviewed, and leaves no residual order, budget, Incident, or unknown
outcome.

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
