# AGENTS.md - Dingdingbot Agent Operating Guide

Last updated: 2026-04-29
Current phase: Live-safe v1 replanning and execution-safety hardening

## Operating Model

This project uses a Codex-led, Claude-bounded workflow.

Codex owns requirements analysis, planning, architecture options, ADRs, core decisions, core implementation, skeleton development, code review, and merge readiness decisions.

Claude Code owns bounded implementation and tests from Codex-issued task cards. Claude must not redefine scope, architecture, priorities, runtime profiles, or strategy parameters.

The user remains Owner / PM / final architecture decision maker.

System goals must be framed as capabilities, not fixed performance promises. Annual return and max drawdown numbers may be used as investor preferences or evaluation dimensions, but must not become architecture constraints, runtime rules, or agent task requirements.

## Current Program SSOT

Read these first for current work:

- `docs/ops/project-roadmap-v2.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/agent-working-rules.md`
- `docs/ops/codex-claude-handoff-template.md`
- `docs/adr/0001-live-safe-v1-scope.md`
- `docs/gpt/`

Archived pre-reset material lives under:

- `archive/2026-04-29-pre-live-safe-replan/`

## Planning And Memory

Plan-with-files is still required, but it is now program-scoped.

For Live-safe v1, write planning state to:

- `docs/ops/project-roadmap-v2.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`

Use Memory MCP only for durable knowledge:

- Accepted collaboration rules.
- Long-lived architecture constraints.
- Accepted ADR summaries.
- Program-level safety decisions.
- Lessons that should apply beyond the current session.

Do not use Memory MCP for daily progress logs.

Do not recreate the old global `docs/planning/*` workflow unless the user explicitly asks for it.

Treat `docs/ops/project-roadmap-v2.md` as the high-level scope authority. Only current active tracks should produce direct implementation tasks by default.

## Red Lines

1. New meaningful requirements need exploration, architecture options when appropriate, and user confirmation before implementation.
2. Task decomposition must identify dependencies and possible parallel work, but execution-chain core files must not be modified concurrently by multiple agents.
3. Long or expensive tests require user confirmation before running.
4. P0 Live-safe work must not optimize strategy returns or tune ETH Pinbar parameters.
5. Runtime profile, live trading config, exchange credentials, and order-sizing default changes require explicit user approval and a separate task.
6. Claude may implement only from a task card with `Allowed files`, `Forbidden files`, `Requirements`, `Tests`, and `Done When`.
7. Do not hard-code fixed return or drawdown targets into system constraints, task cards, runtime rules, or agent instructions.
8. Claude subtasks must stay small: one primary outcome, small file surface, low architecture coupling, and clear acceptance.
9. Real live trading is the absolute execution red line. Runtime, paper,
   testnet, tiny-live, read-only exchange sync, and other non-real-live work may
   proceed only after reasonable scoped verification and explicit Owner
   authorization for the specific action.

## Core Files

Only Codex should modify these by default:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

Claude can touch a core file only when the task card explicitly allows it.

## Claude Task Card

Use `docs/ops/codex-claude-handoff-template.md` as the reusable handoff template.

Use this format when handing work to Claude:

```markdown
# Task ID
LS-xxx

## Goal
...

## Why
...

## Allowed files
- ...

## Forbidden files
- ...

## Requirements
1. ...

## Tests
- ...

## Done When
- ...
```

Claude must stop and report if it needs files outside `Allowed files`.

## Claude Return Format

Claude should return:

- Files changed.
- What changed.
- Tests run.
- Tests not run and why.
- Risks.
- Any out-of-scope needs.

Codex reviews the result before merge decisions.

## Engineering Constraints

- `domain/` must remain pure business logic and must not import I/O frameworks such as `ccxt`, `aiohttp`, `requests`, `fastapi`, or `yaml`.
- Financial calculations must use `decimal.Decimal`, not `float`.
- Sensitive values must be masked in logs.
- Core parameters should use named Pydantic models instead of unstructured `Dict[str, Any]`.
- Polymorphic models should use discriminators where appropriate.
- Execution, recovery, reconciliation, and circuit-breaker state should prefer the PG mainline unless explicitly documented as transitional.

## Live-safe v1 Non-goals

- No strategy-return optimization.
- No multi-asset expansion.
- No real live trading or real-funds activation without a separate explicit
  Owner authorization decision.
- No architecture rewrite.
- No live/runtime profile changes without a separate explicit Owner
  authorization decision.

## Testing

Current tests were archived and will be rebuilt from zero.

Old tests live under:

- `archive/2026-04-29-pre-live-safe-replan/tests/`

New tests should be added only when tied to current Live-safe v1 acceptance criteria.

Do not run long suites without user confirmation.

## Git Discipline

- `dev` is integration, not a scratch branch.
- `program/live-safe-v1` is the Live-safe v1 integration branch.
- Each task should use a focused branch from the program branch.
- Do not commit or push unless the user asks or the active task explicitly includes it.
- Never revert user changes unless explicitly asked.
