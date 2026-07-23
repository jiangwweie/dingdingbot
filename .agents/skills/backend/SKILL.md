---
name: backend
description: Use when implementing or changing Trading Kernel domain, application, PostgreSQL, exchange, risk, lifecycle, reconciliation, or runtime behavior.
user-invocable: true
---

# Backend

## Required Authority

Read before acting:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- the relevant task card and current source files

## Code Boundary

Production execution code belongs only in:

```text
src/trading_kernel/domain
src/trading_kernel/application
src/trading_kernel/infrastructure
src/trading_kernel/interfaces
```

Schema ownership belongs only in `migrations/trading_kernel`.

## Workflow

1. State the invariant and exact authority affected.
2. Write the smallest failing test and confirm the expected failure.
3. Implement the minimum behavior in the existing kernel boundary.
4. Keep database transactions short and network I/O outside them.
5. Persist every exchange mutation as a durable Exchange Command before dispatch.
6. Run targeted tests, then proportional regression and static checks.
7. Delete retired code/tests instead of preserving compatibility.

## Engineering Contract

- Pure domain code; no SQLAlchemy, venue client, filesystem, subprocess, or web
  framework in domain modules.
- `Decimal` for financial values and frozen named models at core boundaries.
- Exact identities, optimistic versions, bounded selectors, and explicit errors.
- ENTRY rejection is terminal; unknown outcome is never blindly resent.
- Partial fill creates an Incident and controlled flatten workflow.
- Healthy idle cadence creates no JSON or Markdown output.
- Logs mask credentials and sensitive exchange values.

## Verification

Report commands actually run, result counts, and skipped checks. Do not claim
completion from a targeted test alone when the change crosses Ticket,
Exchange Command, lifecycle, schema, or runtime ownership boundaries.

## Hard Stops

- No second execution chain, compatibility import, old-table reader, schema
  fallback, or file-backed runtime source.
- No strategy producer may create quantity, budget, Ticket, or exchange order.
- No live profile, capital, sizing, credential, or exchange-write expansion
  without explicit current authority.
