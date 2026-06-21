---
name: qa
description: QA planning and scoped verification workflow. Use for test strategy, bounded test implementation, regression review, or verification plans.
user-invocable: true
---

# QA (Scoped Verification)

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- The relevant task card or ADR

## Role

QA designs and implements scoped tests. New tests should be tied to the current StrategyGroup runtime-governance pilot and Owner supervisor model.

If QA finds a business logic bug, report it and let Codex decide whether to patch or create a new task card.

## Test Discipline

- Ask before long or expensive suites.
- Prefer targeted tests for the active task.
- Record tests run and tests skipped.
- Do not expand implementation scope while writing tests.
