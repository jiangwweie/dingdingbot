# Agent Workflow

Version: strategygroup-runtime-governance
Last updated: 2026-06-16

## Model

This repository uses a Codex-led workflow.

Codex owns analysis, planning, architecture decisions, core implementation, skeleton development, code review, and merge readiness.

Claude Code executes bounded task cards and tests. Claude does not own global direction.

## Active Planning Files

Use current authority files:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`

Do not recreate removed `docs/ops/*`, `docs/canon/*`, or `docs/planning/*` files as active state.

## Memory MCP

Memory MCP is for durable project knowledge:

- Accepted collaboration rules.
- Accepted ADR summaries.
- Long-lived architecture constraints.
- Program-level safety decisions.

Do not write routine progress logs to Memory MCP.

## Claude Task Card

Claude implementation requires a task card:

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

If implementation needs a file outside `Allowed files`, Claude must stop and report the blocker.

## Core File Discipline

Codex owns these files by default:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

Claude may edit a core file only when the task card explicitly allows it.

## Role Responsibilities

Product Manager:
- Helps clarify requirements only when Codex requests product framing.
- Does not create broad PRDs by default during Live-safe v1.

Architect:
- Provides options and trade-offs for architecture-level decisions.
- Uses current tracked code, `docs/current/*`, and accepted Owner decisions.
- Does not force OpenAPI or product-contract artifacts unless the task needs them.

Project Manager:
- Maintains task board state.
- Helps convert Codex plans into bounded task cards.
- Does not auto-dispatch broad parallel implementation by default.

Backend Developer:
- Implements only task-card scoped backend changes.
- Must obey `Allowed files` and `Forbidden files`.

Frontend Developer:
- Implements only scoped console/UI changes.
- Preserves bounded-live operating surface semantics.

QA Tester:
- Designs and implements scoped tests.
- Does not run long suites without user confirmation.
- Reports product/code issues instead of expanding scope.

Reviewer:
- Reviews for bugs, regressions, safety, architecture boundaries, and test gaps.
- Does not patch code unless explicitly asked.

Diagnostic Analyst:
- Diagnoses and reports.
- Does not modify production code.

## P0 Live-safe Rules

- Do not optimize strategy returns.
- Do not tune strategy parameters.
- Do not edit runtime/live profiles.
- Do not add real-funds activation.
- Do not mix profile/config changes with code logic changes.
- Do not run long tests without user confirmation.
- Do not merge execution/risk changes without Codex review.

## Return Format For Claude

Claude should return:

- Files changed.
- What changed.
- Tests run.
- Tests not run and why.
- Risks.
- Any out-of-scope needs.
