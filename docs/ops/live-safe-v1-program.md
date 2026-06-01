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
- `docs/adr/0011-playbook-governance-before-strategy-contract.md`

The current Owner-facing mainline is the Personal Leveraged Campaign chain:

`small-capital risk control -> opportunity detection -> playbook governance -> human arm/pause -> strategy contract -> trade intent -> risk order plan -> execution lifecycle -> position/campaign/profit-protection control`

As of ADR-0011, the active next planning branch is Playbook Governance R0.
Further Strategy Contract/runtime implementation is deferred until playbook
switching governance, decision logs, cooldown/hard-lock rules, and CPV0_2
continuity exist as paper-only governance artifacts.

Live-safe v1 work may support future execution safety. Under `ADR-0009` as
amended on 2026-06-01, real live trading / real-funds order placement remains
prohibited unless separately and explicitly authorized. Runtime, paper, testnet,
tiny-live-style rehearsal, read-only exchange sync, and other non-real-live
steps are governed by scoped verification and hard safety gates, not a blanket
Owner-authorization stop.

## Role Of This Document

This document is the execution-layer program document for the current active track.

Use [project-roadmap-v2.md](/Users/jiangwei/Documents/final/docs/ops/project-roadmap-v2.md) as the high-level roadmap and boundary document.

This file defines the preserved execution-safety foundation for
`Live-safe Foundation`. As of 2026-05-25, it is not the active research or
business mainline.

## Goal

Preserve and harden the execution-safety foundation. Runtime and testnet
execution may be used when it is the appropriate verification boundary after
scoped verification and applicable safety gates.

The scope of this program is `Live-safe Foundation`, not the full long-term
platform roadmap. Current work must not start real live trading, real-funds
deployment, portfolio/router work, SOL Phase 2, CPM reopening, short-side work,
or parameter optimization. Runtime, paper, testnet, or tiny-live-style
non-real-live execution requires scoped verification, profile/environment gates,
and cleanup/exit safety, but not an additional Owner authorization step merely
because it is testnet/dev/readiness work.

The current Owner-facing stage starts from docs/design/sandbox preparation for
the Personal Leveraged Campaign chain. Live-safe implementation tasks may remain
in the backlog, and non-real-live runtime/testnet verification may be used when
authorized, but they do not imply real live activation or a deployable strategy
candidate.

2026-05-25 update: PLC Phase 5A small-scale rehearsal readiness has started
after Phase 4 non-real-live hardening. Phase 5A is still non-real-live and
focuses on account-scope risk, runtime campaign-state transitions, Strategy
Contract promotion gating, and bounded testnet evidence. It does not authorize
repeated rehearsal, multi-symbol runtime, or real live.

2026-05-25 Playbook Governance update: Phase 5 execution-safety evidence is
preserved, but the next active planning step is paper-only Playbook Governance
R0. Tracks B-E runtime implementation, Strategy Contract v2 implementation,
and additional paper/testnet runtime work are deferred until a governed
playbook and promoted strategy justify them.

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
- Do not connect real funds or execute real live trading without a separate
  explicit Owner authorization decision.
- Do not rewrite the architecture.
- Do not change live profile trading parameters.
- Do not turn investor preference numbers into hard-coded engineering constraints.
- Do not start real live or real-funds action without separate explicit Owner
  authorization. For testnet/dev/profile-scoped work, verify scope and safety
  gates, then continue without asking for additional testnet authorization.
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
- Live runtime profile changes require a separate task card and explicit user approval.
- Exchange credentials, order sizing defaults, and live profile changes must not be mixed with code logic changes.
- Real live trading remains the hard execution red line. Non-real-live runtime
  and testnet work is permitted through scoped verification, profile gates, and
  hard safety checks under the current agent baseline.

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
