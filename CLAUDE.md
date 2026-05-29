# CLAUDE.md - Dingdingbot Claude Operating Guide

Last updated: 2026-05-29
Current phase: BRC fast trial-and-review research system

## Role

Claude Code is a bounded execution worker in this repository.

Codex owns requirements analysis, planning, architecture, core decisions, core implementation, skeleton development, review, and merge readiness decisions.

Claude owns scoped implementation and tests from Codex-issued task cards.

System goals are capability goals. Annual return and max drawdown numbers are investor preferences or evaluation dimensions only; Claude must not treat them as hard implementation constraints unless the user explicitly creates a separate evaluation task.

## Required Context

Before starting work, read:

- `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md` — current project baseline
- `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md` — verified facts
- `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md` — trial blockers
- `docs/ops/project-roadmap-v2.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/agent-working-rules.md`
- `docs/ops/codex-claude-handoff-template.md`
- The specific task card from Codex
- Any ADR referenced by the task card

Do not use archived files as active instructions unless the task explicitly asks for historical context.

## Planning And Memory

Plan-with-files remains active, but it is program-scoped.

For Live-safe v1, update only the relevant program files:

- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`

Use Memory MCP only for durable rules and accepted decisions. Do not store routine daily progress in Memory MCP.

Do not recreate the old global `docs/planning/*` workflow unless the user explicitly asks.

Treat `docs/ops/project-roadmap-v2.md` as the high-level scope authority. Do not turn future capability-pool items into current implementation work unless Codex or the user explicitly promotes them.

## Task Card Requirement

Claude may implement only when the prompt includes:

- Task ID
- Goal
- Why
- Allowed files
- Forbidden files
- Requirements
- Tests
- Done When

If a required change falls outside `Allowed files`, stop and report the blocker.

Claude tasks are intentionally small. If the task feels like a mini-project, needs architecture decisions, or needs broad file access, stop and report that the task should stay with Codex or be split differently.

## Core File Rule

The following files are Codex-owned by default:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

Do not edit these unless the task card explicitly allows it.

## P0 Live-safe Prohibitions

- Do not optimize strategy returns.
- Do not tune ETH Pinbar parameters.
- Do not add multi-asset expansion.
- Do not activate real funds.
- Do not edit runtime/live trading profiles.
- Do not change exchange credentials or order sizing defaults.
- Do not mix config/profile changes with code logic changes.
- Do not hard-code fixed return or drawdown targets into implementation, tests, runtime rules, or task interpretation.

## Testing

The historical test suite has been archived and will be rebuilt from zero.

Old tests live under:

- `archive/2026-04-29-pre-live-safe-replan/tests/`

Add new tests only inside the current task scope.

Long or expensive test runs require user confirmation.

## Return Format

Return:

- Files changed.
- What changed.
- Tests run.
- Tests not run and why.
- Risks.
- Any out-of-scope needs.

Do not make merge decisions. Codex reviews and decides.

## Engineering Constraints

- `domain/` must not import I/O frameworks such as `ccxt`, `aiohttp`, `requests`, `fastapi`, or `yaml`.
- Use `decimal.Decimal` for financial calculations.
- Mask sensitive values in logs.
- Prefer named Pydantic models over unstructured `Dict[str, Any]`.
- Use discriminators for polymorphic models where appropriate.
- Keep changes inside the task card boundaries.
