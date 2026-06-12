# Agent Working Rules

## Role Split

Codex owns:

- Requirements analysis.
- Program planning and task sequencing.
- Architecture options and ADRs.
- Core decisions.
- Core implementation and skeleton development.
- Review of Claude output.
- Merge readiness decisions.

Claude Code owns:

- Bounded implementation from a Codex task card.
- Tests for a clearly scoped change.
- Localized docs updates when requested.
- Mechanical cleanup inside allowed files.

## Planning And Memory

Plan-with-files remains required, but it is program-scoped.

For Live-safe v1, use:

- `docs/ops/project-roadmap-v2.md`
- `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`
- `docs/ops/agent-current-brc-baseline.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/codex-claude-handoff-template.md`

Memory MCP is for durable rules and decisions only:

- Agent role split.
- Long-lived architecture constraints.
- Accepted ADR summaries.
- Program-level safety rules.
- Lessons that should apply to future programs.

Do not store routine daily progress in Memory MCP.

## Goal Framing

Write system goals as capability goals, not fixed performance promises.

Allowed framing:

- Execution safety.
- Account-level risk control.
- Research reproducibility.
- Strategy extensibility.
- Regime-aware routing.
- Portfolio-level risk budgeting.
- Auditable and replayable decisions.

Do not write fixed annual return or max drawdown numbers as system constraints. Such numbers may appear only as investor preferences, evaluation dimensions, or phase-specific review metrics.

## Scope Framing

Treat `docs/ops/project-roadmap-v2.md` as the high-level scope authority.
Treat `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md` as the
current product and execution-model authority.
Treat `docs/ops/agent-current-brc-baseline.md` as the current worker execution
boundary. Older research-only/read-only instructions are scope-limited unless
the active task itself is research-only or read-only.

Trading Console / Owner Console is an Owner operations surface, not merely a
read-only dashboard or PG/read-model browser. Read-only endpoint/report labels
must stay scoped to those artifacts and must not be generalized into a
product-wide no-action policy.

Default rule:

- Only current active tracks may produce direct implementation tasks.
- Future capability-pool items stay as backlog unless the user explicitly promotes them.

Codex decides whether a proposed capability belongs to the current active tracks or to the future capability pool. Claude does not own that decision.

## Claude Task Card

Use `docs/ops/codex-claude-handoff-template.md` as the source template.

Claude may start implementation only from a task card with:

- Task ID
- Goal
- Why
- Allowed files
- Forbidden files
- Requirements
- Tests
- Done When

Claude must stop and report if it needs files outside `Allowed files`.

## Claude Task Size

Claude tasks should be sized as bounded worker tasks, not mini-projects.

Default target:

- One primary outcome.
- Usually doable in half a day to one day.
- Usually limited to 1-3 implementation files and 1-2 test files.
- Independently reviewable by Codex.
- Low-cost to redo if the first pass is wrong.

Good Claude task examples:

- Add targeted tests for one risk rule.
- Implement one local writer or adapter.
- Wire one small non-core function behind an already decided interface.
- Add one scoped serializer, validator, or report formatter.

Bad Claude task examples:

- Finish an entire P0 stream.
- Redesign execution or risk flow.
- Make cross-core-module changes that require architecture choices.
- Bundle core logic, observability, and cleanup into one worker task.

If a subtask needs architecture judgment, broad file access, or multiple decision points, Codex should keep it or split it differently.

## Claude Return Format

Claude should return:

- Files changed.
- What changed.
- Tests run.
- Tests not run and why.
- Risks.
- Hard blockers, if any.
- Safety proof.

Claude and Codex worker outputs must not include "Next recommended task",
"Recommended next step", or "What should we do next". The project controller
decides sequencing.

## Core File Discipline

Only Codex should modify core execution files unless a task card explicitly allows otherwise:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

## Prohibitions During P0

- Do not optimize strategy returns.
- Do not tune ETH Pinbar parameters.
- Do not edit live trading profiles, credentials, order-sizing defaults, or
  runtime-boundary expansions without explicit Owner authorization. Auditable
  real-funds order placement through the official runtime / Operation Layer path
  is allowed by default when current action-time gates pass.
- Do not mix live runtime profile changes with code logic changes. Bounded
  testnet/dev/profile-scoped cleanup/reset/repair may be included when the task
  explicitly scopes and verifies it.
- Do not let multiple agents modify core execution files concurrently.
- Do not run long test suites without user confirmation.
- Do not merge execution or risk changes without review.
- Do not hard-code return or drawdown targets into architecture, task cards, runtime rules, or agent instructions.
- Do not send oversized or architecture-shaping tasks to Claude unless the user explicitly approves that exception.

Do not stop at the first blocker. Classify the blocker scope:

- live/real-funds: proceed through the official auditable runtime / Operation
  Layer path when current action-time gates pass; stop on unauditable or
  uncontrolled execution;
- testnet/dev/profile-scoped: inspect, safely repair/reset/cleanup where
  bounded, and continue;
- unknown unsafe: investigate, then block only if safety cannot be established.
