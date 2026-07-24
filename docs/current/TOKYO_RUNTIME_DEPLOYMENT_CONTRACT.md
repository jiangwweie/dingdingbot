---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: DEPLOYED_ACCEPTANCE_ACTIVE
last_verified: 2026-07-23
---

# Tokyo Runtime Deployment Contract

## Current Production Identity

| Identity | Current value |
| --- | --- |
| Git commit | `f9fda21c91482b050e2a630e163f3213386ae6d7` |
| Production tag | `tokyo-runtime-2026.07.23.1`, fixed to `f9fda21c` |
| Local certification | `331 passed`; Ruff clean; Mypy clean; file-I/O audit clean |
| Schema | Single 33-table `0001_initial` baseline |
| Runtime services | Persistent Observation, Entry, Lifecycle, and Reconciliation workers |
| Hourly supervision | Active read-only automation |
| Full policy state | `promote-full` pending |

## Deployment Model

Tokyo runs committed releases only. Local SSH is the control plane; ad hoc
server source edits are forbidden. Production workers are persistent systemd
services with bounded polling, restart-on-failure, and a shared resource slice.
Timer-based worker cold starts are forbidden.

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
margin. `new_entry_submit_enabled` is a new-ENTRY gate only. Every mutating
worker must match the certified commit and schema; a mismatch records a runtime
Incident and fences that writer while readonly checks remain allowed.

## Persistent Worker Contract

| Worker | Exclusive responsibility | Idle behavior |
| --- | --- | --- |
| Observation | Read closed market data, compute Facts, run six detectors, ingest StrategySignals | Bounded poll with no file output |
| Entry | Arbitrate readiness, build CapacityClaim, issue Ticket, dispatch ENTRY | Global new-ENTRY serialization |
| Lifecycle | Install/maintain protection and execute Ticket exits | Concurrent by Ticket, bounded idle poll |
| Reconciliation | Resolve exchange truth, unknown outcomes, terminal closure, Settlement, Review | Bounded current-state queries |

Exactly one deployed service owns each role. Restoring periodic process creation
is a production regression.

## Active Controlled Acceptance

The current natural acceptance flow is:

```text
SOR-001 / SOR-SHORT / SOLUSDT
-> ticket:c1ebc24a178a3ae4d87978e2fa1204ae
-> 0.25 SOL short at 77.51
-> Initial Stop 78.50 accepted
-> TP1 76.52 accepted
-> position_protected
```

This proves natural Observation through protected position, not terminal system
acceptance. Do not call `promote-full` while the Ticket is nonterminal or any
residual order, budget, Incident, unknown outcome, Settlement, or Review item is
unresolved.

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
