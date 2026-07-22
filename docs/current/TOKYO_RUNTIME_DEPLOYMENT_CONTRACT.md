---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: CURRENT
last_verified: 2026-07-22
---

# Tokyo Runtime Deployment Contract

## Deployment Model

Tokyo deployment uses committed code and committed operations tooling. Local
SSH is the control plane. Ad hoc server source edits are forbidden.

## Preconditions

Before destructive cutover, verify from current server and exchange facts:

```text
all exchange positions flat
all open orders absent
all protection orders absent
all old Tickets terminal
all budgets released
all exchange outcomes resolved
all old writers stopped and fenced
target commit and baseline identity reviewed
```

Any failed precondition stops before schema destruction.

## Crash-Safe Cutover Phases

1. plan and record exact target identities;
2. fence new exchange writes;
3. stop and verify all old writers;
4. repeat final readonly flat-state verification;
5. create a short-lived rollback snapshot;
6. drop and recreate the application schema;
7. install `0001_initial`;
8. seed registry, policy, instruments, account, profile, scopes, lane, and
   schema metadata;
9. deploy the exact target release;
10. run schema and readonly certification;
11. enable observation and monitor capability;
12. enable typed signal and non-writing Ticket certification;
13. enable exchange-command capability only after safety passes;
14. execute one controlled in-scope Ticket through terminal review;
15. delete short-lived rollback material and retired releases.

Every phase is idempotent or verifies that its postcondition already holds.
Resume never skips a failed verification.

## Rollback

Before new-schema acceptance, rollback may restore the operational snapshot
with exchange writes fenced. After acceptance, retired program or schema
authority is not restored; failures are fixed forward while write capability
remains disabled.

## Acceptance Evidence

- deployed git SHA;
- Alembic revision and schema metadata identity;
- exact production table allowlist with zero retired tables;
- systemd service/timer state;
- readonly account mode, positions, orders, and protection state;
- runtime capability rows;
- controlled Ticket lineage from signal through terminal review;
- final flatness, no residual orders, released budget, matched reconciliation,
  and Owner-facing completed state.
