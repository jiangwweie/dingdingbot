---
title: P0_PROTECTED_ACTIVE_LIFECYCLE_DEPLOYMENT_DESIGN
status: OWNER_APPROVED
authority: docs/current/P0_PROTECTED_ACTIVE_LIFECYCLE_DEPLOYMENT_DESIGN.md
last_verified: 2026-07-15
---

# P0 Protected Active Lifecycle Deployment Design

## Owner Decision

Manual exchange close ends only the current trade. It does not pause automatic
trading. Tokyo deployments may interrupt lifecycle maintenance for up to one
hour when every active real lifecycle is stable and exchange-protected.

## Problem

The current deploy verifier rejects every real lifecycle whose status is not
`lifecycle_closed`. That treats a stable `position_protected` or
`runner_protected` position as equivalent to an unprotected entry, an unknown
exchange command, or an active recovery hold. Requiring an empty account for
every release is incompatible with continuous live experimentation.

## Decision

Replace the global no-active-lifecycle deploy rule with a typed classification:

```text
active real lifecycle
-> stable status and protection_complete=true
   -> protected_active_lifecycle; deploy may continue under quiescence
-> any other state
   -> unsafe_active_lifecycle; deploy fails closed
```

Stable deployable statuses are exactly:

```text
position_protected
runner_protected
```

An active real lifecycle is unsafe when its status is outside that set, its
protection set is absent/incomplete, it carries a non-empty `first_blocker`, or
the deploy verifier finds a critical exchange command, active scope freeze, or
unprotected real attempt.

## Controlled Sequence

```text
export target release
-> classify active lifecycle state read-only
-> stop watcher, monitor, lifecycle, and backend units
-> repeat classification under quiescence
-> disable lifecycle mutation capability
-> migrate, seed, validate, and switch release
-> refresh account-mode truth
-> reclassify active lifecycle state
-> enable lifecycle mutation capability
-> run one PG-only zero-exchange-write lifecycle scheduler invocation
-> start lifecycle service and timers
-> publish exact-head Action-Time capability/current projections
-> restore watcher timer
```

The synchronous systemd stop is the single-writer fence. The capability remains
disabled throughout the code/schema switch. No second worker, file authority,
or compatibility repository is introduced.

## Fail-Closed Conditions

Deployment remains blocked by any of:

- `critical_exchange_commands > 0` for `dispatching`, `outcome_unknown`, or
  `hard_stopped` commands;
- `active_domain_holds > 0`;
- `unprotected_real_attempts > 0`;
- `unsafe_active_real_lifecycles > 0`;
- missing required PG tables or invalid capability structure;
- missing fresh safe account mode during phase-two enablement;
- failure to stop the old services, disable capability, migrate, validate,
  re-enable capability, or start the new lifecycle service.

## Rollback

Before symlink switch, failure restores the prior capability state and prior
services. After switch, phase-two failure leaves lifecycle mutation disabled;
the release is rolled back through the existing bounded release rollback path.
Exchange-native protection remains active during the accepted maintenance
window. Rollback never submits, cancels, amends, or closes an exchange order.

## Performance And Cadence

- The classification runs only per deploy and uses bounded aggregate PG reads.
- No-signal and normal lifecycle ticks gain no new work.
- The change creates no recurring JSON or Markdown files and no new PG rows.
- Existing SSH, migration, account refresh, and lifecycle checks remain
  timeout-bounded.
- The accepted lifecycle maintenance interruption is at most one hour; the
  normal target remains minutes.

## Acceptance

- A protected `position_protected` lifecycle does not block deploy quiescence.
- A protected `runner_protected` lifecycle does not block deploy quiescence.
- An entry/unprotected lifecycle blocks deployment.
- A protected lifecycle with `first_blocker` blocks deployment.
- Critical commands, domain holds, and unprotected attempts still block.
- Phase-two enablement accepts protected active lifecycles only after current
  account mode and capability checks pass.
- Generated remote commands keep the mutation capability disabled during the
  release switch and execute zero exchange writes during deploy verification.

## Authority Boundary

This design changes deployment eligibility only. It does not expand strategy,
symbol, side, leverage, notional, exposure, FinalGate, Operation Layer, or
exchange-write authority and does not authorize manual position closure.
