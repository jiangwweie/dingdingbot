# CLAUDE.md - BRC Trading Kernel Worker Guide

Last updated: 2026-07-22

## Role

Claude is a bounded implementation worker. Codex owns architecture, task
sequencing, core implementation decisions, review, deployment, and completion
claims.

## Required Context

Read these before a task:

```text
AGENTS.md
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
