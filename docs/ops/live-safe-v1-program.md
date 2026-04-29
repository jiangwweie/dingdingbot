# Live-safe v1 Program

Last updated: 2026-04-29

## Goal

Move the current Sim-ready system toward full-auto small-live safety.

The long-term direction is not an ETH Pinbar system. The system should evolve from a single-strategy research setup into a full-auto, multi-asset, multi-direction, low-frequency portfolio platform with account-level risk control.

Return and drawdown numbers are evaluation dimensions and investor preference signals, not engineering constraints. Do not encode fixed annual-return or max-drawdown targets as hard system rules.

## Evolution Path

Live-safe -> Regime-aware -> Data-aware -> Multi-strategy -> Multi-asset -> Portfolio-level -> Small-live scaling.

## Operating Model

Codex is the program owner for requirements analysis, planning, architecture decisions, core implementation, skeleton development, code review, and merge decisions.

Claude Code is an execution worker for bounded implementation and tests. Claude must work from a Codex-issued task card and must not redefine scope, architecture, or priorities.

## Planning System

Use program-scoped plan-with-files:

- `docs/ops/live-safe-v1-program.md`: goal, non-goals, safety rules, scope.
- `docs/ops/live-safe-v1-task-board.md`: task status and ownership.
- `docs/ops/live-safe-v1-findings.md`: program-local findings and short-lived technical notes.
- `docs/ops/live-safe-v1-progress.md`: session progress and handoff notes.
- `docs/adr/`: accepted or proposed long-lived architecture decisions.

Use Memory MCP only for durable rules and decisions that should survive across programs and sessions.

## Non-goals

- Do not optimize strategy returns in P0.
- Do not tune ETH Pinbar parameters.
- Do not add multi-asset expansion.
- Do not connect real funds.
- Do not rewrite the architecture.
- Do not change live/runtime profile trading parameters.
- Do not turn investor preference numbers into hard-coded engineering constraints.

## P0 Scope

- LS-001 Start `watch_orders`.
- LS-002 Make daily max loss and daily max trades effective.
- LS-003 Add structured runtime logs.
- LS-004 Add daily equity snapshot.
- LS-005 Add periodic reconciliation.
- LS-006 Add account risk state machine.
- LS-007 Add liquidation distance and margin safety checks.

## Branch Policy

- `dev` is integration, not a scratch branch.
- `program/live-safe-v1` is the program integration branch.
- Each task uses one focused branch from `program/live-safe-v1`.
- Use `fix/*` for bug fixes and `feature/*` for new scoped features.
- Core execution files must not be modified by multiple agents at the same time.

## Runtime Safety

- Default to sim/testnet behavior.
- Runtime profile changes require a separate task card and explicit user approval.
- Exchange credentials, order sizing defaults, and live profile changes must not be mixed with code logic changes.

## Core Files

Only Codex should modify these unless the user explicitly approves a bounded Claude task:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

## Task Card Contract

Every Claude task must include:

- Task ID
- Goal
- Why
- Allowed files
- Forbidden files
- Requirements
- Tests
- Done When

If Claude needs files outside `Allowed files`, it must stop and report the blocker instead of expanding scope.
