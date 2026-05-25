# Live-safe v1 Program

Last updated: 2026-05-25

## Current Status

Status: Runtime safety foundation / not current business mainline

This document remains useful for execution-safety boundaries, core-file
ownership, and Live-safe backlog context. It is superseded as a mainline
planning document by:

- `docs/ops/project-roadmap-v2.md`
- `docs/ops/personal-leveraged-campaign-mainline-v0.md`
- `docs/adr/0008-personal-leveraged-campaign-business-chain.md`

The current Owner-facing mainline is the Personal Leveraged Campaign chain:

`small-capital risk control -> opportunity detection -> human arm/pause -> strategy contract -> trade intent -> risk order plan -> execution lifecycle -> position/campaign control -> withdrawal instruction`

Live-safe v1 work may support future execution safety, but this document does
not authorize runtime activation, paper, testnet, live, tiny-live, real account
actions, leverage, sizing, or direct research-to-order wiring.

## Role Of This Document

This document is the execution-layer program document for the current active track.

Use [project-roadmap-v2.md](/Users/jiangwei/Documents/final/docs/ops/project-roadmap-v2.md) as the high-level roadmap and boundary document.

This file defines the preserved execution-safety foundation for
`Live-safe Foundation`. As of 2026-05-25, it is not the active research or
business mainline.

## Goal

Preserve and harden the execution-safety foundation without activating runtime
trading.

The scope of this program is `Live-safe Foundation`, not the full long-term
platform roadmap. Current work must not start strategy runtime, paper/testnet/
live trading, small-live execution, portfolio/router work, SOL Phase 2, CPM
reopening, short-side work, or parameter optimization.

The current Owner-facing stage is docs/design/sandbox preparation for the
Personal Leveraged Campaign chain. Live-safe implementation tasks may remain in
the backlog, but they do not imply live activation or a deployable strategy
candidate.

## Operating Model

Codex is the program owner for requirements analysis, planning, architecture decisions, core implementation, skeleton development, code review, and merge decisions.

Claude Code is an execution worker for bounded implementation and tests. Claude must work from a Codex-issued task card and must not redefine scope, architecture, or priorities.

## Planning System

Use program-scoped plan-with-files:

- `docs/ops/project-roadmap-v2.md`: high-level roadmap, current-stage boundaries, capability-pool rules.
- `docs/ops/live-safe-v1-program.md`: current live-safe program scope, non-goals, safety rules.
- `docs/ops/live-safe-v1-task-board.md`: task status and ownership.
- `docs/ops/live-safe-v1-findings.md`: program-local findings and short-lived technical notes.
- `docs/ops/live-safe-v1-progress.md`: session progress and handoff notes.
- `docs/adr/`: accepted or proposed long-lived architecture decisions.

Use Memory MCP only for durable rules and decisions that should survive across programs and sessions.

## Non-goals

- Do not optimize strategy returns in P0.
- Do not tune ETH Pinbar parameters.
- Do not add multi-asset expansion.
- Do not add Regime, Data, Strategy Router, or Portfolio capabilities unless the user explicitly promotes them from the capability pool.
- Do not connect real funds.
- Do not rewrite the architecture.
- Do not change live/runtime profile trading parameters.
- Do not turn investor preference numbers into hard-coded engineering constraints.
- Do not start any strategy runtime, paper/testnet/live execution, or
  small-live/tiny-live operation during the current Personal Leveraged Campaign
  docs/design/sandbox stage.
- Do not promote SOL Phase 2, CPM, short-side, portfolio/router, or
  multi-strategy work into current mainline without a separate Owner decision.

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
