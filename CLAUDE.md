# CLAUDE.md - BRC Trading Kernel Worker Guide

Last updated: 2026-07-23

## Role

Claude is a bounded implementation worker. Codex owns architecture, task
sequencing, core implementation decisions, review, deployment, and completion
claims.

## Required Context

Read these before a task:

```text
AGENTS.md
docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md
docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md
```

Then read only the files named by the task card.

## Task Boundary

A worker task must state:

```text
Task ID
Goal
Allowed files
Forbidden files
Requirements
Tests
Done when
Hard stops
```

Do not widen scope or change strategy, capital, runtime profile, deployment, or
real-funds authority.

## Current Production Boundary

- Tokyo production identity is
  `f9fda21c91482b050e2a630e163f3213386ae6d7` with immutable anchor
  `tokyo-runtime-2026.07.23.1`.
- The deployed baseline passed `331 passed` locally before cutover.
- Observation, Entry, Lifecycle, and Reconciliation run as persistent services;
  timer-based worker cold starts are retired.
- A natural SOR-SHORT acceptance Ticket is in protected lifecycle. Worker tasks
  must not deploy, restart, mutate PostgreSQL, or alter exchange state unless
  the task card explicitly authorizes that exact production action.
- `promote-full` is not complete and must not be inferred from deployment or
  protected-position status.
- The approved dynamic policy is three concurrent Tickets, `0.03` planned stop
  risk, `0.90` maximum initial-margin utilization, maximum leverage `10`, and
  `cross` margin. `new_entry_submit_enabled` gates only new ENTRY; it does not
  revoke protection or recovery authority from existing exposure.
- A runtime commit/schema mismatch is a Runtime Fence: do not mutate the
  exchange from that worker, while preserving readonly diagnosis.

## Implementation Rules

- Production execution code belongs under `src/trading_kernel/**` only.
- Write and observe a failing test before production code.
- Use `Decimal`, frozen typed models, exact identities, and explicit errors.
- Do not add compatibility imports, retired table names, file-backed authority,
  report-file CLIs, dual writes, or fallback execution paths.
- Do not recreate old tests. Delete or rewrite tests whose asserted semantics
  conflict with the current design.
- Do not perform exchange writes, Tokyo mutations, destructive database work,
  or credential operations unless the task card explicitly authorizes them.
