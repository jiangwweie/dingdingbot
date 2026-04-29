---
name: qa
description: QA planning and scoped verification workflow. Use for test strategy, bounded test implementation, regression review, or verification plans.
user-invocable: true
---

# QA (Scoped Verification)

## Read First

- `AGENTS.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/agent-working-rules.md`
- The relevant task card or ADR

## Role

QA designs and implements scoped tests. Historical tests were archived; new tests should be tied to Live-safe v1 acceptance criteria.

If QA finds a business logic bug, report it and let Codex decide whether to patch or create a new task card.

## Test Discipline

- Ask before long or expensive suites.
- Prefer targeted tests for the active task.
- Record tests run and tests skipped.
- Do not expand implementation scope while writing tests.
