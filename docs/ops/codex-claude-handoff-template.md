# Codex-Claude Handoff Template

Last updated: 2026-06-01

## Purpose

This document is the reusable operating template for Codex and Claude Code collaboration.

The user should not need to remember or recreate handoff wording. Codex should generate Claude task cards from this template, and Claude should return results in the matching format.

## Workflow

1. Codex reads the current program docs and decides whether a task is core work or bounded worker work.
2. Codex owns architecture, task boundaries, file ownership, and acceptance criteria.
3. Codex creates a Claude task card only for bounded implementation or tests.
4. Claude executes only the task card.
5. Claude returns the required result format.
6. Codex reviews Claude output before merge or integration decisions.

Current execution boundary:

- read `docs/ops/agent-current-brc-baseline.md`;
- real live trading / real-funds order placement requires separate explicit
  Owner authorization;
- testnet/dev/readiness/controlled rehearsal/profile-scoped cleanup work does
  not require additional Owner authorization just because it touches
  execution-chain concepts;
- blocker handling is progress-first: live/real-funds stops, testnet/dev scope
  is repaired/reset/cleaned when safe, unknown unsafe blockers are investigated
  before blocking.

## Delegation Size Rule

Claude should receive only bounded worker tasks.

Use this default size:

- One primary result.
- Half-day to one-day execution size.
- Small file surface.
- No architecture ownership.
- Clear pass/fail acceptance.

Default limit:

- A main task should usually produce at most 1-2 Claude subtasks.

Codex should keep the task if any of these are true:

- The task changes core execution files.
- The task needs architecture or state-model decisions.
- The task spans several modules with coupled behavior.
- The task cannot be described with a clear `Done When`.
- The rollback or rework cost would be high.

## Codex Planning Prompt

Use this when starting or resuming a task:

```markdown
Read:
- AGENTS.md
- docs/ops/agent-current-brc-baseline.md
- docs/ops/live-safe-v1-program.md
- docs/ops/live-safe-v1-task-board.md
- docs/ops/agent-working-rules.md
- docs/ops/codex-claude-handoff-template.md
- relevant ADRs

Plan TASK_ID.

Output:
1. Goal
2. Current evidence
3. Files to inspect
4. Files likely to change
5. Core risks
6. Tests and verification
7. What Codex should own
8. What can be delegated to Claude, if anything
9. Delegation size check
10. Stop points requiring user decision

Do not modify files yet.
```

For item 9, Codex should explicitly answer:

- Is there only one primary result?
- Can the worker stay within a small file surface?
- Can Claude avoid architecture judgment?
- Is `Done When` easy to write?
- Is failure cheap to contain and redo?

If two or more answers are "no", do not delegate that unit to Claude.

## Claude Task Card

Codex must use this exact structure when delegating to Claude:

```markdown
# Task ID
LS-xxx-A

## Goal
One bounded outcome.

## Why
Why this worker task exists and how it fits the Codex-owned plan.

## Context
- Current program: Live-safe v1
- Codex owns architecture and merge readiness.
- Claude owns only this bounded implementation/test task.
- Return/drawdown numbers are evaluation dimensions, not hard constraints.
- Real live / real-funds order placement requires separate explicit Owner authorization.
- Testnet/dev/readiness/profile-scoped cleanup does not require additional Owner authorization when the task card allows it.
- Do not stop at the first blocker: classify live/real-funds, testnet/dev/profile-scoped, or unknown unsafe.

## Allowed files
- path/to/file_a.py
- path/to/test_file.py

## Forbidden files
- src/application/execution_orchestrator.py
- src/application/order_lifecycle_service.py
- src/application/position_projection_service.py
- src/application/capital_protection.py
- src/infrastructure/exchange_gateway.py
- src/application/reconciliation.py
- src/application/startup_reconciliation_service.py
- config/
- runtime profiles

## Requirements
1. ...
2. ...
3. ...
- Preserve real live / real-funds safety boundaries.
- Do not ask Owner for testnet authorization.
- Do not output a next recommended task.

## Tests
- Exact command or targeted verification.

## Done When
- ...
- No forbidden files changed.
- Claude returns the required result format.

## Stop And Ask If
- A required change falls outside Allowed files.
- The task requires architecture, live runtime profile, real-funds permission,
  strategy parameter, or merge decisions.
- Existing behavior conflicts with the task card.
- A blocker is live/real-funds or remains unknown unsafe after investigation.
```

Codex should prefer worker tasks like tests, local adapters, local serializers, narrow reports, and scoped integrations. Codex should not delegate an entire stream, a cross-core refactor, or a task that bundles several independent outcomes.

## Claude Return Format

Claude must return:

```markdown
## Files changed
- ...

## What changed
- ...

## Tests run
- Command:
- Result:

## Tests not run
- ...

## Risks
- ...

## Hard blockers
- ...

## Safety proof
- ...
```

Claude must not include "Next recommended task", "Recommended next step", or
"What should we do next".

## Codex Review Prompt

Use this when Claude returns work:

```markdown
Review Claude output for TASK_ID.

Check:
1. Did Claude stay inside Allowed files?
2. Did Claude avoid Forbidden files?
3. Does the implementation satisfy Requirements?
4. Are tests adequate for the risk?
5. Did Claude introduce architecture, strategy, runtime profile, or merge decisions?
6. Are there hidden execution, risk, Decimal, logging, or sensitive-data issues?
7. Accept, request changes, or reject.

Return:
- Verdict
- Findings by severity
- Required fixes
- Tests to run before merge
- Whether Codex needs to integrate anything
```

## Documentation Updates

For active Live-safe v1 work:

- Update `docs/ops/live-safe-v1-task-board.md` when task status changes.
- Update `docs/ops/live-safe-v1-findings.md` for technical findings.
- Update `docs/ops/live-safe-v1-progress.md` for session progress and handoff notes.
- Update `docs/adr/` only for durable architecture decisions.
- Update Memory MCP only for durable rules and accepted decisions.

Do not recreate old `docs/planning/*` files unless the user explicitly asks.
