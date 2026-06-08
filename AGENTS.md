# AGENTS.md - Dingdingbot Agent Operating Guide

Last updated: 2026-06-08
Current phase: BRC productized bounded-live operations system

## Current Document Authority

When project documents conflict, follow this order:

1. Owner explicit correction / decision
2. Current tracked code + current git status
3. Current verified reports
4. ADR / decision records
5. Historical docs
6. Archived knowledge-pack v0

Current project baseline starts from:
`docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`

Current agent execution baseline starts from:
`docs/ops/agent-current-brc-baseline.md`

Untracked files must never be described as integrated capabilities.
Real live trading / real-funds order placement is prohibited unless Owner
explicitly authorizes that live action.

## Operating Model

This project uses a Codex-led, Claude-bounded workflow.

Codex owns requirements analysis, planning, architecture options, ADRs, core decisions, core implementation, skeleton development, code review, and merge readiness decisions.

Claude Code owns bounded implementation and tests from Codex-issued task cards. Claude must not redefine scope, architecture, priorities, runtime profiles, or strategy parameters.

The user remains Owner / PM / final architecture decision maker.

System goals must be framed as capabilities, not fixed performance promises. Annual return and max drawdown numbers may be used as investor preferences or evaluation dimensions, but must not become architecture constraints, runtime rules, or agent task requirements.

## Current Program SSOT

**Current canon (start here)**:

- `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`
- `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`
- `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md`
- `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md`
- `docs/ops/knowledge-pack/DOCUMENT_GOVERNANCE.md`

**Operational context (still valid)**:

- `docs/ops/project-roadmap-v2.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/agent-working-rules.md`
- `docs/ops/codex-claude-handoff-template.md`
- `docs/adr/0001-live-safe-v1-scope.md`

Archived pre-reset material lives under:

- `archive/2026-04-29-pre-live-safe-replan/`

## Current Product Direction

The current target is an Owner-facing productized bounded-live trading
operations system for fast small-capital trial-and-review Campaigns.

Do not interpret Trading Console or Owner Console as merely:

- a read-only dashboard;
- a PG/read-model browser;
- a research dashboard;
- a passive status or enum display;
- a documentation surface.

The console is the Owner's operating surface for understanding system state,
reviewing `ActionCandidate` records, seeing budget availability, seeing blockers
and recovery conditions, authorizing bounded live actions through the official
path, checking `FinalGate`, monitoring active position/protection, pausing or
revoking autonomy or budget, reviewing completed trades, and feeding Review
Ledger outcomes into promote / revise / park decisions.

Current product chain:

```text
StrategyFamily / Carrier
-> ActionCandidate
-> Owner risk understanding
-> Owner authorization or BudgetEnvelope authorization
-> ActionSpec
-> FinalGate
-> Operation Layer
-> official bounded live action
-> active position / TP/SL protection monitoring
-> close / TP / SL
-> Review Ledger
-> promote / revise / park
```

Read-only documents remain valid only for the specific namespace, report, or
handoff they describe. They must not be generalized into "the product is
read-only" or "no PG mutation/deployment/exchange access is allowed."

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
5. Live runtime profile, live trading config, exchange credentials, and
   real-funds order-sizing default changes require explicit user approval and a
   separate task. Testnet/dev/profile-scoped cleanup/reset/repair can proceed
   within the active task boundary after scoped verification.
6. Claude may implement only from a task card with `Allowed files`, `Forbidden files`, `Requirements`, `Tests`, and `Done When`.
7. Do not hard-code fixed return or drawdown targets into system constraints, task cards, runtime rules, or agent instructions.
8. Claude subtasks must stay small: one primary outcome, small file surface, low architecture coupling, and clear acceptance.
9. Real live trading / real-funds order placement is the absolute execution
   red line. Testnet, dev, readiness, controlled rehearsal, PG non-live,
   console/API, and profile-scoped cleanup/reset/repair work may proceed after
   scoped verification without an additional Owner authorization step.
10. Blocker handling must be progress-first: live/real-funds blockers stop;
    testnet/dev/profile-scoped blockers should be inspected, safely repaired,
    reset, or cleaned up where bounded, then work should continue; unknown
    unsafe blockers stop only after investigation cannot establish safety.

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
- Hard blockers, if any.
- Safety proof.

Claude and Codex worker reports should not include "Next recommended task",
"Recommended next step", or "What should we do next". The project controller
decides sequencing.

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
- Testnet/dev/readiness/controlled rehearsal work is not a live authorization
  boundary by itself.
- No architecture rewrite.
- No live runtime profile changes without a separate explicit Owner
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
